# Architecture (Round 3A)

## Purpose

AI Development OS is a **local control plane** for structured software tasks. It does not call model APIs. It validates tasks, routes them deterministically, builds minimal context packets, manages **plan approval gates**, writes **manual handoff** files for Claude, Cursor, or Codex, and (Round 3A) runs **allowlisted local pytest** inside isolated Git worktrees.

## Inspired by (patterns only — no copied code)

See `docs/OPEN_SOURCE_REFERENCE_ASSESSMENT.md`.

| Pattern | Inspiration | Status |
| --- | --- | --- |
| Approved-spec / plan gate before implementation | CC-SDD | Implemented independently |
| Lifecycle FSM + audit fields (`approved_by`, starting commit, blocked/rejected/superseded) | Liza | Implemented independently |
| Max repair rounds → blocked / human review | Ralphex | Implemented independently |
| Worktrees / sessions | Agent Orchestrator | **Round 3A:** isolated sessions + confined worktrees (safe slice) |
| Real provider CLI adapters | MCO | Deferred to Round 3B |
| Allowlisted local pytest exec | — | **Round 3A** |

These notes document conceptual inspiration only. **No compatibility is claimed** unless a feature is implemented and tested here.

## Layers

1. **Config** (`config/`) — routing rules, risk levels, token budgets, repair-round limits, project registry.
2. **Schemas** (`schemas/`) — JSON schemas documenting task/plan/report contracts.
3. **Domain** (`models.py`, `validation.py`, `fingerprints.py`) — dataclasses, enums, lifecycle FSM, content hashes.
4. **Services** — registry, routing, context, git inspect, task/plan/report/repair stores, approval, gates, handoffs, behavioral metrics, **sessions / worktrees / safe_exec / execution audit**.
5. **Adapters / handoffs** — Claude/Cursor/Codex packets with `automation_status: manual_handoff_required`.
6. **CLI** — operator interface for the above.
7. **Demo** — `demo_projects/calculator-demo` synthetic lifecycle + Round 3A session target (not Equitify).

## Data flow (Round 2 + 3A session lane)

```
register-project → create-task → … → approve-plan → prepare-handoff (manual)
                 ↘ create-session → run-tests (allowlisted pytest) → cleanup-session
```

## Non-goals (still)

- Network I/O / paid LLM APIs from the product
- Auto-execution of model-generated shell
- Dashboards / browser automation / cloud workers
- Equitify connection
- Spawning Claude / Cursor / Codex CLIs (Round 3B)
- Self-improving rule rewrites
- Auto-merge / auto-push
