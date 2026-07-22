# Round 4D1.2 — Authentication and Noninteractive Readiness Design

**Package target:** `0.8.2` (hardening of Round 4D1 / 4D1.1 readiness; not a new major subsystem)  
**Readiness schema:** `4d1.2`  
**Readiness policy:** `4d1.2`  
**Authentication probe policy:** `4d1.2`  
**Noninteractive contract policy:** `4d1.2`  
**Role eligibility policy:** `4d1.2`  
**Host system verdict schema:** `4d1.2`  
**Baseline:** `master` @ `17dc3da` (package `0.8.1`, Round 4D1.1 complete)  
**Live model invocations authorized in this round:** **0**

---

## 1. Purpose

Resolve the two remaining Round 4D1.1 blockers safely and read-only:

1. **Authentication readiness** — does the trusted CLI expose a safe authentication-status command, and what is the verified auth state?
2. **Noninteractive execution readiness** — what exact headless contract (flags/docs/adapter allowlists) exists, proven with **synthetic fixtures only**?

Also refresh the **role / independence matrix** and emit a single **host/system final verdict** for whether Round 4D2 may later be considered.

Round 4D1.2 does **not** authorize, enable, or perform live model smoke (Round 4D2).

---

## 2. Non-goals

- Live prompts, completions, coding tasks, or paid API use
- Login / logout / refresh / browser auth / credential-file reads
- Printing tokens or full PATH/env
- PATH or install changes; live-mode enablement
- Equitify access
- Claiming help text as proof of successful live execution
- Treating same-provider fresh-context review as true independent-provider review

---

## 3. Threat model

| Threat | Mitigation |
| --- | --- |
| Accidental live prompt | Argv allowlist; forbid `prompt`/`agent`/`login`/`-p`/auto-approve; `live_provider_invocations` fixed at 0 |
| Credential leakage | Never open token DBs/files; redact probe output; never print secrets |
| Help-as-executable | Help is untrusted data; never re-exec help-suggested argv unless already allowlisted |
| Overclaiming Cursor automation | Editor CLI help without headless agent contract → `unsupported_verified` / ambiguous — never `supported_verified` from version alone |
| Synthetic ≠ live | Synthetic fixture pass never flips live policy |
| Auth inference from files | Forbidden; only dedicated allowlisted auth-status commands may yield `*_verified` |

---

## 4. Authentication probe policy

### 4.1 Allowed sources

1. **Profile-declared** `auth_argv` — only when the adapter profile explicitly marks a read-only status command as safe.
2. **Help-confirmed allowlist** — when profile `auth_probe_mode` is `help_confirmed_allowlist`, a prior `--help` summary may **advertisement-match** an allowlisted argv sequence (e.g. `auth status`, `whoami`). Matching advertisement alone does **not** authenticate; it only permits running that exact allowlisted probe.
3. Otherwise → do **not** probe; status `verification_unsupported`.

### 4.2 Forbidden

- Credential files, keychains, browser storage
- `login` / `logout` / `refresh` / browser OAuth flows
- Any prompt/agent/completion argv
- Inferring auth from “CLI installed” or subscription UI

### 4.3 States (unchanged vocabulary)

| State | Meaning |
| --- | --- |
| `authenticated_verified` | Allowlisted auth-status command output positively confirms authenticated |
| `unauthenticated_verified` | Allowlisted auth-status command output positively confirms unauthenticated |
| `reported_authenticated` | Soft/self-report only (not used as live-smoke gate without operator policy) |
| `unknown` | Probe ran but inconclusive |
| `verification_unsupported` | No safe status command available / not probed |
| `verification_failed` | Probe failed (timeout/nonzero without clear status) |

**Hard rule:** `unknown` ≠ authenticated and ≠ unauthenticated.

### 4.4 Advertisement vs verification

Records may include:

- `auth_status_command_advertised` — help/docs mention an allowlisted status pattern
- `auth_status_command_runnable` — policy permits probing it
- `authentication_verification_method` — e.g. `auth_status_command` | `none` | `help_inconclusive`

---

## 5. Noninteractive contract verification

### 5.1 Contract dimensions

Assessed **without** sending a provider prompt:

| Dimension | Evidence sources |
| --- | --- |
| Prompt / input binding | Adapter allowlisted argv shape; help flags; synthetic argv builder |
| Working-directory binding | Adapter/docs/help; synthetic cwd confinement check |
| Structured output | Adapter envelope contract; synthetic fixture |
| Timeout | Probe/runner timeout policy (OS-level); adapter docs |
| Cancellation | Existing cancel request contract |
| Output limits | Probe/runner truncation policy |

### 5.2 Classification

| Status | When |
| --- | --- |
| `supported_verified` | Synthetic fixture proves argv/contract dimensions without live model call |
| `supported_documented` | Adapter/docs/help claim support; not synthetically proven |
| `unsupported_verified` | Help/adapter prove this executable is **not** a headless agent CLI (e.g. editor-only) |
| `ambiguous` | Installed but insufficient evidence |
| `unavailable` | Not installed / not assessable |

### 5.3 Cursor rule

Cursor desktop/editor CLI (`cursor --help` showing file/diff/window options without a documented headless agent invocation contract) must **not** be treated as automation-ready. Prefer `unsupported_verified` when help clearly describes an editor CLI; otherwise remain `ambiguous`. Version success alone never proves noninteractive agent capability.

### 5.4 Synthetic proof rules

- Fake executables only in automated tests
- May construct and validate **would-be** headless argv against allowlists
- May run allowlisted `--version` / `--help` / auth-status on fakes
- Must **never** include prompt text, model names as live calls, or network to provider backends in tests

---

## 6. Role and independence matrix

Roles unchanged: `planner`, `implementer`, `reviewer`, `repair_implementer`, `final_verifier`.

Eligibility requires adapter role support + discovery + auth readiness + noninteractive readiness (conditional path when auth unknown and operator flag set).

Independence categories:

- `separate_provider` — true independent-provider review
- `fresh_context_same_provider` — **not** true independence; must be labeled as such
- `deterministic_review_only` / `no_safe_independent_reviewer`

---

## 7. Host / system final verdicts

Exactly one aggregate host verdict (distinct from per-provider readiness verdicts):

| Verdict | Meaning |
| --- | --- |
| `live_smoke_ready` | At least one provider eligible for bounded live smoke (still requires separate 4D2 auth) |
| `live_smoke_ready_with_operator_auth` | Conditional eligibility; operator must approve unknown-auth path before 4D2 |
| `authentication_unverified` | Blocking: no provider has verified auth (and auth is the primary gate) |
| `noninteractive_unverified` | Blocking: auth ok/conditional but noninteractive not ready |
| `no_independent_reviewer` | Implementer path exists but no independent reviewer provider |
| `provider_not_eligible` | No installed eligible provider / policy blocked / not installed |

**Priority (first match wins after scanning records):**  
`live_smoke_ready` → `live_smoke_ready_with_operator_auth` → `authentication_unverified` → `noninteractive_unverified` → `no_independent_reviewer` → `provider_not_eligible`.

Only `live_smoke_ready*` would later unlock Round 4D2 consideration (still requiring separate human authorization). Round 4D1.2 never enables live mode.

---

## 8. CLI

```bash
ai-dev-os provider-readiness --project-id <id> [--provider ID]
ai-dev-os provider-readiness --project-id <id> --include-help-summary
ai-dev-os provider-readiness --project-id <id> --verify-noninteractive-contract
ai-dev-os provider-readiness --project-id <id> --show-host-system-verdict
ai-dev-os provider-readiness --project-id <id> --allow-unknown-auth-conditional
```

`--verify-noninteractive-contract` runs help/adapter/synthetic assessment only — never a live prompt.

---

## 9. Reporting and audit

- Round 4C evidence type remains `provider_readiness`
- Audience reports include auth advertisement/verification, noninteractive contract dimensions, host system verdict
- Audit events: auth probe attempted/skipped; noninteractive contract assessed; host verdict produced; live invocation blocked
- Always `live_provider_invocations: 0`

---

## 10. Staleness

In addition to Round 4D1 / 4D1.1 staleness inputs, records stale when:

- `authentication_probe_policy_version` changes
- `noninteractive_contract_policy_version` changes
- Host system verdict schema version changes
- Auth advertisement / noninteractive evidence fingerprints change

Not stale solely due to wall-clock age.

---

## 11. Test matrix (synthetic only)

| Case | Expectation |
| --- | --- |
| Auth status advertised + probe yes | `authenticated_verified` |
| Auth status advertised + probe no | `unauthenticated_verified` |
| No auth command in help/profile | `verification_unsupported` |
| Inconclusive auth output | `unknown` (not authenticated) |
| Forbidden auth/login argv | PolicyError; never run |
| Editor-only help (Cursor-like) | `unsupported_verified` noninteractive |
| Documented headless adapter | `supported_documented` |
| Synthetic fixture contract pass | `supported_verified` |
| Token in help | Redacted |
| Role matrix / independence labels | Fresh-context ≠ separate-provider |
| Host verdict mapping | Exact enum; priority order |
| Live counter | Always 0 |

---

## 12. Round 4D2 boundary

Round 4D1.2 **stops** after readiness evidence + host verdict. Round 4D2 requires:

1. Explicit human authorization
2. Host verdict `live_smoke_ready` or `live_smoke_ready_with_operator_auth` (plus operator auth approval if conditional)
3. Existing multi-gate live policy still disabled until separately enabled
4. No Equitify

---

## 13. Versioning

- Package: `0.8.2`
- Schema/policy constants: `4d1.2` for readiness, auth probe, noninteractive contract, role eligibility, host verdict
- Ambiguity/pin schemas remain `4d1.1.1` (unchanged)
