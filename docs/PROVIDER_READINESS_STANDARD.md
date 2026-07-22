# Provider Readiness Standard (Round 4D1 / 4D1.1)

**Schema version:** `4d1.1`
**Policy version:** `4d1.1`
**Ambiguity / pin / selection schemas:** `4d1.1.1`
**Package:** `0.8.1`

## Purpose

Safely determine whether adapter-backed provider CLIs are **technically eligible** for a future bounded live orchestration smoke test (Round 4D2), without sending any model prompt. Round 4D1.1 additionally resolves ambiguous installations via identity/wrapper analysis, logical installations, host-local pins, and operator decision records.

## Hard rules

- Round 4D1 / 4D1.1 perform **no** live model invocation (`live_provider_invocations: 0`).
- **Installed ≠ eligible.**
- **Authentication unknown ≠ authenticated** (and ≠ unauthenticated).
- **Help output ≠ proof of successful execution.**
- **Simulation ≠ live provider result.**
- **PATH precedence alone is not trust.**
- **Matching versions do not prove executable equivalence.**
- **Distinct trusted binaries require explicit operator selection** (no silent pick).
- **Local executable pins do not enable live mode** and do not imply authentication.
- A **separate authorization** is required for Round 4D2.
- Equitify remains **disconnected**.

## States

### Discovery

`installed` | `not_installed` | `ambiguous_installation` | `executable_untrusted` | `probe_failed`

### Version compatibility

`supported` | `unsupported` | `unverified` | `malformed` | `unavailable`

### Ambiguity (4D1.1)

Classifications include `wrapper_and_target`, `same_binary_duplicate_path`, `distinct_installations_*`, `multiple_trusted_candidates`, `unsupported_wrapper`, and related categories in the Round 4D1.1 design. Automatic collapse requires an explicit rule ID (`AC-*`).

### Authentication

`authenticated_verified` | `unauthenticated_verified` | `reported_authenticated` | `unknown` | `verification_unsupported` | `verification_failed`

### Noninteractive

`supported_verified` | `supported_documented` | `unsupported_verified` | `ambiguous` | `unavailable`

### Readiness verdicts

`eligible_for_bounded_live_smoke` | `conditionally_eligible_for_bounded_live_smoke` | `installed_but_authentication_unverified` | `installed_but_noninteractive_unverified` | `installed_but_version_unsupported` | `ambiguous_provider_installation` | `no_eligible_provider` | `policy_blocked` | `probe_failed` | `invalid_record`

## Version / help probes

Allowlisted argv only (`--version`, `version`, `--help`, `help`, …). Forbidden: prompts, login, agent, auto-approve. Output redacted and bounded. Help text is untrusted data. Wrapper script contents are untrusted data and are never executed.

## Noninteractive / worktree / bounds

Assessed from adapter contracts, docs, and help — **not** live prompts. Round 4D2 will still require session worktree binding, timeouts, output caps, and existing safety gates.

## Role matrix and independence

Deterministic matrix per provider. Preferred Round 4D2 shape: separate implementer + reviewer providers. Same-provider review is at most fresh-context (not true independence).

## Live-policy boundary

Readiness tooling **never** enables live mode or mutates provider config. Eligibility is advisory for a future authorized smoke. Host-local pins never flip live mode.

## Executable pinning (host-local)

Pins live under `workspace/provider_pins/` (gitignored). Path + SHA-256 fingerprint required. Path-only pins rejected. Templates only: `config/provider_pins.example.json`. Never commit real local paths or usernames.

## CLI

```bash
ai-dev-os provider-readiness --project-id <registered> [--provider ID] [--json]
ai-dev-os provider-readiness --project-id <registered> --show-combinations --audience auditor
ai-dev-os provider-readiness --project-id <registered> --show-candidates --explain-ambiguity --show-logical-installations
ai-dev-os provider-readiness --project-id <registered> --generate-selection-record
ai-dev-os provider-readiness --validate-pin <provider_id>
ai-dev-os provider-readiness --project-id <registered> --validate <readiness_id>
```

Always includes `live_provider_invocations: 0`.

## Storage and reports

Records under `workspace/provider_readiness/` (gitignored). Audience reports: executive / operator / developer / auditor. Round 4C evidence type: `provider_readiness`. Operator reports include candidate matrices and approval phrases when selection is required.

## Staleness

Stale when commit, adapter version, policy versions, executable fingerprint/path/target, wrapper contents, CLI version, host binding, pin inputs, or config/registration fingerprints change. Not stale merely due to wall-clock age. Do not silently reuse stale pins.

## Synthetic testing

Automated tests use fake executables only — never real providers, network, or live auth.

## Round 4D2 authorization requirements

Before any live smoke:

1. Explicit human authorization for Round 4D2
2. Unambiguous trusted executable (after 4D1.1 resolution or approved pin)
3. Supported CLI version
4. Authentication verified (or operator-approved unknown)
5. Noninteractive capability adequate
6. Independent review plan documented
7. Live mode still gated by existing multi-gate policy
8. No Equitify involvement

See also: `docs/ROUND_4D1_PROVIDER_READINESS_DESIGN.md`, `docs/ROUND_4D1_1_CLI_AMBIGUITY_RESOLUTION_DESIGN.md`.
