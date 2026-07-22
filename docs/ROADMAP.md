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

## Round 3B (this release)

Controlled provider CLI adapters:

- Provider-neutral contracts + result schema `3b.1`
- Safe discovery (no install, no auth inspection)
- Fail-closed config modes including simulated / live_gated
- Deterministic simulated provider + fixtures
- CLI shells for Claude Code / Codex / Cursor (live not authorized)
- Operator CLI for list/capabilities/discover/config/validate/preview/simulate/status/result/cancel
- Design: `docs/ROUND_3B_PROVIDER_ADAPTER_DESIGN.md`

## Round 3B+ / later (only with explicit approval)

- Separately authorized **live** local CLI smoke for one provider (2026-07-22 attempt: **blocked_before_execution** — no installed provider with proven noninteractive live path; Cursor PATH detection alone is insufficient; live still gated)
- Broader command profiles beyond pytest
- Equitify connection after the exact user command
- Any automation beyond manual handoff + local allowlisted exec + gated providers

## Explicitly deferred

- LangChain / CrewAI / AutoGen
- Paid API adapters
- Browser automation
- Auto-merge / auto-push
- Self-modifying routing / safety rules
- Copying third-party orchestrator code into this repo
