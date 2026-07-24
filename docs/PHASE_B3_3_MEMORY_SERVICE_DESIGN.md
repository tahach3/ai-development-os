# Phase B3.3 — Memory Service Layer + First Consumer

**Status:** Implementation design for Phase B3.3 (local service lifecycle + optional context_builder consumer)  
**Baseline:** package **0.8.10** · HEAD `a201afe` · branch `master`  
**Authoritative priors:** [`SHARED_MEMORY_DESIGN.md`](SHARED_MEMORY_DESIGN.md) (B1), [`SHARED_MEMORY_IMPLEMENTATION_PLAN.md`](SHARED_MEMORY_IMPLEMENTATION_PLAN.md) (B2), [`SHARED_MEMORY_SQLITE_PERSISTENCE.md`](SHARED_MEMORY_SQLITE_PERSISTENCE.md) (B3.2)

**Scope:** Service orchestration over B3.2 `SqliteMemoryRepository`, per-registered-project opt-in, thin CLI verbs, optional approved-memory section in `context_builder` when explicitly requested **and** the project is opted in.

**Not in scope:** Round 4D2 / live models / network / paid APIs, Equitify, FTS5 / embeddings, auto-populate from workspace artifacts, wiring memory into orchestration or provider execution paths, global default enable, STAGE_ORDER / `4a.1` changes, new runtime deps.

---

## 1. Purpose

Ship a **local-only** service layer that:

1. Owns lifecycle transitions (propose → validate → approve | reject → supersede | archive → forget / hard-delete) using existing B3.1 validation + B3.2 CRUD.
2. Gates every mutating/read-store operation on **per-project opt-in** (not a repo-wide flip).
3. Appends audit rows to `memory_events` for every lifecycle action (and default retrieve).
4. Exposes operator CLI verbs for explicit, audited population.
5. Adds **one** bounded consumer: `build_context_packet(..., include_approved_memory=True)` for opted-in projects only.

Memory remains a **passive store**. Orchestration and provider runners keep calling `build_context_packet` with the default (`include_approved_memory=False`) so memory content never enters those packets this phase.

---

## 2. Per-project opt-in mechanism

| Item | Choice |
| --- | --- |
| Where | First-class `ProjectRecord.memory_enabled: bool = False` in `config/projects.yaml` (serialized with the rest of the project entry) |
| Default | `False` — existing registries and projects without the key behave as today |
| How read | `ProjectRegistry.require(project_id)` → `record.memory_enabled` |
| Enable | Explicit operator action: `ai-dev-os memory-enable --project-id …` (sets flag + saves registry) or register with `--memory-enabled` |
| Global config | `DEFAULT_MEMORY_CONFIG.enabled` stays **`False`**. Service constructs a **session** `MemoryConfig(enabled=True, db_path=…)` only **after** project opt-in succeeds |
| No opt-in | Raise existing `MemoryDisabledError` (reuse; no second error type). No DB open, no migrate, no write |

**Identical-to-today for non-opted projects:** service refuses; `build_context_packet` default path adds no memory section; `memory-status` still reports global `"disabled"`.

Equitify registration remains refused by the registry; memory cannot enable an Equitify project.

---

## 3. Lifecycle ↔ repository mapping

B3.2 repository surface used (plus thin event helpers deferred from B3.2 §6):

| Service method | Repo / helpers | Record mutation |
| --- | --- | --- |
| `propose` | `prepare_candidate_record` / `validate_propose_dict` → `create_record` + `append_event` | Insert candidate / `proposed` |
| `validate` | `get_record` → `update_record` + `append_event` | `proposed` → `validated` (class stays candidate) |
| `approve` | `get_record` → `update_record` + `append_event` | `validated` → `approved` / `approved_memory`; requires human `approval_method` |
| `reject` | `get_record` → `update_record` + `append_event` | → `rejected` / `rejected_memory` + reason |
| `supersede` | `get_record` ×2 → `update_record` (old) + `create_record` or `update_record` (new) + `create_link` ×2 + events | Old → superseded; new approved; `supersedes` / `superseded_by` links |
| `archive` | `get_record` → `update_record` + `append_event` | approved/superseded → archived |
| `forget` | `get_record` → `update_record` + `append_event` | → `forgotten` + `forgotten_at`; content retained |
| `hard_delete` | `get_record` → `update_record` + `append_event` | Content erased (`content` empty, `content_erased_at` set); record + events retained; **human only** |
| `retrieve` / `list` | `list_records` (+ in-service sort) + optional `append_event(action=retrieve)` | Read-only; default filter: approved class + approved status |

**Thin repo additions (not new tables):** `append_event` and `list_events` against existing `memory_events` DDL — B3.2 deferred these for the service layer.

No silent overwrite of approved content: supersede creates/links a new record.

---

## 4. Authorization (unchanged B3.1 model)

Reuse `authorize_memory_action` / `ACTION_ALLOWED_ROLES`:

| Action | Allowed roles |
| --- | --- |
| propose | Any `MemoryActorRole` (models/providers may propose only) |
| validate | `os_control_plane` |
| approve / reject / supersede / archive / forget | `human_operator`, `os_control_plane` |
| hard_delete | `human_operator` **only** |

Model-like roles (`claude`, `cursor`, `codex`, `provider`, `orchestration`) attempting anything other than propose → `MemoryAuthorizationError`.

Prototype approval_method remains **human** only (B3.1 validation).

---

## 5. `context_builder` consumer (bounded)

| Rule | Behavior |
| --- | --- |
| Default | `include_approved_memory=False` → **byte-identical** markdown/manifest shape to pre-B3.3 (no memory keys/sections) |
| Opt-in path | Caller passes `include_approved_memory=True` **and** project `memory_enabled=True` |
| Missing opt-in | `MemoryDisabledError` (fail closed; do not silently omit when explicitly requested) |
| What retrieved | Approved memories only (`approved_memory` + `approved`), project-scoped |
| Cap | `MemoryConfig.default_retrieve_limit` (20), hard max `max_retrieve_limit` (100) |
| Order | Deterministic: evidence_strength DESC → `approved_at` DESC → `memory_id` ASC |
| Packet shape | Optional `## Approved Project Memory` section + `manifest["approved_memory_ids"]` list (ordered) |
| Non-consumers | `orchestration_engine`, `provider_runner`, adapters leave the flag **False** |

CLI: `build-context --include-memory` sets the flag for operator-triggered local packets only.

---

## 6. Audit requirements

- Every lifecycle transition appends one `memory_events` row in the **same** logical operation as the record mutation (service commits via repo methods sequentially; event insert fails closed if write fails).
- Forget is audited (`action=forget`); hard-delete is audited (`action=hard_delete`) and **never** silent.
- Default retrieve may append `action=retrieve` when `MemoryConfig.audit_retrievals` is true (B3.2 config field).
- No DELETE/UPDATE of event rows.

---

## 7. CLI surface (exact verbs)

| Verb | Purpose |
| --- | --- |
| `memory-status` | Unchanged read-only global status (`disabled` by default) |
| `memory-enable` | Set `memory_enabled=true` on a registered project |
| `memory-disable` | Clear opt-in flag (does not delete DB rows) |
| `memory-propose` | Propose candidate (`--project-id`, `--content`, `--category`, …) |
| `memory-validate` | OS validate (`--project-id`, `--memory-id`) |
| `memory-approve` | Human approve (`--approver` required) |
| `memory-reject` | Reject with `--reason` |
| `memory-list` | List project memories (optional lifecycle/class filters) |
| `memory-retrieve` | Retrieve approved set (deterministic order) |
| `memory-archive` | Archive approved/superseded |
| `memory-supersede` | Supersede old with new content / id |
| `memory-forget` | Soft-forget |
| `memory-hard-delete` | Erase content (human; audited) |

Also: `register-project --memory-enabled` and `build-context --include-memory`.

All mutating verbs fail closed with `MemoryDisabledError` when the project is not opted in.

---

## 8. Deferred (still)

- Live-model / Round 4D2 consumption of memory content
- Wiring memory into orchestration or provider execution
- Cross-project memory sharing / global memory
- Automatic population / migrate-from-workspace
- FTS5, embeddings, encryption-at-rest
- Policy auto-approve
- Equitify

---

## 9. Testing strategy

| Area | Assertions |
| --- | --- |
| Opt-in gate | Non-opted project → `MemoryDisabledError`; opted project can propose/approve/retrieve |
| Lifecycle + permissions | Legal transitions succeed; model cannot approve; illegal transitions → conflict/auth errors |
| Forget audit | Soft-forget + hard-delete leave event rows; content erased only on hard-delete |
| context_builder regression | Default / non-opted path: no memory section; identical shape to pre-B3.3 |
| Deterministic order | retrieve order stable under fixed fixtures |

Then focused suite + full pytest + `ai-dev-os ci-check`. One patch version bump; all test version pins updated.

---

## 10. Acceptance checklist

- [x] Design documented before service code
- [x] Per-project opt-in; global default remains disabled
- [x] Service maps lifecycle onto B3.2 repo (+ event helpers)
- [x] Authorization reuses B3.1 roles
- [x] CLI verbs as listed; population explicit
- [x] context_builder optional path only; orch/providers untouched
- [x] Focused + full suite green; one commit; **not pushed**

---

## Document control

| | |
| --- | --- |
| Phase | B3.3 |
| Package after ship | **0.8.11** (one patch from 0.8.10) |
| Must not change | Equitify, 4D2 unlock, STAGE_ORDER, `4a.1` schema, live/paid APIs |
