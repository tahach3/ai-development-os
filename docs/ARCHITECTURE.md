# Architecture (Round 3B)

## Purpose

AI Development OS is a **local control plane** for structured software tasks. It does not call paid model APIs by default. It validates tasks, routes them deterministically, builds minimal context packets, manages **plan approval gates**, writes **manual handoff** files, runs **allowlisted local pytest** in isolated worktrees (Round 3A), and (Round 3B) exposes **controlled provider CLI adapters** for discovery, simulation, and gated future live local CLI use.

## Inspired by (patterns only — no copied code)

See `docs/OPEN_SOURCE_REFERENCE_ASSESSMENT.md`.

| Pattern | Inspiration | Status |
| --- | --- | --- |
| Approved-spec / plan gate before implementation | CC-SDD | Implemented independently |
| Lifecycle FSM + audit fields | Liza | Implemented independently |
| Max repair rounds → blocked | Ralphex | Implemented independently |
| Worktrees / sessions | Agent Orchestrator | Round 3A |
| Provider CLI adapters | MCO | **Round 3B:** contracts + discovery + simulated + shells (live not authorized) |
| Allowlisted local pytest exec | — | Round 3A |

## Layers

1. **Config** — routing, risk, budgets, repair limits, projects, **`providers.yaml` (fail-closed)**.
2. **Schemas** — task/plan/report + execution `3a.1` + provider result `3b.1`.
3. **Domain** — models, validation, fingerprints.
4. **Services** — registry, routing, context, git inspect, stores, approval, sessions/worktrees/safe_exec, **provider discovery/policy/runner/audit**.
5. **Adapters** — manual handoff (`adapters/`) **and** provider CLI lane (`providers/`).
6. **CLI** — operator interface.
7. **Demo** — `demo_projects/calculator-demo` only (not Equitify).

## Data flow

```
register-project → create-task → … → approve-plan → prepare-handoff (manual)
                 ↘ create-session → run-tests (allowlisted pytest)
                 ↘ build provider request → validate/preview → run-simulated-provider
                                            (live CLI gated; not authorized in 3B validation)
```

## Compatibility

- Package version `0.4.0`
- Round 3A execution envelopes remain schema `3a.1`
- Provider results use schema `3b.1` (do not overwrite 3a schemas)

## Non-goals (still)

- Network I/O / paid LLM APIs from the product by default
- Auto-execution of model-generated shell
- Dashboards / browser automation / cloud workers
- Equitify connection
- Authorized live Claude/Codex/Cursor model smoke (separate approval)
- Self-improving rule rewrites
- Auto-merge / auto-push
