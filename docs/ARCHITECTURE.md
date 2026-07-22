# Architecture (Round 4D1.2)

## Purpose

AI Development OS is a **local control plane** for structured software tasks. It does not call paid model APIs by default. It validates tasks, routes them deterministically, builds minimal context packets, manages **plan approval gates**, writes **manual handoff** files, runs **allowlisted local pytest** in isolated worktrees (Round 3A), exposes **controlled provider CLI adapters** (Round 3B), runs **bounded simulated orchestration** (Round 3C), provides **local CI quality gates** plus **pull-request / change validation** (Round 4A), has **validated private remote GitHub Actions** on `tahach3/ai-development-os` (Round 4B), produces **evidence-first audience-specific reports** (Round 4C), performs **safe provider readiness auditing** (Round 4D1 — discovery/version/help/auth-status only; **zero live prompts**), **resolves trusted CLI ambiguity** (Round 4D1.1 — wrapper identity, logical installations, host-local pins, operator selection), and **assesses authentication + noninteractive contracts** (Round 4D1.2 — allowlisted auth-status + synthetic/help/adapter contract proof; **still zero live prompts**).

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
| Private remote CI validation | — | **Round 4B** (run `29930178622`) |
| Evidence-first multi-audience reporting | — | **Round 4C** |
| Safe provider readiness / eligibility audit | — | **Round 4D1** |
| Trusted CLI ambiguity resolution / pinning | — | **Round 4D1.1** |
| Auth-status + noninteractive contract readiness | — | **Round 4D1.2** |
| Allowlisted local pytest exec | — | Round 3A |

## Layers

1. **Config** — routing, risk, budgets, repair limits, projects, providers, orchestration, **`ci_policy.yaml`**.
2. **Schemas** — task/plan/report + execution `3a.1` + provider `3b.1` + orchestration `3c.1` + CI/PR `4a.1` + reporting `4c.1` + provider readiness `4d1.1` + ambiguity/pin `4d1.1.1`.
3. **Domain** — models, validation, fingerprints, orchestration models, CI models, reporting models, **provider readiness / ambiguity models**, **shared-memory domain foundations (B3.1; disabled)**.
4. **Services** — registry, routing, context, git inspect, stores, approval, sessions/worktrees/safe_exec, provider lane, orchestration engine, CI engine, canonical report builder/renderer/validator, **provider readiness engine + ambiguity resolver** (no memory service yet).
5. **Adapters** — manual handoff (`adapters/`) **and** provider CLI lane (`providers/`) **and** legacy report importers.
6. **CLI** — operator interface including `ci-check`, `validate-change`, `build-report`, `render-report`, `validate-report`, `show-report`, `provider-readiness` (incl. ambiguity flags).
7. **CI definition + remote parity** — `.github/workflows/ci.yml` with `permissions: contents: read` only; Round 4B validated private remote execution (no secrets, no live providers, no deploy/merge).
8. **Demo** — `demo_projects/calculator-demo` only (not Equitify).

## Data flow

```
register-project → create-task → … → approve-plan
  ↘ prepare-handoff (manual)
  ↘ create-session → run-tests (allowlisted pytest)
  ↘ create-orchestration → step / run-until-boundary (simulated)
  ↘ ci-check → fixed stages → normalized CIRun
  ↘ validate-change → diff inspect → PRValidationSummary (no auto-merge)
  ↘ build-report → canonical snapshot → render-report (audience/detail)
```

## Compatibility

- Package version `0.8.2`
- Round 3A execution envelopes remain schema `3a.1`
- Provider results remain schema `3b.1`
- Orchestration artifacts remain schema `3c.1`
- CI / PR validation artifacts use schema `4a.1`
- Reporting evidence / canonical report use schema `4c.1`

## Future platform direction

The current implemented architecture is **Round 4A/4B CI + Round 4C reporting + Round 4D1 readiness + Round 4D1.1 ambiguity resolution + Round 4D1.2 auth/noninteractive readiness** (package **0.8.2**). [`docs/AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md`](AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md) defines longer-term platform direction; blueprint features are not implemented unless explicitly recorded in later rounds. Live provider smoke requires separate Round 4D2 authorization.

Phase B1 shared-memory design: [`SHARED_MEMORY_DESIGN.md`](SHARED_MEMORY_DESIGN.md). Phase B2 implementation decisions: [`SHARED_MEMORY_IMPLEMENTATION_PLAN.md`](SHARED_MEMORY_IMPLEMENTATION_PLAN.md). **Phase B3.1** adds pure domain foundations under `src/ai_dev_os/memory/` (enums, immutable models, validation, normalization, fingerprints, auth/transitions, disabled-by-default config). No SQLite, repositories, CLI, providers, or runtime memory enablement.

## Non-goals (still)


- Network I/O / paid LLM APIs from the product by default
- Auto-execution of model-generated shell or patches
- Dashboards / browser automation / cloud workers
- Equitify connection
- Live multi-agent claims (simulation only for Round 3C validation)
- Self-improving rule rewrites
- Auto-merge / auto-push / auto-deploy
- Vulnerability database scanning (deferred; dependency-policy only)
- Broadening workflow permissions or adding repository secrets / live provider CI steps
