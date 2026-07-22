# AI Development Operating System

Local-first orchestration layer for multi-model software work (Claude / Cursor / Codex) with **manual handoff only**.

## Round 2 scope

Extends Round 1 with plan artifacts, approval gates, fingerprints, role-specific handoffs, review verdict gates, repair-round limits, synthetic calculator demo, and extended project-status.

**Not included:** paid LLM APIs, LangChain/CrewAI/AutoGen, dashboards, browser automation, network calls from the product, Equitify integration, worktrees (Round 3), real agent CLI adapters (Round 3), executing generated code, auto-approving high-risk work.

Open-source references were reviewed for patterns only — see `docs/OPEN_SOURCE_REFERENCE_ASSESSMENT.md`. No third-party orchestrator code was copied; no new dependencies were added from those projects.

## Requirements

- Python 3.11+
- Dependencies: PyYAML (+ pytest for dev)

## Install

```bash
cd C:\Users\Taha\ai-development-os
pip install -e ".[dev]"
```

## Quick start (Round 2)

```bash
ai-dev-os init
ai-dev-os register-project --id calculator-demo --name "Calculator Demo" --root C:\Users\Taha\ai-development-os\demo_projects\calculator-demo
ai-dev-os create-task --project-id calculator-demo --id calc-multiply --title "Add multiplication" --description "Add multiply with tests" --complexity small --risk-level low
ai-dev-os set-task-status --task-id calc-multiply --status ready_for_planning
ai-dev-os route-task --task-id calc-multiply
ai-dev-os create-plan --task-id calc-multiply --plan-id plan-1 --planner-agent claude --objective "Add multiply" --file-expected calculator/ops.py --step "implement" --test "pytest -q"
ai-dev-os submit-plan --plan-id plan-1
ai-dev-os approve-plan --plan-id plan-1 --approver human-operator
ai-dev-os prepare-handoff --task-id calc-multiply --role cursor
ai-dev-os project-status --project-id calculator-demo
```

## Tests

```bash
python -m pytest -q
```

## Equitify boundary

Equitify (`equitify-machine`) is **not** registered and must not be opened, inspected, or integrated until you explicitly say:

> Connect the AI Development Operating System to Equitify.

## Docs

See `docs/` for architecture, open-source assessment, boundaries, model roles, security, zero-click limits, and roadmap.
