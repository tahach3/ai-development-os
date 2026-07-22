# Phase B1 — Controlled Shared Memory Design

**Status:** Design only (Phase B1)  
**Scope:** Implementation-ready design for project-scoped shared memory authority, classes, approval lifecycle, retrieval, retention, security, SQLite prototype boundaries, and conceptual API  
**Not in scope:** Schema files, databases, migrations, memory services, CLI commands, dependencies, packages, providers, runtime configuration, or any persistence implementation

**Implemented baseline (unchanged):** Round 4A, package **`0.6.0`**  
**Architectural source of truth:** [`AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md`](AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md) §7 (Shared Memory Design), plus related isolation / audit / three-model client rules  
**Related current docs:** [`ARCHITECTURE.md`](ARCHITECTURE.md), [`MODEL_ROLES.md`](MODEL_ROLES.md), [`ROADMAP.md`](ROADMAP.md), [`SECURITY_MODEL.md`](SECURITY_MODEL.md), [`PROJECT_BOUNDARIES.md`](PROJECT_BOUNDARIES.md)

**Honest status:** No shared-memory implementation exists yet. Round 4A remains the shipped capability set. This document prepares Phase B implementation; it does not authorize code, SQLite files, or new dependencies.

---

## Self-review vs existing controls

| Existing control | Phase B1 stance |
| --- | --- |
| Project registry + Equitify sentinels | Every memory write/read resolves `project_id` through the registry; Equitify refused; unregistered IDs fail closed. |
| Plan/task fingerprints | Provenance may reference `task_id`, approved plan fingerprint, context/handoff fingerprint; fingerprints do not alone approve memory. |
| Approval / lifecycle gates | Memory promotion mirrors plan-gate discipline: propose freely, persist only through OS-owned approval transitions. |
| Provider lane (3B) / orchestration (3C) | Providers and orchestration may **propose** candidate memories; they never open a memory store or write approved records. |
| Local CI / secret scan (4A) | Memory content subject to secret/PII redaction rules; raw secrets never persist. |
| Audit / behavioral metrics | Memory lifecycle emits append-only audit events; metrics may aggregate sanitized counts later — not auto-routing. |
| Manual handoff | Handoff packets remain ephemeral unless an operator explicitly proposes and the OS approves a memory. |
| No network / paid APIs by default | Memory MVP tests are simulation-only; no live model required to exercise memory APIs. |

No contradiction with `MODEL_ROLES.md`: AI Development OS remains the only persistence authority; Claude / Cursor / Codex stay clients.

---

## 1. Memory authority

The **AI Development OS** is the only authority permitted to approve and persist project memory.

| Actor | May propose | May validate (deterministic checks) | May approve / reject / supersede / archive / forget | May open a private memory DB |
| --- | --- | --- | --- | --- |
| AI Development OS (control plane) | Yes (system events) | Yes | Yes (policy + human gates as required) | Yes (future, behind adapter) |
| Claude (planning role) | Yes (candidate knowledge / plans) | No | No | No |
| Cursor (implementation role) | Yes (implementation facts) | No | No | No |
| Codex/GPT (review role) | Yes (challenges, review findings) | No | No | No |
| Workflows / orchestration | Yes (outcome proposals) | Limited (schema/binding checks only) | No | No |
| Provider adapters | Yes (structured proposal envelopes) | Limited (schema only) | No | No |
| Humans / operators | Yes | N/A | Yes (required for high-risk / policy / global) | Via OS CLI only |

**Rules:**

- Models, IDEs, workflows, and providers **must not** persist memories directly to disk, SQLite, or any sidecar store.
- “Approved memory” means a record that passed OS validation **and** an explicit approval transition owned by the OS.
- Deterministic validators may auto-store **operational events** only into non-authoritative classes (see §2), never into `approved_memory`, without a defined promotion path.
- Cursor three-model client workflows must not maintain a competing project-memory database (see §13).

---

## 2. Memory classes

Define at least these classes (status/class labels for records):

| Class | Meaning | Survives task end | Survives session end | Survives project active life | Survives repository / workspace wipe |
| --- | --- | --- | --- | --- | --- |
| `ephemeral_context` | Active-task notes, intermediate summaries, retrieved snippets, unverified suggestions | No (default drop) | No | No | No |
| `candidate_memory` | Proposed persistent fact awaiting validation/approval | Optional (kept until decided) | Yes (until decided) | Until approved/rejected/expired | Only if persisted as candidate in store |
| `approved_memory` | Authoritative, project-scoped (or explicitly global) memory | Yes | Yes | Yes (until superseded/archived/forgotten) | Yes (in store + backups) |
| `rejected_memory` | Explicitly refused proposal; retained for audit/learning | Yes (as history) | Yes | Yes (retention policy) | Yes (audit retention) |
| `superseded_memory` | Formerly approved; replaced by a newer approved record | Yes | Yes | Yes (historical readability) | Yes |
| `archived_memory` | No longer active for default retrieval; retained | Yes | Yes | Yes until forget/delete | Yes until hard delete |

**Notes:**

- Blueprint terms *authoritative / observational / temporary / rejected-or-superseded* map onto these classes: authoritative → `approved_memory`; temporary → `ephemeral_context` (+ short-lived candidates); rejected/superseded → `rejected_memory` / `superseded_memory`; observational events may land as `candidate_memory` or auto-validated operational candidates pending promotion policy (open decision: auto-promote observational metrics — see §15).
- Only `approved_memory` is default-eligible for retrieval into new task context packets.
- `ephemeral_context` must not be treated as truth and must not be promoted without re-entering the proposal path with evidence.

---

## 3. Project isolation

### Ownership

- Every memory record belongs to **exactly one** `project_id`, **unless** explicitly approved as **global** under a separate, stricter gate (global policy is an open decision — §15).
- Default retrieval is **project-scoped only**. Cross-project reads are forbidden unless an explicit, audited authorization record exists (future; not required for MVP).

### Project identity resolution

Align with existing registry terms:

1. Caller supplies `project_id` (same id space as `config/projects.yaml` / `ProjectRegistry`).
2. OS calls registry `require(project_id)` — unregistered → fail closed.
3. Equitify sentinels (`equitify`, `equitify-machine`, …) → refuse.
4. Optional path bindings (workspace roots, artifact paths) must pass `ensure_path_allowed(project_id, path)` when memory content references filesystem paths.
5. Task-linked memories must also satisfy `task.project_id == memory.project_id`.

### Validation on write and read

- Writes without a resolvable registered `project_id` fail closed (except the future global class, which requires its own approved scope id and human gate).
- Reads filter by `project_id` **before** relevance ranking. Missing or mismatched project scope returns empty / error — never another project’s rows.
- Export/import between projects is prohibited without an explicit approved migration/copy operation (out of MVP).

---

## 4. Approval lifecycle

```text
proposed → validated → approved | rejected → active → superseded | archived → forgotten/deleted
```

| Transition | Who / what | Notes |
| --- | --- | --- |
| → `proposed` | Any allowed proposer (model role, operator, workflow) via `propose_memory` | Creates `candidate_memory`; no authoritative retrieval yet |
| `proposed` → `validated` | OS deterministic validators | Schema, project scope, secret redaction, duplicate checks, required provenance fields; failure stays proposed or moves to rejected per policy |
| `validated` → `approved` | OS approval path: policy auto-approve **only** for explicitly allowlisted low-risk categories **or** human/operator approval | High-risk / policy / global / cross-project → human required (open: always-human — §15) |
| `validated` → `rejected` | OS or human | Becomes `rejected_memory`; reason required |
| `approved` → `active` | Implicit on approval | `approved_memory` eligible for retrieval |
| `active` → `superseded` | OS via `supersede_memory` with successor id | Prior record becomes `superseded_memory`; never silent overwrite |
| `active` → `archived` | OS / human via `archive_memory` | Removed from default retrieval; retained |
| `*` → forgotten/deleted | OS / human via `forget_memory` | Soft-forget vs hard-delete distinguished (§9); audit preserved |

**Forbidden:** providers or models calling approve/reject/supersede/forget directly; silent in-place mutation of approved content; skipping validation.

---

## 5. Memory contents

### Permitted categories (when evidenced and approved)

- Confirmed project facts (registry-aligned, path-safe)
- Approved architecture decisions
- User preferences **relevant to the project**
- Accepted plans (reference by plan id / fingerprint; not full unbounded transcripts)
- Resolved incidents and known constraints
- Verified provider behavior **for this project/task type** (with outcome evidence)
- Lessons supported by evidence (tests, review verdicts, CI runs, operator confirmation)

### Prohibited / restricted

| Content | Rule |
| --- | --- |
| Raw secrets / credentials / tokens / API keys | Never store; redact or refuse |
| Unnecessary personal data | Refuse or minimize; open retention/PII policy |
| Unverified model claims | Remain `candidate_memory` or `ephemeral_context` only |
| Full hidden reasoning / chain-of-thought dumps | Do not persist as memory |
| Uncontrolled full transcripts | Do not store as permanent memory by default (blueprint §17) |
| Unsupported assumptions | Reject or keep candidate until evidenced |
| Memories imported from another project | Forbidden without explicit approved copy + new provenance |

Sensitivity classification (conceptual): `public_project` / `internal` / `sensitive` / `secret_adjacent`. Secret-adjacent content must fail closed on write.

---

## 6. Evidence and provenance

Each **persistent** memory (`candidate_memory` and above, excluding pure ephemeral scratch) must record enough to answer:

| Question | Conceptual fields |
| --- | --- |
| Who proposed? | `proposed_by` (role / operator id / system), `source_type` |
| Which task? | `task_id` (optional but preferred), related session/orchestration ids when applicable |
| Which model/provider? | `provider_id` / logical role (`claude` / `cursor` / `codex`) when proposed by a model path |
| What evidence? | `evidence_refs` (plan fingerprint, test run id, CI run id, review verdict id, commit SHA, handoff fingerprint, operator note) |
| Who/what approved? | `approved_by`, `approval_method` (`human` / `policy`), timestamp |
| When active? | `created_at`, `validated_at`, `approved_at`, `valid_from`, `valid_until` |
| Whether superseded? | `status`, `supersedes`, `superseded_by` |

Additional recommended fields (from blueprint §7.3): `memory_id`, `project_id`, `category`, `content`, `confidence`, `security_classification`, revision linkage.

**Principle:** Memory is evidence, not truth by default. Confidence scores without evidence refs must not outrank empty-evidence approved peers in retrieval (§7).

---

## 7. Retrieval policy

### Filters (applied before ranking)

1. `project_id` (mandatory; fail closed if missing/unauthorized)
2. Memory status/class (default: `approved_memory` / active only)
3. Sensitivity vs caller role / provider eligibility (do not send sensitive memory to unapproved providers)
4. Optional `task_id` / category / tags
5. Age / `valid_until` (expired → exclude from default active set)
6. Evidence strength floor (configurable later)

### Ranking (deterministic MVP expectation)

1. **Approved** memory outranks model-generated guesses and ephemeral context  
2. Higher evidence strength / completeness  
3. Newer `approved_at` (or `valid_from`) when otherwise equal  
4. Stable tie-break on `memory_id` for reproducibility  

Retrieval returns references + bounded content suitable for context packets — not unbounded dumps. Cross-project results never appear in the default path.

---

## 8. Conflict handling

| Situation | Required behavior |
| --- | --- |
| Contradictory approved vs new proposal | Keep both visible as conflict; new item stays candidate until supersession or rejection |
| Supersession | Create new approved record; mark old `superseded_memory` with bidirectional links |
| Missing evidence | Do not approve; remain candidate or reject |
| Conflicting provider proposals | Store as separate candidates; reviewers may challenge; OS does not majority-vote truth |
| Historical readability | Superseded/rejected/archived remain queryable via explicit history/audit APIs |
| Accidental duplicate | Validator may reject or link as duplicate candidate — must not silently overwrite approved rows |

**Hard rule:** Do not silently overwrite approved memory.

---

## 9. Retention and forgetting

| Mechanism | Behavior |
| --- | --- |
| Retention defaults | Active approved retained for project life; rejected/superseded retained per audit policy (duration open — §15) |
| Archival | Soft removal from default retrieval; record remains |
| Explicit forgetting | Operator/OS `forget_memory`: mark forgotten; exclude from retrieval; retain tombstone + audit |
| Hard deletion | Optional later step for content erasure; **audit events preserved** (may retain redacted summaries only) |
| Superseded handling | Keep readable as history; not default-retrieved |
| Ephemeral | Dropped at task/session end; not in durable store by default |

Forgetting must itself be an audited action. Backup/recovery expectations: local store recoverable from OS-managed backups without resurrecting forgotten content into default retrieval unless an explicit undo is audited.

---

## 10. Security

Aligned with [`SECURITY_MODEL.md`](SECURITY_MODEL.md) and blueprint §13:

- **Least privilege:** proposers write candidates only; readers get project-scoped approved set; no provider DB credentials.
- **Fail-closed writes:** missing project, failed validation, secret hit, unauthorized approver → no mutation of approved set.
- **Sensitive-value redaction:** reuse Round 4A secret-pattern discipline; never persist raw secret values.
- **No direct provider DB access:** adapters speak proposal/retrieve APIs only through the OS.
- **Immutable audit events:** append-only `audit_memory_action` stream; no rewrite of past events.
- **Cross-project leak prevention:** scope filter mandatory; tests must prove isolation (§14).
- **Backup/recovery:** local single-user backups; restore must re-apply forget tombstones and project scope; no Equitify paths.
- **Network default off:** memory subsystem does not require network for MVP.

---

## 11. SQLite prototype boundaries

**Describe only — do not implement in this round.**

Future SQLite prototype should be:

| Property | Meaning |
| --- | --- |
| Local-only | File under this repo’s workspace (path TBD); no hosted DB |
| Single-user | No multi-writer cluster assumptions |
| Deterministic | Stable ordering; no nondeterministic “AI rank” in core path |
| Project-scoped | Tables/queries enforce `project_id` |
| Migration-ready | Versioned schema later; expandable without rewrite of callers |
| Replaceable behind adapter | `memory_backends/` style interface (blueprint); Postgres/pgvector only when justified |
| Suitable for tests | Temp DB fixtures; simulation-only; no live models |
| Not final distributed platform | Explicitly not Neo4j/Redis/Mem0/Graphiti/etc. for Phase B |

Blueprint “first tables” (`projects`, `facts`, `project_decisions`, …) are **inspirational categories**, not a locked schema. Exact schema is an open decision (§15).

---

## 12. API boundaries (conceptual)

No production code in this round. Conceptual operations:

| Operation | Inputs (conceptual) | Outputs | Authorization | Failure behavior |
| --- | --- | --- | --- | --- |
| `propose_memory` | `project_id`, content, category, proposer, evidence refs, optional `task_id` | `memory_id`, class=`candidate_memory` | Registered project; authenticated operator or bound provider role | Fail closed on bad scope/secrets/schema |
| `validate_memory` | `memory_id` | validation report; status→validated or rejected | OS validators only | Invalid → no approve path |
| `approve_memory` | `memory_id`, approver, method | class=`approved_memory`, active | OS policy and/or human; high-risk human | Refuse if not validated / unauthorized |
| `reject_memory` | `memory_id`, reason, actor | class=`rejected_memory` | OS or human | Refuse unknown id / wrong project |
| `retrieve_memory` | `project_id`, filters, limit | ordered memory hits | Project scope + sensitivity vs caller | Empty on deny; never cross-project |
| `supersede_memory` | `old_id`, `new_id` or new content proposal | old→superseded, new→approved/active | Same as approve + linkage rules | Refuse silent overwrite without link |
| `archive_memory` | `memory_id` | class=`archived_memory` | OS / human | Fail if not found / wrong project |
| `forget_memory` | `memory_id`, mode soft/hard | forgotten tombstone; audit | Human for hard delete (recommended) | Preserve audit; fail closed if mode unsupported |
| `audit_memory_action` | filter by project/memory/time | append-only event list | Operator / OS | Read-only; no mutation |

All operations emit audit events. Providers call propose/retrieve only through OS-mediated surfaces.

---

## 13. Three-model boundaries

```text
Claude proposes plans and candidate knowledge.
Cursor implements approved work and may propose implementation facts.
Codex/GPT independently reviews and may challenge memories.
AI Development OS alone controls persistence and lifecycle.
```

- No model maintains a separate project-memory database.
- Independent review may produce `candidate_memory` challenges that block or delay approval; review cannot unilaterally delete approved memory.
- Context packets may **include** retrieved approved memory selected by the OS; models do not pull raw DB handles.
- Matches [`MODEL_ROLES.md`](MODEL_ROLES.md): OS owns future approved shared memory; Cursor three-model workflow is a client.

---

## 14. MVP acceptance criteria

Measurable criteria for a **later** implementation round (not claimed now):

1. **No write without approval** — attempts to persist as approved without `approve_memory` fail; tests cover bypass attempts.
2. **Project isolation proven** — memory written for project A never returned for project B queries; Equitify ids refused.
3. **Deterministic retrieval ordering** — same DB + query → same ordered ids across runs.
4. **Conflict preservation** — contradictory candidates coexist; supersession links retained; no silent overwrite.
5. **Complete provenance** — every approved record has proposer, evidence refs (or explicit operator attestation), approver, timestamps.
6. **Audit coverage** — each lifecycle transition produces an append-only audit event.
7. **Forgetting behavior** — forgotten memories excluded from default retrieve; audit/tombstone remain.
8. **Restart persistence** — process restart reloads approved memories from store.
9. **No provider/live-model requirement** — full test suite passes with simulation/fixtures only.
10. **Simulation-only tests** — no network, no paid APIs, no Equitify access.

---

## 15. Open decisions

Require explicit approval before implementation. **Do not silently choose:**

| Decision | Why it matters |
| --- | --- |
| Exact SQLite schema | Table layout, indexes, revision model |
| Embeddings: use or no | Semantic search vs deterministic filters-only MVP |
| FTS5 full-text search | Optional SQLite FTS vs simple field match |
| Encryption at rest | Local file threat model vs complexity |
| Global-memory policy | Whether global memories exist; who approves; how retrieved |
| Audit retention duration | How long rejected/forgotten audits/content survive |
| Migration strategy | JSON workspace artifacts → SQLite; future Postgres |
| Memory scoring / confidence formula | Ranking beyond deterministic status+evidence+recency |
| Whether human approval is **always** required | vs allowlisted auto-approve for low-risk observational events |
| Observational auto-promote | Whether provider timeout/ perf events may auto-land as approved |
| Workspace path for DB file | Exact location under `workspace/` and gitignore rules |
| CLI surface naming | Exact `ai-dev-os` subcommands for Phase B2+ |

---

## Implementation non-goals (this document / Phase B1)

- Creating `memory/` packages, SQLite files, migrations, or adapters
- Adding dependencies (including sqlite wrappers beyond stdlib later — still deferred)
- Changing Round 4A runtime behavior or package version
- Enabling live providers for memory proposals
- Connecting Equitify
- Importing Mem0, Graphiti, Letta, Neo4j, Redis, pgvector, or similar

---

## Next step (not started)

**Phase B2+ (future, separate approval):** implement SQLite prototype behind an adapter, CLI propose/approve/retrieve/supersede, and simulation tests meeting §14 — only after open decisions in §15 are resolved as needed for that round.
