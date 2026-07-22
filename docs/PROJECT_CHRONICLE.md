# AI Development OS — Project Chronicle

Human-oriented summary of everything shipped to date in this repository.  
**As of:** 2026-07-22 · **Package version:** `0.6.0` · **Round:** 4A

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
- A **local CI / PR validation** lane (Round 4A): deterministic quality gates, change-range validation, dependency-policy (not vuln DB), GitHub workflow definition only.

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
| Local CI / PR | Round 4A: fixed stages; no arbitrary commands; no auto-merge; workflow defined but not executed/pushed; no vuln DB. |

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

### Deferred (explicit approval)

- Push/execute GitHub workflow remotely; pin action commit SHAs
- Vulnerability database scanning
- Separately authorized **live** local CLI model smoke (retry only with a proven noninteractive installed provider + implemented gated live path)
- Equitify connection (connect phrase only)
- Broader command profiles beyond pytest
- General provider-generated patch engines
- Automation beyond manual handoff + local allowlisted exec + gated providers + simulated orchestration + local CI

Still explicitly out of scope unless re-approved later:

- LangChain / CrewAI / AutoGen
- Paid API adapters
- Browser automation / dashboards
- Auto-merge / auto-push
- Self-modifying routing / safety rules
- Copying third-party orchestrator code into this repo

Source: `docs/ROADMAP.md`.

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
| `README.md` | Install, Round 4A quick start |
| `docs/ARCHITECTURE.md` | Layers and data flow (through Round 4A) |
| `docs/ROUND_3A_SAFE_EXECUTION_DESIGN.md` | Round 3A safe execution design |
| `docs/ROUND_3B_PROVIDER_ADAPTER_DESIGN.md` | Round 3B provider adapter design |
| `docs/ROUND_3C_BOUNDED_ORCHESTRATION_DESIGN.md` | Round 3C bounded orchestration design |
| `docs/ROUND_4A_LOCAL_CI_DESIGN.md` | Round 4A local CI / PR validation design |
| `docs/PROJECT_BOUNDARIES.md` | Registry + Equitify rules |
| `docs/OPEN_SOURCE_REFERENCE_ASSESSMENT.md` | OSS pattern adopt/defer |
| `docs/ROADMAP.md` | Round sequencing |
| `docs/SECURITY_MODEL.md` | Prohibitions and trust boundary |
| `docs/ZERO_CLICK_LIMITATIONS.md` | What stays human |
| `docs/MODEL_ROLES.md` | Claude / Cursor / Codex roles |
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
| *(this commit)* | Round 4A local CI, PR validation, workflow definition |
