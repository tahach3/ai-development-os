# Architecture (Round 3C)

## Purpose

AI Development OS is a **local control plane** for structured software tasks. It does not call paid model APIs by default. It validates tasks, routes them deterministically, builds minimal context packets, manages **plan approval gates**, writes **manual handoff** files, runs **allowlisted local pytest** in isolated worktrees (Round 3A), exposes **controlled provider CLI adapters** (Round 3B), and (Round 3C) runs a **bounded orchestration** loop (implementation → test → review → repair) over the **simulated** provider with deterministic stalemate detection.

## Inspired by (patterns only — no copied code)

See `docs/OPEN_SOURCE_REFERENCE_ASSESSMENT.md`.

| Pattern | Inspiration | Status |
| --- | --- | --- |
| Approved-spec / plan gate before implementation | CC-SDD | Implemented independently |
| Lifecycle FSM + audit fields | Liza | Implemented independently |
| Max repair rounds → blocked | Ralphex | Implemented independently |
| Worktrees / sessions | Agent Orchestrator | Round 3A |
| Provider CLI adapters | MCO | Round 3B (live not authorized) |
| Bounded impl/test/review/repair loop + stalemate | Agent Orchestrator / Ralphex concepts | **Round 3C** (simulated) |
| Allowlisted local pytest exec | — | Round 3A |

## Layers

1. **Config** — routing, risk, budgets, repair limits, projects, providers, **`orchestration.yaml`**.
2. **Schemas** — task/plan/report + execution `3a.1` + provider `3b.1` + orchestration `3c.1`.
3. **Domain** — models, validation, fingerprints, orchestration models/state machine.
4. **Services** — registry, routing, context, git inspect, stores, approval, sessions/worktrees/safe_exec, provider discovery/policy/runner/audit, **orchestration engine/store/stalemate**.
5. **Adapters** — manual handoff (`adapters/`) **and** provider CLI lane (`providers/`).
6. **CLI** — operator interface including orchestration commands.
7. **Demo** — `demo_projects/calculator-demo` only (not Equitify).

## Data flow

```
register-project → create-task → … → approve-plan
  ↘ prepare-handoff (manual)
  ↘ create-session → run-tests (allowlisted pytest)
  ↘ create-orchestration → step / run-until-boundary (simulated)
       → impl (simulated) → harness mutation (fixture-controlled)
       → targeted tests → fresh review context → simulated review
       → complete | repair (bounded) | stalemate/human_review | blocked | cancelled
```

## Compatibility

- Package version `0.5.0`
- Round 3A execution envelopes remain schema `3a.1`
- Provider results remain schema `3b.1`
- Orchestration artifacts use schema `3c.1` (do not rewrite older artifacts)

## Non-goals (still)

- Network I/O / paid LLM APIs from the product by default
- Auto-execution of model-generated shell or patches
- Dashboards / browser automation / cloud workers
- Equitify connection
- Live multi-agent claims (simulation only for Round 3C validation)
- Self-improving rule rewrites
- Auto-merge / auto-push / auto-deploy
