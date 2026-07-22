# Security Model

## Hard prohibitions (product)

- No paid LLM API keys or network model calls
- No reading env secrets for automation
- No storing API keys in repo or workspace artifacts
- No executing generated code from adapters
- No auto-approve for high/critical risk
- No auto-activate self-improvement / rule rewrite
- No destructive Git from this OS (`reset --hard`, force-push, etc.)

## Subprocess policy

Git inspection uses `subprocess` with:

- Argument arrays (never `shell=True`)
- Timeouts
- Allowlist of inspect verbs only

Round 3A safe execution adds:

- Separate allowlisted `python -m pytest` runner (`safe_exec.py`) — never `shell=True`
- Minimal environment allowlist (secrets not inherited)
- Working-directory confinement under session worktrees
- Output-size limits and normalized audit envelopes
- Git **worktree add/list/remove only** via `worktrees.py` (not via inspect helpers; no reset/push/merge/commit)

## Validation

- Explicit required fields and enums
- Lifecycle transition checks
- Project registry gate before task create/validate/context/handoff/session
- Prohibited path prefix checks
- Equitify sentinel refusal

## Trust boundary

Humans paste handoff packets into external tools. Results are recorded back via CLI. The OS never pretends those tools were invoked automatically. Local pytest runs are explicitly `automation_status: local_allowlisted_execution`.
