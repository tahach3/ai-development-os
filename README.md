# AI Development Operating System

Local-first orchestration layer for multi-model software work (Claude / Cursor / Codex) with **manual handoff only**, plus Round 3A **safe local execution** (isolated sessions / worktrees / allowlisted pytest).

## Round 3A scope

Adds isolated session records, confined Git worktrees for registered synthetic projects, allowlisted subprocess execution (`python -m pytest` only via argument arrays), env filtering, timeouts, output caps, normalized execution envelopes, and audit persistence.

**Still not included:** paid LLM APIs, LangChain/CrewAI/AutoGen, dashboards, browser automation, network model calls, Equitify integration, spawning Claude/Cursor/Codex CLIs, auto-merge/push, arbitrary shell.

Open-source references were reviewed for patterns only — see `docs/OPEN_SOURCE_REFERENCE_ASSESSMENT.md`. Design: `docs/ROUND_3A_SAFE_EXECUTION_DESIGN.md`.

## Requirements

- Python 3.11+
- Dependencies: PyYAML (+ pytest for dev)
- Git (for session worktrees)

## Install

```bash
cd C:\Users\Taha\ai-development-os
pip install -e ".[dev]"
```

## Quick start (Round 2 lifecycle)

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

## Safe execution (Round 3A)

`calculator-demo` must be a Git repository (initialize once if needed). Then:

```bash
ai-dev-os create-session --project-id calculator-demo --session-id calc-sess-1
ai-dev-os run-tests --session-id calc-sess-1 --test-path tests/test_ops.py
ai-dev-os show-execution --execution-id <id-from-run-tests>
ai-dev-os cleanup-session --session-id calc-sess-1
```

No freeform shell strings are accepted — only allowlisted argv profiles.

## Tests

```bash
python -m pytest -q
```

## Equitify boundary

Equitify (`equitify-machine`) is **not** registered and must not be opened, inspected, or integrated until you explicitly say:

> Connect the AI Development Operating System to Equitify.

## Docs

Project chronicle: [`docs/PROJECT_CHRONICLE.md`](docs/PROJECT_CHRONICLE.md) (export copy: [`exports/AI_Development_OS_Project_Chronicle.md`](exports/AI_Development_OS_Project_Chronicle.md)).

See `docs/` for architecture, Round 3A design, open-source assessment, boundaries, security, and roadmap.
