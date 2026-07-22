# Model Roles

Logical roles remain **Claude**, **Cursor**, and **Codex**. Round 1–2 adapters produce manual handoff packets only.

## Claude

- Large multi-system builds, deep investigation, long autonomous planning
- Preferred for `complex` / `high_risk` complexity and `high` / `critical` risk
- Round 3B provider id: `claude_code` (adapter shell; live not authorized)

## Cursor

- Daily editing, navigation, targeted fixes, UI, diff review, verification
- Default for `small` / `normal` work and UI / small_fix / verification
- Round 3B provider id: `cursor` — CLI automation is **not claimed** unless safely detected; manual handoff remains the supported path

## Codex

- Second-opinion / independent review
- Preferred for `review` and `independent_review`
- Round 3B provider id: `codex` (adapter shell; live not authorized)

## Round 3B provider lane

| Provider | Adapter implemented | Live authorized |
| --- | --- | --- |
| `simulated` | Yes (fixtures) | N/A (no network model) |
| `claude_code` | Yes (shell) | No |
| `codex` | Yes (shell) | No |
| `cursor` | Yes (shell / honest ambiguity) | No |

Manual `prepare-handoff` continues to work alongside provider commands.

## Routing

Deterministic rules live in `config/default_routing.yaml`. Every route includes a written `routing_explanation` stored on the task.
