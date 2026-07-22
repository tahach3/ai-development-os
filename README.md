# AI Development Operating System

Local-first orchestration layer for multi-model software work (Claude / Cursor / Codex) with **manual handoff only**.

## Round 1 scope

- Project registry (refuse unregistered projects; Equitify not connected)
- Structured tasks + lifecycle FSM
- Deterministic routing and token budget bands
- Minimal context packets
- Inspect-only Git safety
- Placeholder adapters (`automation_status: manual_handoff_required`)
- Implementation / review reports and behavioral recommendations

**Not included:** paid LLM APIs, LangChain/CrewAI/AutoGen, dashboards, browser automation, network calls from the product, Equitify integration, executing generated code, auto-approving high-risk work.

## Requirements

- Python 3.11+
- Dependencies: PyYAML (+ pytest for dev)

## Install

```bash
cd C:\Users\Taha\ai-development-os
pip install -e ".[dev]"
```

## Quick start

```bash
ai-dev-os init
ai-dev-os register-project --id demo --name "Demo" --root C:\Users\Taha\Projects\demo
ai-dev-os create-task --project-id demo --id t1 --title "Add tests" --description "Cover validation" --task-type small_fix --complexity small --risk-level low
ai-dev-os validate-task --task-id t1
ai-dev-os route-task --task-id t1
ai-dev-os build-context --task-id t1
ai-dev-os prepare-handoff --task-id t1
ai-dev-os project-status --project-id demo
```

## Tests

```bash
python -m pytest -q
```

## Equitify boundary

Equitify (`equitify-machine`) is **not** registered and must not be opened, inspected, or integrated until you explicitly say:

> Connect the AI Development Operating System to Equitify.

## Docs

See `docs/` for architecture, boundaries, model roles, security, zero-click limits, and roadmap.
