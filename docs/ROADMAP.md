# Roadmap

## Round 1

Foundation: registry, tasks, lifecycle, routing, budgets, context, git inspect, manual adapters, reports, behavioral metrics, CLI, docs, tests.

## Round 2

- Plan artifacts + approval gates
- Fingerprints and approval invalidation
- Role-specific handoff packets, review verdicts, repair rounds
- Synthetic `calculator-demo` lifecycle
- Open-source reference assessment (patterns only)

## Round 3A

Safe execution foundation: sessions, worktrees, allowlisted pytest, envelopes, audits.

## Round 3B

Controlled provider CLI adapters (contracts, discovery, simulated provider, gated live shells — live not authorized in validation). Live smoke attempt 2026-07-22: **blocked_before_execution**, zero live calls.

## Round 3C

Bounded orchestration with deterministic stalemate detection (simulated-only). Package `0.5.0`. **Complete.**

## Round 4A (complete)

Local CI, quality gates, and pull-request validation foundation:

- Deterministic `ci-check` stage pipeline (`4a.1`)
- Normalized CI run / stage / PR validation schemas
- `validate-change` without executing change code
- Dependency-policy (not vulnerability DB scanning)
- Secret-pattern + runtime artifact controls
- Minimal GitHub Actions workflow **definition** (not pushed/executed in 4A)
- Sanitized behavioral CI aggregates; recommendations inactive until human approval
- Design: `docs/ROUND_4A_LOCAL_CI_DESIGN.md`
- Package `0.6.0`

## Round 4B (complete) — first private remote CI validation

- Private GitHub repository: `tahach3/ai-development-os`
- First successful remote CI evidence: Actions run `29930178622` (conclusion **success**) on head SHA `a01f6725d415977c982fd3c9ad524ef5656ddce3`
- Workflow permissions remain least-privilege (`contents: read` only)
- No repository secrets; no live provider/model steps; no deploy / auto-merge / auto-push
- Equitify remains disconnected
- Package remains **`0.6.0`** (no version bump)
- Documentation closeout records the validation; runtime CI engine unchanged from Round 4A

## Next development round (planned)

**Separately authorized live local CLI smoke (Round 4D2)** — requires explicit approval after Round 4D1 readiness evidence.

## Round 4C (complete) — evidence-first reporting

- Canonical evidence + claim-status model (`4c.1`)
- Audience/detail renderers (executive, operator, developer, independent_reviewer, auditor)
- Deterministic relevance engine and template executive summaries (no LLM)
- Report integrity fingerprints, redaction, legacy adapters
- CLI: `build-report`, `render-report`, `validate-report`, `show-report`
- Design: `docs/ROUND_4C_HIGH_QUALITY_REPORTING_DESIGN.md`
- Standard: `docs/REPORTING_STANDARD.md`
- Package **`0.7.0`** (superseded package baseline by Round 4D1)
- Round 4B remote CI remains complete; no live provider; no vuln DB; Equitify disconnected

## Round 4D1 (complete) — live-provider readiness hardening

- Safe multi-candidate executable discovery (no full PATH dump)
- Allowlisted version/help probes; auth-status only when explicitly safe
- Noninteractive / role / independence matrices (no live prompts)
- Readiness verdicts and Round 4C audience reports
- CLI: `provider-readiness`
- Design: `docs/ROUND_4D1_PROVIDER_READINESS_DESIGN.md`
- Standard: `docs/PROVIDER_READINESS_STANDARD.md`
- Schema/policy **`4d1.1`**; package **`0.8.0`** (superseded by 4D1.1 / `0.8.1`)
- Live mode remains disabled; Round 4D2 requires separate authorization

## Round 4D1.1 (complete) — trusted CLI ambiguity resolution

- Executable identity, wrapper/shim inspection (contents as data; never executed)
- Logical-installation normalization with automatic-collapse rule IDs only
- Operator decision records when distinct trusted binaries remain
- Host-local executable pins (`workspace/provider_pins/`) — fingerprint required; never enable live
- CLI: `--show-candidates`, `--explain-ambiguity`, `--show-logical-installations`, `--generate-selection-record`, `--validate-pin`
- Design: `docs/ROUND_4D1_1_CLI_AMBIGUITY_RESOLUTION_DESIGN.md`
- Ambiguity/pin/selection schemas **`4d1.1.1`**; package **`0.8.1`** (superseded by 4D1.2 / `0.8.2`)
- Live mode remains disabled; Round 4D2 requires separate authorization

## Round 4D1.2 (complete) — authentication and noninteractive readiness

- Allowlisted auth-status probes (profile or help-confirmed); never login/credential files
- Noninteractive contract dimensions from adapter/help/synthetic fixtures only
- Host/system verdict enum (`live_smoke_ready*` / auth / noninteractive / independence / not eligible)
- CLI: `--verify-noninteractive-contract`, `--show-host-system-verdict`
- Design: `docs/ROUND_4D1_2_AUTH_AND_NONINTERACTIVE_DESIGN.md`
- Standard: `docs/PROVIDER_AUTH_NONINTERACTIVE_STANDARD.md`
- Schema/policy **`4d1.2`**; package **`0.8.2`** (superseded by 4D1.3 / `0.8.3`)
- Live mode remains disabled; Round 4D2 requires separate authorization after a `live_smoke_ready*` host verdict

## Round 4D1.3 (complete) — trusted Codex headless-provider readiness

- Official OpenAI Codex CLI installed on the operator host (Method C: official `install.ps1` + hashed release package)
- ChatGPT authentication verified via allowlisted `codex login status` only (no credential-file reads; no API-key mode)
- Noninteractive contract from help + adapter docs + synthetic tests — **zero** `codex exec <prompt>`
- Codex JSONL normalization + env sanitization modules for future Round 4D2
- Open-source adoption roadmap persisted (`docs/OPEN_SOURCE_ADOPTION_ROADMAP.md` v1.0)
- Design: `docs/ROUND_4D1_3_CODEX_HEADLESS_PROVIDER_DESIGN.md`
- Schema/policy **`4d1.3`**; package **`0.8.3`**
- Host outcome: `live_smoke_ready_with_operator_auth` / `conditionally_eligible_for_bounded_live_smoke`
- Cursor remains editor-only on this host; Claude not installed; fresh-context ≠ independent review
- ACP / scanners **not** installed; Round 4D2 remains **LOCKED**

## Round 4E (complete) — multi-project boundary enforcement (local only)

- Design: `docs/ROUND_4E_BOUNDARY_ENFORCEMENT_DESIGN.md`
- Additive `project_boundaries` on CI policy (`4a.1` unchanged; **no** STAGE_ORDER change)
- Pure path + simple import-string boundary checker; `validate-change` + optional `ci-boundaries`
- Package **`0.8.5`**
- Round **4D2 remains LOCKED**; Equitify disconnected; no live model/network/paid-API calls

## Round 4F (complete) — CI ergonomics (local only)

- Design: `docs/ROUND_4F_CI_ERGONOMICS_DESIGN.md`
- Opt-in `--isolate-flaky` (honesty rule → `flaky_test_detected`); `--coverage` notes + optional `[cov]`
- PR-only `ci-targeted` fast signal; full pytest + `ci-check` authoritative; `contents: read`
- Package **`0.8.6`**
- Round **4D2 remains LOCKED**; Equitify disconnected

## Round 4A hardening (complete) — CI history/compare + cross-platform fix

- Additive layer on top of Round 4A/4E/4F; fixed `STAGE_ORDER` and CI schema **unchanged** (`4a.1`)
- Cross-platform fix: `sanitize_executable_location` now redacts Windows/UNC paths on POSIX (privacy + determinism); fixed the one flaky/failing test this exposed on Linux
- CI run history + regression comparison: `ci-history`, `ci-compare` (`--against-previous` exits non-zero only on a genuine new regression); reuses the existing `ci_run` schema (`4a.1`) plus a new `ci_run_comparison` schema
- Deterministic human-readable CI reports: `ci-check --format md` / `ci-targeted --format md`
- Reconciled with Round 4F's independently-built `ci-targeted` (kept as the single canonical implementation — already integrated with the `CIRun` envelope and flaky isolation); an earlier parallel selection module here was superseded and dropped rather than shipping two competing implementations
- No new runtime dependency; no workflow/permission/secret/live-model/Equitify change
- Design: `docs/ROUND_4A_LOCAL_CI_HARDENING_DESIGN.md`; package **`0.8.7`**

## Round 4G (complete) — ci-targeted selection quality (local only)

- Design: `docs/ROUND_4G_CI_TARGETED_SELECTION_DESIGN.md`
- Upgrade in place: import-string scanning under `tests/` for changed module dotted paths; broad-impact fail-safe for `__init__.py` / `cli.py` / `models.py` / `config/**` / `schemas/**` → note **broad impact, full suite recommended** (never silent empty-green)
- Keeps Round 4F flaky/coverage/`CIRun`/`--format md` behavior; `STAGE_ORDER` / `4a.1` unchanged; no second competing `ci-targeted` module
- Package **`0.8.8`**
- Round **4D2 remains LOCKED**; Equitify disconnected

## Round 4H (complete) — Markdown rendering parity (local only)

- Design: `docs/ROUND_4H_MD_RENDERING_PARITY_DESIGN.md`
- `ci-boundaries --format md` / `validate-change --format md` via `render_boundary_summary` / `render_validate_change_summary` in `ci_report.py`
- JSON remains default; exit codes and `to_dict()` shapes unchanged; `STAGE_ORDER` / `4a.1` unchanged
- Package **`0.8.10`**
- Round **4D2 remains LOCKED**; Equitify disconnected; memory untouched/disabled

**Phase B3.3 (memory service + first consumer):** [`PHASE_B3_3_MEMORY_SERVICE_DESIGN.md`](PHASE_B3_3_MEMORY_SERVICE_DESIGN.md) — lifecycle service over B3.2 SQLite, per-project `memory_enabled` opt-in, CLI verbs, optional `context_builder` retrieval. Package **`0.8.11`**. Global memory default remains disabled; orchestration/provider paths do not consume memory; 4D2 locked; Equitify untouched.

## Later (only with explicit approval)

- Pin GitHub Actions to immutable commit SHAs
- Vulnerability database scanning (OSV/NVD/etc.) when explicitly approved
- Required status-check enforcement
- Separately authorized **live** local CLI smoke for one provider (Round 4D2)
- Broader command profiles beyond pytest
- Equitify connection after the exact user command
- Any automation beyond manual handoff + local allowlisted exec + gated providers + simulated orchestration + local/remote CI gates + readiness auditing

## Longer-term vision (not implementation status)

Completed rounds above remain authoritative for **what is implemented**. Blueprint Phases A–I in [`docs/AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md`](AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md) define the longer-term vision beyond Round 4B. Each future implementation round requires separate approval and planning.

**Phase B1 (design only):** [`SHARED_MEMORY_DESIGN.md`](SHARED_MEMORY_DESIGN.md) — controlled shared-memory design for a future SQLite prototype.

**Phase B2 (implementation decisions only):** [`SHARED_MEMORY_IMPLEMENTATION_PLAN.md`](SHARED_MEMORY_IMPLEMENTATION_PLAN.md) — SQLite schema/policy/adapter plan for later B3.x checkpoints.

**Phase B3.1 (domain foundations only):** `src/ai_dev_os/memory/` — enums, immutable models, validation, normalization, hashing/fingerprints, typed errors, pure lifecycle/auth checks, disabled-by-default config. Package remains **0.8.1**. No SQLite, migrations, repositories, service orchestration, CLI, providers, or runtime enablement.

**Phase B3.2 (SQLite persistence, disabled by default):** [`SHARED_MEMORY_SQLITE_PERSISTENCE.md`](SHARED_MEMORY_SQLITE_PERSISTENCE.md) — stdlib `sqlite3` schema + idempotent migrations + repository CRUD over B3.1 models; hard refuse when disabled; read-only `memory-status` CLI. Package **`0.8.9`**. No service orchestration, no auto-enable, no FTS5/embeddings, no 4D2, Equitify untouched.

**Phase B3.3 (service + context consumer):** [`PHASE_B3_3_MEMORY_SERVICE_DESIGN.md`](PHASE_B3_3_MEMORY_SERVICE_DESIGN.md) — audited lifecycle service, per-project opt-in, CLI verbs, optional approved-memory section in context packets. Package **`0.8.11`**.

## Explicitly deferred

- LangChain / CrewAI / AutoGen
- Paid API adapters
- Browser automation
- Auto-merge / auto-push / auto-deploy
- General provider-generated patch application engines
- Self-modifying routing / safety rules
- Copying third-party orchestrator code into this repo
- LLM-based stalemate judges
- Claiming vulnerability scanning without a real vuln DB
