# AI Development OS — Project Chronicle

Human-oriented summary of everything shipped to date in this repository.  
**As of:** 2026-07-22 · **Package version:** `0.3.0` · **Round:** 3A

---

## 1. What this project is (and is not)

### It is

- A **local-first control plane** for structured multi-model software work (Claude / Cursor / Codex).
- A Python package (`ai-dev-os`) that validates tasks, routes them deterministically, builds **minimal** context packets, manages **plan approval gates**, writes **manual handoff** files, and (Round 3A) runs **allowlisted local pytest** in isolated worktrees.
- An operator CLI plus YAML/JSON workspace artifacts under this repo’s `workspace/` directory.
- A **manual-handoff** system: humans paste packets into external tools; results are recorded back via CLI.
- A **safe local execution** lane: sessions, confined worktrees, env filtering, timeouts, output caps, audit envelopes.

### It is not

- An autonomous agent runner or “zero-click” coding system.
- A caller of paid LLM APIs, LangChain, CrewAI, AutoGen, or cloud workers.
- A dashboard, browser automation layer, or network-connected orchestrator.
- An Equitify integration (see §11).
- A system that executes arbitrary shell, spawns Claude/Cursor/Codex CLIs, or auto-approves high-risk work.

---

## 2. Hard boundaries (current rounds)

| Boundary | Rule |
| --- | --- |
| Equitify | Disconnected until the exact user phrase (see §11). Registration sentinels reject `equitify` / `equitify-machine`. |
| Network / paid APIs | No product network model calls; no API keys in repo or workspace. |
| Frameworks | No LangChain / CrewAI / AutoGen. |
| UI / automation | No dashboards, browser automation, or auto agent spawn. |
| Git mutation | Inspect-only via `git_safety.py`. Round 3A additionally allows **worktree add/list/remove** only under session confinement — no reset/push/merge/commit. |
| Adapters | Always `automation_status: manual_handoff_required`. |
| Local pytest | `automation_status: local_allowlisted_execution` only after policy allow. |
| Risk | No auto-approve for high/critical risk; no auto rule rewrite / self-improvement. |
| Scope of work | Only projects in `config/projects.yaml`; unregistered IDs refused. |
| Provider CLIs | Claude / Cursor / Codex are **not** spawned (deferred to Round 3B). |

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

## 10. Round 3A shipped + deferred to 3B+

### Round 3A (done)

- Design: `docs/ROUND_3A_SAFE_EXECUTION_DESIGN.md`
- Sessions + confined worktrees for registered synthetic projects
- Allowlisted `python -m pytest` via argument arrays (`shell=False`)
- Env filtering, timeouts, output limits, path/symlink confinement
- Execution envelopes + `workspace/executions/` audit JSON
- CLI: `create-session`, `show-session`, `list-sessions`, `cleanup-session`, `run-tests`, `show-execution`

### Deferred to Round 3B+ (explicit approval)

- Equitify connection (connect phrase only)
- Real provider CLI adapters (Claude / Cursor / Codex spawn)
- Broader command profiles beyond pytest
- Automation beyond manual handoff + local allowlisted exec

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
| `README.md` | Install, Round 2 + 3A quick start |
| `docs/ARCHITECTURE.md` | Layers and data flow |
| `docs/ROUND_3A_SAFE_EXECUTION_DESIGN.md` | Round 3A safe execution design |
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
| *(Round 3A)* | Safe sessions, worktrees, allowlisted pytest, audits |
