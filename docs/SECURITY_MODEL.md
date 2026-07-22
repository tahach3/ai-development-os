# Security Model

## Hard prohibitions (product)

- No paid LLM API keys or network model calls by default
- No reading env secrets for automation; no auth-file / cookie / token enumeration
- No storing API keys in repo or workspace artifacts
- No executing generated code from adapters or provider text
- No auto-approve for high/critical risk
- No auto-activate self-improvement / rule rewrite
- No destructive Git from this OS (`reset --hard`, force-push, etc.)
- No silent provider CLI installation
- No live provider model execution without explicit multi-gate authorization (Round 3B/3C validation never takes this path)
- No unbounded repair loops; stalemate requires human review
- No automatic merge, push, or deployment
- No repository secrets in GitHub Actions (Round 4A workflow)
- No vulnerability-scan claims without querying a real vulnerability database (deferred)

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

Round 3C orchestration adds:

- Simulated-only default orchestration config (`config/orchestration.yaml`)
- Fail-closed binding/staleness checks before every step
- Fixture-controlled synthetic worktree mutations only (no arbitrary patch engine; provider text never executed)
- Deterministic stalemate stop → `human_review_required` / `blocked` (no live escalate)
- Atomic persistence for orchestration records/events

Round 4A CI / PR validation adds:

- Fixed-stage local CI (`ci-check`) with argv arrays, sanitized env, timeouts, output caps
- No arbitrary commands from config or PR text
- Secret-pattern scan with redaction (values never persisted raw)
- Dependency-policy (declared deps / prohibited categories / URL-Git-editable bans) — **not** vuln DB scanning
- `validate-change` inspects diffs without executing change code
- Safety-critical path changes → human review classification (not auto-approve)
- GitHub workflow: `permissions.contents: read` only; no secrets; no live providers; not executed/pushed in Round 4A

Round 4C reporting adds:

- Fail-closed report redaction before persistence of user-facing fields
- Claim statuses prevent silent promotion of agent statements to verified facts
- No raw prompts/transcripts/secrets in reports; Equitify identifiers rejected
- `vulnerability_scan: unavailable` unless a real vulnerability database was queried (never in 4C)
- Report generation never executes commands selected from report content
- Runtime reports remain local and gitignored

## Validation

- Explicit required fields and enums
- Lifecycle transition checks
- Project registry gate; Equitify sentinel refusal
- Provider request binding fingerprints; stale bindings fail closed
- Malformed provider output cannot become impl/review/repair input
- Orchestration schema `3c.1`; unsupported versions fail closed
- CI schema/policy `4a.1`; unsupported versions fail closed
- Reporting schema/policy `4c.1`; fingerprint + freshness validation fail closed

## Trust boundary

Humans paste handoff packets into external tools, or operators run **simulated** provider fixtures and **simulated** orchestrations. Local CI reports sanitized aggregates only. Round 4C reports are built from persisted evidence only (no live network, no LLM). The OS does not pretend external tools or GitHub Actions were invoked for live model work or remote CI unless separately authorized later.
