# AI Development Operating System

Local-first orchestration layer for multi-model software work (Claude / Cursor / Codex) with **manual handoff**, Round 3A **safe local pytest**, Round 3B **controlled provider adapters**, and Round 3C **bounded implementation → test → review → repair orchestration** with deterministic stalemate detection — validated through the **simulated** provider only (**no live model calls**).

## Round 3C scope

Adds a resumable orchestration engine that coordinates approved task/plan → simulated implementation → targeted tests → independent simulated review → bounded repair → completion, block, cancel, or human escalation. Stalemate detection is **deterministic** (structured evidence), not LLM-based.

**Honest status:**

| Claim | Round 3C |
| --- | --- |
| Bounded orchestration state machine | Yes |
| Simulated full-loop validation | Yes |
| Deterministic stalemate / repair limits | Yes |
| Live multi-agent automation | **No** |
| Provider text executed as code/commands | **No** |
| Live provider smoke | Still `blocked_before_execution` (zero live calls) |

**Still not included:** paid LLM APIs, LangChain/CrewAI/AutoGen, dashboards, browser automation, Equitify integration, auto-merge/push, arbitrary patch engines, credential inspection.

## Install (dev)

```bash
cd C:\Users\Taha\ai-development-os
python -m pip install -e ".[dev]"
```

## Quick start

```bash
ai-dev-os init
ai-dev-os register-project --id calculator-demo --name "Calculator Demo" --root demo_projects/calculator-demo
# … Round 2 plan approval + Round 3A session as needed …

# Round 3C (simulated default):
ai-dev-os create-orchestration --task-id … --plan-id … --session-id … --scenario direct_success
ai-dev-os validate-orchestration --orchestration-id …
ai-dev-os preview-orchestration --orchestration-id …
ai-dev-os run-orchestration --orchestration-id …
ai-dev-os show-orchestration --orchestration-id …
ai-dev-os show-stalemate-evidence --orchestration-id …
```

## Safe execution (Round 3A)

Isolated sessions / worktrees / allowlisted `python -m pytest` remain available (`create-session`, `run-tests`, …).

## Provider adapters (Round 3B)

- Default config is **fail-closed** (`disabled`).
- Modes: `disabled` | `discovery_only` | `simulated` | `manual_handoff` | `live_local_cli_allowed`.
- Live requires every gate in `docs/ROUND_3B_PROVIDER_ADAPTER_DESIGN.md` and is **not** exercised in validation.

## Bounded orchestration (Round 3C)

- Config: `config/orchestration.yaml` (schema `3c.1`, simulated-only, fail-closed).
- Design: `docs/ROUND_3C_BOUNDED_ORCHESTRATION_DESIGN.md`.
- Worktree mutations in synthetic demos are **harness/fixture-controlled** — provider text is never executed.
- Loops stop on repair limit, step limit, stalemate → `human_review_required` / `blocked`.

## Docs

See `docs/` for architecture, Round 3A/3B/3C designs, security, model roles, zero-click limits, roadmap, and project chronicle.
