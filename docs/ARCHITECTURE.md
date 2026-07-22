# Architecture (Round 4A)

## Purpose

AI Development OS is a **local control plane** for structured software tasks. It does not call paid model APIs by default. It validates tasks, routes them deterministically, builds minimal context packets, manages **plan approval gates**, writes **manual handoff** files, runs **allowlisted local pytest** in isolated worktrees (Round 3A), exposes **controlled provider CLI adapters** (Round 3B), runs **bounded simulated orchestration** (Round 3C), and (Round 4A) provides **local CI quality gates** plus **pull-request / change validation** with a GitHub Actions workflow **definition** (not executed in this round).

## Inspired by (patterns only — no copied code)

See `docs/OPEN_SOURCE_REFERENCE_ASSESSMENT.md`.

| Pattern | Inspiration | Status |
| --- | --- | --- |
| Approved-spec / plan gate before implementation | CC-SDD | Implemented independently |
| Lifecycle FSM + audit fields | Liza | Implemented independently |
| Max repair rounds → blocked | Ralphex | Implemented independently |
| Worktrees / sessions | Agent Orchestrator | Round 3A |
| Provider CLI adapters | MCO | Round 3B (live not authorized) |
| Bounded impl/test/review/repair loop + stalemate | Agent Orchestrator / Ralphex concepts | Round 3C (simulated) |
| Local CI / PR validation gates | — | **Round 4A** |
| Allowlisted local pytest exec | — | Round 3A |

## Layers

1. **Config** — routing, risk, budgets, repair limits, projects, providers, orchestration, **`ci_policy.yaml`**.
2. **Schemas** — task/plan/report + execution `3a.1` + provider `3b.1` + orchestration `3c.1` + CI/PR `4a.1`.
3. **Domain** — models, validation, fingerprints, orchestration models, **CI models**.
4. **Services** — registry, routing, context, git inspect, stores, approval, sessions/worktrees/safe_exec, provider lane, orchestration engine, **CI engine / validate-change / dependency-policy / secret scan**.
5. **Adapters** — manual handoff (`adapters/`) **and** provider CLI lane (`providers/`).
6. **CLI** — operator interface including `ci-check` and `validate-change`.
7. **CI definition** — `.github/workflows/ci.yml` (contents: read; not pushed/executed in Round 4A).
8. **Demo** — `demo_projects/calculator-demo` only (not Equitify).

## Data flow

```
register-project → create-task → … → approve-plan
  ↘ prepare-handoff (manual)
  ↘ create-session → run-tests (allowlisted pytest)
  ↘ create-orchestration → step / run-until-boundary (simulated)
  ↘ ci-check → fixed stages → normalized CIRun
  ↘ validate-change → diff inspect → PRValidationSummary (no auto-merge)
```

## Compatibility

- Package version `0.6.0`
- Round 3A execution envelopes remain schema `3a.1`
- Provider results remain schema `3b.1`
- Orchestration artifacts remain schema `3c.1`
- CI / PR validation artifacts use schema `4a.1`

## Non-goals (still)

- Network I/O / paid LLM APIs from the product by default
- Auto-execution of model-generated shell or patches
- Dashboards / browser automation / cloud workers
- Equitify connection
- Live multi-agent claims (simulation only for Round 3C validation)
- Self-improving rule rewrites
- Auto-merge / auto-push / auto-deploy
- Vulnerability database scanning (deferred; dependency-policy only)
- Executing or pushing the GitHub workflow during Round 4A
