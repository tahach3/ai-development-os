# Zero-Click Limitations

Round 1 is **not** zero-click automation.

## What is automated locally

- Validation, routing, context packet generation
- Writing handoff markdown/JSON
- Storing reports and behavioral recommendations

## What always requires a human

- Opening Claude / Cursor / Codex
- Pasting context and performing the work
- Approving high/critical risk changes
- Committing / pushing in target repositories
- Connecting Equitify (explicit user command only)
- Applying any behavioral recommendation (no auto rule rewrite)

## Adapter contract

Every adapter result includes:

```text
automation_status: manual_handoff_required
```

There is no cloud agent, dashboard trigger, or browser automation in Round 1.
