# Phase B3.2 — Shared Memory SQLite Persistence

**Status:** Implementation design for Phase B3.2 (local SQLite persistence, disabled by default)

**Baseline:** package **0.8.8** · HEAD `73bfb83` · branch `master`

**Authoritative priors:** [`SHARED_MEMORY_DESIGN.md`](SHARED_MEMORY_DESIGN.md) (B1), [`SHARED_MEMORY_IMPLEMENTATION_PLAN.md`](SHARED_MEMORY_IMPLEMENTATION_PLAN.md) (B2), B3.1 domain under `src/ai_dev_os/memory/`

**Scope of this phase:** stdlib `sqlite3` schema + idempotent migrations + repository CRUD over immutable B3.1 models + hard disabled-by-default guard + optional read-only `memory-status` CLI

**Not in scope:** service orchestration / approve-promote workflows, FTS5, embeddings, live providers, network, Equitify, Round 4D2, STAGE_ORDER changes, `4a.1` schema bump, ORM / new runtime deps

---

## 1. Purpose

Ship a **local-only**, **opt-in** SQLite persistence layer that:

1. Materializes the B2 relational schema with forward-only, checksummed migrations.
2. Maps create/read/update/list onto frozen B3.1 `MemoryRecord` / evidence / link models.
3. **Refuses** all write and enable paths when `MemoryConfig.enabled` is false (the default) with a typed `MemoryDisabledError` — never a silent no-op.
4. Does **not** auto-wire into providers, orchestration, CI stages, or any auto-activating runtime path.

---

## 2. WIP decision (this implementation)

Untracked pre-work existed at baseline:

| Path | Role |
| --- | --- |
| `src/ai_dev_os/memory/sqlite_schema.py` | DDL builder + compatibility checks |
| `src/ai_dev_os/memory/sqlite_migrations.py` | Migration registry + apply/verify |
| `src/ai_dev_os/memory/sqlite_connection.py` | Path safety, PRAGMA policy, init/validate |
| `tests/memory/test_sqlite_*.py` | Schema / migration / connection coverage |

**Decision: build on this WIP** (not discard). It already matches B2 table/index intent, uses stdlib `sqlite3` only, and encodes fail-closed migration checksums. Gaps completed in B3.2:

- Typed `MemoryMigrationError` / `MemoryPersistenceError` on the B3.1 error taxonomy
- `MemoryConfig.backend` field (default `"sqlite"`) for explicit backend refuse
- Public exports from `memory/__init__.py`
- Repository CRUD (`sqlite_repository.py`) over B3.1 models
- Read-only `memory-status` CLI reporting `"disabled"` under default config
- This design document

Unrelated untracked `workspace/_*.txt` / `_*.json` artifacts are **not** part of B3.2 and are left unstaged.

---

## 3. Module layout

```text
src/ai_dev_os/memory/
  … B3.1 domain (unchanged contracts) …
  sqlite_schema.py       # DDL + REQUIRED_TABLES/INDEXES + enum CHECK helpers
  sqlite_migrations.py   # REGISTERED_MIGRATIONS, apply/verify, MemoryDatabaseInfo
  sqlite_connection.py   # path validation, open/configure, initialize/validate
  sqlite_repository.py   # create/read/update/list over MemoryRecord (+ evidence)
```

CLI: thin `memory-status` in `cli.py` — reports config/status only; does not open or create a DB when disabled.

---

## 4. Table DDL (migration `001` / compatibility `memory.1`)

### 4.1 `schema_migrations`

| Column | Type | Constraints |
| --- | --- | --- |
| `version` | TEXT | PK; non-empty (e.g. `001`) |
| `name` | TEXT | NOT NULL |
| `checksum` | TEXT | NOT NULL; 64 lowercase hex (SHA-256 of normalized SQL) |
| `applied_at` | TEXT | NOT NULL; UTC ISO via `utc_now_iso()` |
| `description` | TEXT | NOT NULL |

Insert-only on successful migrate. Never update/delete applied rows in normal operation. Checksum mismatch → `MemoryMigrationError` (fail closed).

### 4.2 `memory_records`

One row per durable memory item (candidate through forgotten / content-erased). Columns align with B2 §6.3 and B3.1 `MemoryRecord`:

- Identity / scope: `memory_id` (PK, `mem-{12 hex}`), `project_id`
- Class / lifecycle / category / sensitivity / evidence_strength / source_type
- Content: `title`, `content`, `content_normalized`, `content_hash` (64 hex)
- Provenance: `proposed_by`, `provider_id`, `task_id`, `plan_fingerprint`, `session_id`, `orchestration_id`
- Approval / rejection / supersession / forget / erase timestamps and actors
- `schema_version` CHECK-constrained to `MEMORY_SCHEMA_VERSION` (`memory.1`)
- CHECK: approved class requires approver + approved_at + approval_method; forgotten requires `forgotten_at`; rejected requires `rejection_reason`; content present OR `content_erased_at` set
- `UNIQUE (memory_id, project_id)` for composite FK targets

Evidence attached to a record is **not** denormalized into `memory_records`; it lives in `memory_evidence` (1:N). In-memory `MemoryRecord.evidence` is reconstructed on read.

### 4.3 `memory_evidence`

| Column | Notes |
| --- | --- |
| `evidence_id` | PK; `evid-{12 hex}` |
| `memory_id`, `project_id` | FK → `memory_records (memory_id, project_id)` |
| `evidence_type`, `evidence_ref`, `created_at` | B3.1 `MemoryEvidenceRef` (+ store `created_at`) |

`MemoryEvidenceRef.note` is **deferred** from the relational row in this phase (optional domain field; not required for hash integrity — fingerprints exclude `note`).

### 4.4 `memory_events`

Append-only audit/lifecycle events. Actions = B3.1 `MemoryAction` values **plus** deferred-store actions `retrieve` and `migrate` (B2 §10). Actor kinds: `human` \| `system` \| `service`.

### 4.5 `memory_links`

Explicit relationships (`LinkType`). Composite FKs to both endpoints within the same `project_id`. `UNIQUE (from_memory_id, to_memory_id, link_type)`.

### 4.6 Indexes

Project-scoped retrieval indexes per B2 §6.3–6.5 / §8 (lifecycle/class, category, approved_at, content_hash, task_id partial, evidence/events/links). Exact names live in `REQUIRED_INDEXES` in `sqlite_schema.py`.

### 4.7 Explicitly deferred schema

- FTS5 virtual tables / triggers
- Separate category tables
- Encryption-at-rest columns
- Global-memory scope tables
- Evidence `note` column (optional domain-only for now)

---

## 5. Migration / versioning

| Rule | Behavior |
| --- | --- |
| Registry | `REGISTERED_MIGRATIONS` tuple; currently only `001` / `initial_memory_schema` |
| Compatibility label | `MEMORY_SCHEMA_VERSION = "memory.1"` (independent of package `__version__`) |
| Apply | `apply_pending_migrations` — contiguous prefix only; each migration in one explicit transaction (DDL + `schema_migrations` insert) |
| Idempotent | Re-running when already current is a no-op verify + compatibility check |
| Checksum | SHA-256 of CRLF-normalized SQL + trailing newline; stored and re-verified |
| Fail closed | Unknown/future versions, name mismatch, checksum mismatch, tables without history, missing required tables/indexes, FK pragma off → `MemoryMigrationError` |
| Import / default path | Package import and default `MemoryConfig` **never** create a DB file |

`initialize_memory_database` / `validate_memory_database` require `config.enabled=True` when `require_enabled=True` (default).

---

## 6. Repository interface (over B3.1 models)

`SqliteMemoryRepository` (stdlib SQL only; no ORM):

| Method | Behavior |
| --- | --- |
| `create_record(record: MemoryRecord) -> MemoryRecord` | Validate via existing B3.1 helpers (`validate_memory_record_fields` / content hash); INSERT record + evidence rows in one transaction; return immutable model |
| `get_record(project_id, memory_id) -> MemoryRecord` | Project-scoped SELECT + evidence load; missing → `MemoryNotFoundError` |
| `update_record(record: MemoryRecord, *, expected_content_hash: str \| None = None) -> MemoryRecord` | Replace mutable fields; optional optimistic hash check → `MemoryConflictError` on mismatch; replace evidence set atomically |
| `list_records(project_id, *, lifecycle_status=None, memory_class=None, category=None, limit=..., offset=...) -> tuple[MemoryRecord, ...]` | Always filter `project_id`; deterministic order: `created_at ASC, memory_id ASC` (no wall-clock “now” ordering); limit/offset capped by config |

Additional helpers (same guard):

- `create_link` / `list_links` for `MemoryLink`
- Optional `append_event` for raw audit rows (service layer later owns policy)

**Hard guard:** constructing a repository or calling any mutating/read-store method when `config.enabled` is false raises `MemoryDisabledError` immediately. Reads are also refused while disabled so operators cannot accidentally treat an on-disk file as active memory without an explicit enable.

Normalization / hashing: repository **reuses** `normalize_memory_content`, `compute_content_hash`, `validate_content_hash`, `validate_sensitivity_for_persist` — it does not invent a second fingerprint path.

---

## 7. Disabled-by-default hard guard

| Surface | Default | Disabled behavior |
| --- | --- | --- |
| `MemoryConfig.enabled` | `False` | — |
| `DEFAULT_MEMORY_CONFIG` | disabled | — |
| `config.require_enabled()` | — | raises `MemoryDisabledError` |
| `initialize_memory_database` | — | raises `MemoryDisabledError` (no file created) |
| `SqliteMemoryRepository` ops | — | raises `MemoryDisabledError` |
| CLI `memory-status` | — | prints status `"disabled"`; exit 0; **does not** open/create DB |
| Providers / orch / CI | untouched | no imports that enable memory |

Silent no-ops and accidental enablement are forbidden. Enabling remains an **explicit** `MemoryConfig(enabled=True)` (or future operator config) — never inferred from DB file presence.

---

## 8. Determinism

- List/query order is stable (`created_at`, then `memory_id`) — not “most recently touched by wall clock at query time.”
- Migration SQL checksum uses newline-normalized text.
- Content hashes use existing canonical JSON + SHA-256 helpers (`MEMORY_FINGERPRINT_VERSION`).
- CLI JSON (if any) uses `sort_keys=True`.
- Tests use fixed timestamps / hashes where order assertions matter.

---

## 9. Connection policy (B2)

| Setting | Value |
| --- | --- |
| Foreign keys | `PRAGMA foreign_keys = ON` (required) |
| Busy timeout | `busy_timeout_ms` (default 5000) |
| Journal | WAL for file-backed; not required for `:memory:` |
| Synchronous | `NORMAL` when WAL |
| Path safety | Absolute or root-relative; containment via `is_path_under`; reject URI modes; default path `workspace/memory/memory.sqlite3` |
| Backend | `MemoryConfig.backend == "sqlite"` only |

---

## 10. CLI (read-only status)

```text
ai-dev-os memory-status
```

Emits deterministic JSON roughly:

```json
{
  "enabled": false,
  "status": "disabled",
  "backend": "sqlite",
  "db_path": "workspace/memory/memory.sqlite3",
  "schema_version": "memory.1"
}
```

No migrate, no write, no enable. When disabled, does not touch the filesystem for the DB.

---

## 11. Testing strategy

| Area | Assertions |
| --- | --- |
| Migrations | Clean DB applies `001`; second apply idempotent; checksum/unknown/ambiguous fail closed |
| Schema | CHECK / FK constraints; required indexes; enum parity with B3.1 |
| Connection | Path refuse; disabled init refuse; WAL/FK pragmas when enabled |
| Repository | create/read/update round-trip preserves hash/version; list order deterministic; disabled guard typed refuse |
| Package | `__version__` bump one patch; all test version pins updated |
| Regression | Full pytest + `ai-dev-os ci-check` e2e |

---

## 12. Deferred (explicit)

| Item | Why deferred |
| --- | --- |
| Service layer (`propose`/`approve`/`retrieve` orchestration) | B3.4+ |
| Runtime enablement UX / config file wiring | Keep disabled default; avoid auto-activate |
| FTS5 / embeddings / semantic rank | B2 A5 |
| Evidence `note` column | Optional domain field; not in fingerprint |
| Global memory / cross-project | B1/B2 deferred |
| Encryption at rest | Productization later |
| Multi-writer / connection pool | Single-process prototype |
| Round 4D2 live model | Locked |
| Equitify | Untouched |
| STAGE_ORDER / `4a.1` schema | Unchanged |

---

## 13. Acceptance checklist

- [x] Design documented before completing persistence surface
- [x] Stdlib `sqlite3` only; no new runtime dependency
- [x] Migrations idempotent + checksum verified
- [x] Repository CRUD over immutable B3.1 models
- [x] Disabled-by-default; typed refuse on write/enable
- [x] At most read-only `memory-status` → `"disabled"`
- [x] No provider/orch/CI auto-wiring
- [x] Focused + full suite green; one dedicated commit; **not pushed**

---

## Document control

| | |
| --- | --- |
| Phase | B3.2 |
| Package after ship | **0.8.9** (one patch from 0.8.8) |
| Must not change | Equitify, 4D2 unlock, STAGE_ORDER, `4a.1` schema, live/paid APIs |
