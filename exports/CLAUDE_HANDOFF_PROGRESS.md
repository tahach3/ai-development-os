# AI Development OS — Claude Handoff (Progress Discussion)

**Purpose:** Brief an external AI (Claude Code or similar) for a **next-progress** discussion.  
**Generated:** 2026-07-23  
**Workspace:** AI Development OS only — **do not touch Equitify.**

---

## Executive summary

AI Development OS (`ai-dev-os`) is a **local-first control plane** for structured multi-model software work (Claude / Cursor / Codex). It validates tasks, routes deterministically, gates plans, supports manual handoffs, allowlisted pytest in worktrees, simulated orchestration, local + private GitHub CI, evidence-first reporting, and **provider readiness auditing** — without calling paid LLM APIs by default and **without live model prompts** until Round **4D2** is separately authorized.

| Fact | Value |
| --- | --- |
| GitHub | [`tahach3/ai-development-os`](https://github.com/tahach3/ai-development-os) (**private**) |
| Branch | `master` tracking `origin/master` |
| **Committed HEAD** | `f330c417c358484c9c73816962bc83b0eccbb4df` — *Avoid secret_scan false positive in memory domain tests* |
| **Committed package** | **`0.8.2`** (Round **4D1.2** complete on `master`) |
| Working tree | **Dirty** — Round **4D1.3** + Phase **B3.2** memory SQLite work in progress (docs/code claim **`0.8.3`**, **not committed**) |
| Remote CI | Latest push on HEAD: GitHub Actions `ci` **success** (run `29950638076`) |
| Live prompts | **0 authorized / 0 issued**; Round **4D2 LOCKED** |
| Equitify | **Disconnected** — hard boundary |

**Honest 4D1.3 status:** Roadmap/chronicle/README in the working tree describe Round 4D1.3 as complete (Codex install + ChatGPT auth + host verdict). That work exists as **uncommitted** design, code, tests, and host evidence under `workspace/provider_readiness/`. **Do not treat 4D1.3 as merged until it lands on `master`.** Prefer finishing/committing 4D1.3 cleanly before any 4D2 discussion.

**Host readiness (workspace evidence only, generated against HEAD while dirty tree claimed `4d1.3`):**

- Codex: installed (official Method C), ChatGPT auth verified via `codex login status`, noninteractive `supported_documented`
- Host verdict: `live_smoke_ready_with_operator_auth`
- Aggregate: `conditionally_eligible_for_bounded_live_smoke` (same-provider fresh-context review only — **not** true independent review)
- Cursor: **editor-only** on this host (not a headless agent)
- Claude Code: **not installed** (as of last recorded smoke/readiness narratives)
- `live_provider_invocations: 0`

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
- Provider readiness / ambiguity / auth / noninteractive audit (4D1–4D1.2; 4D1.3 mid-flight)

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
| Memory test hygiene | Done | `f330c41` | **Current HEAD** — secret_scan false-positive fix |
| **R4D1.3 Codex headless** | **In progress / uncommitted** | *(no commit yet)* | Design + code + tests + host evidence in **dirty tree**; docs claim `0.8.3` / schema `4d1.3` |
| Phase B3.2 SQLite bootstrap | **In progress / uncommitted** | *(no commit yet)* | `sqlite_*` modules + `tests/memory/` in dirty tree; memory still disabled |

### Recent `git log -20 --oneline` (as of handoff)

```
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
f1d1029 Add downloadable project chronicle export
d4c9133 Add project chronicle documenting Round 1-2 state.
```

---

## 4. Current HEAD, package, tests, remote CI

### Git

- **HEAD:** `f330c417c358484c9c73816962bc83b0eccbb4df`
- **Branch:** `master` @ `origin/master` (in sync at handoff generation for committed tip)
- **Remote:** `https://github.com/tahach3/ai-development-os.git`
- **Worktree:** Many modified + untracked files (4D1.3 providers/readiness, B3.2 memory SQLite, docs, tests, workspace pytest/CI scratch). **Another agent may be mid-flight — do not stomp.**

### Package version

| Layer | Version |
| --- | --- |
| Committed `pyproject.toml` / `__init__` at HEAD | **`0.8.2`** |
| Dirty working tree (claimed) | **`0.8.3`** (4D1.3 target — not on `master` yet) |

### Test posture

- Committed baseline: Round 4D1.2 + B3.1 memory domain tests green on remote CI for HEAD.
- Dirty-tree pytest scratch (`workspace/_pytest_*.txt`) showed **failures/errors** during mid-flight 4D1.3 work (e.g. readiness probe expectations). Treat local dirty-tree results as **non-authoritative** until 4D1.3 is finished and re-run clean.
- Always re-verify with: `python -m pytest -q` after install.

### Remote CI

- Workflow: `.github/workflows/ci.yml`
- Permissions: `contents: read` only; no secrets; no live providers
- First private success: run `29930178622` on `a01f672`
- Latest known success on current HEAD tip: run `29950638076` (*Avoid secret_scan false positive…*)
- Earlier 4D1.2 / B3.1 pushes had failures then fixes — tip is green

---

## 5. Current host provider verdict

| Provider | Verdict (honest) |
| --- | --- |
| **Cursor** | Present as desktop/editor CLI; **not** headless automation on this host |
| **Claude Code** | **Not installed** (R3B smoke + 4D1.3 narratives) |
| **Codex** | Host evidence (dirty 4D1.3): official install Method C (`install.ps1` + hashed release asset), ChatGPT mode, `authenticated_verified`, noninteractive `supported_documented`, **zero** `codex exec <prompt>` |
| **Host system verdict** (workspace audit) | `live_smoke_ready_with_operator_auth` |
| **Aggregate** | `conditionally_eligible_for_bounded_live_smoke` — reviewer independence only `fresh_context_same_provider` (Codex as both implementer and “reviewer”) |
| **Warnings** | Provider mode still disabled in config until 4D2; noninteractive documented not live-verified; 4D2 still needs explicit authorization |
| **ACP / scanners** | **Not installed** (adoption roadmap defers) |

Round **4D2 remains LOCKED** even with a `live_smoke_ready*` host verdict.

---

## 6. Architecture snapshot

```
Config (routing, risk, budgets, repair, projects, providers, orchestration, ci_policy)
  → Schemas (task/plan/report + 3a.1 / 3b.1 / 3c.1 / 4a.1 / 4c.1 / 4d1.*)
  → Domain (models, validation, fingerprints, CI/reporting/readiness; memory domain B3.1)
  → Services (registry, tasks, plans, sessions, providers, orchestration, CI, reports, readiness)
  → Adapters (manual handoff) + providers/ (CLI shells; Codex env/events modules in dirty tree)
  → CLI (ai-dev-os)
  → Workspace artifacts (gitignored runtime under workspace/)
  → GitHub Actions (private parity with local gates)
```

| Area | Location (paths) |
| --- | --- |
| CLI | `src/ai_dev_os/cli.py` |
| Registry / tasks / plans | `src/ai_dev_os/` + `config/` + `schemas/` |
| Safe exec | sessions / worktrees / allowlisted pytest (3A) |
| Providers | `src/ai_dev_os/providers/` |
| Orchestration | Round 3C engine + CLI |
| Reporting | Round 4C builder/renderer (`build-report`, etc.) |
| Readiness | `provider_readiness_*.py` + `provider-readiness` CLI |
| Memory (partial) | `src/ai_dev_os/memory/` — B3.1 committed; B3.2 SQLite uncommitted; **disabled** |
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
- R4D1–4D1.2 readiness / ambiguity / auth / noninteractive audit (**no live prompts**)
- B3.1 memory domain foundations (disabled)

### Gated / incomplete

| Item | Gate |
| --- | --- |
| Round **4D1.3** Codex headless readiness | Finish + commit + green tests; currently **dirty tree only** |
| Round **4D2** live local CLI smoke | Separate explicit human authorization after `live_smoke_ready*` |
| True independent review path | Second eligible provider (e.g. Claude) or accepted policy for fresh-context limitation |
| Memory CRUD / runtime (B3.3+) | Not started; B3.2 schema uncommitted |
| Equitify | Exact connect phrase only |
| ACP, zizmor, pip-audit, Gitleaks, Inspect AI | Adoption roadmap — not installed |
| Vuln DB scanning, SHA-pinned Actions | Deferred |
| Auto-merge / deploy / paid APIs / dashboards | Out of scope |

---

## 8. Open questions for next progress discussion

1. **Ship 4D1.3 first?** Should the dirty Codex headless + docs/`0.8.3` change set be completed, tested, and committed before any other work?
2. **4D2 authorization criteria:** What exact human phrase/scope (one provider? one prompt? calculator-demo only? timeout/output caps?) unlocks Round 4D2?
3. **Independence gap:** Is `fresh_context_same_provider` acceptable for a first bounded smoke, or must Claude Code be installed for a true implementer≠reviewer split?
4. **Cursor policy:** Keep forever editor-only on this host, or re-evaluate if a real headless Cursor agent CLI appears?
5. **Memory vs providers:** Parallelize B3.2/B3.3 memory with provider readiness, or serialize after 4D1.3 lands?
6. **Open-source adoption:** When to evaluate ACP / scanners as **adapters** (OS remains authority) vs continue Codex-only path?
7. **Config enablement:** When/how to flip provider mode flags for Codex without implying 4D2 authorization?
8. **CI on dirty 4D1.3:** Any host-specific PATH/Codex assumptions that would break remote CI (must stay install-agnostic)?

---

## 9. Recommended next steps

1. **Finish Round 4D1.3** on a clean commit series: design already at `docs/ROUND_4D1_3_CODEX_HEADLESS_PROVIDER_DESIGN.md`; land code/tests/docs; bump package to **`0.8.3`**; ensure `live_provider_invocations: 0`; push and confirm remote CI green.
2. Confirm host still reports `live_smoke_ready*` / conditional eligibility **without** any `codex exec <prompt>`.
3. **Do not start 4D2** until the operator explicitly authorizes it.
4. After authorization: **bounded** calculator-demo live smoke only (one provider, hard timeouts, output caps, audit envelope, fail-closed).
5. Optionally install Claude Code later for independence — separate readiness pass.
6. Continue **open-source adoption roadmap** (`docs/OPEN_SOURCE_ADOPTION_ROADMAP.md`) as planning only; ACP/scanners later.
7. Memory track: complete B3.2 commit if ready → B3.3 repositories; keep memory **disabled** until a dedicated enablement round.
8. Keep Equitify disconnected.

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

---

## Instructions for the discussing AI

- Stay inside **this** repository only.
- Prefer **committed** facts (`HEAD` / `0.8.2` / 4D1.2) over aspirational dirty-tree docs.
- Never propose live prompts, credential inspection, Equitify access, or force-push.
- If recommending implementation, plan **minimal diffs**, tests first for behavior changes, and explicit round gates.
- Ask the human for 4D2 authorization before any live smoke design execution.

---

*End of handoff. No secrets included. Host evidence paths under `workspace/` are gitignored runtime artifacts.*
