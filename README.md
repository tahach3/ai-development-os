# AI Development Operating System

Local-first orchestration layer for multi-model software work (Claude / Cursor / Codex) with **manual handoff**, Round 3A **safe local pytest**, Round 3B **controlled provider adapters**, Round 3C **bounded simulated orchestration**, and Round 4A **local CI / quality gates / PR validation** (GitHub workflow **defined**, not executed in this round).

## Round 4A scope

Adds a deterministic local CI pipeline (`ai-dev-os ci-check`), change-range validation (`ai-dev-os validate-change`), dependency-policy checks (not vulnerability DB scanning), secret/artifact gates, normalized CI/PR schemas (`4a.1`), sanitized behavioral CI aggregates, and a minimal private-repo GitHub Actions workflow definition.

**Honest status:**

| Claim | Round 4A |
| --- | --- |
| Local CI quality gates | Yes |
| PR/change validation without executing change code | Yes |
| GitHub Actions workflow **file** | Yes (definition only) |
| Workflow pushed/executed on GitHub | **No** |
| Vulnerability database queried | **No** |
| Live provider / auto review / merge / push / deploy | **No** |
| Equitify connected | **No** |

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

# Round 4A:
ai-dev-os ci-check
ai-dev-os validate-change --base HEAD~1
```

## Prior rounds (complete)

- Round 3A: sessions / worktrees / allowlisted pytest
- Round 3B: provider adapters (live gated; smoke `blocked_before_execution`)
- Round 3C: bounded simulated orchestration + stalemate detection

## Docs

See `docs/` for architecture, Round 3A/3B/3C/4A designs, security, model roles, zero-click limits, roadmap, and project chronicle. Package version **0.6.0**.

- [`docs/AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md`](docs/AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md) — master architectural direction for future AI OS integration, shared memory, provider routing, plugins, and open-source component decisions (not yet implemented).
- [`docs/SHARED_MEMORY_DESIGN.md`](docs/SHARED_MEMORY_DESIGN.md) — Phase B1 controlled shared-memory **design only**; no memory implementation yet. Round 4A package **0.6.0** remains the implemented baseline.
- [`docs/SHARED_MEMORY_IMPLEMENTATION_PLAN.md`](docs/SHARED_MEMORY_IMPLEMENTATION_PLAN.md) — Phase B2 **implementation decisions only** (SQLite schema/policy plan); no memory runtime yet. Round 4A package **0.6.0** remains the implemented baseline.
