# Architecture (Round 2)

## Purpose

AI Development OS is a **local control plane** for structured software tasks. It does not call model APIs. It validates tasks, routes them deterministically, builds minimal context packets, manages **plan approval gates**, and writes **manual handoff** files for Claude, Cursor, or Codex.

## Inspired by (patterns only — no copied code)

See `docs/OPEN_SOURCE_REFERENCE_ASSESSMENT.md`.

| Pattern | Inspiration | Round 2 status |
| --- | --- | --- |
| Approved-spec / plan gate before implementation | CC-SDD | Implemented independently |
| Lifecycle FSM + audit fields (`approved_by`, starting commit, blocked/rejected/superseded) | Liza | Implemented independently |
| Max repair rounds → blocked / human review | Ralphex | Implemented independently |
| Worktrees / sessions | Agent Orchestrator | Deferred to Round 3 |
| Real provider CLI adapters | MCO | Deferred to Round 3 |

These notes document conceptual inspiration only. **No compatibility is claimed** unless a feature is implemented and tested here.

## Layers

1. **Config** (`config/`) — routing rules, risk levels, token budgets, repair-round limits, project registry.
2. **Schemas** (`schemas/`) — JSON schemas documenting task/plan/report contracts.
3. **Domain** (`models.py`, `validation.py`, `fingerprints.py`) — dataclasses, enums, lifecycle FSM, content hashes.
4. **Services** — registry, routing, context, git inspect, task/plan/report/repair stores, approval, gates, handoffs, behavioral metrics.
5. **Adapters / handoffs** — Claude/Cursor/Codex packets with `automation_status: manual_handoff_required`.
6. **CLI** — operator interface for the above.
7. **Demo** — `demo_projects/calculator-demo` synthetic lifecycle target (not Equitify).

## Data flow (Round 2)

```
register-project → create-task → set-task-status(ready_for_planning) → route-task
  → create-plan → validate-plan → submit-plan → approve-plan
  → build-context / prepare-handoff (cursor, approved plan only)
  → record-report (implementation) → prepare-handoff (codex review)
  → record-report (review) → complete → behavioral-report
```

## Non-goals (still)

- Network I/O / paid LLM APIs from the product
- Auto-execution of model output
- Dashboards / browser automation / cloud workers
- Equitify connection
- Worktrees (Round 3)
- Real agent CLI adapters (Round 3)
- Self-improving rule rewrites
