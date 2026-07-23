# Provider Readiness Standard (Round 4D1 / 4D1.1 / 4D1.2 / 4D1.3)

**Schema version:** `4d1.3`
**Policy version:** `4d1.3`
**Authentication probe policy:** `4d1.3`
**Authentication mode policy:** `4d1.3`
**Noninteractive contract policy:** `4d1.3`
**Host system verdict schema:** `4d1.3`
**Ambiguity / pin / selection schemas:** `4d1.1.1`
**Package:** `0.8.3`

## Purpose

Safely determine whether adapter-backed provider CLIs are **technically eligible** for a future bounded live orchestration smoke test (Round 4D2), without sending any model prompt. Round 4D1.1 resolves ambiguous installations. Round 4D1.2 hardens authentication-status probing and noninteractive contract verification (synthetic/help/adapter only). Round 4D1.3 adds a trusted **OpenAI Codex** headless path (official install + ChatGPT `login status` + JSONL/env hardening) while keeping Round 4D2 locked.

## Hard rules

- Round 4D1 / 4D1.1 / 4D1.2 / 4D1.3 perform **no** live model invocation (`live_provider_invocations: 0`).
- **Installed ≠ eligible.**
- **Authentication unknown ≠ authenticated** (and ≠ unauthenticated).
- **API-key auth mode is unsupported for Round 4D1.3 Codex eligibility** (ChatGPT required).
- **`login status` is a read-only status probe; bare `login` is not.**
- **Help output ≠ proof of successful execution.**
- **Simulation ≠ live provider result.**
- **PATH precedence alone is not trust.**
- **Matching versions do not prove executable equivalence.**
- **Distinct trusted binaries require explicit operator selection** (no silent pick).
- **Local executable pins do not enable live mode** and do not imply authentication.
- **Editor CLI ≠ headless agent CLI.**
- **Fresh-context same-provider review ≠ independent review.**
- A **separate authorization** is required for Round 4D2.
- Equitify remains **disconnected**.
- ACP and external security scanners are **not** installed in Round 4D1.3.

## States

### Discovery

`installed` | `not_installed` | `ambiguous_installation` | `executable_untrusted` | `probe_failed`

### Version compatibility

`supported` | `unsupported` | `unverified` | `malformed` | `unavailable`

### Ambiguity (4D1.1)

Classifications include `wrapper_and_target`, `same_binary_duplicate_path`, `distinct_installations_*`, `multiple_trusted_candidates`, `unsupported_wrapper`, and related categories in the Round 4D1.1 design. Automatic collapse requires an explicit rule ID (`AC-*`).

### Authentication

`authenticated_verified` | `unauthenticated_verified` | `reported_authenticated` | `unknown` | `verification_unsupported` | `verification_failed`

Auth probes run only when profile-declared or help-confirmed allowlisted (`auth status`, `whoami`). Never credential files / login.

### Noninteractive

`supported_verified` | `supported_documented` | `unsupported_verified` | `ambiguous` | `unavailable`

Contract dimensions: prompt input, working-directory binding, structured output, timeout, cancellation, output limits — from adapter/help/synthetic fixtures only.

### Readiness verdicts (per provider)

`eligible_for_bounded_live_smoke` | `conditionally_eligible_for_bounded_live_smoke` | `installed_but_authentication_unverified` | `installed_but_noninteractive_unverified` | `installed_but_version_unsupported` | `ambiguous_provider_installation` | `no_eligible_provider` | `policy_blocked` | `probe_failed` | `invalid_record`

### Host / system verdicts (4D1.2)

`live_smoke_ready` | `live_smoke_ready_with_operator_auth` | `authentication_unverified` | `noninteractive_unverified` | `no_independent_reviewer` | `provider_not_eligible`

## Version / help / auth probes

Allowlisted argv only. Forbidden: prompts, login, agent, auto-approve. Output redacted and bounded. Help text is untrusted data.

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
ai-dev-os provider-readiness --project-id <registered> --verify-noninteractive-contract --show-host-system-verdict
ai-dev-os provider-readiness --project-id <registered> --generate-selection-record
ai-dev-os provider-readiness --validate-pin <provider_id>
ai-dev-os provider-readiness --project-id <registered> --validate <readiness_id>
```

Always includes `live_provider_invocations: 0`.

## Storage and reports

Records under `workspace/provider_readiness/` (gitignored). Audience reports: executive / operator / developer / auditor. Round 4C evidence type: `provider_readiness`.

## Staleness

Stale when commit, adapter version, policy versions (including auth/noninteractive/host-verdict), executable fingerprint/path/target, wrapper contents, CLI version, host binding, pin inputs, or config/registration fingerprints change. Not stale merely due to wall-clock age.

## Synthetic testing

Automated tests use fake executables only — never real providers, network, or live auth.

## Round 4D2 authorization requirements

Before any live smoke:

1. Explicit human authorization for Round 4D2
2. Host verdict `live_smoke_ready` or `live_smoke_ready_with_operator_auth` (plus operator auth approval if conditional)
3. Unambiguous trusted executable (after 4D1.1 resolution or approved pin)
4. Supported CLI version
5. Authentication verified (or operator-approved unknown)
6. Noninteractive capability adequate
7. Independent review plan documented
8. Live mode still gated by existing multi-gate policy
9. No Equitify involvement

See also: `docs/ROUND_4D1_PROVIDER_READINESS_DESIGN.md`, `docs/ROUND_4D1_1_CLI_AMBIGUITY_RESOLUTION_DESIGN.md`, `docs/ROUND_4D1_2_AUTH_AND_NONINTERACTIVE_DESIGN.md`, `docs/PROVIDER_AUTH_NONINTERACTIVE_STANDARD.md`.
