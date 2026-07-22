# Phase B2 — Shared Memory Implementation Plan

**Status:** Implementation decisions only (Phase B2)
**Scope:** SQLite prototype schema, lifecycle policy, retrieval/determinism, adapter/module boundaries, API contracts, migrations/config, test strategy, and B3.x checkpoints
**Not in scope:** Python memory runtime, SQLite files, migrations on disk, ORM, dependencies, CLI commands, providers, embeddings, FTS5 code, Live model calls, Equitify, package version changes

**Implemented baseline (unchanged):** Round 4B closeout, package **`0.6.0`** · HEAD at plan authorship: `382eb8a`
**Principles source of truth:** [`SHARED_MEMORY_DESIGN.md`](SHARED_MEMORY_DESIGN.md) (Phase B1)
**Architectural direction:** [`AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md`](AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md) §7 / Phase B
**Related:** [`ARCHITECTURE.md`](ARCHITECTURE.md), [`MODEL_ROLES.md`](MODEL_ROLES.md), [`ROADMAP.md`](ROADMAP.md), [`SECURITY_MODEL.md`](SECURITY_MODEL.md)

**Honest status:** No shared-memory implementation exists. This document resolves Phase B1 open decisions needed to implement a local SQLite prototype in later Phase B3 checkpoints. It does not authorize code, databases, or dependency changes.

---

## 1. Purpose

Convert Phase B1 principles into **implementation-ready decisions** for a local, project-scoped, approval-gated shared memory prototype:

- Lock prototype boundaries and non-goals.
- Choose SQLite stdlib storage and an explicit relational schema (documented here; no SQL files yet).
- Define enums, identifiers, approval, candidate persistence, retrieval, audit, and deletion semantics.
- Map module/adapter placement onto the **existing** `src/ai_dev_os/` package conventions.
- Sequence Phase B3.1–B3.9 with acceptance and rollback rules.

This plan does **not** claim memory already exists.

---

## 2. Current baseline

| Item | Value |
| --- | --- |
| Branch | `master` |
| HEAD (pre-edit) | `382eb8aee23230ce46b082fa47a3ef468bf707d9` |
| Package | `ai-dev-os` **0.6.0** |
| Runtime capability | Round 4A local CI / PR validation |
| Persistence today | YAML/JSON workspace file stores (tasks, plans, sessions, orchestration, CI, audits) |
| SQLite / memory package | **None** |
| Dependencies | `PyYAML` only (dev: `pytest`) |

Authority model (unchanged):

```text
AI Development OS = controller and safety authority
Claude            = planning and hard reasoning
Cursor            = implementation
Codex/GPT         = independent review
```

Cursor three-model workflow remains a **client** — no parallel task/approval/routing/audit/memory system.

---

## 3. Repository findings

Inspected: `src/ai_dev_os/`, `tests/`, `pyproject.toml`, README, architecture/design docs. Patterns that Phase B3 **must reuse**:

| Pattern | Where | Implication for memory |
| --- | --- | --- |
| Flat package + small subpackages | `src/ai_dev_os/` with `adapters/`, `providers/` | Add `memory/` subpackage; do not restructure the whole repo |
| File stores as classes | `task_store.py`, `plan_store.py`, `orchestration_store.py`, `*_audit.py` | SQLite lives behind a `MemoryStore` / backend adapter; service layer owns policy |
| Domain models | dataclasses + `str, Enum` in `models.py` / `*_models.py` | New `memory_models.py` (keep core `models.py` from ballooning) |
| Fail-closed validation | `ValidationError` in `validation.py`; registry `require()` | Memory errors subclass or wrap `ValidationError`; unregistered project → refuse |
| Project identity | `ProjectRegistry` + Equitify sentinels | Every write/read calls `registry.require(project_id)` |
| Approval discipline | `approval.py` — human approver, fingerprint lock, no planner self-approve for high risk | Memory promote mirrors: propose freely, activate only via OS approval |
| Fingerprints | `fingerprints.canonical_json` + `sha256_hex` | Content hash / proposal fingerprint use same helpers |
| UTC timestamps | `utc_now_iso()` (second resolution, timezone-aware ISO) | All memory timestamps use this helper |
| ID style | Prefixed short hex: `exec-…`, `ci_…`, `orch-…`, `sess-…`, `preq-…`, `evt-…` | `mem-{12 hex}`, `mev-{12 hex}`, `mlk-{12 hex}`, `evid-{12 hex}` |
| Atomic file IO | `atomic_io.py` | Not used for SQLite rows; used if writing sidecar config/manifests |
| Config disabled-by-default | Provider/orchestration live flags fail closed | `memory.enabled=false` by default |
| Secret scan | `ci_secrets.redact_secrets` / `SECRET_RULES` | Reuse on propose/validate content |
| Tests | `tests/test_*.py`, tmp_path fixtures, simulation only | Memory tests: temp SQLite path; no network/providers |
| Workspace layout | `workspace/{active,plans,ci_runs,…}` + `.gitignore` globs | DB path: `workspace/memory/memory.sqlite3` (gitignored in B3) |
| Blueprint §14 tree | Ideal `memory/sqlite_backend/` | Adopt **conceptually** as `ai_dev_os.memory` without wholesale migration |

**No existing SQLite, ORM, or migration framework.** Persistence today is filesystem YAML/JSON. Choosing stdlib `sqlite3` is consistent with “no new dependency without approval.”

---

## 4. Locked prototype scope

### In scope (local SQLite prototype)

| Property | Decision |
| --- | --- |
| Local-only | Single DB file under this repo’s `workspace/` |
| Single-process | One OS process opens the DB; no multi-writer cluster |
| Single-user | Operator workstation; no authz server |
| SQLite | stdlib `sqlite3` only |
| Simulation-testable | Full suite with fixtures; no live models |
| Provider-independent | Providers may propose via OS APIs later; never open the DB |
| Project-scoped | Mandatory `project_id` from registry |
| Adapter-replaceable | `MemoryBackend` protocol; SQLite is the first backend |

### Explicitly not in scope

- Distributed / multi-host memory
- Vector DB, embeddings, semantic rankers
- Chat-history / full transcript warehouse
- Neo4j / Redis / Mem0 / Graphiti / Letta / Postgres
- Global memory (deferred)
- Cross-project reads
- Encryption-at-rest productization
- Network sync
- Claiming memory is already shipped

---

## 5. Architecture decisions

| # | Decision | Choice | Rationale |
| --- | --- | --- | --- |
| A1 | Storage technology | **stdlib `sqlite3`** | No persistence abstraction exists; YAML stores do not justify SQLAlchemy/ORM. Zero new deps. |
| A2 | ORM | **None** | Hand-written SQL in repository layer; typed dataclasses at boundary. |
| A3 | Candidate persistence | **Option A — persist candidates** | See §7. Enables audit, recovery, multi-session approval workflow. |
| A4 | Ephemeral context | **Not persisted** by default | In-memory / context packet only; never a durable class unless future audit mandate. |
| A5 | Search | **Structured filters + deterministic substring match** | No embeddings. **FTS5 deferred** (schema-ready note only). |
| A6 | Approval | **Human (or OS operator identity) required to activate** | No model/provider approval. Policy auto-approve deferred. Fail closed. |
| A7 | Global memory | **Deferred** | Prototype project-scoped only. |
| A8 | Memory feature flag | **Disabled by default** | `memory.enabled=false` until operator enables for a registered project. |
| A9 | Journal / locking | **WAL + busy_timeout=5000** | Simple single-user concurrency; no connection pool product. |
| A10 | Module home | **`src/ai_dev_os/memory/`** | Matches `providers/` precedent; avoids blueprint-wide restructure. |

---

## 6. Data model

Conceptual principles remain in B1 §§2–6. Below is the **locked relational shape** for the prototype. No `.sql` migration files are created in Phase B2.

### 6.1 Tables overview

| Table | Purpose |
| --- | --- |
| `schema_migrations` | Versioned schema apply history |
| `memory_records` | One row per memory item (candidate through forgotten tombstone) |
| `memory_evidence` | Evidence refs attached to a record (1:N) |
| `memory_events` | Append-only lifecycle / audit events |
| `memory_links` | Explicit relationships (supersedes, duplicate_of, challenges, …) |

Blueprint inspirational category tables (`facts`, `project_decisions`, …) map to **`category` values** on `memory_records`, not separate tables, for MVP simplicity.

### 6.2 `schema_migrations`

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| `version` | TEXT | PK | e.g. `memory.1` |
| `applied_at` | TEXT | NOT NULL | UTC ISO via `utc_now_iso()` |
| `description` | TEXT | NOT NULL | Human note |

Lifecycle: insert-only on successful migrate; never update/delete.

### 6.3 `memory_records`

| Column | Type | Null? | Constraints / notes |
| --- | --- | --- | --- |
| `memory_id` | TEXT | NO | PK; `mem-{12 hex}` |
| `project_id` | TEXT | NO | Indexed; registry-validated at service layer |
| `memory_class` | TEXT | NO | Enum §6.6; CHECK |
| `lifecycle_status` | TEXT | NO | Enum §6.6; CHECK; **distinct** from class |
| `category` | TEXT | NO | Controlled vocabulary §6.7 |
| `title` | TEXT | YES | Short label; optional |
| `content` | TEXT | NO* | *NULL only after hard-delete content erasure |
| `content_normalized` | TEXT | YES | Derived; used for hash/search |
| `content_hash` | TEXT | NO | SHA-256 hex of fingerprint payload |
| `sensitivity` | TEXT | NO | Enum §6.6; CHECK |
| `evidence_strength` | TEXT | NO | Enum §6.6; default `none` |
| `confidence` | REAL | YES | 0.0–1.0 optional; never alone ranks above evidence |
| `source_type` | TEXT | NO | e.g. `operator`, `claude`, `cursor`, `codex`, `system`, `orchestration` |
| `proposed_by` | TEXT | NO | Role / operator id |
| `provider_id` | TEXT | YES | When proposed via provider path |
| `task_id` | TEXT | YES | Prefer set; must match project if set |
| `plan_fingerprint` | TEXT | YES | Provenance |
| `session_id` | TEXT | YES | Provenance |
| `orchestration_id` | TEXT | YES | Provenance |
| `approved_by` | TEXT | YES | Required when class=`approved_memory` |
| `approval_method` | TEXT | YES | `human` only in prototype (`policy` reserved) |
| `rejection_reason` | TEXT | YES | Required when rejected |
| `valid_from` | TEXT | YES | UTC ISO |
| `valid_until` | TEXT | YES | UTC ISO; NULL = no expiry |
| `supersedes_memory_id` | TEXT | YES | FK soft (also mirrored in `memory_links`) |
| `superseded_by_memory_id` | TEXT | YES | Set on supersession |
| `forgotten_at` | TEXT | YES | Soft-forget timestamp |
| `content_erased_at` | TEXT | YES | Hard-delete content erasure |
| `created_at` | TEXT | NO | UTC ISO |
| `updated_at` | TEXT | NO | UTC ISO |
| `validated_at` | TEXT | YES | |
| `approved_at` | TEXT | YES | |
| `schema_version` | TEXT | NO | e.g. `memory.1` |

**Uniqueness**

- PK: `memory_id`
- Partial uniqueness (application-enforced in MVP; SQL UNIQUE optional later): within (`project_id`, `content_hash`) among non-forgotten, non-rejected duplicates → validator may link `duplicate_of` rather than silent overwrite.

**Indexes (planned)**

- `(project_id, lifecycle_status, memory_class)`
- `(project_id, category)`
- `(project_id, approved_at)`
- `(project_id, content_hash)`
- `(task_id)` where not null

**Lifecycle of a row:** insert as candidate → update class/status fields on transitions → soft-forget sets flags → hard-delete nulls `content` / `content_normalized` but keeps row + events.

### 6.4 `memory_evidence`

| Column | Type | Null? | Notes |
| --- | --- | --- | --- |
| `evidence_id` | TEXT | NO | PK `evid-{12 hex}` |
| `memory_id` | TEXT | NO | FK → `memory_records.memory_id` |
| `project_id` | TEXT | NO | Denormalized for isolation queries |
| `evidence_type` | TEXT | NO | `plan_fingerprint`, `test_run`, `ci_run`, `review_verdict`, `commit_sha`, `handoff_fingerprint`, `operator_note`, `other` |
| `evidence_ref` | TEXT | NO | Opaque id / fingerprint / note |
| `created_at` | TEXT | NO | UTC ISO |

Indexes: `(memory_id)`, `(project_id, evidence_type)`.

### 6.5 `memory_events` (append-only)

| Column | Type | Null? | Notes |
| --- | --- | --- | --- |
| `event_id` | TEXT | NO | PK `mev-{12 hex}` |
| `memory_id` | TEXT | YES | NULL only for store-level events |
| `project_id` | TEXT | NO | Mandatory scope |
| `action` | TEXT | NO | Enum of audited actions §10 |
| `actor` | TEXT | NO | Operator / `system` / never a model claiming approve |
| `actor_kind` | TEXT | NO | `human`, `system`, `service` |
| `from_class` | TEXT | YES | |
| `to_class` | TEXT | YES | |
| `from_status` | TEXT | YES | |
| `to_status` | TEXT | YES | |
| `detail_json` | TEXT | YES | Canonical JSON; no secrets |
| `created_at` | TEXT | NO | UTC ISO |

**No UPDATE/DELETE** of event rows in normal operation. Indexes: `(project_id, created_at)`, `(memory_id, created_at)`.

### 6.6 `memory_links`

| Column | Type | Null? | Notes |
| --- | --- | --- | --- |
| `link_id` | TEXT | NO | PK `mlk-{12 hex}` |
| `project_id` | TEXT | NO | Both ends must share project |
| `from_memory_id` | TEXT | NO | FK |
| `to_memory_id` | TEXT | NO | FK |
| `link_type` | TEXT | NO | `supersedes`, `superseded_by`, `duplicate_of`, `challenges`, `related` |
| `created_at` | TEXT | NO | |
| `created_by` | TEXT | NO | |

Unique: `(from_memory_id, to_memory_id, link_type)`.

### 6.7 Memory record field matrix

Fingerprint participation = included in `content_hash` / proposal fingerprint payload.

| Field | Mandatory on propose | Nullable in DB | Enum / derived | Fingerprint? |
| --- | --- | --- | --- | --- |
| `memory_id` | Generated | NO | derived id | No (identity) |
| `project_id` | Yes | NO | registry | Yes |
| `memory_class` | Default candidate | NO | enum | Yes |
| `lifecycle_status` | Default `proposed` | NO | enum | Yes |
| `category` | Yes | NO | vocabulary | Yes |
| `title` | No | YES | — | Yes if set |
| `content` | Yes | NO* | — | Yes |
| `content_normalized` | Derived | YES | derived | Yes (hash input) |
| `content_hash` | Derived | NO | derived | N/A (is the hash) |
| `sensitivity` | Yes (default `internal`) | NO | enum | Yes |
| `evidence_strength` | Default `none` | NO | enum | Yes |
| `confidence` | No | YES | 0..1 | No (volatile score) |
| `source_type` | Yes | NO | vocabulary | Yes |
| `proposed_by` | Yes | NO | — | Yes |
| `provider_id` | If provider path | YES | — | Yes if set |
| `task_id` | Preferred | YES | — | Yes if set |
| evidence rows | Preferred for approve | — | child table | Refs yes |
| `approved_by` / `approval_method` / `approved_at` | On approve | YES until approve | — | No (approval meta; gate separately) |
| timestamps | System | NO/YES | UTC ISO | `created_at` excluded from content hash |

### 6.8 Enums and state definitions

**Keep `memory_class` and `lifecycle_status` distinct.**

| `memory_class` | Meaning | Default retrieval? |
| --- | --- | --- |
| `candidate_memory` | Proposed; awaiting decision | No |
| `approved_memory` | Authoritative | Yes (if active) |
| `rejected_memory` | Explicitly refused | No |
| `superseded_memory` | Replaced by newer approved | No (history API) |
| `archived_memory` | Retained; off default retrieve | No |

**Do not persist `ephemeral_context`.**

| `lifecycle_status` | Typical class pairing |
| --- | --- |
| `proposed` | candidate |
| `validated` | candidate (passed deterministic checks) |
| `approved` | approved_memory (active for retrieve) |
| `rejected` | rejected_memory |
| `superseded` | superseded_memory |
| `archived` | archived_memory |
| `forgotten` | any prior; excluded from retrieve |

| `sensitivity` (locked for B3) | Maps from B1 conceptual |
| --- | --- |
| `public` | `public_project` |
| `internal` | `internal` (default) |
| `restricted` | `sensitive` |
| `secret_prohibited` | `secret_adjacent` — **fail closed on write** |

| `evidence_strength` | Meaning |
| --- | --- |
| `none` | No evidence refs |
| `weak` | Single soft ref (note / unverified) |
| `moderate` | Task/plan/CI/review linkage |
| `strong` | Multiple independent refs + operator attestation |

**Category vocabulary (MVP):** `project_fact`, `architecture_decision`, `user_preference`, `accepted_plan_ref`, `incident_constraint`, `provider_behavior`, `lesson`, `operational_observation`, `other`.

---

## 7. Lifecycle and policy

### 7.1 Approval model (locked)

| Rule | Decision |
| --- | --- |
| Who may approve | Human / operator identity recorded in `approved_by`; OS service executes transition |
| Models / providers / workflows | May **propose** only; **cannot** approve, reject, supersede, archive, forget, or hard-delete |
| Active write without approval | **Forbidden** — no path inserts `approved_memory` without `approve_memory` |
| Auto-approve / policy method | **Deferred** — prototype `approval_method` is always `human` |
| Observational auto-promote | **Forbidden** in prototype |
| Fail closed | Missing project, failed validation, secret hit, unauthorized actor → no mutation of approved set |
| Candidate vs active | Persist candidates (Option A); activation is a separate audited transition |

Mirrors plan-gate discipline in `approval.py`: propose/submit freely; activation requires explicit approver and locked content identity (`content_hash` must match at approve time).

### 7.2 Candidate persistence — Option A

| Dimension | Option A (chosen): persist candidates | Option B: ephemeral only |
| --- | --- | --- |
| Audit | Full propose→decide trail | Weak; proposals vanish |
| Privacy | More durable content until reject/forget | Less durable |
| Complexity | Slightly higher schema/status | Simpler store; harder UX |
| Recovery | Restart-safe approval queue | Lost on process end |
| Workflow | Multi-session human approve | Must approve in-session |

**Choice: Option A.** Rejected candidates remain as `rejected_memory` per retention policy. Operators may soft-forget candidates.

### 7.3 Conflict and supersession

- Never silent-overwrite `content` of an approved row.
- Contradictory proposals → separate candidates + optional `challenges` link.
- Supersession: create/approve successor (or approve existing validated successor); set predecessor `memory_class=superseded_memory`, `lifecycle_status=superseded`, bidirectional `memory_links`, fill `supersedes_*` columns — **single transaction**.
- Duplicate `content_hash` in same project → validator links `duplicate_of` or rejects; does not mutate approved content.

### 7.4 Project isolation

1. Caller supplies `project_id` (registry id space).
2. Service calls `ProjectRegistry.require(project_id)` — unregistered / inactive / Equitify → fail closed.
3. All SQL filters include `project_id = ?` as first predicate.
4. Links require both ends same `project_id`.
5. No arbitrary provider-supplied project ids without registry validation.
6. Global memory deferred.

---

## 8. Retrieval and determinism

### 8.1 Filters (mandatory order)

1. `project_id` (mandatory; missing/unauthorized → error or empty per API; **never** other projects)
2. `lifecycle_status IN (...)` — default: `approved` only
3. `memory_class` — default: `approved_memory`
4. `forgotten_at IS NULL` and `content_erased_at` handling (forgotten excluded)
5. Sensitivity ≤ caller eligibility (default: exclude `restricted` from unapproved providers; never return `secret_prohibited`)
6. Optional: `category`, `task_id`, tags (future), `valid_until` not expired
7. Optional: minimum `evidence_strength`
8. Optional: deterministic text match on `content_normalized` / `title` (casefold substring)

### 8.2 Ordering (locked; never rely on SQLite unspecified order)

1. `evidence_strength` rank DESC (`strong` > `moderate` > `weak` > `none`)
2. `approved_at` DESC (NULL last)
3. `memory_id` ASC (stable tie-break)

Approved memory outranks model claims by **not including** candidates/ephemeral in default retrieve.

### 8.3 Pagination

- `limit` required (default 20, max 100)
- `offset` ≥ 0
- Return total_count optional via separate COUNT with identical filters

### 8.4 Search decision

| Capability | Prototype |
| --- | --- |
| Structured filters | Yes |
| Deterministic text match | Yes (`content_normalized` LIKE / Python filter after SQL) |
| Embeddings / vector | **No** |
| FTS5 | **Deferred** — may add virtual table in later migration without changing service API |

### 8.5 Content normalization and hashing

1. NFKC normalize Unicode.
2. Strip leading/trailing whitespace; collapse internal whitespace runs to single space.
3. Casefold for `content_normalized` (search); store original `content` unchanged (unless redacted).
4. Secret scan: refuse or redact per policy — **refuse** on `secret_prohibited` patterns for durable store.
5. Fingerprint payload (canonical JSON via `fingerprints.canonical_json`): `project_id`, `category`, `title`, `content_normalized`, `sensitivity`, `memory_class`, `lifecycle_status`, `evidence_strength`, sorted evidence refs, `source_type`, `proposed_by`, optional ids.
6. `content_hash = sha256_hex(payload)`.
7. Approve re-hashes; mismatch → fail closed (stale candidate).

---

## 9. Security and privacy

| Control | Prototype rule |
| --- | --- |
| Least privilege | Proposers write candidates; retrieve returns project-scoped approved set |
| No provider DB access | Adapters never receive SQLite path/connection |
| Secrets | Reuse Round 4A `ci_secrets` patterns; never persist raw secrets |
| Sensitivity | `secret_prohibited` refused at propose/validate |
| Cross-project | Impossible via mandatory filter + registry |
| Equitify | Registry sentinels refuse |
| Encryption at rest | Deferred (local single-user threat model) |
| Feature disabled | When `memory.enabled=false`, all mutating APIs fail closed; retrieve returns empty/error |
| Backups | Operator file copy of SQLite; restore must preserve forget tombstones |

---

## 10. Audit and deletion

### 10.1 Audit design

- All lifecycle transitions append to `memory_events` in the **same transaction** as the row mutation.
- Event rows are append-only.

| Action audited | Always? |
| --- | --- |
| `propose`, `validate`, `approve`, `reject`, `supersede`, `archive`, `forget`, `hard_delete` | Yes |
| `retrieve` (default context retrieve) | **Yes** — record `project_id`, filter summary, result ids/count, actor; **not** full content dump |
| Internal `get_memory` by id for operator show | Optional; audit when `--audit` / operator history path |
| Health/schema migrate | Yes (store-level event, `memory_id` NULL) |

### 10.2 Forgetting and deletion

| Mode | Behavior |
| --- | --- |
| Archive | `memory_class=archived_memory`, `lifecycle_status=archived`; off default retrieve; content retained |
| Soft forget | `lifecycle_status=forgotten`, `forgotten_at` set; excluded from retrieve; content retained for audit retention window |
| Hard delete | Null `content` / `content_normalized`; set `content_erased_at`; keep row + events + redacted summary in event `detail_json`; **human required** |
| Superseded | Remains readable via history API |

Forgetting is itself audited. No silent hard delete.

---

## 11. Adapter and module design

### 11.1 Package layout (B3 target — not created in B2)

Align with existing `src/ai_dev_os/` conventions (not a wholesale §14 restructure):

```text
src/ai_dev_os/memory/
  __init__.py          # public service façade exports
  models.py            # enums, dataclasses (memory_models conceptually)
  errors.py            # MemoryError taxonomy
  config.py            # MemoryConfig; disabled by default
  normalize.py         # content normalization + hash
  policy.py            # transitions, approval checks, sensitivity
  service.py           # propose/approve/retrieve/... orchestration
  audit.py             # event helpers
  backend/
    __init__.py
    base.py            # MemoryBackend protocol
    sqlite.py          # sqlite3 implementation
  migrations.py        # apply schema_migrations versions
```

CLI wiring (later checkpoint): thin commands in `cli.py` calling `memory.service` only when enabled.

### 11.2 Backend protocol (conceptual)

```text
MemoryBackend
  connect() / close()
  migrate()
  insert_record / update_record / get_record
  insert_evidence / list_evidence
  insert_event / list_events
  insert_link / list_links
  query_records(filters, order, limit, offset)  # must apply project_id
  begin / commit / rollback  (or connection context)
```

Replaceable later with Postgres without changing `service.py` contracts.

### 11.3 Transaction boundaries

| Operation | Single transaction includes |
| --- | --- |
| `propose_memory` | insert record + evidence + `propose` event |
| `validate_memory` | status update + event |
| `approve_memory` | class/status/approver fields + event (+ optional activate) |
| `reject_memory` | class/status/reason + event |
| `supersede_memory` | old+new row updates + links + events |
| `archive` / `forget` / `hard_delete` | row update + event |
| `retrieve_memory` | read query + optional retrieve audit insert |

Failure mid-way → rollback; no partial approved activation.

### 11.4 Concurrency

| Setting | Value |
| --- | --- |
| Journal mode | `WAL` |
| Busy timeout | `5000` ms |
| Isolation | Default SQLite; service uses one connection per operation context |
| Multi-process writers | Out of scope; document “single writer expected” |

Do not build a connection pool or distributed lock service.

---

## 12. API contracts

Conceptual service methods (OS-owned). Providers call only through OS; never SQL.

| Method | Inputs (core) | Success | AuthZ | Failure |
| --- | --- | --- | --- | --- |
| `propose_memory` | project_id, content, category, proposed_by, source_type, sensitivity, evidence[], optional task_id/… | memory_id, class=candidate, status=proposed | registry + enabled | ValidationError / MemorySecurityError |
| `validate_memory` | memory_id, project_id | status=validated or rejected | OS validator only | not found / wrong project |
| `approve_memory` | memory_id, project_id, approver | class=approved_memory, status=approved | human approver; hash match | refuse if not validated |
| `reject_memory` | memory_id, project_id, actor, reason | class=rejected_memory | OS/human | refuse unknown |
| `retrieve_memory` | project_id, filters, limit, offset, caller_ctx | ordered hits | project + sensitivity | empty/deny; never cross-project |
| `supersede_memory` | project_id, old_id, new_id or new proposal+approve | linked supersession | same as approve | no silent overwrite |
| `archive_memory` | memory_id, project_id, actor | archived | OS/human | not found |
| `forget_memory` | memory_id, project_id, actor, mode=soft | forgotten | OS/human | fail closed |
| `hard_delete_memory` | memory_id, project_id, human actor | content erased | **human only** | refuse if mode unsupported |
| `get_memory_history` | memory_id, project_id | events + links + record | operator | wrong project |

All mutating methods emit audit events.

### 12.1 Error taxonomy

| Error | When |
| --- | --- |
| `MemoryDisabledError` | feature flag off |
| `MemoryNotFoundError` | unknown id / wrong project (avoid cross-project oracle where practical) |
| `MemoryValidationError` | schema/enum/content/hash |
| `MemorySecurityError` | secrets, sensitivity, Equitify |
| `MemoryAuthorizationError` | model/provider attempted approve/delete |
| `MemoryConflictError` | illegal transition, stale hash, supersession rules |
| `MemoryIsolationError` | project scope violation |

Prefer subclassing `ValidationError` for CLI consistency where appropriate.

---

## 13. Migration and configuration

### 13.1 Migration strategy

1. On connect, read `schema_migrations`.
2. Apply pending versions in order (`memory.1` creates five tables + indexes).
3. Record version row in same transaction as DDL when possible.
4. Unsupported newer DB → fail closed.
5. No JSON→SQLite legacy import in prototype (no prior memory artifacts).
6. Future Postgres: new backend; keep `memory.N` version names.

**Phase B2 produces no migration files on disk.**

### 13.2 Configuration

| Key | Default | Meaning |
| --- | --- | --- |
| `memory.enabled` | `false` | Master switch |
| `memory.db_path` | `workspace/memory/memory.sqlite3` | Relative to repo/workspace root |
| `memory.default_retrieve_limit` | `20` | |
| `memory.max_retrieve_limit` | `100` | |
| `memory.busy_timeout_ms` | `5000` | |
| `memory.audit_retrievals` | `true` | |

Config file (future): `config/memory.yaml` with schema_version `memory.1` — **not created in B2**. Gitignore DB path when implementation lands.

---

## 14. Test strategy

No live providers. Use `tmp_path` SQLite files.

| Layer | Examples |
| --- | --- |
| Unit | normalize/hash stability; enum transitions; fingerprint payload |
| Repository | CRUD, FK, indexes used by queries, migration apply, WAL connect |
| Service | propose→validate→approve; reject; supersede links; archive/forget/hard_delete |
| Determinism | same DB + query → identical ordered `memory_id` list |
| Security | project A≠B isolation; Equitify refuse; secret content refused; model cannot approve; disabled flag |
| Audit | every transition has event; retrieve audited when enabled |
| Concurrency smoke | busy timeout behaves; no corruption on sequential writers |

Acceptance mirrors B1 §14 MVP criteria once B3 completes — **not claimed now**.

---

## 15. Implementation checkpoints

Each checkpoint is separately approvable. Rollback = revert checkpoint commit(s); delete temp DB files; leave Round 4A untouched.

### B3.1 — Models, errors, config (disabled)

| | |
| --- | --- |
| Files | `memory/models.py`, `errors.py`, `config.py`, tests |
| Acceptance | Enums/dataclasses importable; `enabled=false` default; no DB file created |
| Prohibited | sqlite connect, CLI, providers |

### B3.2 — Normalization + fingerprints

| | |
| --- | --- |
| Files | `memory/normalize.py`, tests vs `fingerprints.py` |
| Acceptance | Stable hash across runs; secret refuse cases |
| Prohibited | persistence |

### B3.3 — SQLite backend + migration `memory.1`

| | |
| --- | --- |
| Files | `backend/base.py`, `backend/sqlite.py`, `migrations.py`, tests |
| Acceptance | Temp DB migrates; tables exist; rollback on failed migrate |
| Prohibited | service approval, CLI |

### B3.4 — Propose / validate / reject

| | |
| --- | --- |
| Files | `service.py` (partial), `policy.py`, `audit.py`, tests |
| Acceptance | Option A candidates persist; registry required; no approve yet |
| Prohibited | auto-approve, embeddings |

### B3.5 — Approve + retrieve + determinism

| | |
| --- | --- |
| Files | service approve/retrieve; tests |
| Acceptance | No approve without human; default retrieve approved-only; stable order; project isolation |
| Prohibited | FTS5, vectors |

### B3.6 — Supersede + archive + links

| | |
| --- | --- |
| Acceptance | No silent overwrite; bidirectional links; history readable |
| Prohibited | cross-project links |

### B3.7 — Forget / hard delete + audit retention

| | |
| --- | --- |
| Acceptance | Soft forget excludes retrieve; hard delete erases content, keeps events; human for hard delete |
| Prohibited | deleting `memory_events` rows |

### B3.8 — CLI surface (optional thin)

| | |
| --- | --- |
| Files | `cli.py` subcommands gated by `memory.enabled` |
| Acceptance | Disabled → fail closed; simulation tests only |
| Prohibited | live provider wiring |

### B3.9 — Docs sync + package note

| | |
| --- | --- |
| Files | ARCHITECTURE/ROADMAP/chronicle honesty; version bump **only if approved** |
| Acceptance | Docs do not claim features beyond tests; Round 4A still baseline until bump approved |
| Prohibited | Equitify, LangGraph, LiteLLM |

---

## 16. Acceptance criteria

Prototype is acceptable when:

1. No approved write without `approve_memory` + human approver.
2. Project isolation proven (A never visible to B; Equitify refused).
3. Deterministic retrieval ordering with explicit tie-break.
4. Conflicts preserved; supersession linked; no silent overwrite.
5. Provenance present on approved records (proposer, evidence or operator attestation, approver, timestamps).
6. Append-only audit for lifecycle (+ default retrieve).
7. Soft-forget excludes default retrieve; hard delete preserves audit.
8. Restart reloads approved memories from SQLite.
9. Suite passes with simulation/fixtures only — no network, no paid APIs.
10. Memory disabled by default; enabling is explicit.
11. No new runtime dependencies beyond stdlib `sqlite3`.
12. Package/docs honesty: memory not claimed until checkpoints land.

---

## 17. Deferred scope

| Item | Why deferred |
| --- | --- |
| Embeddings / vector search | Complexity; nondeterministic rank risk |
| FTS5 | Optional later; filters suffice for MVP |
| Encryption at rest | Local single-user; productize later |
| Global memory | Needs stricter human gate |
| Policy auto-approve | Safety; observe human-only first |
| Observational auto-promote | B1 open; refuse for prototype |
| Audit retention duration product policy | Keep forever locally for now |
| Postgres / multi-writer | No scale need |
| Cross-project authorization | Explicit future feature |
| CLI final naming bikeshed | Decide in B3.8 |
| Confidence scoring formula beyond evidence_strength | Deterministic order first |
| Full transcript / CoT storage | Prohibited by design |
| Mem0/Graphiti/Neo4j/Redis/pgvector | Blueprint non-goals for Phase B |
| Round 4B complete / Equitify / LiteLLM / LangGraph | Separate tracks; memory work does not reopen CI permission or provider scope |

---

## 18. Risks and open issues

| Risk / issue | Severity | Mitigation |
| --- | --- | --- |
| Sensitivity enum rename vs B1 labels | Low | Mapping table in §6.8; B1 remains conceptual |
| Candidate content privacy on disk | Medium | gitignore DB; soft/hard forget; secret refuse |
| Retrieve audit volume | Low | Summarize filters/ids; config toggle |
| WAL + antivirus on Windows | Low | busy_timeout; document single-writer |
| Operator confusion: class vs status | Medium | Distinct fields + docs + validation matrix |
| Scope creep into FTS/embeddings | High | Hard deferral in §17; reject in code review |
| Claiming memory shipped early | High | Docs honesty gate in B3.9 |

**No contradiction found** with blueprint §7, Phase B1 design, or `MODEL_ROLES.md` requiring a B1 doc edit. OS remains sole memory authority; models cannot persist directly; project isolation default-deny; approved memory outranks model claims via retrieve policy; no silent overwrite; local simulation-only; memory not claimed implemented.

---

## 19. Recommended next prompt

**Phase B3.1 only:** implement `src/ai_dev_os/memory/` models, errors, and disabled-by-default config + unit tests — no SQLite file creation, no CLI, no service mutations, no dependency/version changes — following this plan §§6.8, 11, 13.2, 15 (B3.1).

Do not start B3.2+ until B3.1 is reviewed and approved.

---

## Document control

| | |
| --- | --- |
| Phase | B2 |
| Changes allowed this round | This file + short cross-links in README / ARCHITECTURE / ROADMAP / PROJECT_CHRONICLE |
| Must not change | Runtime code, `pyproject.toml`, `SHARED_MEMORY_DESIGN.md` (unless contradiction — none found) |
