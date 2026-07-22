# Zero-Click Limitations

This OS is **not** zero-click automation.

## What is automated locally

- Validation, routing, context packet generation
- Writing handoff markdown/JSON
- Storing reports and behavioral recommendations
- Round 3A allowlisted pytest in isolated sessions
- Round 3B provider **discovery**, **preview**, and **simulated** fixture execution (when explicitly enabled)
- Round 3C **bounded** simulated orchestration steps (until a safety boundary)
- Round 4A **local CI stages** and **static change validation** when an operator runs `ci-check` / `validate-change`
- Round 4B **private remote GitHub Actions** for the fixed workflow on `push` / `pull_request` / `workflow_dispatch` (same least-privilege permissions; no secrets; no live providers)
- Round 4C **evidence-first report build/render/validate** from persisted/synthetic evidence bundles (no LLM; no network required to render)

## What always requires a human

- Opening Claude / Cursor / Codex for real work (manual handoff)
- Approving plans and high/critical risk changes
- Enabling any provider beyond fail-closed defaults
- Authorizing any future **live** local CLI model smoke test
- Committing / pushing in target repositories
- Connecting Equitify (explicit user command only)
- Applying any behavioral recommendation (no auto rule rewrite; Round 4A recommendations remain proposed/inactive)
- Resolving orchestration **stalemate** / repair-limit / blocked states
- Creating a new orchestration after cancellation (cancelled cannot silently resume)
- Approving safety-critical CI/policy/workflow changes flagged by `validate-change`
- Interpreting incomplete / conflicting / blocked / stale reports and deciding next actions
- Broadening GitHub Actions permissions, adding repository secrets, live provider CI steps, deploy, or auto-merge (Round 4B validated remote CI only under `contents: read`)

## Adapter contracts

Manual handoff results include:

```text
automation_status: manual_handoff_required
```

Simulated provider results use:

```text
automation_status: simulated_provider_execution
```

Simulated orchestration uses:

```text
automation_status: simulated_orchestration
```

Discovery-only uses `discovery_only`. Live local CLI (`live_local_cli`) is gated and **not authorized** in Round 3B/3C validation.

There is no cloud agent, dashboard trigger, browser automation, auto-merge, auto-push, or auto-deploy.
