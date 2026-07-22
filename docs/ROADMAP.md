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

## Round 4A (this release)

Local CI, quality gates, and pull-request validation foundation:

- Deterministic `ci-check` stage pipeline (`4a.1`)
- Normalized CI run / stage / PR validation schemas
- `validate-change` without executing change code
- Dependency-policy (not vulnerability DB scanning)
- Secret-pattern + runtime artifact controls
- Minimal GitHub Actions workflow **definition** (not pushed/executed)
- Sanitized behavioral CI aggregates; recommendations inactive until human approval
- Design: `docs/ROUND_4A_LOCAL_CI_DESIGN.md`
- Package `0.6.0`

## Round 4B+ / later (only with explicit approval)

- Execute/push GitHub workflow on a remote; verify action SHA pins
- Vulnerability database scanning (OSV/NVD/etc.) when explicitly approved
- Required status-check enforcement
- Separately authorized **live** local CLI smoke for one provider
- Broader command profiles beyond pytest
- Equitify connection after the exact user command
- Any automation beyond manual handoff + local allowlisted exec + gated providers + simulated orchestration + local CI

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
