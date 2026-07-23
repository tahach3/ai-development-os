# AI Development OS — Claude Handoff (Progress Discussion)

**Purpose:** Brief an external AI (Claude Code or similar) for a **next-progress** discussion.  
**Generated:** 2026-07-23 (post Round **4D1.3**)  
**Workspace:** AI Development OS only — **do not touch Equitify.**

---

## Executive summary

AI Development OS (`ai-dev-os`) is a **local-first control plane** for structured multi-model software work (Claude / Cursor / Codex). It validates tasks, routes deterministically, gates plans, supports manual handoffs, allowlisted pytest in worktrees, simulated orchestration, local + private GitHub CI, evidence-first reporting, and **provider readiness auditing** — without calling paid LLM APIs by default and **without live model prompts** until Round **4D2** is separately authorized.

| Fact | Value |
| --- | --- |
| GitHub | [`tahach3/ai-development-os`](https://github.com/tahach3/ai-development-os) (**private**) |
| Branch | `master` tracking `origin/master` |
| **Committed HEAD** | `330ffa3d47d618a124d143d87cfcfadf50e85807` — *Complete Round 4D1.3 Codex headless-provider readiness.* |
| **Committed package** | **`0.8.3`** (Round **4D1.3** complete on `master`) |
| Working tree | **Dirty (out-of-band WIP only)** — untracked Phase **B3.2** memory SQLite modules (`sqlite_*`, `tests/memory/`); **do not stage/commit** with provider work |
| Remote CI | GitHub Actions `ci` **success** on HEAD — run [`29982270706`](https://github.com/tahach3/ai-development-os/actions/runs/29982270706) |
| Live prompts | **0 authorized / 0 issued** (`live_provider_invocations: 0`); Round **4D2 LOCKED** until separate explicit authorization |
| Equitify | **Disconnected** — hard boundary |

**Round 4D1.3 status: COMPLETE and merged.** Official Codex CLI installed and ChatGPT-authenticated on the operator host; readiness code/tests/docs at package **`0.8.3`** / schema **`4d1.3`**. Host is conditionally eligible for a future bounded live smoke — **readiness ≠ live**. Do not start Round 4D2 without a separate explicit human authorization.

**Host readiness (post-4D1.3):**

- Codex CLI **0.145.0** installed via official Method C (`install.ps1` + hashed release asset); ChatGPT auth verified via allowlisted `codex login status` only
- Host verdict: `live_smoke_ready_with_operator_auth` / `live_smoke_ready_with_conditions`
- Aggregate: `conditionally_eligible_for_bounded_live_smoke`
- Codex: **conditionally eligible as implementer**; reviewer independence = `fresh_context_same_provider_only` (**not** true separate-provider independence)
- Cursor: still **editor-only** on this host (not a headless agent)
- Claude Code: **not installed**
- `live_provider_invocations: 0`
- Recommendation artifact (not executed): `workspace/provider_readiness/round4d2_recommendation.json` — `live_execution_authorized: false`, `round_4d2_gate: locked`

---

## Addendum — Round 4E, 4F, and Round 4A hardening (package `0.8.7`)

Since the last handoff snapshot, three more additive local-CI rounds shipped and were reconciled onto `master` (no new round of the live/provider track; Round 4D2 stays **LOCKED**):

- **Round 4E** (`0.8.5`): multi-project boundary enforcement — `project_boundaries` in CI policy, a pure path/import checker, wired into `validate-change` and optional `ci-boundaries`.
- **Round 4F** (`0.8.6`): CI ergonomics — opt-in `--isolate-flaky` (honesty rule: fail-then-pass → non-blocking `flaky_test_detected`, never a silent pass), `--coverage` notes (optional `[cov]` extra, never a gate), and the canonical `ci-targeted` fast-signal command (`ci_targeted.py` + `ci_pytest_ergonomics.py`, integrated with the real `CIRun` envelope).
- **Round 4A hardening** (`0.8.7`, this pass): cross-platform fix — `sanitize_executable_location` now redacts Windows drive/UNC paths on POSIX too, closing a username-leak that also made one test red on Linux. Added `ci-history` / `ci-compare` (`ci_history.py`) to index `workspace/ci_runs/*.json` and diff two runs deterministically — `ci-compare --against-previous` exits non-zero only on a genuine new regression. Added `ci-check` / `ci-targeted --format md` for deterministic human-readable reports (`ci_report.py`), plus a `ci_run_comparison` schema (`4a.1`).
- **Reconciliation note:** an earlier, independently-built targeted-test selector in this pass duplicated what Round 4F had already shipped as `ci-targeted`. Rather than ship two competing implementations, the earlier one (and its now-unused schema) was dropped during the merge in favor of Round 4F's, which was already tested, integrated with flaky isolation, and green on CI.
- **Guarantees:** fixed CI `STAGE_ORDER` and `4a.1` schema unchanged throughout; no new runtime dependency beyond 4F's optional dev-only `coverage` extra; workflow permissions/secrets untouched; Equitify disconnected. Also fixed during this window: a genuine (non-flaky-isolation) root-cause bug in the Round 3C repair-simulation harness — stale `.pyc` bytecode under same-second/same-size mutation rewrites — restoring true determinism to `test_test_fail_then_repair`. Design: `docs/ROUND_4A_LOCAL_CI_HARDENING_DESIGN.md`, `docs/ROUND_4E_BOUNDARY_ENFORCEMENT_DESIGN.md`, `docs/ROUND_4F_CI_ERGONOMICS_DESIGN.md`.

---

## 1. What this project is

A Python package + operator CLI that acts as the **workflow authority** for:

- Project registration (scoped allowlist)
- Tasks, routing, budgets, minimal context packets
- Plan create/submit/approve + fingerprints
- Manual handoff packets (Claude / Cursor / Codex)
- Safe local pytest in confined worktrees (3A)
- Controlled provider adapters — discovery / simulate / gated live shells (3B)
- Bounded simulated orchestration + stalemate detection (3C)
- Local CI gates + private remote GitHub Actions (4A/4B)
- Evidence-first multi-audience reporting (4C)
- Provider readiness / ambiguity / auth / noninteractive / Codex headless audit (4D1–**4D1.3**)

**It is not:** an autonomous zero-click agent runner, a paid API client, LangChain/CrewAI/AutoGen, a dashboard, browser automation, or an Equitify integration.

**Roles (intended):** OS = controller/safety authority; Claude plans; Cursor implements (interactive editor); Codex/GPT independent review when a true independent path exists. Cursor’s three-model UI is a **client**, not a competing task/approval/memory authority.

---

## 2. Hard boundaries

| Boundary | Rule |
| --- | --- |
| Equitify | Disconnected until the exact user phrase: *Connect the AI Development Operating System to Equitify.* Registration rejects `equitify` / `equitify-machine`. Do not open, inspect, or integrate that tree. |
| Live model prompts | **Forbidden** until Round **4D2** is **separately authorized** after readiness evidence. Readiness ≠ live. |
| Simulation vs live | Round 3C orchestration and provider `simulate` are **not** live. Simulated fixtures must never be reported as live success. |
| Cursor on this host | Desktop/PATH CLI is **editor-only**; `supports_noninteractive=false` for headless agent use. Do not claim Cursor as automation. |
| Network / secrets | No product network model calls; no API keys in repo; no credential-file inspection. |
| Frameworks | No LangChain / CrewAI / AutoGen. |
| Git mutation | Inspect-only (+ confined worktree add/list/remove in 3A). No reset/push/merge/commit from product automation. |
| CI | `permissions: contents: read` only; no repo secrets; no live providers in Actions; no auto-merge/deploy. |
| Scope | Only projects in `config/projects.yaml`. Demo target: `demo_projects/calculator-demo`. |

Details: `docs/PROJECT_BOUNDARIES.md`, `docs/SECURITY_MODEL.md`, `docs/ZERO_CLICK_LIMITATIONS.md`.

---

## 3. Timeline of rounds (with commits)

| Round | Status | Key commit(s) | Notes |
| --- | --- | --- | --- |
| **R1 foundation** | Done | `3fcef7e` | Registry, tasks, routing, context, git inspect, manual adapters, CLI, docs, tests |
| **R2 plans/approval** | Done | `a41c0f4` | Plans, gates, fingerprints, repair, calculator-demo, OSS assessment |
| Chronicle export | Docs | `d4c9133`, `f1d1029` | Project chronicle + downloadable export |
| **R3A safe exec / worktrees** | Done | `eb6aba3` | Sessions, confined worktrees, allowlisted pytest, envelopes `3a.1` |
| **R3B provider adapters** | Done | `305c0d7` | Contracts, discovery, simulated fixtures, CLI shells; package `0.4.0` |
| **R3B live smoke blocked** | Recorded | `87068fd` | `blocked_before_execution`; zero live calls; Claude/Codex `not_installed`; Cursor editor-only |
| **R3C orchestration + stalemate** | Done | `734b8c8` | Simulated impl→test→review→repair; package `0.5.0` |
| **R4A local CI** | Done | `eeebbe7` | `ci-check`, `validate-change`, workflow definition; package `0.6.0` |
| **R4B private GitHub CI** | Done | First success on `a01f672`; closeout `9f7ec38` | Run [`29930178622`](https://github.com/tahach3/ai-development-os/actions/runs/29930178622) success; least-privilege workflow |
| Phase A/B1/B2 docs | Done | `a01f672`, `382eb8a`, `09cf1e6` | Master blueprint + shared-memory design/plan (docs only at those commits) |
| **R4C evidence-first reporting** | Done | `afe95fb` (+ `d0a1d33` test fix) | Canonical evidence, audiences, renderers; package `0.7.0` |
| **R4D1 provider readiness** | Done | `cd7ad86` (+ `e926712` py3.11 fix) | Discovery/version/help/auth-status; package `0.8.0`; schema `4d1.1` |
| **R4D1.1 ambiguity resolution** | Done | `17dc3da` | Logical installs, pins, operator selection; package `0.8.1`; schema `4d1.1.1` |
| Phase B3.1 memory domain | Done | `c11ccb7` | Pure memory domain; disabled; no SQLite yet |
| **R4D1.2 auth/noninteractive** | Done | `8d999f8` (+ `223c565` CI fixes) | Auth-status probes, noninteractive contract, host verdicts; package **`0.8.2`**; schema `4d1.2` |
| Memory test hygiene | Done | `f330c41` | secret_scan false-positive fix |
| Handoff progress doc | Docs | `9254fca` | Claude handoff progress document added |
| **R4D1.3 Codex headless** | **Done** | **`330ffa3`** | Official Codex install + ChatGPT auth + headless readiness path; package **`0.8.3`**; schema **`4d1.3`**; CI [`29982270706`](https://github.com/tahach3/ai-development-os/actions/runs/29982270706) success |
| Phase B3.2 SQLite bootstrap | **Out-of-band WIP** | *(untracked; not on master)* | Untracked `sqlite_*` + `tests/memory/` in worktree — **leave alone** unless a dedicated memory commit is authorized |

### Recent `git log -20 --oneline` (as of handoff)

```
330ffa3 Complete Round 4D1.3 Codex headless-provider readiness.
9254fca Add Claude handoff progress document
f330c41 Avoid secret_scan false positive in memory domain tests
223c565 Fix POSIX auth fixtures and package version assertions for CI
8d999f8 Add auth and noninteractive provider readiness
c11ccb7 Add Phase B3.1 memory domain foundations
17dc3da Resolve provider CLI ambiguity safely
e926712 Fix Python 3.11 f-string syntax in readiness discovery
cd7ad86 Add safe live-provider readiness auditing
d0a1d33 Fix Round 4C tests to avoid secret_scan false positives
afe95fb Add evidence-first audience-specific reporting
9f7ec38 Record first private GitHub CI validation / Round 4B closeout
09cf1e6 Add Phase B2 shared memory implementation plan
382eb8a Add Phase B1 shared memory design
a01f672 Add AI OS integration master blueprint
eeebbe7 Add Round 4A local CI and PR validation foundation.
734b8c8 Add bounded orchestration and stalemate detection
87068fd Record Round 3B live smoke blocked before execution
305c0d7 Add Round 3B controlled provider CLI adapters.
eb6aba3 Add Round 3A safe sessions, worktrees, and allowlisted pytest execution.
```

---

## 4. Current HEAD, package, tests, remote CI

### Git

- **HEAD:** `330ffa3d47d618a124d143d87cfcfadf50e85807`
- **Branch:** `master` @ `origin/master` (in sync at handoff generation for committed tip)
- **Remote:** `https://github.com/tahach3/ai-development-os.git`
- **Worktree:** Clean for Round 4D1.3. Untracked **only** Phase B3.2 SQLite WIP + gitignored `workspace/` scratch — **do not stomp or mix into provider commits.**

### Package version

| Layer | Version |
| --- | --- |
| Committed `pyproject.toml` / `__init__` at HEAD | **`0.8.3`** |

### Test posture

- Round 4D1.3 + prior suites green on remote CI for HEAD (`330ffa3`).
- Always re-verify locally with: `python -m pytest -q` after install.
- Do not treat untracked B3.2 memory SQLite files as part of the 4D1.3 baseline.

### Remote CI

- Workflow: `.github/workflows/ci.yml`
- Permissions: `contents: read` only; no secrets; no live providers
- First private success: run `29930178622` on `a01f672`
- **Latest success on current HEAD:** run [`29982270706`](https://github.com/tahach3/ai-development-os/actions/runs/29982270706) (*Complete Round 4D1.3 Codex headless-provider readiness.*)

---

## 5. Current host provider verdict

| Provider | Verdict (honest) |
| --- | --- |
| **Cursor** | Present as desktop/editor CLI; **editor-only** — not headless automation on this host |
| **Claude Code** | **Not installed** |
| **Codex** | CLI **0.145.0** via official Method C; ChatGPT mode; auth verified via `codex login status`; noninteractive contract from help/docs/synthetic tests; **conditionally eligible as implementer**; **zero** `codex exec <prompt>` |
| **Host system verdict** | `live_smoke_ready_with_operator_auth` / `live_smoke_ready_with_conditions` |
| **Aggregate** | `conditionally_eligible_for_bounded_live_smoke` |
| **Independence** | `fresh_context_same_provider_only` — Codex as implementer; same-provider fresh-context review only (**not** true independent review) |
| **4D2 recommendation** | File present at `workspace/provider_readiness/round4d2_recommendation.json` — **not executed**; `live_execution_authorized: false`; `round_4d2_gate: locked` |
| **ACP / scanners** | **Not installed** (adoption roadmap defers) |

Round **4D2 remains LOCKED** even with a `live_smoke_ready*` host verdict. Separate explicit authorization required before any live smoke.

---

## 6. Architecture snapshot

```
Config (routing, risk, budgets, repair, projects, providers, orchestration, ci_policy)
  → Schemas (task/plan/report + 3a.1 / 3b.1 / 3c.1 / 4a.1 / 4c.1 / 4d1.*)
  → Domain (models, validation, fingerprints, CI/reporting/readiness; memory domain B3.1)
  → Services (registry, tasks, plans, sessions, providers, orchestration, CI, reports, readiness)
  → Adapters (manual handoff) + providers/ (CLI shells; Codex env/events/4D2-envelope helpers — readiness only)
  → CLI (ai-dev-os)
  → Workspace artifacts (gitignored runtime under workspace/)
  → GitHub Actions (private parity with local gates)
```

| Area | Location (paths) |
| --- | --- |
| CLI | `src/ai_dev_os/cli.py` |
| Registry / tasks / plans | `src/ai_dev_os/` + `config/` + `schemas/` |
| Safe exec | sessions / worktrees / allowlisted pytest (3A) |
| Providers | `src/ai_dev_os/providers/` (incl. `codex_env.py`, `codex_events.py`, `codex_round4d2_envelope.py`) |
| Orchestration | Round 3C engine + CLI |
| Reporting | Round 4C builder/renderer (`build-report`, etc.) |
| Readiness | `provider_readiness_*.py` + `provider-readiness` CLI |
| Memory (partial) | `src/ai_dev_os/memory/` — B3.1 committed; B3.2 SQLite **untracked WIP**; **disabled** |
| CI | local engine + `.github/workflows/ci.yml` |
| Demo | `demo_projects/calculator-demo` |

---

## 7. What works / what is gated

### Works (on committed `master` / proven)

- Full R1–R2 control plane + calculator-demo synthetic lifecycle
- R3A allowlisted pytest in worktrees
- R3B discovery + simulated providers (live shells refuse unauthorized live)
- R3C simulated orchestration + stalemate
- R4A local `ci-check` / `validate-change`
- R4B private remote CI (least privilege)
- R4C evidence-first reports (no LLM summaries)
- R4D1–**4D1.3** readiness / ambiguity / auth / noninteractive / Codex headless audit (**no live prompts**)
- B3.1 memory domain foundations (disabled)

### Gated / incomplete

| Item | Gate |
| --- | --- |
| Round **4D2** live local CLI smoke | Separate explicit human authorization after `live_smoke_ready*` — recommendation JSON exists but **must not** be executed until authorized |
| True independent review path | Second eligible provider (e.g. Claude Code) or accepted policy for `fresh_context_same_provider_only` limitation |
| Memory CRUD / runtime (B3.3+) | Not started; B3.2 SQLite is **out-of-band untracked WIP** |
| Equitify | Exact connect phrase only |
| ACP, zizmor, pip-audit, Gitleaks, Inspect AI | Adoption roadmap — not installed |
| Vuln DB scanning, SHA-pinned Actions | Deferred |
| Auto-merge / deploy / paid APIs / dashboards | Out of scope |

---

## 8. Open questions for next progress discussion

1. **Authorize Round 4D2?** What exact human phrase/scope (one provider? one prompt? calculator-demo only? timeout/output caps from `round4d2_recommendation.json`?) unlocks live smoke?
2. **Independence gap:** Is `fresh_context_same_provider_only` acceptable for a first bounded smoke, or must Claude Code be installed for a true implementer≠reviewer split?
3. **Cursor policy:** Keep forever editor-only on this host, or re-evaluate if a real headless Cursor agent CLI appears?
4. **Memory track:** Finish/commit Phase B3.2 SQLite bootstrap as a dedicated round (separate from 4D2), or hold until after first live smoke?
5. **Open-source adoption:** When to evaluate ACP / scanners as **adapters** (OS remains authority) vs continue Codex-only path?
6. **Config enablement:** When/how to flip provider mode flags for Codex without implying 4D2 authorization?
7. **Recommendation envelope:** Review `workspace/provider_readiness/round4d2_recommendation.json` constraints (sandbox, timeouts, forbidden flags) before any authorization decision?
8. **Post-4D2 reporting:** Which Round 4C audience/detail level for the first live-smoke evidence bundle?

---

## 9. Recommended next steps

1. **Do not start Round 4D2** until the operator explicitly authorizes it — readiness success does not unlock live prompts.
2. Optionally review (read-only) `workspace/provider_readiness/round4d2_recommendation.json` for proposed bounds; leave `live_execution_authorized: false`.
3. After authorization: **bounded** calculator-demo live smoke only (Codex implementer, hard timeouts, output caps, audit envelope, fail-closed; prefer deterministic non-model validation over claiming independent review).
4. Optionally install Claude Code later for independence — separate readiness pass.
5. Continue **open-source adoption roadmap** (`docs/OPEN_SOURCE_ADOPTION_ROADMAP.md`) as planning only; ACP/scanners later.
6. Memory track: if ready, commit B3.2 SQLite as a **dedicated** change set (do not mix with 4D2); keep memory **disabled** until enablement is authorized.
7. Keep Equitify disconnected.

---

## 10. How to run locally

```bash
# From repository root
python -m pip install -e ".[dev]"
python -m pytest -q

ai-dev-os --version
ai-dev-os init

# Demo project
ai-dev-os register-project --id calculator-demo --name "Calculator Demo" --root demo_projects/calculator-demo

# Local CI / change validation
ai-dev-os ci-check
ai-dev-os validate-change --base HEAD~1

# Reporting (evidence bundle path required)
ai-dev-os build-report --evidence-bundle PATH --audience executive --detail-level summary
ai-dev-os render-report --report-id RID
ai-dev-os validate-report --report-id RID
ai-dev-os show-report --report-id RID --json

# Provider readiness (no live prompts)
ai-dev-os provider-readiness --project-id calculator-demo --json --show-combinations
ai-dev-os provider-readiness --project-id calculator-demo --show-candidates --explain-ambiguity --show-logical-installations
ai-dev-os provider-readiness --project-id calculator-demo --verify-noninteractive-contract --show-host-system-verdict
ai-dev-os provider-readiness --validate-pin cursor

# Providers / orchestration (simulated)
ai-dev-os discover-providers
ai-dev-os list-provider-adapters
ai-dev-os run-simulated-provider ...
ai-dev-os create-orchestration ...
```

Requires **Python 3.11+**, runtime dep **PyYAML**, dev dep **pytest**.

---

## 11. Key docs (paths only)

| Path | Topic |
| --- | --- |
| `README.md` | Install + status |
| `docs/PROJECT_CHRONICLE.md` | Human chronicle of shipped rounds |
| `docs/ROADMAP.md` | Round sequencing |
| `docs/ARCHITECTURE.md` | Layers / data flow |
| `docs/PROJECT_BOUNDARIES.md` | Registry + Equitify rules |
| `docs/SECURITY_MODEL.md` | Trust boundary |
| `docs/ZERO_CLICK_LIMITATIONS.md` | What stays human |
| `docs/MODEL_ROLES.md` | Claude / Cursor / Codex roles |
| `docs/ROUND_3A_SAFE_EXECUTION_DESIGN.md` | Safe exec |
| `docs/ROUND_3B_PROVIDER_ADAPTER_DESIGN.md` | Provider adapters |
| `docs/ROUND_3C_BOUNDED_ORCHESTRATION_DESIGN.md` | Orchestration |
| `docs/ROUND_4A_LOCAL_CI_DESIGN.md` | Local CI (+ 4B notes) |
| `docs/ROUND_4C_HIGH_QUALITY_REPORTING_DESIGN.md` | Reporting design |
| `docs/REPORTING_STANDARD.md` | Reporting contract |
| `docs/ROUND_4D1_PROVIDER_READINESS_DESIGN.md` | Readiness design |
| `docs/ROUND_4D1_1_CLI_AMBIGUITY_RESOLUTION_DESIGN.md` | Ambiguity |
| `docs/ROUND_4D1_2_AUTH_AND_NONINTERACTIVE_DESIGN.md` | Auth / noninteractive |
| `docs/ROUND_4D1_3_CODEX_HEADLESS_PROVIDER_DESIGN.md` | Codex headless (4D1.3) |
| `docs/PROVIDER_READINESS_STANDARD.md` | Readiness standard |
| `docs/PROVIDER_AUTH_NONINTERACTIVE_STANDARD.md` | Auth standard |
| `docs/OPEN_SOURCE_REFERENCE_ASSESSMENT.md` | OSS patterns adopt/defer |
| `docs/OPEN_SOURCE_ADOPTION_ROADMAP.md` | Adoption roadmap v1.0 |
| `docs/AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md` | Long-term blueprint |
| `docs/SHARED_MEMORY_DESIGN.md` | Memory B1 design |
| `docs/SHARED_MEMORY_IMPLEMENTATION_PLAN.md` | Memory B2 plan |
| `exports/AI_Development_OS_Project_Chronicle.md` | Chronicle export copy |
| `docs/CLAUDE_HANDOFF_PROGRESS.md` | This handoff (repo copy) |
| `exports/CLAUDE_HANDOFF_PROGRESS.md` | Handoff export copy |

---

## Instructions for the discussing AI

- Stay inside **this** repository only.
- Prefer **committed** facts (`HEAD` `330ffa3` / package **`0.8.3`** / Round **4D1.3** complete).
- Treat untracked Phase B3.2 SQLite files as unrelated WIP — do not stage them with other work.
- Never propose live prompts, credential inspection, Equitify access, or force-push.
- If recommending implementation, plan **minimal diffs**, tests first for behavior changes, and explicit round gates.
- Ask the human for **4D2 authorization** before any live smoke design execution. The recommendation JSON is advisory only until then.

---

*End of handoff. No secrets included. Host evidence paths under `workspace/` are gitignored runtime artifacts.*
