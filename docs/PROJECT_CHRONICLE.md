# AI Development OS — Project Chronicle

Human-oriented summary of everything shipped to date in this repository.  
**As of:** 2026-07-23 · **Package version:** `0.8.4` · **Round:** 4D1.3 + Round 4A hardening

---

## 1. What this project is (and is not)

### It is

- A **local-first control plane** for structured multi-model software work (Claude / Cursor / Codex).
- A Python package (`ai-dev-os`) that validates tasks, routes them deterministically, builds **minimal** context packets, manages **plan approval gates**, writes **manual handoff** files, runs **allowlisted local pytest** in isolated worktrees (Round 3A), and (Round 3B) exposes **controlled provider CLI adapters** (discovery / simulated / gated — live not authorized by default).
- An operator CLI plus YAML/JSON workspace artifacts under this repo’s `workspace/` directory.
- A **manual-handoff** system: humans paste packets into external tools; results are recorded back via CLI.
- A **safe local execution** lane: sessions, confined worktrees, env filtering, timeouts, output caps, audit envelopes.
- A **provider adapter** lane: contracts, safe discovery, fail-closed config, simulated fixtures, CLI shells without live model calls in validation.
- A **bounded orchestration** lane (Round 3C): simulated implementation → targeted tests → independent review → repair with deterministic stalemate detection.
- A **local CI / PR validation** lane (Round 4A): deterministic quality gates, change-range validation, dependency-policy (not vuln DB), GitHub workflow definition.
- A **private remote CI validation** lane (Round 4B): first successful GitHub Actions run on private repo `tahach3/ai-development-os` (no secrets, no live providers, no deploy/merge).
- An **evidence-first reporting** lane (Round 4C): canonical evidence, claim statuses, audience/detail renderers, deterministic relevance, integrity fingerprints (no LLM summaries).
- A **provider readiness** lane (Round 4D1 / 4D1.1 / 4D1.2 / 4D1.3): safe eligibility auditing for future live smoke — discovery/version/help/auth-status + ambiguity resolution + auth/noninteractive contracts + trusted Codex headless path; never live prompts.
- A **local-CI hardening** lane (Round 4A extension, package `0.8.4`): deterministic targeted / related-module test selection (`ci-targeted`), CI run history + regression comparison (`ci-history` / `ci-compare`), human-readable Markdown CI reports (`ci-check --format md`), and a cross-platform executable-path redaction fix — all additive, with the fixed CI `STAGE_ORDER` and `4a.1` schema unchanged.

### It is not

- An autonomous agent runner or “zero-click” coding system.
- Live multi-agent automation (Round 3C is simulation-proven only).
- A caller of paid LLM APIs, LangChain, CrewAI, AutoGen, or cloud workers.
- A dashboard, browser automation layer, or network-connected orchestrator.
- An Equitify integration (see §11).
- A system that executes arbitrary shell, auto-approves high-risk work, or performs **live** provider model calls without separate authorization.

---

## 2. Hard boundaries (current rounds)

| Boundary | Rule |
| --- | --- |
| Equitify | Disconnected until the exact user phrase (see §11). Registration sentinels reject `equitify` / `equitify-machine`. |
| Network / paid APIs | No product network model calls; no API keys in repo or workspace. |
| Frameworks | No LangChain / CrewAI / AutoGen. |
| UI / automation | No dashboards, browser automation, or auto agent spawn. |
| Git mutation | Inspect-only via `git_safety.py`. Round 3A additionally allows **worktree add/list/remove** only under session confinement — no reset/push/merge/commit. |
| Adapters | Manual handoff remains `manual_handoff_required`. Provider lane uses distinct automation statuses (`simulated_provider_execution`, `discovery_only`, …). |
| Local pytest | `automation_status: local_allowlisted_execution` only after policy allow. |
| Risk | No auto-approve for high/critical risk; no auto rule rewrite / self-improvement. |
| Scope of work | Only projects in `config/projects.yaml`; unregistered IDs refused. |
| Provider CLIs | Round 3B: discovery/version and simulated fixtures allowed; **live model execution not authorized** in this round’s validation. |
| Orchestration | Round 3C: simulated-only loops; bounded repair; stalemate → human review; provider text never executed. |
| Local CI / PR | Round 4A: fixed stages; no arbitrary commands; no auto-merge; no vuln DB. Round 4B: private remote workflow executed with `permissions: contents: read` only; no repository secrets; no live providers; no deploy/merge. |

Details: `docs/PROJECT_BOUNDARIES.md`, `docs/SECURITY_MODEL.md`, `docs/ZERO_CLICK_LIMITATIONS.md`.

---

## 3. Workspace path and Equitify separation

| Item | Value |
| --- | --- |
| This project | `C:\Users\Taha\ai-development-os` |
| Equitify (do not touch) | `C:\Users\Taha\equitify-machine` |
| Runtime artifacts | `workspace/` **inside** `ai-development-os` |
| Demo target (Round 2) | `demo_projects/calculator-demo` (synthetic; not Equitify) |

Operators and agents working in this OS must not open, inspect, modify, copy from, test, or integrate Equitify until explicitly connected.

---

## 4. Round 1 — foundation (shipped)

**Commit:** `3fcef7e` — *Initial foundation for AI Development Operating System*

Shipped in that commit (and still present):

| Area | What landed |
| --- | --- |
| **Project registry** | `project_registry.py`; example `config/projects.example.yaml`; Equitify sentinels |
| **Tasks** | `task_store.py`, task schema, lifecycle status transitions (`validation.py` / `models.py`) |
| **Routing** | Deterministic role + budget band from `config/default_routing.yaml`, `risk_levels.yaml`, `token_budgets.yaml` |
| **Budgets** | Token budget bands wired through routing decisions |
| **Context** | Minimal context packets (`context_builder.py`); capped paths, no full-repo dump |
| **Git safety** | Inspect-only (`git_safety.py`): allowlisted verbs, no shell, timeouts |
| **Adapters** | Claude / Cursor / Codex stubs with `manual_handoff_required` |
| **Reports** | Implementation + review report store; JSON schemas + Markdown templates |
| **Behavioral metrics** | Aggregate recommendations; no auto-apply |
| **CLI** | `init`, register/create/validate/route tasks, context, handoff, reports, behavioral + project status |
| **Docs** | Architecture, boundaries, model roles, security, zero-click limits, roadmap |
| **Tests** | Models, registry, tasks, routing, validation, context, git safety, reports/behavioral |

Round 1 is **complete** and frozen as the foundation; Round 2 built on top without rewriting that charter.

---

## 5. Round 2 — plans, gates, demo (shipped)

**Commit:** `a41c0f4` — *Add Round 2 plan approval, fingerprints, and synthetic lifecycle.*  
**Status:** **Done** (committed on `master`; working tree clean at chronicle time).

| Scope item | Status | Where |
| --- | --- | --- |
| Plan artifacts (create / validate / submit / show / update) | **Done** | `plan_store.py`, CLI plan commands, `schemas/plan.schema.json` |
| Approval gates (approve / reject; human approver) | **Done** | `approval.py`, `lifecycle_gates.py` |
| Fingerprints + approval invalidation on content change | **Done** | `fingerprints.py`, `apply_plan_content_update` |
| Pre-approval handoff blocking; task↔plan linkage | **Done** | `handoffs.py`, gates |
| Role-specific handoffs | **Done** | `prepare_role_handoff` / `prepare-handoff --role` |
| Review verdicts (`pass` / `pass_with_notes` / `changes_required` / `blocked`) | **Done** | `review_gate.py`, review report model |
| Repair rounds with configurable max → blocked | **Done** | `repair_rounds.py`, `config/repair_rounds.yaml` |
| Synthetic calculator demo | **Done** | `demo_projects/calculator-demo` |
| OSS reference assessment (patterns only) | **Done** | `docs/OPEN_SOURCE_REFERENCE_ASSESSMENT.md` |
| Extended `project-status` | **Done** | plan/approval/review/repair/next-action fields |
| Round 2 tests | **Done** | `tests/test_round2_plans_approval.py` |

**Not claimed as done:** real agent CLI spawn, worktrees, Equitify, paid APIs, dashboards — those remain deferred (§10).

---

## 6. Open-source reference strategy

Full write-up: [`docs/OPEN_SOURCE_REFERENCE_ASSESSMENT.md`](OPEN_SOURCE_REFERENCE_ASSESSMENT.md).

**Method:** public metadata/docs review only. **No repos cloned into this product. No third-party orchestrator code copied. No new dependencies from those projects.**

| Source | Borrow (patterns) | Defer / reject |
| --- | --- | --- |
| **cc-sdd** (gotalab) | Approved-spec / plan gate; durable plan fields; independent review mindset | Autonomous execution; auto-approval flags; copying skills |
| **Liza** | Lifecycle FSM; audit fields (`approved_by`, starting commit); blocked/rejected/superseded; planner ≠ approver | Worktrees; Go supervisors; autonomous merge |
| **Ralphex** | Max repair rounds → blocked; stalemate as a later concept | Autonomous Ralph loops; live Claude spawn |
| **Agent Orchestrator** | Study session/isolation ideas for later | Worktrees, daemon, dashboard, auto CI/merge (**Round 3+**) |
| **MCO** | Provider-adapter *concept* for later | Real provider CLI fan-out (**Round 3+**) |

---

## 7. Current architecture (brief)

Layers (Round 2):

1. **Config** — routing, risk, budgets, repair limits, project registry  
2. **Schemas** — task / plan / report / decision contracts  
3. **Domain** — models, validation, fingerprints, lifecycle FSM  
4. **Services** — registry, routing, context, git inspect, task/plan/report/repair stores, approval, gates, handoffs, behavioral metrics  
5. **Adapters / handoffs** — manual packets for Claude / Cursor / Codex  
6. **CLI** — operator interface  
7. **Demo** — `calculator-demo` synthetic lifecycle target  

Typical Round 2 flow:

```text
register-project → create-task → set-task-status(ready_for_planning) → route-task
  → create-plan → validate-plan → submit-plan → approve-plan
  → build-context / prepare-handoff (implementation role)
  → record-report (implementation) → prepare-handoff (review)
  → record-report (review) → [repair rounds if needed] → complete
  → behavioral-report
```

See `docs/ARCHITECTURE.md` for the inspired-by table and non-goals.

---

## 8. CLI commands (from `src/ai_dev_os/cli.py`)

Entry point: `ai-dev-os` → `ai_dev_os.cli:main`.

| Command | Purpose |
| --- | --- |
| `init` | Create workspace dirs + seed `config/projects.yaml` if missing |
| `register-project` | Register a project (Equitify rejected) |
| `create-task` | Create draft task (flags or `--from-file`) |
| `set-task-status` | Lifecycle transition |
| `validate-task` | Validate stored task or file |
| `route-task` | Deterministic role + budget routing |
| `build-context` | Minimal context packet |
| `prepare-handoff` | Role-specific manual handoff (`claude` / `cursor` / `codex`) |
| `create-plan` | Draft plan for a ready task |
| `validate-plan` | Validate plan |
| `submit-plan` | Submit for approval |
| `approve-plan` | Human approve |
| `reject-plan` | Reject with reason |
| `show-plan` | Print plan (optional `--json`) |
| `update-plan` | Update from YAML (may invalidate approval) |
| `record-report` | Implementation or review report |
| `record-repair-round` | Track a repair iteration |
| `review-status` | Latest review verdict for a task |
| `behavioral-report` | Aggregate behavioral metrics |
| `project-status` | Extended project/task/plan/repair summary |

Also: `--version` on the root parser.

---

## 9. How to run tests

```bash
cd C:\Users\Taha\ai-development-os
pip install -e ".[dev]"
python -m pytest -q
```

- **Requires:** Python 3.11+  
- **Runtime dependency:** PyYAML  
- **Dev dependency:** pytest  
- Test paths: `tests/` (configured in `pyproject.toml`)

---

## 10. Round 3B shipped + deferred

### Round 3A (done)

- Design: `docs/ROUND_3A_SAFE_EXECUTION_DESIGN.md`
- Sessions + confined worktrees; allowlisted pytest; execution envelopes `3a.1`

### Round 3B (done)

- Design: `docs/ROUND_3B_PROVIDER_ADAPTER_DESIGN.md`
- Provider-neutral contracts + result schema `3b.1`
- Safe discovery (no install, no auth inspection)
- Fail-closed provider config; simulated provider fixtures
- CLI shells for `claude_code` / `codex` / `cursor` (live not authorized)
- CLI: list/capabilities/discover/config/validate/preview/simulate/status/result/cancel
- Package version `0.4.0`

### Round 3B live smoke (2026-07-22) — blocked before execution

- **Baseline:** `master` @ `305c0d7`, package `0.4.0`, clean tree, `80 passed, 1 skipped`
- **Authorization consumed:** exactly one separately authorized live local CLI model invocation was permitted; **zero live model requests were issued**
- **Provider selection:** none — fail-closed
  - `claude_code`: `not_installed`
  - `codex`: `not_installed`
  - `cursor`: detected on PATH (`--version` → `3.12.30`) but `supports_noninteractive=false` (desktop/PATH CLI ≠ proven automation agent path); live argv not implemented in adapter shell
  - `simulated`: fixtures only; not a live provider
- **Classification:** `blocked_before_execution`
- **Limitation:** live remains gated; Round 3B shells refuse live spawn; policy `assert_live_gates` still hard-stops live until a proven noninteractive provider path exists
- Equitify was not accessed; no provider source mutation; no retry

### Round 3C (done)

- Design: `docs/ROUND_3C_BOUNDED_ORCHESTRATION_DESIGN.md`
- Orchestration state machine + durable records/events/round evidence (`3c.1`)
- Binding/staleness fail-closed checks; role-separated simulated impl/review
- Deterministic stalemate (consecutive identical evidence, no-change repair, oscillation, repeated malformed)
- CLI: create/validate/preview/step/run/resume/show/history/stalemate/cancel
- Synthetic calculator-demo scenarios: direct success, one repair, stalemate, repair limit
- Package version `0.5.0`
- Validated through simulation only; zero live provider calls; Equitify not accessed

### Round 4A (done)

- Design: `docs/ROUND_4A_LOCAL_CI_DESIGN.md`
- Local CI engine (`ai-dev-os ci-check`) with fixed stages and normalized results (`4a.1`)
- PR/change validation (`ai-dev-os validate-change`) without executing change code
- Dependency-policy checks (explicitly **not** vulnerability database scanning)
- Secret-pattern scan with redaction; runtime artifact exclusion
- Minimal GitHub Actions workflow definition (`.github/workflows/ci.yml`) — **not pushed or executed** in Round 4A
- Behavioral report CI aggregates; recommendations proposed/inactive until human approval
- Package version `0.6.0`
- Zero live provider calls; Equitify not accessed; no auto-merge/push/deploy

### Round 4B (done) — first private remote CI validation

- **Private repo:** [`tahach3/ai-development-os`](https://github.com/tahach3/ai-development-os) (visibility: private)
- **First remote CI success evidence:** GitHub Actions run [`29930178622`](https://github.com/tahach3/ai-development-os/actions/runs/29930178622) — conclusion **success**, workflow `ci`, event `push`, head SHA `a01f6725d415977c982fd3c9ad524ef5656ddce3` (*Add AI OS integration master blueprint*)
- Subsequent successful remote runs on later docs pushes (including Phase B1/B2) confirm continued parity
- Closeout baseline before this documentation commit: local/origin `master` at `09cf1e67d55c85273babe9b595ccc9cd8f1a3dd6`
- Workflow posture unchanged and verified: `permissions: contents: read` only; **no** repository secrets; **no** live provider / model steps; **no** deploy / auto-merge / auto-push; Equitify disconnected
- Package version remains **`0.6.0`** (no bump)
- **Next development round (completed in Round 4C):** high-quality reporting system upgrade

### Round 4C (done) — evidence-first audience-specific reporting

- Design: `docs/ROUND_4C_HIGH_QUALITY_REPORTING_DESIGN.md`
- Standard: `docs/REPORTING_STANDARD.md`
- Canonical evidence + claim statuses (`verified`/`reported`/`inferred`/`conflicting`/`unavailable`/`not_applicable`)
- Audiences: executive, operator, developer, independent_reviewer, auditor
- Detail levels: summary, standard, full, audit
- Deterministic relevance engine + template executive summaries (no LLM)
- Report statuses distinct from task/review/CI verdicts
- Integrity fingerprints, fail-closed redaction, legacy adapters (no historical rewrite)
- CLI: `build-report`, `render-report`, `validate-report`, `show-report`
- Storage: `workspace/reports/{canonical,rendered,manifests}/` (gitignored runtime)
- Schema/policy/renderer versions: `4c.1`
- Package version **`0.7.0`**
- Round 4B remote CI remains complete; no live provider; no vuln DB; no dashboard; Equitify disconnected

### Round 4D1 (done) — live-provider eligibility audit and readiness hardening

- Design: `docs/ROUND_4D1_PROVIDER_READINESS_DESIGN.md`
- Standard: `docs/PROVIDER_READINESS_STANDARD.md`
- Multi-candidate executable discovery (Python/`where`/`Get-Command`); no full PATH dump
- Allowlisted version/help probes; auth-status only when adapter-safe (otherwise `verification_unsupported`)
- Noninteractive / role / independence matrices without live prompts
- Controlled readiness verdicts; Round 4C audience reports
- CLI: `provider-readiness` with `live_provider_invocations: 0`
- Storage: `workspace/provider_readiness/` (gitignored)
- Schema/policy versions: `4d1.1` (independent of provider `3b.1` / reporting `4c.1`)
- Package version **`0.8.0`**
- Live mode remains disabled; Round 4D2 requires separate authorization
- Equitify disconnected; no credential-file inspection; simulation ≠ live

### Round 4D1.1 (done) — trusted provider CLI ambiguity resolution

- Design: `docs/ROUND_4D1_1_CLI_AMBIGUITY_RESOLUTION_DESIGN.md`
- Executable identity, wrapper/shim inspection, logical-installation normalization
- Automatic collapse only with rule IDs (`AC-*`); no PATH-only or version-text equivalence
- Operator decision records + approval phrases when distinct trusted installs remain
- Host-local pins under `workspace/provider_pins/` (gitignored); fingerprint required; never enable live
- CLI extensions: `--show-candidates`, `--explain-ambiguity`, `--show-logical-installations`, `--generate-selection-record`, `--validate-pin`
- Ambiguity/pin/selection schemas **`4d1.1.1`**; package **`0.8.1`**
- Live mode remains disabled; Round 4D2 requires separate authorization
- Equitify disconnected; wrapper contents never executed; no credential inspection

### Round 4D1.2 (done) — authentication and noninteractive readiness

- Design: `docs/ROUND_4D1_2_AUTH_AND_NONINTERACTIVE_DESIGN.md`
- Standard: `docs/PROVIDER_AUTH_NONINTERACTIVE_STANDARD.md`
- Allowlisted auth-status probes (profile or help-confirmed); never login/credential files
- Noninteractive contract dimensions from adapter/help/synthetic fixtures only
- Host/system verdict enum; editor CLI help can classify noninteractive as `unsupported_verified`
- CLI: `--verify-noninteractive-contract`, `--show-host-system-verdict`
- Schema/policy **`4d1.2`**; package **`0.8.2`**
- Live mode remains disabled; Round 4D2 requires separate authorization after `live_smoke_ready*`
- Equitify disconnected; `live_provider_invocations: 0`

### Deferred (explicit approval)

- Pin GitHub Actions to immutable commit SHAs (tags remain residual supply-chain risk)
- Vulnerability database scanning
- Separately authorized **live** local CLI model smoke (**Round 4D2** — only after readiness evidence + explicit authorization)
- Equitify connection (connect phrase only)
- Broader command profiles beyond pytest
- General provider-generated patch engines
- Automation beyond manual handoff + local allowlisted exec + gated providers + simulated orchestration + local/remote CI gates + evidence-first reporting + readiness auditing

Still explicitly out of scope unless re-approved later:

- LangChain / CrewAI / AutoGen
- Paid API adapters
- Browser automation / dashboards
- Auto-merge / auto-push / auto-deploy
- Self-modifying routing / safety rules
- Copying third-party orchestrator code into this repo

Source: `docs/ROADMAP.md`.

### Phase A docs — master integration blueprint (documentation only)

- Added `docs/AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md` as the architectural source of truth for future AI OS integration decisions
- Aligned `docs/MODEL_ROLES.md` so AI Development OS remains controller/safety authority; Claude plans; Cursor implements; Codex/GPT independently reviews; Cursor three-model workflow is a client (no separate task/approval/routing/memory authority)
- Light cross-links in README, architecture, roadmap, OSS assessment, and this chronicle
- **No runtime behavior changed**; no dependencies or package versions changed
- Implemented runtime baseline remains Round 4A local CI + Round 4B remote validation, package **0.6.0**; the blueprint defines future direction only

### Phase B1 docs — shared memory design (documentation only)

- Added [`docs/SHARED_MEMORY_DESIGN.md`](SHARED_MEMORY_DESIGN.md): Phase B1 controlled shared-memory design (authority, classes, isolation, approval lifecycle, retrieval, retention, security, SQLite prototype boundaries, conceptual APIs, MVP criteria, open decisions)
- **No memory implementation**, schema, database, dependency, provider, or runtime change
- Package **0.6.0** / Round 4B closeout remains the implemented baseline (no memory runtime)

### Phase B2 docs — shared memory implementation plan (documentation only)

- Added [`docs/SHARED_MEMORY_IMPLEMENTATION_PLAN.md`](SHARED_MEMORY_IMPLEMENTATION_PLAN.md): Phase B2 SQLite schema, approval, retrieval, audit, module-boundary, and B3.x checkpoint decisions
- Phase B2 defines **implementation decisions only**; **no memory runtime** exists yet
- Package **0.6.0** / Round 4B closeout remains the implemented baseline (no memory runtime)

### Phase B3.1 — shared-memory domain foundations

- Added `src/ai_dev_os/memory/`: enums, immutable models, validation, normalization, hashing (reuses `fingerprints` + `ci_secrets`), typed errors, pure lifecycle transitions + authorization, disabled-by-default `MemoryConfig`
- Memory remains **disabled**; no SQLite, migrations, repositories, services, CLI, providers, or runtime enablement
- Package version unchanged at **0.8.1** when B3.1 landed (Round 4D1.1 baseline); memory-specific constants use `memory.1`

---

## 11. Equitify is not connected

**Equitify (`C:\Users\Taha\equitify-machine`) is not registered, not inspected by this OS, and not integrated.**

Do not open, modify, or connect it until the user explicitly says:

> Connect the AI Development Operating System to Equitify.

Until then, treat Equitify as a hard off-limits path for all AI Development OS workstreams.

---

## Related docs

| Doc | Topic |
| --- | --- |
| `README.md` | Install, Round 4A/4B status |
| `docs/ARCHITECTURE.md` | Layers and data flow (through Round 4B) |
| `docs/ROUND_3A_SAFE_EXECUTION_DESIGN.md` | Round 3A safe execution design |
| `docs/ROUND_3B_PROVIDER_ADAPTER_DESIGN.md` | Round 3B provider adapter design |
| `docs/ROUND_3C_BOUNDED_ORCHESTRATION_DESIGN.md` | Round 3C bounded orchestration design |
| `docs/ROUND_4A_LOCAL_CI_DESIGN.md` | Round 4A local CI / PR validation design (+ Round 4B remote evidence) |
| `docs/ROUND_4C_HIGH_QUALITY_REPORTING_DESIGN.md` | Round 4C evidence-first reporting design |
| `docs/REPORTING_STANDARD.md` | Round 4C reporting standard / CLI contract |
| `docs/ROUND_4D1_PROVIDER_READINESS_DESIGN.md` | Round 4D1 provider readiness design |
| `docs/ROUND_4D1_1_CLI_AMBIGUITY_RESOLUTION_DESIGN.md` | Round 4D1.1 CLI ambiguity resolution design |
| `docs/ROUND_4D1_2_AUTH_AND_NONINTERACTIVE_DESIGN.md` | Round 4D1.2 auth + noninteractive design |
| `docs/ROUND_4D1_3_CODEX_HEADLESS_PROVIDER_DESIGN.md` | Round 4D1.3 Codex headless-provider design |
| `docs/OPEN_SOURCE_ADOPTION_ROADMAP.md` | Open-source adoption roadmap (OS remains authority) |
| `docs/PROVIDER_READINESS_STANDARD.md` | Round 4D1 / 4D1.1 / 4D1.2 / 4D1.3 readiness standard / CLI contract |
| `docs/PROVIDER_AUTH_NONINTERACTIVE_STANDARD.md` | Round 4D1.2 auth + noninteractive standard |
| `docs/PROJECT_BOUNDARIES.md` | Registry + Equitify rules |
| `docs/OPEN_SOURCE_REFERENCE_ASSESSMENT.md` | OSS pattern adopt/defer |
| `docs/ROADMAP.md` | Round sequencing |
| `docs/SECURITY_MODEL.md` | Prohibitions and trust boundary |
| `docs/ZERO_CLICK_LIMITATIONS.md` | What stays human |
| `docs/MODEL_ROLES.md` | Claude / Cursor / Codex roles; OS as platform authority |
| `docs/AI_OS_OPEN_SOURCE_INTEGRATION_MASTER_BLUEPRINT.md` | Future AI OS integration master blueprint (direction only) |
| `docs/SHARED_MEMORY_DESIGN.md` | Phase B1 shared-memory design |
| `docs/SHARED_MEMORY_IMPLEMENTATION_PLAN.md` | Phase B2 implementation decisions; B3.1 domain foundations landed (no SQLite runtime) |
| `exports/AI_Development_OS_Project_Chronicle.md` | Downloadable chronicle copy |

---

## Git timeline (this repo)

| Commit | Summary |
| --- | --- |
| `3fcef7e` | Round 1 foundation |
| `a41c0f4` | Round 2 plans, approval, fingerprints, repair, demo, OSS assessment |
| `d4c9133` | Project chronicle (Round 1–2) |
| `f1d1029` | Downloadable chronicle export |
| `eb6aba3` | Round 3A safe sessions, worktrees, allowlisted pytest, audits |
| `305c0d7` | Round 3B controlled provider adapters, simulated fixtures, discovery shells |
| `87068fd` | Round 3B live smoke record: blocked_before_execution (zero live calls) |
| `734b8c8` | Round 3C bounded orchestration + deterministic stalemate detection |
| `eeebbe7` | Round 4A local CI, PR validation, workflow definition |
| `9f7ec38` | Round 4B closeout / first private CI validation record |
| *(pending)* | Round 4C evidence-first audience-specific reporting (`0.7.0`) |
| `382eb8a` | Phase B1 shared memory design (docs only) |
| `09cf1e6` | Phase B2 shared memory implementation plan (docs only) |
| *(this commit)* | Round 4B documentation closeout (first private GitHub CI validation recorded) |
