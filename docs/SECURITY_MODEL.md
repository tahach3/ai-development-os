# Security Model

## Hard prohibitions (product)

- No paid LLM API keys or network model calls by default
- No reading env secrets for automation; no auth-file / cookie / token enumeration
- No storing API keys in repo or workspace artifacts
- No executing generated code from adapters
- No auto-approve for high/critical risk
- No auto-activate self-improvement / rule rewrite
- No destructive Git from this OS (`reset --hard`, force-push, etc.)
- No silent provider CLI installation
- No live provider model execution without explicit multi-gate authorization (Round 3B validation never takes this path)

## Subprocess policy

Git inspection uses `subprocess` with argument arrays (never `shell=True`), timeouts, and inspect-verb allowlists.

Round 3A safe execution adds allowlisted `python -m pytest`, env filtering, worktree confinement, output caps, and worktree add/list/remove only.

Round 3B provider lane adds:

- Separate discovery runner (`--version` / `--help` only, short timeouts)
- Provider executable basename allowlists (no arbitrary paths)
- Fail-closed provider config (`disabled` default)
- Live gates: provider + project + plan + session + worktree + commit + task execution approval; high/critical never auto-live
- Provider results audited under `workspace/provider_executions/` with truncated stdout/stderr
- Status CLI omits full private prompts (fingerprints / paths only)

## Validation

- Explicit required fields and enums
- Lifecycle transition checks
- Project registry gate; Equitify sentinel refusal
- Provider request binding fingerprints; stale bindings fail closed
- Malformed provider output cannot become impl/review/repair input

## Trust boundary

Humans paste handoff packets into external tools, or operators run **simulated** provider fixtures. The OS does not pretend external tools were invoked for live model work unless a separately authorized live smoke is approved later.
