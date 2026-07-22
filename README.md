# AI Development Operating System

Local-first orchestration layer for multi-model software work (Claude / Cursor / Codex) with **manual handoff**, Round 3A **safe local pytest execution**, and Round 3B **controlled provider CLI adapters** (discovery / simulated / gated — **no live model calls by default**).

## Round 3B scope

Adds provider-neutral adapter contracts, safe CLI discovery (version/help only, no install), fail-closed provider config, a deterministic **simulated** provider with fixtures, CLI adapter shells for Claude Code / Codex / Cursor, normalized provider result envelopes, and operator CLI for list/discover/preview/simulate/status/cancel.

**Status distinctions (important):**

| Claim | Round 3B |
| --- | --- |
| Adapter implemented | Yes — `simulated`, `claude_code`, `codex`, `cursor` |
| CLI detected | Only if present on PATH / configured path (honest reporting) |
| Provider capability verified | Discovery/version only; noninteractive Cursor **not** assumed |
| Simulated execution verified | Yes — fixtures + policy/session/audit paths |
| Live execution authorized | **No** — separately authorized smoke only |

**Still not included:** paid LLM APIs, LangChain/CrewAI/AutoGen, dashboards, browser automation, Equitify integration, auto-merge/push, silent CLI installs, credential inspection.

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

ai-dev-os list-provider-adapters
ai-dev-os discover-providers
ai-dev-os show-provider-config
# Enable simulated provider in config (see config/providers.example.yaml) before:
# ai-dev-os run-simulated-provider --task-id … --plan-id … --session-id … --fixture success_impl
```

## Safe execution (Round 3A)

Isolated sessions / worktrees / allowlisted `python -m pytest` remain available (`create-session`, `run-tests`, …).

## Provider adapters (Round 3B)

- Default config is **fail-closed** (`disabled`).
- Modes: `disabled` | `discovery_only` | `simulated` | `manual_handoff` | `live_local_cli_allowed`.
- Live requires every gate in `docs/ROUND_3B_PROVIDER_ADAPTER_DESIGN.md` and is **not** exercised in this round’s validation.

## Docs

See `docs/` for architecture, Round 3A/3B designs, security, model roles, zero-click limits, roadmap, and project chronicle.
