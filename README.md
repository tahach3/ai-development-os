# AI Development Operating System

Local-first orchestration layer for multi-model software work (Claude / Cursor / Codex) with **manual handoff**, Round 3A **safe local pytest**, Round 3B **controlled provider adapters**, Round 3C **bounded simulated orchestration**, Round 4A **local CI / quality gates / PR validation**, Round 4B **first private remote GitHub Actions validation**, and Round 4C **evidence-first audience-specific reporting**.

## Round 4C status

Round 4C adds deterministic, model-free reporting: canonical evidence + claim statuses, relevance selection, audience/detail renderers, integrity fingerprints, redaction, and CLI (`build-report` / `render-report` / `validate-report` / `show-report`). Runtime reports stay under `workspace/reports/{canonical,rendered,manifests}/` (gitignored).

**Honest status:**

| Claim | Status |
| --- | --- |
| Local CI quality gates (Round 4A) | Yes |
| Private remote CI executed successfully (Round 4B) | Yes — run `29930178622` (and subsequent closeout) on `tahach3/ai-development-os` |
| Evidence-first reporting (Round 4C) | Yes — deterministic templates; no LLM summaries |
| Workflow permissions | `contents: read` only |
| Repository secrets / live provider / auto review / merge / deploy | **No** |
| Vulnerability database queried | **No** |
| Equitify connected | **No** |
| Package version | **0.7.0** |

**Still not included:** paid LLM APIs, LangChain/CrewAI/AutoGen, dashboards, browser automation, Equitify integration, auto-merge/push/deploy, arbitrary patch engines, credential inspection.

## Install (dev)

```bash
cd C:\Users\Taha\ai-development-os
python -m pip install -e ".[dev]"
```

## Quick start

```bash
ai-dev-os init
ai-dev-os register-project --id calculator-demo --name "Calculator Demo" --root demo_projects/calculator-demo

# Round 4A local gates:
ai-dev-os ci-check
ai-dev-os validate-change --base HEAD~1

# Round 4C reporting (from a persisted/synthetic evidence bundle JSON):
ai-dev-os build-report --evidence-bundle PATH --audience executive --detail-level summary
ai-dev-os render-report --report-id RID
ai-dev-os validate-report --report-id RID
ai-dev-os show-report --report-id RID --json
```

## Prior rounds (complete)

- Round 3A: sessions / worktrees / allowlisted pytest
- Round 3B: provider adapters (live gated; smoke `blocked_before_execution`)
- Round 3C: bounded simulated orchestration + stalemate detection
- Round 4A: local CI / PR validation foundation
- Round 4B: first private remote CI validation (`tahach3/ai-development-os`, run `29930178622`)
- Round 4C: evidence-first audience-specific reporting (`4c.1`)

## Docs

See `docs/` for architecture, Round 3A–4C designs, reporting standard, security, model roles, zero-click limits, roadmap, and project chronicle. Package version **0.7.0**.

- [`docs/REPORTING_STANDARD.md`](docs/REPORTING_STANDARD.md) — Round 4C reporting contract
- [`docs/ROUND_4C_HIGH_QUALITY_REPORTING_DESIGN.md`](docs/ROUND_4C_HIGH_QUALITY_REPORTING_DESIGN.md) — Round 4C design
- [`docs/AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md`](docs/AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md) — master architectural direction (not all implemented)
- [`docs/SHARED_MEMORY_DESIGN.md`](docs/SHARED_MEMORY_DESIGN.md) — Phase B1 shared-memory **design only**
- [`docs/SHARED_MEMORY_IMPLEMENTATION_PLAN.md`](docs/SHARED_MEMORY_IMPLEMENTATION_PLAN.md) — Phase B2 **implementation decisions only**
