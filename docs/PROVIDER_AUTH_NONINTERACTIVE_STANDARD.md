# Provider Authentication and Noninteractive Standard (Round 4D1.2)

**Package:** `0.8.3`

**Auth probe policy:** `4d1.3`

**Noninteractive contract policy:** `4d1.3`

**Host system verdict schema:** `4d1.3`

**Authentication mode policy:** `4d1.3` (Codex: ChatGPT required; API-key unsupported for 4D1.3 eligibility)

This standard extends [`PROVIDER_READINESS_STANDARD.md`](PROVIDER_READINESS_STANDARD.md). Design: [`ROUND_4D1_2_AUTH_AND_NONINTERACTIVE_DESIGN.md`](ROUND_4D1_2_AUTH_AND_NONINTERACTIVE_DESIGN.md).

## Authentication

- Only allowlisted read-only status argv (`auth status`, `whoami`, Codex `login status`) may run.
- Profile-declared argv **or** help-confirmed allowlist (when `auth_probe_mode=help_confirmed_allowlist`).
- Never login/logout/refresh, credential files, or token printing.
- `unknown` ≠ authenticated and ≠ unauthenticated.
- Advertisement (`auth_status_command_advertised`) ≠ verification.

## Noninteractive contract

Assessed from adapter allowlists, help (untrusted data), and **synthetic fixtures only**:

| Dimension | Notes |
| --- | --- |
| Prompt / input binding | Documented argv shapes; never append live prompt text in readiness |
| Working-directory binding | Adapter/docs/help; synthetic confinement |
| Structured output | Adapter envelope / documented flags |
| Timeout | Runner probe timeout policy |
| Cancellation | Cancel-request store contract |
| Output limits | Probe truncation policy |

Editor-only CLI help (e.g. Cursor desktop `--diff` / `--goto`) → `unsupported_verified` for headless agent use. Version success alone never proves automation.

## Host / system verdicts

Exactly one:

`live_smoke_ready` | `live_smoke_ready_with_operator_auth` | `authentication_unverified` | `noninteractive_unverified` | `no_independent_reviewer` | `provider_not_eligible`

Only `live_smoke_ready*` would later unlock Round 4D2 consideration (still requires separate human authorization). Round 4D1.2/4D1.3 never enables live mode.

## Independence

Separate-provider review ≠ same-provider fresh-context review. Fresh-context must be labeled honestly.

## CLI

```bash
ai-dev-os provider-readiness --project-id <id> --verify-noninteractive-contract --show-host-system-verdict
```

Always `live_provider_invocations: 0`.
