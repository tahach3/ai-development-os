# Architecture (Round 1)

## Purpose

AI Development OS is a **local control plane** for structured software tasks. It does not call model APIs. It validates tasks, routes them deterministically, builds minimal context packets, and writes **manual handoff** files for Claude, Cursor, or Codex.

## Layers

1. **Config** (`config/`) — routing rules, risk levels, token budgets, project registry example.
2. **Schemas** (`schemas/`) — JSON schemas documenting task/plan/report contracts.
3. **Domain** (`src/ai_dev_os/models.py`, `validation.py`) — dataclasses, enums, lifecycle FSM.
4. **Services** — registry, routing, context builder, git inspect, task/report stores, behavioral metrics.
5. **Adapters** — Claude/Cursor/Codex placeholders that only write handoff files.
6. **CLI** — operator interface for the above.

## Data flow

```
register-project → create-task → validate-task → route-task
        → build-context / prepare-handoff (manual)
        → record-report → review-status / behavioral-report
```

## Lifecycle FSM

`draft → ready_for_planning → planned → approved_for_implementation → implementing → validating → ready_for_review → review_failed|review_passed → ready_to_commit → completed`

Also: `blocked`, `cancelled`. Illegal jumps (e.g. `draft → completed`) are rejected.

## Determinism

Routing and budget band selection are pure functions of task fields + YAML config. Token usage is recorded as `measured|estimated|unavailable` and is **never fabricated**.

## Non-goals (Round 1)

- Network I/O from the product
- Auto-execution of model output
- Dashboards / browser automation
- Equitify connection
- Self-improving rule rewrites
