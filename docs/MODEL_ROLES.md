# Model Roles

Round 1 uses three **logical roles**. Adapters produce manual handoff packets only.

## Claude

- Large multi-system builds
- Deep investigation
- Long autonomous planning
- Preferred for `complex` / `high_risk` complexity and `high` / `critical` risk

## Cursor

- Daily editing, navigation, targeted fixes, UI, diff review, verification
- Default for `small` / `normal` work and UI / small_fix / verification task types

## Codex

- Second-opinion / independent review
- Preferred for `review` and `independent_review` task types

## Routing

Deterministic rules live in `config/default_routing.yaml`. Every route includes a written `routing_explanation` stored on the task.
