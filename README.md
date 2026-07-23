# AI Development Operating System

Local-first orchestration layer for multi-model software work (Claude / Cursor / Codex) with **manual handoff**, Round 3A **safe local pytest**, Round 3B **controlled provider adapters**, Round 3C **bounded simulated orchestration**, Round 4A **local CI / quality gates / PR validation**, Round 4B **first private remote GitHub Actions validation**, Round 4C **evidence-first audience-specific reporting**, Round 4D1–4D1.2 **provider readiness**, and Round 4D1.3 **trusted Codex headless-provider readiness** (install/auth/status + contract hardening — **no live prompts**; Round 4D2 locked).

## Round 4D1.3 status

Round 4D1.3 establishes one official OpenAI Codex CLI path on the operator host: trusted install, ChatGPT auth via `codex login status`, noninteractive contract from help/adapter/synthetic tests, JSONL/env hardening for a future Round 4D2. **Cursor remains editor-only. No `codex exec` prompts. ACP/scanners not installed.**

**Honest status:**

| Claim | Status |
| --- | --- |
| Local CI quality gates (Round 4A) | Yes |
| Private remote CI executed successfully (Round 4B) | Yes — on `tahach3/ai-development-os` |
| Evidence-first reporting (Round 4C) | Yes — deterministic templates; no LLM summaries |
| Provider readiness audit (Round 4D1–4D1.2) | Yes — **no live model invocations** |
| Trusted Codex headless readiness (Round 4D1.3) | Yes — ChatGPT auth verified; live still **not** authorized |
| Workflow permissions | `contents: read` only |
| Repository secrets / live provider / auto review / merge / deploy | **No** |
| Vulnerability database queried | **No** |
| Equitify connected | **No** |
| Local CI hardening (Round 4A ext.) | Yes — targeted tests, run history, regression compare, MD reports |
| Package version | **0.8.4** |

**Still not included:** paid LLM APIs, LangChain/CrewAI/AutoGen, dashboards, browser automation, Equitify integration, auto-merge/push/deploy, arbitrary patch engines, credential inspection, live provider smoke (requires separate Round 4D2 authorization), ACP, security scanners.

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
ai-dev-os ci-check --format md              # human-readable summary
ai-dev-os validate-change --base HEAD~1

# Round 4A hardening — fast targeted gate + regression awareness:
ai-dev-os ci-targeted --base HEAD~1         # run only tests related to the change
ai-dev-os ci-targeted --changed-file src/ai_dev_os/routing.py --select-only
ai-dev-os ci-history --limit 10             # list persisted CI runs (newest first)
ai-dev-os ci-compare --against-previous     # exit 1 only if a new regression appeared

# Round 4C reporting (from a persisted/synthetic evidence bundle JSON):
ai-dev-os build-report --evidence-bundle PATH --audience executive --detail-level summary
ai-dev-os render-report --report-id RID
ai-dev-os validate-report --report-id RID
ai-dev-os show-report --report-id RID --json

# Round 4D1 / 4D1.1 / 4D1.2 provider readiness (no live prompts):
ai-dev-os provider-readiness --project-id calculator-demo --json --show-combinations
ai-dev-os provider-readiness --project-id calculator-demo --show-candidates --explain-ambiguity --show-logical-installations
ai-dev-os provider-readiness --project-id calculator-demo --verify-noninteractive-contract --show-host-system-verdict
ai-dev-os provider-readiness --validate-pin cursor
```

## Prior rounds (complete)

- Round 3A: sessions / worktrees / allowlisted pytest
- Round 3B: provider adapters (live gated; smoke `blocked_before_execution`)
- Round 3C: bounded simulated orchestration + stalemate detection
- Round 4A: local CI / PR validation foundation
- Round 4B: first private remote CI validation (`tahach3/ai-development-os`)
- Round 4C: evidence-first audience-specific reporting (`4c.1`)
- Round 4D1: safe provider readiness auditing (`4d1.1`) — live smoke **not** authorized
- Round 4D1.1: trusted CLI ambiguity resolution (`4d1.1.1`) — pins/host-local only; live still **not** authorized
- Round 4D1.2: authentication + noninteractive readiness (`4d1.2`)
- Round 4D1.3: trusted Codex headless-provider readiness (`4d1.3`) — package **0.8.3**; live still **not** authorized
- Round 4A hardening: cross-platform sanitize fix, targeted/related-module tests (`ci-targeted`), CI run history + regression compare (`ci-history`/`ci-compare`), deterministic Markdown reports — package **0.8.4**; additive, CI schema unchanged (`4a.1`)

## Docs

See `docs/` for architecture, Round 3A–4D1.3 designs, the Round 4A local-CI + hardening designs, reporting/readiness standards, security, model roles, zero-click limits, roadmap, and project chronicle. Package version **0.8.4**.

- [`docs/OPEN_SOURCE_ADOPTION_ROADMAP.md`](docs/OPEN_SOURCE_ADOPTION_ROADMAP.md) — OS remains authority; phased external adapters
- [`docs/PROVIDER_READINESS_STANDARD.md`](docs/PROVIDER_READINESS_STANDARD.md) — Round 4D1 / 4D1.1 / 4D1.2 / 4D1.3 readiness contract
- [`docs/PROVIDER_AUTH_NONINTERACTIVE_STANDARD.md`](docs/PROVIDER_AUTH_NONINTERACTIVE_STANDARD.md) — auth + noninteractive contract
- [`docs/ROUND_4D1_PROVIDER_READINESS_DESIGN.md`](docs/ROUND_4D1_PROVIDER_READINESS_DESIGN.md) — Round 4D1 design
- [`docs/ROUND_4D1_1_CLI_AMBIGUITY_RESOLUTION_DESIGN.md`](docs/ROUND_4D1_1_CLI_AMBIGUITY_RESOLUTION_DESIGN.md) — Round 4D1.1 design
- [`docs/ROUND_4D1_2_AUTH_AND_NONINTERACTIVE_DESIGN.md`](docs/ROUND_4D1_2_AUTH_AND_NONINTERACTIVE_DESIGN.md) — Round 4D1.2 design
- [`docs/ROUND_4D1_3_CODEX_HEADLESS_PROVIDER_DESIGN.md`](docs/ROUND_4D1_3_CODEX_HEADLESS_PROVIDER_DESIGN.md) — Round 4D1.3 design
- [`docs/REPORTING_STANDARD.md`](docs/REPORTING_STANDARD.md) — Round 4C reporting contract
- [`docs/ROUND_4C_HIGH_QUALITY_REPORTING_DESIGN.md`](docs/ROUND_4C_HIGH_QUALITY_REPORTING_DESIGN.md) — Round 4C design
- [`docs/AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md`](docs/AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md) — master architectural direction (not all implemented)
- [`docs/SHARED_MEMORY_DESIGN.md`](docs/SHARED_MEMORY_DESIGN.md) — Phase B1 shared-memory **design only**
- [`docs/SHARED_MEMORY_IMPLEMENTATION_PLAN.md`](docs/SHARED_MEMORY_IMPLEMENTATION_PLAN.md) — Phase B2 **implementation decisions only**
