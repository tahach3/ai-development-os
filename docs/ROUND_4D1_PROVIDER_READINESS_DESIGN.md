# Round 4D1 — Provider Readiness Design

**Package target:** `0.8.0`  
**Readiness schema:** `4d1.1`  
**Readiness policy:** `4d1.1`  
**Baseline:** `master` @ `d0a1d33` (package `0.7.0`, Round 4C complete)  
**Live model invocations authorized in this round:** **0**

---

## 1. Purpose

Determine, safely and reproducibly, whether any locally installed AI coding-provider CLI represented by an existing adapter is **technically eligible** for a *future* bounded live orchestration smoke test (Round 4D2), without sending any model prompt, completion, or coding request.

Round 4D1 answers: what is installed, which executable would run, whether installation is ambiguous, version/auth/noninteractive readiness, role matrix, independence options, exact blockers, and the safest authorized 4D2 configuration — using discovery/version/help/auth-status probes only.

## 2. Non-goals

- Live model requests, prompts, completions, or coding tasks
- Paid API use, API-key creation, login/refresh/browser auth
- Reading credential DBs/token files; printing tokens or full env/PATH
- Installing/upgrading CLIs; modifying PATH or provider config
- Enabling live mode; calculator-demo implementation; AI worktree changes
- Dashboard, browser automation, cloud workers, merge/deploy/release
- New orchestration frameworks or arbitrary shell
- Treating simulation results as live eligibility proof
- Equitify access or registration

## 3. Threat model

| Threat | Mitigation |
| --- | --- |
| Accidental live prompt | Strict argv allowlists; no prompt/agent/approval flags; `live_provider_invocations` counter fixed at 0 |
| Token / env leakage | Never open credential files; redact probe output; never print full PATH/env |
| Ambiguous executable silently selected | Multi-candidate discovery; block when precedence unclear |
| Help text as executable instructions | Treat help as untrusted data; never re-exec help content |
| Symlink / path escape | Resolve + trust rules; Equitify / prohibited path rejection |
| Stale readiness reused | Staleness on commit, adapter, policy, exe fingerprint, CLI version, config |
| Live mode flipped on | Policy and CLI never mutate `allow_live` / provider mode |
| Equitify inspection | `assert_not_equitify_blob`; project registration gates |

## 4. Provider-readiness lifecycle

1. **Select scope** — registered project (required) + optional provider filter  
2. **Discover** — multi-method executable candidates (no PATH dump)  
3. **Probe** — allowlisted version/help; optional safe auth-status only when adapter permits  
4. **Assess** — version compatibility, noninteractive contract (code/docs/help only), roles, independence  
5. **Decide** — deterministic policy → readiness verdict (never enables live)  
6. **Persist** — versioned JSON record under `workspace/provider_readiness/`  
7. **Report** — Round 4C audience renders (executive / operator / developer / auditor)  
8. **Revalidate** — staleness check without model invocation  

## 5. Read-only probe policy

Allowed argv tokens (provider-specific subsets): `--version`, `version`, `-V`, `--help`, `help`, `-h`, and adapter-declared read-only auth-status tokens (e.g. `auth`, `status`) only when explicitly profiled as safe.

Forbidden: prompts, task text, interactive sessions, completion/agent flags, auto-approve, unrestricted tools, login/logout/refresh, install/upgrade.

When safety is uncertain → status `unverified` / `verification_unsupported`; **do not probe**.

## 6. Provider discovery model

Discover candidates via:

1. Configured path (if set and allowlisted basename)
2. Python `shutil.which` / PATH resolution (record basename only in public output)
3. Windows: `where.exe <basename>` when available
4. Optional PowerShell `Get-Command` metadata when safely invocable

Statuses: `installed` | `not_installed` | `ambiguous_installation` | `executable_untrusted` | `probe_failed`

Do not add providers merely because something is installed locally. Only adapters registered in code are audited.

## 7. Executable provenance model

Record for the selected (or candidate) executable:

- basename
- sanitized location (directory class: `path_entry`, `configured`, `user_local`, `unknown` — never dump full machine PATH)
- SHA-256 of file contents when safely readable as a regular file
- resolution methods that found it
- duplicate count
- selection rule (`single_candidate`, `path_precedence`, `configured_override`, `none`)

## 8. Duplicate-installation handling

If two or more distinct resolved paths match allowlisted basenames and precedence is not deterministic under policy → `ambiguous_installation`; **no silent selection**. Precedence may be accepted only when a single PATH winner is unambiguous and fingerprints differ only by identical content, or when configured path uniquely selects one trusted file.

## 9. CLI-version compatibility

Parse version from probe stdout/stderr with bounded regex. Compatibility:

- `supported` — parsed and within adapter profile constraints (or unconstrained known adapter with clean parse)
- `unsupported` — outside declared range
- `unverified` — parse failed constraints unknown
- `malformed` — unparseable output
- `unavailable` — no version probe run / not installed

A readiness decision bound to version V must not be reused for version W.

## 10. Capability-verification states

Capabilities (worktree bind, structured output, timeout, cancel, output bounds, env sanitize) are classified from **adapter code + documented flags + help summary**, never from live prompts:

- `supported_verified` — proven by synthetic adapter contract tests / explicit adapter guarantees
- `supported_documented` — adapter/docs/help claim support
- `unsupported_verified` — adapter explicitly lacks support
- `ambiguous` / `unavailable`

Help output ≠ execution proof.

## 11. Authentication-verification states

`authenticated_verified` | `unauthenticated_verified` | `reported_authenticated` | `unknown` | `verification_unsupported` | `verification_failed`

Rules:

- Never infer auth from credential file existence
- Never open token DBs / browser storage
- Unknown ≠ authenticated; unknown ≠ unauthenticated
- Only dedicated allowlisted auth-status commands may produce verified states

## 12. Noninteractive-readiness states

`supported_verified` | `supported_documented` | `unsupported_verified` | `ambiguous` | `unavailable`

Cursor desktop ≠ automation CLI. Editor presence alone → not noninteractive agent.

## 13. Role eligibility

Roles: `planner`, `implementer`, `reviewer`, `repair_implementer`, `final_verifier`.

Per role: technically supported, adapter-supported, policy-allowed, auth-ready, noninteractive-ready → final: `eligible` | `conditionally_eligible` | `ineligible` | `unverified` | `policy_blocked`.

## 14. Reviewer independence

`separate_provider_available` | `separate_model_available` | `fresh_context_same_provider_only` | `independence_unverified` | `unavailable`

Do not claim true independence when same provider/model/context/session is reused.

## 15. Worktree-binding requirements

Live smoke (4D2) will require session worktree binding via existing Round 3A/3B gates. Round 4D1 records whether the adapter/request contract supports binding — without creating provider-invoking worktrees. Synthetic path confinement checks allowed without provider spawn.

## 16. Structured-output requirements

Adapter must normalize success / failure / timeout / malformed / cancelled. Status from adapter contracts and fixtures, not live calls.

## 17. Timeout and cancellation requirements

Probes: short bounded timeouts (default 5s, max 15s), process kill on timeout. Cancellation support assessed from existing cancel request store / adapter contract.

## 18. Output-limit requirements

Stdout/stderr truncated to discovery limits; ANSI stripped; summaries only in records (no full help dump by default).

## 19. Safe working-directory requirements

Probes run with sanitized env; cwd must not escape repo confinement when a project cwd is used; Equitify paths rejected.

## 20. Environment-sanitization requirements

Reuse `filter_environment`. Never serialize full env into readiness records.

## 21. Live-policy gating

Readiness audit **never** sets `allow_live` or `LIVE_LOCAL_CLI_ALLOWED`. Records report current mode and `live_policy_status: disabled_for_round_4d1` (or equivalent). Eligibility for *future* smoke ≠ live enabled now.

## 22. Evidence model

Probe records: command identity, adapter version, exe fingerprint, timeout, limit, exit code, sanitized summary, parsed version, parse status, failure class. Audit events for discovery/probes/decisions/blocks. Round 4C `EvidenceItem` type `provider_readiness`.

## 23. Readiness verdicts

Per provider / aggregate:

- `eligible_for_bounded_live_smoke`
- `conditionally_eligible_for_bounded_live_smoke`
- `installed_but_authentication_unverified`
- `installed_but_noninteractive_unverified`
- `installed_but_version_unsupported`
- `ambiguous_provider_installation`
- `no_eligible_provider`
- `policy_blocked`
- `probe_failed`
- `invalid_record`

Installed ≠ eligible.

## 24. Failure classes

Reuse / extend: `none`, `policy_rejected`, `not_installed`, `unsupported`, `timeout`, `malformed_output`, `probe_failed`, `ambiguous_installation`, `untrusted_executable`, `auth_unverified`, `stale_record`, `equitify_rejected`.

## 25. Stale-readiness handling

Stale when any of: repo commit, adapter version, readiness policy version, exe path/fingerprint, CLI version, provider config fingerprint, live-execution policy, project registration fingerprint, safe-runner policy version change.

Not stale solely due to wall-clock age (age reported separately).

## 26. Fingerprints and integrity

Record fingerprint over canonical payload excluding volatile display-only fields. Executable content SHA-256 when safe. Source fingerprints for policy/config/adapter.

## 27. CLI design

Command: `ai-dev-os provider-readiness`

| Flag | Behavior |
| --- | --- |
| `--provider` | Single provider |
| `--project-id` | Required registered project |
| `--json` | Machine-readable |
| `--output` | Write record path |
| `--validate` | Validate/stale-check existing record |
| `--show-combinations` | Independence matrix |
| `--include-help-summary` | Include sanitized help summary |

Always emit `live_provider_invocations: 0`. Read-only defaults.

## 28. Storage design

`workspace/provider_readiness/` (gitignored, `.gitkeep` tracked). Filenames: `{readiness_id}.json`. No tokens, raw env, full help, or credential paths.

## 29. Reporting design

Integrate Round 4C audiences:

- **Executive:** smoke ready?, combination, top blocker, human action, model requests = 0  
- **Operator:** actionable blockers and next steps  
- **Developer:** adapters, resolution, versions, matrix, suggested 4D2 envelope  
- **Auditor:** sanitized probes, fingerprints, policy version, redactions, proof of zero prompts  

## 30. Backward compatibility

- Prior provider discovery / adapters unchanged in behavior for simulation  
- New subsystem additive  
- Schema `4d1.1` independent of provider `3b.1` and reporting `4c.1`  
- Package bump to `0.8.0` for new readiness subsystem  

## 31. Test matrix

Fake executables only; 10 synthetic scenarios; cover discovery/auth/noninteractive/roles/staleness/CLI/reporting/leakage; no real providers, network, or auth.

## 32. Round 4D2 authorization boundary

4D2 requires **separate** explicit human authorization. 4D1 must not:

- enable live mode
- send prompts
- claim smoke completed

Recommended 4D2 config is advisory output only.

## 33. Explicitly deferred

- Actual live smoke / model invocations  
- Provider install/upgrade automation  
- Auth login flows  
- Calculator-demo live implementation  
- Equitify connection  
- Auto-merge / deploy  
- New provider adapters beyond existing registry  

---

## Contradiction resolutions

| Tension | Resolution |
| --- | --- |
| Adapter claims `assumed_external_cli_session` vs auth unknown | Readiness uses stricter vocab; assumed ≠ verified → `unknown` / `verification_unsupported` |
| `supports_noninteractive=True` on detect vs proof | Map to `supported_documented` unless synthetic verified contract |
| Cursor on PATH vs agent CLI | Desktop/editor alone → ambiguous / noninteractive unavailable |
| Eligible verdict vs live disabled | Eligibility is *future* smoke readiness; live remains off |
| Help shows auth subcommands | Do not execute help-derived commands; only pre-allowlisted argv |

## Phase 2 inspection summary (code truth)

| Question | Finding |
| --- | --- |
| Supported by adapters | `simulated`, `claude_code`, `codex`, `cursor` |
| Config-only | none beyond adapter-backed IDs |
| Simulation | `simulated` only executes fixtures |
| Live claims | All adapters `live_execution_permission=False`; live gates refuse |
| Multi-install | Current discovery returns first `which` hit — **insufficient** → 4D1 multi-candidate |
| Provenance / version policy | Partial — 4D1 adds fingerprints + compatibility |
| Auth | Inferred/assumed — **not verified** |
| Noninteractive | Assumed from adapter flags — not live-proven |
| Accidental live on readiness | Discovery already allowlists version/help; 4D1 keeps stricter allowlists + counter |
| Reports | 4C does not yet distinguish install/auth/tech/policy/live — 4D1 adds readiness evidence |
