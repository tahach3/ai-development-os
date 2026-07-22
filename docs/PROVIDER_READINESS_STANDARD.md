# Provider Readiness Standard (Round 4D1)

**Schema version:** `4d1.1`  
**Policy version:** `4d1.1`  
**Package:** `0.8.0`

## Purpose

Safely determine whether adapter-backed provider CLIs are **technically eligible** for a future bounded live orchestration smoke test (Round 4D2), without sending any model prompt.

## Hard rules

- Round 4D1 performs **no** live model invocation (`live_provider_invocations: 0`).
- **Installed ≠ eligible.**
- **Authentication unknown ≠ authenticated** (and ≠ unauthenticated).
- **Help output ≠ proof of successful execution.**
- **Simulation ≠ live provider result.**
- A **separate authorization** is required for Round 4D2.
- Equitify remains **disconnected**.

## States

### Discovery

`installed` | `not_installed` | `ambiguous_installation` | `executable_untrusted` | `probe_failed`

### Version compatibility

`supported` | `unsupported` | `unverified` | `malformed` | `unavailable`

### Authentication

`authenticated_verified` | `unauthenticated_verified` | `reported_authenticated` | `unknown` | `verification_unsupported` | `verification_failed`

Credential files are never inspected. Only allowlisted read-only auth-status commands may verify auth.

### Noninteractive

`supported_verified` | `supported_documented` | `unsupported_verified` | `ambiguous` | `unavailable`

Cursor desktop ≠ automation CLI.

### Role eligibility

`eligible` | `conditionally_eligible` | `ineligible` | `unverified` | `policy_blocked`

Roles: planner, implementer, reviewer, repair_implementer, final_verifier.

### Reviewer independence

`separate_provider_available` | `separate_model_available` | `fresh_context_same_provider_only` | `independence_unverified` | `unavailable`

### Final verdicts

`eligible_for_bounded_live_smoke` | `conditionally_eligible_for_bounded_live_smoke` | `installed_but_authentication_unverified` | `installed_but_noninteractive_unverified` | `installed_but_version_unsupported` | `ambiguous_provider_installation` | `no_eligible_provider` | `policy_blocked` | `probe_failed` | `invalid_record`

## Executable discovery

Multi-method (Python PATH/`which`, Windows `where.exe`, optional `Get-Command`). No full PATH print. Duplicate distinct candidates → ambiguous (no silent pick). Symlink/Equitify escapes rejected. Executable content SHA-256 when safe.

## Version / help probes

Allowlisted argv only (`--version`, `version`, `--help`, `help`, …). Forbidden: prompts, login, agent, auto-approve. Output redacted and bounded. Help text is untrusted data.

## Noninteractive / worktree / bounds

Assessed from adapter contracts, docs, and help — **not** live prompts. Round 4D2 will still require session worktree binding, timeouts, output caps, and existing safety gates.

## Role matrix and independence

Deterministic matrix per provider. Preferred Round 4D2 shape: separate implementer + reviewer providers. Same-provider review is at most fresh-context (not true independence).

## Live-policy boundary

Readiness tooling **never** enables live mode or mutates provider config. Eligibility is advisory for a future authorized smoke.

## CLI

```bash
ai-dev-os provider-readiness --project-id <registered> [--provider ID] [--json]
ai-dev-os provider-readiness --project-id <registered> --show-combinations --audience auditor
ai-dev-os provider-readiness --project-id <registered> --validate <readiness_id>
```

Always includes `live_provider_invocations: 0`.

## Storage and reports

Records under `workspace/provider_readiness/` (gitignored). Audience reports: executive / operator / developer / auditor. Round 4C evidence type: `provider_readiness`.

## Staleness

Stale when commit, adapter version, policy versions, executable fingerprint/path, CLI version, or config/registration fingerprints change. Not stale merely due to wall-clock age.

## Synthetic testing

Automated tests use fake executables only — never real providers, network, or live auth.

## Round 4D2 authorization requirements

Before any live smoke:

1. Explicit human authorization for Round 4D2
2. Unambiguous trusted executable
3. Supported CLI version
4. Authentication verified (or operator-approved unknown)
5. Noninteractive capability adequate
6. Independent review plan documented
7. Live mode still gated by existing multi-gate policy
8. No Equitify involvement

See also: `docs/ROUND_4D1_PROVIDER_READINESS_DESIGN.md`.
