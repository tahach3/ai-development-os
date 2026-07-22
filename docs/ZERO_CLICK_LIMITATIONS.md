# Zero-Click Limitations

This OS is **not** zero-click automation.

## What is automated locally

- Validation, routing, context packet generation
- Writing handoff markdown/JSON
- Storing reports and behavioral recommendations
- Round 3A allowlisted pytest in isolated sessions
- Round 3B provider **discovery**, **preview**, and **simulated** fixture execution (when explicitly enabled)

## What always requires a human

- Opening Claude / Cursor / Codex for real work (manual handoff)
- Approving plans and high/critical risk changes
- Enabling any provider beyond fail-closed defaults
- Authorizing any future **live** local CLI model smoke test
- Committing / pushing in target repositories
- Connecting Equitify (explicit user command only)
- Applying any behavioral recommendation (no auto rule rewrite)

## Adapter contracts

Manual handoff results include:

```text
automation_status: manual_handoff_required
```

Simulated provider results use:

```text
automation_status: simulated_provider_execution
```

Discovery-only uses `discovery_only`. Live local CLI (`live_local_cli`) is gated and **not authorized** in Round 3B validation.

There is no cloud agent, dashboard trigger, or browser automation.
