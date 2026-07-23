# Round 4D1.3 — Codex Headless Provider Readiness Design

**Package target:** `0.8.3` (host readiness + Codex adapter contract hardening; live still gated)  
**Readiness schema:** `4d1.3`  
**Readiness policy:** `4d1.3`  
**Authentication probe policy:** `4d1.3`  
**Authentication mode policy:** `4d1.3`  
**Noninteractive contract policy:** `4d1.3`  
**Codex event normalization schema:** `4d1.3`  
**Codex environment sanitization policy:** `4d1.3`  
**Codex compatibility policy:** `4d1.3`  
**Role eligibility policy:** `4d1.3`  
**Open-source adoption roadmap:** `1.0`  
**Baseline:** `master` @ `f330c41` (package `0.8.2`, Round 4D1.2 complete)  
**Live model invocations authorized in this round:** **0**  
**Round 4D2 status:** **LOCKED** (even if readiness succeeds)

---

## 1. Objective and non-goals

### Objective

Establish **one** trusted, authenticated, noninteractive provider path using the **official OpenAI Codex CLI**, so host readiness can reach `eligible_for_bounded_live_smoke` / `conditionally_eligible_for_bounded_live_smoke` (or the host verdict `live_smoke_ready` / `live_smoke_ready_with_operator_auth`) **without** sending any model prompt.

### Non-goals

- Any `codex exec <prompt>` (including trivial PING)
- API-key authentication as an accepted Round 4D1.3 mode
- Reading credential files, tokens, or browser storage
- Automating ChatGPT browser login
- Installing Claude Code, ACP, scanners, or other frameworks
- Enabling live provider mode or beginning Round 4D2
- Equitify access; system PATH mutation; global Cursor config changes
- Claiming Cursor is a headless agent on this host

---

## 2. Installation trust model

| Rule | Detail |
| --- | --- |
| Single method | Exactly one install path: A (existing trusted), B (npm pinned), or C (official Windows `install.ps1`) |
| Provenance | Official OpenAI/ChatGPT sources only |
| No mirrors | No Chocolatey/Scoop of uncertain provenance; no copied binaries |
| No pipe-to-IEX | Download installer to temp, hash, inspect as bounded text, then execute file |
| Pin ≠ auth | Executable pin never implies authentication or Round 4D2 authorization |
| Host-local only | Pins and readiness records stay under ignored workspace paths |

---

## 3. Official installation sources

| Method | Source |
| --- | --- |
| B | npm package `@openai/codex@<exactVersion>` from the public npm registry |
| C | `https://chatgpt.com/codex/install.ps1` downloaded to `%TEMP%\codex-install.ps1` |

Record sanitized provenance: package/binary version, mechanism, integrity hash when available, install timestamp. Never commit private install paths or full npm cache paths.

---

## 4. Package-manager selection

Decision order (Phase 5):

1. **A** — If one trusted Codex already exists → do not reinstall; resolve via 4D1.1.
2. **B** — If Codex absent and `npm`/`node` available → pin exact `npm view` version + integrity; `npm install -g @openai/codex@exact`.
3. **C** — If npm unavailable → official `install.ps1` only; do **not** install Node automatically.

**This host (baseline):** `npm`/`node` not on PATH → **Method C**.

---

## 5. Executable provenance

After install:

- Enumerate via Round 4D1.1 discovery (`Get-Command` / `where` as operator aids; engine uses its own PATH scan).
- Classify candidates (binary, npm shim, wrapper).
- Reject Equitify / untrusted roots.
- Record `installation_mechanism` in readiness metadata (sanitized).

---

## 6. Executable fingerprinting

Reuse 4D1.1:

- SHA-256 of the **resolved real target** (not path-only).
- Pin requires: fingerprint, CLI version, adapter version, policy versions.
- Paths sanitized in reports (no full user home leak).

---

## 7. Duplicate-installation handling

Reuse logical-installation collapse:

- Wrappers resolving to the same target → one logical install.
- Distinct trusted binaries remaining → `operator_selection_required` (stop; do not PATH-pick).

---

## 8. Version compatibility

- Parse `codex --version` via existing version probe.
- Codex compatibility policy `4d1.3`: known adapter + clean semver parse → `supported` unless min/max bounds reject.
- CLI version change must stale the readiness record (existing staleness rules + policy version bump).

---

## 9. Authentication verification

### Allowed status probe (new for Codex)

Exact argv: `login status` — read-only status only.

| Allowed | Forbidden |
| --- | --- |
| `("login", "status")` | `("login",)` alone |
| Existing `("auth", "status")`, `("whoami",)` | `logout`, credential-file reads, token decode |

`login` remains in the general forbidden set **except** when the full argv equals an allowlisted auth-status sequence.

### Interpretation

Parse only safe status text:

- ChatGPT / Plus / Pro / subscription language → authenticated + mode `chatgpt`
- API key language → authenticated + mode `api_key` (**unsupported for Round 4D1.3 eligibility**)
- not logged in → `unauthenticated_verified`
- inconclusive → `unknown`

Plan tier: `unavailable` unless a safe status line exposes it (do not invent).

---

## 10. Human login boundary

When status is not ChatGPT-authenticated:

1. Explain human auth required.
2. Run `codex login` **once** (operator command, not readiness probe).
3. Human completes browser ChatGPT sign-in — **no** automated clicks/credentials.
4. On human confirmation, re-run `codex login status`.
5. If human unavailable → stop `operator_auth_required` (still ship code/docs/tests).
6. If API-key mode → stop `unsupported_authentication_mode`; do **not** logout.

---

## 11. Noninteractive capability evidence

**Never** run `codex exec <prompt>`.

Evidence sources:

1. `codex --help` and `codex exec --help` (operator-safe; `exec --help` allowlisted as help-only probe).
2. Adapter-documented argv shape.
3. Exact installed CLI version.
4. Synthetic fake-executable tests.

Future Round 4D2 shape (flags taken from installed help; conceptual):

```text
codex exec --json --ephemeral --sandbox <approved-mode> -C <approved-worktree> <prompt-from-envelope>
```

OS wrapper supplies timeout, cancellation, output caps. Live remains disabled in 4D1.3.

---

## 12. Codex JSON event normalization

New module: normalize JSONL events into provider-result / safe summaries.

Supported event classes (when present): thread/session started, turn started, agent message, command request/result, file-change, approval request, usage, turn completed, error, interrupted, malformed, unexpected EOF.

Normalized outcomes distinguish: success, provider failure, auth failure, quota, timeout, cancel, malformed, incomplete turn, permission/sandbox/network blocked, stale request, policy blocked.

**Do not** persist complete raw JSONL by default — store safe summaries, counts, fingerprints, truncation metadata, final safe message when allowed, usage only when reported.

---

## 13. Working-directory binding

Future live argv uses `-C` / `--cd` (per help) **and** OS `cwd` set to the approved isolated worktree. Readiness records capability as documented/verified via help + synthetic construction tests only.

---

## 14. Ephemeral-session policy

Prefer `--ephemeral` when advertised so sessions are not written to durable Codex home. Represented in contract dimensions; not exercised with a live prompt in this round.

---

## 15. Session-persistence policy

- No copying auth files into the repo or worktrees.
- No raw session transcripts in canonical reports.
- Host Codex home remains outside the repository.

---

## 16. Sandbox policy

Require explicit `--sandbox <approved-mode>`. Never recommend `danger-full-access`, YOLO, or unrestricted filesystem. Default recommendation for 4D2: most restrictive mode the CLI documents that still allows the approved worktree task.

---

## 17. Network policy

Codex may contact OpenAI backends when authenticated. Future 4D2 envelope must state network expectation explicitly. Do not enable unrestricted network beyond provider backend needs.

---

## 18. Approval policy

Do not use `--dangerously-bypass-approvals-and-sandbox` / `--yolo`. Approvals remain under AI Development OS plan gates; Codex approval events normalize to evidence, not auto-approve.

---

## 19. Environment sanitization

Child env for future Codex runs uses filtered allowlist (existing `filter_environment`) plus Codex-specific policy:

| Variable | Policy |
| --- | --- |
| `OPENAI_API_KEY` | **Do not copy** for ChatGPT mode (presence recorded as boolean only) |
| `CODEX_HOME` | Do not copy into worktrees; do not invent isolated home by copying credentials |
| Proxy vars (`HTTP_PROXY`, etc.) | Presence booleans only; do not print values |
| Unrelated provider credentials | Never inherited |

ChatGPT-authenticated execution must not require an API key in the child environment.

---

## 20. Timeout and cancellation

OS-level timeout via existing safe runner / probe timeout policy. Cancellation via process-tree cancel request store contract. Represented as supported by wrapper even when CLI lacks a flag.

---

## 21. Output limits

Reuse probe/output truncation policies. Cap stdout/stderr; mark truncation in envelopes.

---

## 22. Error classification

Map Codex/normalized failures into existing `FailureClass` / readiness failure classes; extend only with additive metadata, not a competing vocabulary.

---

## 23. Role eligibility

Update Codex readiness profile roles to include **implementer** and **repair_implementer** (first headless implementer candidate), while retaining reviewer/planner/final_verifier as technically possible.

Expected matrix after success:

- Codex implementer: eligible (if auth + NI + install ok)
- Codex reviewer: technically possible, same provider
- Cursor: editor only
- Claude: not installed
- Separate-provider independent review: unavailable

---

## 24. Reviewer-independence limitations

Fresh-context same-provider review ≠ independent review. Do not weaken independence policy. Round 4D2 recommendation: Codex implementation + deterministic non-model validation, **or** labeled limited fresh-context Codex review — never claim separate-provider independence.

---

## 25. Round 4D2 request envelope

Produce a **proposed** configuration only (no task/plan creation required beyond synthetic fixtures):

- provider `codex`; pinned executable; CLI version; auth mode `chatgpt`
- project `calculator-demo`; isolated worktree; starting commit binding
- sandbox explicit; network documented; timeout + max output; JSON + ephemeral
- max repair rounds: 1; reviewer mode limited independence or deterministic-only
- separate explicit authorization required; live mode off until authorized

---

## 26. Staleness rules

Existing staleness + bumps to readiness/auth/NI/compat policy versions. Codex CLI version change or fingerprint change invalidates prior readiness.

---

## 27. Reporting integration

Reuse Round 4C audience reports from readiness records. Counts:

- `live_provider_invocations: 0`
- `model_responses_generated: 0`

No raw auth or full PATH in reports.

---

## 28. Testing strategy

Synthetic fake Codex executables only in pytest. Cover:

- `login status` allowlist vs bare `login` forbid
- ChatGPT vs API-key mode classification
- JSONL normalization / malformed / incomplete
- env sanitization (no API key copy)
- role matrix (implementer eligible; fresh ≠ independent)
- noninteractive from help + synthetic
- regression of prior 4D1.x suites

No internet; no real Codex in CI.

---

## 29. Rollback and uninstall guidance

Operator may remove the Codex install per the mechanism used (uninstall script / remove npm global / remove user install dir). Delete host-local pins under `workspace/provider_pins/`. Product code remains usable with `not_installed` discovery. No automated uninstall in-repo.

---

## 30. Explicitly deferred ACP integration

Agent Client Protocol is **planned** as optional transport later. Not installed or implemented in Round 4D1.3.

---

## 31. Explicitly deferred external security tools

zizmor, pip-audit, Gitleaks remain planned separate adapters. **Not** installed in this round.

---

## 32. Round 4D2 authorization boundary

Readiness success does **not** authorize Round 4D2. Live mode stays disabled. No `codex exec` with prompts. Separate explicit user authorization required before any live smoke.

---

## Implementation gaps vs baseline code (source of truth)

| Gap | Fix in 4D1.3 |
| --- | --- |
| `login` forbidden; no `login status` allowlist | Exact-sequence exception + auth patterns |
| No ChatGPT vs API-key mode | `authentication_mode` metadata + eligibility gate |
| Codex roles omit implementer | Profile roles updated |
| No JSONL normalizer | New Codex event normalization module |
| Env may not document Codex specifics | Codex env sanitization helpers + presence booleans |
| `exec` forbidden entirely | Allow `("exec", "--help")` only as help probe |
| Live path exists but refused | Keep refused; harden preview/contract only |
| npm absent on host | Method C install |

---

## Contradiction resolutions

1. **`login` forbidden vs `login status` required** — Forbid bare login in probes; allow exact `("login", "status")`. Human `codex login` is an operator gate outside the probe runner.
2. **`exec` forbidden vs `exec --help` evidence** — Allow only `("exec", "--help")` / equivalent help-only tails; never prompt tokens.
3. **Eligibility vs independence** — Implementer may be eligible while independence remains `fresh_context_same_provider_only` / unavailable; host may still be live-smoke ready with conditions.
4. **Version bump** — Prefer `0.8.3` (readiness hardening lineage). Adapter contract additions are readiness-facing; live remains off → not `0.9.0`.
