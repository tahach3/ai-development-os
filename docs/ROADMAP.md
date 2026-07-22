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

## Round 3C (this release)

Bounded orchestration with deterministic stalemate detection:

- Explicit orchestration state machine + durable records/events/round evidence (`3c.1`)
- Binding/staleness fail-closed checks before every step
- Simulated impl → Round 3A targeted tests → independent simulated review → bounded repair
- Deterministic progress/stalemate (consecutive identical evidence, no-change repair, A-B-A oscillation, repeated malformed)
- CLI: create/validate/preview/step/run/resume/show/history/stalemate/cancel
- Design: `docs/ROUND_3C_BOUNDED_ORCHESTRATION_DESIGN.md`
- Package `0.5.0`

## Round 3D+ / later (only with explicit approval)

- Separately authorized **live** local CLI smoke for one provider (only with proven noninteractive path)
- Broader command profiles beyond pytest
- Equitify connection after the exact user command
- Any automation beyond manual handoff + local allowlisted exec + gated providers + simulated orchestration

## Explicitly deferred

- LangChain / CrewAI / AutoGen
- Paid API adapters
- Browser automation
- Auto-merge / auto-push
- General provider-generated patch application engines
- Self-modifying routing / safety rules
- Copying third-party orchestrator code into this repo
- LLM-based stalemate judges
