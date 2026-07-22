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

## Validation

- Explicit required fields and enums
- Lifecycle transition checks
- Project registry gate before task create/validate/context/handoff
- Prohibited path prefix checks

## Trust boundary

Humans paste handoff packets into external tools. Results are recorded back via CLI. The OS never pretends those tools were invoked automatically.
