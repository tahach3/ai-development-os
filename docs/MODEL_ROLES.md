# Model Roles

Logical roles remain **Claude**, **Cursor**, and **Codex** (Codex/GPT for independent review). Round 1–2 adapters produce manual handoff packets only.

These are **logical roles**. The concrete provider may vary by round and configuration, but role separation and independent review must remain enforced.

## Platform authority

The **AI Development OS** owns:

- project registration;
- task lifecycle;
- plan state;
- approvals;
- routing decisions;
- fingerprints;
- context manifests;
- provider eligibility;
- orchestration state;
- audit records;
- behavioral metrics;
- future approved shared memory.

Models and IDE agents perform bounded jobs and return structured results. They do not become a second source of truth for lifecycle, policy, or memory.

## Three-model client workflow

The Cursor three-model workflow is a **client** of the AI Development OS.

It must not maintain a separate:

- task lifecycle;
- task database;
- approval database;
- routing history;
- audit trail;
- provider eligibility policy;
- project memory;
- shared-memory store;
- conflicting orchestration state.

Authority model:

```text
AI Development OS = controller and safety authority
Claude            = planning and hard reasoning
Cursor            = implementation
Codex/GPT         = independent review
```

Future platform direction (not yet implemented): see `docs/AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md`.

## Logical model roles

### Claude

Use Claude for:

- architecture;
- planning;
- ambiguous requirements;
- difficult reasoning;
- risk analysis;
- hard debugging;
- sensitive or high-risk decisions.

Also preferred for `complex` / `high_risk` complexity and `high` / `critical` risk. Round 3B provider id: `claude_code` (adapter shell; live not authorized).

### Cursor

Use Cursor for:

- implementation from an approved plan;
- routine and medium code changes;
- tests;
- refactoring;
- documentation;
- mechanical fixes.

Also covers daily editing, navigation, targeted fixes, UI, and diff review. Default for `small` / `normal` work and UI / small_fix / verification. Round 3B provider id: `cursor` — CLI automation is **not claimed** unless safely detected; manual handoff remains the supported path. Round 3C default **implementation** role in simulated orchestration.

### Codex / GPT

Use Codex or GPT for:

- independent review;
- adversarial analysis;
- acceptance-criteria verification;
- missing-requirement detection;
- implementation-report checking;
- final review findings.

Preferred for `review` and `independent_review`. Round 3B provider id: `codex` (adapter shell; live not authorized). Round 3C default **review** role in simulated orchestration (fresh context; not the implementation result as its own review).

## Round 3B provider lane

| Provider | Adapter implemented | Live authorized |
| --- | --- | --- |
| `simulated` | Yes (fixtures) | N/A (no network model) |
| `claude_code` | Yes (shell) | No |
| `codex` | Yes (shell) | No |
| `cursor` | Yes (shell / honest ambiguity) | No |

## Round 3C role separation

The same simulated adapter may serve both roles, but requests use different role bindings, request IDs, and context fingerprints. Audit records must **not** claim two real independent providers were used.

Manual `prepare-handoff` continues to work alongside provider and orchestration commands.

## Routing

Deterministic rules live in `config/default_routing.yaml`. Every route includes a written `routing_explanation` stored on the task. Routing decisions remain owned by the AI Development OS, not by any Cursor-local agent workflow.
