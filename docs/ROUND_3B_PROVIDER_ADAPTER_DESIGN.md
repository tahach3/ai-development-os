# Round 3B — Controlled Provider CLI Adapter Design

**Status:** Approved for implementation in this round  
**Scope:** Provider-neutral contracts, safe discovery, fail-closed config, simulated provider, CLI adapter shells (no live model calls by default), normalized result envelopes, operator CLI, synthetic validation on `calculator-demo`  
**Not in scope:** Live provider model execution (separately authorized smoke only), Equitify, paid APIs, HTTP model calls, LangChain/CrewAI/AutoGen, dashboards, browser automation, auto-merge/push/deploy

**Follow-on:** Round 4D1 (`docs/ROUND_4D1_PROVIDER_READINESS_DESIGN.md`, `docs/PROVIDER_READINESS_STANDARD.md`) adds readiness/eligibility auditing without live prompts.

**Package version target:** `0.4.0` (schema `3b.1`; Round 3A envelopes remain `3a.1`)

---

## Self-review vs existing boundaries (contradictions resolved)

| Existing rule / Round 3A stance | Round 3B resolution |
| --- | --- |
| Adapters always `manual_handoff_required` | **Manual handoff adapters remain.** Provider CLI adapters are a **parallel lane** with their own `automation_status` values (`manual_handoff`, `simulated_provider_execution`, `discovery_only`, `live_local_cli` only when all live gates pass). |
| Round 3A `safe_exec` blocks `claude`/`cursor`/`codex` | **Unchanged for pytest lane.** Provider discovery/live uses a **separate** argv-allowlisted path (`provider_safe_exec`) that never opens shell and never inherits secret env. Live spawn is opt-in and gated; Round 3B tests never take it. |
| No spawning provider CLIs | Round 3B may run **discovery-only** (`--version` / `--help`) and **simulated** fixtures. **Live model argv is coded but refuse-by-default.** |
| No credentials inspection | Discovery never reads auth files, cookies, tokens, or login state. Auth category is `unknown` / `assumed_external` / `not_applicable` without data. |
| High/critical never auto-approve | Enabling a provider does **not** auto-authorize high/critical tasks. Task-level execution approval + plan approval still required; high/critical additionally require explicit live allowlist entry and never auto-enter live. |
| Workspace artifacts under this repo | Provider results under `workspace/provider_executions/`; config under `config/providers.yaml` (example provided; defaults fail-closed in code). |

No contradictions remain after separating: (1) manual handoff, (2) Round 3A pytest safe exec, (3) provider discovery/sim/live lane.

---

## 1. Provider adapter interface

Each provider implements `ProviderAdapter`:

- `provider_id`, `adapter_version`
- `describe_capabilities()` → `ProviderCapability`
- `discover()` → installation/availability without install or auth inspection
- `build_request(...)` / `validate_bindings(...)`
- `preview_invocation(request)` → sanitized argv + mode (never secrets)
- `execute(request)` → routes by configured mode; default refuse live
- `normalize_result(...)` → versioned `ProviderResultEnvelope`
- `cancel(request_id)` when safely supported (cooperative for simulated; best-effort for live)

Manual handoff (`prepare-handoff`) continues via existing `adapters/` package.

---

## 2. Provider capability model

Capabilities are declarative and honest:

| Field | Meaning |
| --- | --- |
| `supported_roles` | Subset of `claude` / `cursor` / `codex` logical roles |
| `supported_modes` | `disabled`, `discovery_only`, `simulated`, `manual_handoff`, `live_local_cli_allowed` |
| `supports_noninteractive` | True only if discovery proves a CLI that can run non-interactively |
| `supports_stdin_prompt` / `supports_file_prompt` | How context may be transferred |
| `network_use` | `none_expected` \| `may_contact_provider_backend` \| `unknown` |
| `auth_category` | `not_applicable` \| `unknown` \| `assumed_external_cli_session` (never secrets) |
| `live_execution_permission` | From config + gates, not from “CLI found” |
| `notes` | Human-readable honesty (e.g. Cursor desktop ≠ automation CLI) |

---

## 3. Installed-CLI discovery without installation

- Never install packages or download binaries.
- Never recursively search the filesystem.
- Resolution order: configured absolute path (if allowlisted basename) → `PATH` lookup via `shutil.which` for known basenames only.
- Discovery argv only: `--version` or `--help` (provider-specific allowlist).
- Short timeout (default 5s, max 15s), output capped.
- No login / auth / account commands.
- Missing CLI → `not_installed`; ambiguous → `ambiguous`; found version string → `detected` (not “verified for live”).

---

## 4. Exact executable resolution policy

1. Basename must be in provider allowlist (`claude`, `claude.exe`, `codex`, `codex.exe`, `cursor`, `cursor.exe`, `agent` only if configured and documented).
2. Absolute configured paths: resolve, require basename match, reject Equitify path blobs and shell metacharacters.
3. Reject arbitrary paths outside allowlist basenames.
4. Simulated provider uses no external executable (`executable_identity=simulated`).

---

## 5. Version detection

- Capture stdout/stderr from discovery argv; take first line matching a conservative version pattern; truncate to 200 chars.
- Store as `detected_version` string or `null` if unparsable.
- Failure to parse ⇒ `version_unknown` capability note, not a live-ready claim.

---

## 6. Supported invocation modes

| Mode | Behavior |
| --- | --- |
| `disabled` | All execute/preview-live refused |
| `discovery_only` | Version/help only |
| `simulated` | Fixture-driven; real policy/session/audit/normalize paths |
| `manual_handoff` | Produce/require manual handoff; no CLI spawn |
| `live_local_cli_allowed` | Live argv allowed **only** when every live gate passes |

---

## 7. Disabled, simulated, manual, and live-enabled states

Default global + per-provider mode: **`disabled`** (fail-closed).  
Example config may set `simulated` for the synthetic provider in operator docs; shipped default remains disabled until operator writes config.  
Code paths that run tests inject an in-memory or temp config with `simulated` enabled for `simulated` provider only.

---

## 8. Explicit live-execution approval requirements

Live requires **all**:

1. Provider mode is `live_local_cli_allowed`
2. Project registered and active
3. Project `metadata.allowed_providers` includes provider id
4. Task eligible for assigned role (routing / role match)
5. Plan approved; fingerprint matches
6. Session active; worktree valid; starting commit matches session + request
7. Command policy approves argv
8. Task-level `provider_execution_approved=true` (and approver) in task metadata
9. No prohibited / Equitify paths
10. Risk high/critical: additional explicit `allow_high_risk_live=true` on task metadata — still never auto merely from provider enablement

Round 3B validation **never** sets live mode.

---

## 9. Task, plan, session, worktree, and role binding

`ProviderRequest` freezes:

- `task_id`, `plan_id`, `approved_plan_fingerprint`
- `project_id`, `session_id`, `worktree_id` (session worktree path id/path)
- `starting_commit`, `role`
- `context_or_handoff_fingerprint`
- `provider_id`, `adapter_version`, `invocation_mode`
- `timeout_seconds`, `output_limit_bytes`

On execute: reload task/plan/session and **reject** on any mismatch (project, role, session, worktree, plan fingerprint, commit, context fingerprint).

---

## 10. Prompt/context transfer through bounded files or standard input

- Preferred: write bounded handoff/context artifact under session workspace; pass **path** in argv (not inline secrets).
- Stdin only if capability declares it and content is size-capped.
- Status CLI never dumps full private prompts; show fingerprints and paths only.

---

## 11. Command argument construction

- Argv arrays only; `shell=False`.
- Template per provider; no freeform operator argv.
- Metacharacter reject on tokens.
- Preview shows sanitized argv (absolute exe path ok; no env secrets).

---

## 12. Environment-variable policy

Reuse Round 3A `filter_environment` allowlist + secret-name deny.  
Provider children do not receive `PYTHONPATH`, API keys, tokens, or provider credential env vars.

---

## 13. Authentication boundary

- Never read/print/persist credentials, cookies, auth files, or tokens.
- `auth_category` is categorical only.
- Live assumes operator already authenticated externally if CLI requires it; OS does not verify login.

---

## 14. Timeout and cancellation behavior

- Default provider timeout 30s; hard ceiling 120s (discovery ≤ 15s).
- Timeout → `timeout_status=true`, failure class `timeout`.
- Cancel: cooperative flag for simulated; live (future) best-effort terminate if PID tracked — Round 3B tests cover simulated cancel only.

---

## 15. Output limits and sanitization

- Default 65_536 bytes/stream; truncate + flags.
- Audit stores truncated stdout/stderr only.
- Result artifact path separate; bounded write under workspace.

---

## 16. Provider result normalization

Versioned envelope schema `3b.1` with all fields in Phase 7 brief (see § schemas).  
Malformed/incomplete → fail closed; cannot feed impl/review/repair until validated.

---

## 17. Retry policy

- Default `max_retries=0` for live/sim unless fixture requests retry count recording.
- Retries never bypass gates; duplicate fingerprint still detected.
- Retry count recorded on envelope.

---

## 18. Idempotency and duplicate-run prevention

- `request_fingerprint` = hash of binding + mode + provider + adapter version (stable).
- If prior non-rejected envelope exists with same fingerprint and status in `{success, running, timeout}` → `duplicate_request_status=true` and reject new spawn (or return prior for show).

---

## 19. Audit records

- Persist under `workspace/provider_executions/<request_id>.json`
- Deterministic `json.dumps(..., sort_keys=True, indent=2)`
- Link optional Round 3A session id; do not mix schemas (`3a.1` vs `3b.1`)

---

## 20. Provider-specific failure classification

| Class | Examples |
| --- | --- |
| `policy_rejected` | Gates, bindings, disabled |
| `not_installed` | Discovery miss |
| `unsupported` | Ambiguous/unsupported CLI |
| `timeout` | Deadline |
| `cancelled` | Cooperative cancel |
| `nonzero_exit` | Process exit ≠ 0 |
| `malformed_output` | Schema fail |
| `missing_artifact` | Expected file absent |
| `duplicate_request` | Idempotency hit |
| `stale_binding` | Plan/commit/context mismatch |
| `provider_error` | Generic spawn/normalize error |
| `none` | Success |

---

## 21. Compatibility and adapter versioning

- Package `0.4.0`; adapter_version per provider e.g. `3b.1`
- Result schema `3b.1`; do not mutate `3a.1` execution envelopes
- Unknown future schema versions fail closed on load-as-input

---

## 22. Synthetic provider fixtures

Simulated provider fixture ids:

`success_impl`, `success_review`, `provider_rejection`, `malformed_output`, `timeout`, `nonzero_exit`, `truncated_output`, `missing_artifact`, `duplicate_request`, `stale_plan`, `stale_commit`, `cancelled`

Fixtures live under `tests/fixtures/provider/` and/or in-code deterministic payloads.

---

## 23. Threat model

| Threat | Control |
| --- | --- |
| Silent live model spend | Default disabled; live needs all gates; tests never live |
| Shell injection | argv arrays; meta reject |
| Arbitrary exe | Basename allowlist |
| Secret leakage | Env filter; no auth file read; status sanitization |
| Binding retarget | Frozen fingerprints; reject mismatch |
| Equitify bleed | Sentinel checks |
| Provider install surprise | No install; discovery only |
| Overclaim Cursor automation | Honest `ambiguous` / unsupported noninteractive |
| Audit poisoning | Validate before report intake |

---

## 24. Acceptance criteria

See Phase 9 matrix: Equitify/unregistered reject; disabled refuse; discovery non-live; unsupported honesty; arbitrary exe/shell reject; secrets absent from audit; immutable bindings; unapproved plan refuse; live refuse without permissions; simulated uses policy+audit; duplicates; timeout/cancel normalize; malformed fail closed; deterministic fingerprints; manual handoffs still work; Round 1–3A tests green.

---

## 25. Explicitly deferred functionality

- Authorized live smoke of Claude/Codex/Cursor model calls
- Broader command profiles / multi-provider fan-out supervisors
- Equitify connection
- Paid HTTP APIs / LangChain / CrewAI / AutoGen
- Dashboard / browser automation
- Auto-merge / auto-push / deploy
- Credential brokers / login automation
- Self-modifying safety policy
