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
- Schema/policy **`4d1.1`**; package **`0.8.0`**
- Live mode remains disabled; Round 4D2 requires separate authorization

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

**Phase B1 (design only):** [`SHARED_MEMORY_DESIGN.md`](SHARED_MEMORY_DESIGN.md) — controlled shared-memory design for a future SQLite prototype. No memory implementation exists yet; Round 4D1 / package **0.8.0** is the implemented baseline (memory still deferred).

**Phase B2 (implementation decisions only):** [`SHARED_MEMORY_IMPLEMENTATION_PLAN.md`](SHARED_MEMORY_IMPLEMENTATION_PLAN.md) — SQLite schema/policy/adapter plan for a future prototype. No memory runtime exists yet; Round 4D1 / package **0.8.0** remains the implemented baseline for CI + reporting + readiness.

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
