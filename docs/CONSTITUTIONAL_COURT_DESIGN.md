# Constitutional Court — Deterministic Gate Design

**Status:** Implemented (package **0.8.13**) — deterministic local preflight; no LLM / no 4D2

**Baseline (design):** package **0.8.12** · HEAD `92f1378` · branch `master`

**Implementation:** package **0.8.13** · Article XIV Court checkers + `approve_plan` major-change gate

**Constitution:** [`CONSTITUTION.md`](CONSTITUTION.md) Article XIV (Court); related I–II, V, VIII, X–XIII, XV, XVII

**Operational priors:** [`SECURITY_MODEL.md`](SECURITY_MODEL.md), [`PROJECT_BOUNDARIES.md`](PROJECT_BOUNDARIES.md), `config/risk_levels.yaml`

**Code style priors:** `lifecycle_gates.py`, `review_gate.py`, `approval.py`, `ci_boundaries.py`, `fingerprints.py`

**Not in scope (still LOCKED / deferred):** Round 4D2 / live models / network / paid APIs; wiring memory into orchestration; Equitify content inspection; LLM-based Court; auto-blocking merge/push/deploy; soft-bypass of `rejected`; mandatory CI `STAGE_ORDER` insert.

---

## 1. Purpose and non-goals

### 1.1 Purpose

Provide an **independent, deterministic, fail-closed** pre-approval review that answers Article XIV’s five questions for a proposed change (primarily a **plan** bound to a **task**), emits an auditable **Court record**, and (when required) blocks progression until findings are resolved or a human explicitly overrides under documented rules.

The Court is software governance, not a model:

- Deterministic code before AI (Article II / VII).
- Evidence stronger than assumptions (Article II).
- Fail closed instead of guessing (Article II / X).
- Every important action auditable (Article II / VIII).

### 1.2 Non-goals

| Non-goal | Why |
| --- | --- |
| Semantic “understanding” of proposal quality | Requires LLM/judgment; deferred |
| Replacing human plan approval | Court advises/blocks gates; Taha remains final authority (Articles III / XIV + approval.py) |
| Replacing code review (`review_gate`) | Review judges implementation quality; Court judges constitutional fitness of the *proposal* |
| Auto-merge / auto-push / auto-deploy | Forbidden by SECURITY_MODEL |
| Live provider / Round 4D2 unlock | Explicitly locked |
| Memory → orchestration wiring | Explicitly deferred |
| Equitify inspection or integration | Article XV + PROJECT_BOUNDARIES |
| Amending the Constitution | Article XVII; Court enforces, does not rewrite |

---

## 2. Article XIV mapping — five deterministic checks

Article XIV:

> Before any major change, an independent review checks:  
> 1. Does it violate the Constitution?  
> 2. Does it reduce safety?  
> 3. Does it increase risk?  
> 4. Is it reproducible?  
> 5. Is it measurable?  
> If any answer fails, the proposal is rejected.

### 2.1 Verdict polarity (fail-closed)

Each question yields a **check result**:

| Result | Meaning |
| --- | --- |
| `pass` | Structured evidence satisfies the rule table |
| `fail` | Evidence shows violation / unsafe / non-reproducible / non-measurable |
| `insufficient_evidence` | Required inputs missing or incomplete — **treated as fail** for required Court runs |

Overall Court verdict is `rejected` if **any** of the five checks is `fail` or `insufficient_evidence` (Article XIV: any fail → reject). Optional advisory runs may surface `advisory_fail` without mutating lifecycle (see §5).

### 2.2 Question 1 — Does it violate the Constitution?

**Operationalized as:** rule-table match against declared intents, paths, prohibited actions, and task/plan metadata — **not** free-text constitutional interpretation.

**Structured inputs:**

- Task: `project_id`, `task_type`, `complexity`, `risk_level`, `allowed_paths`, `prohibited_paths`, acceptance criteria
- Plan: `objective`, `scope`, `prohibited_actions`, `files_expected_to_change`, `implementation_steps`, `risks`, `unresolved_questions`, `approval_requirement`, `risk_level`
- Registry / policy: project roots, Equitify sentinels, `config/risk_levels.yaml` `prohibited_without_user_command`
- Optional evidence refs: path list from plan, declared “authorization tokens” (boolean flags in evidence envelope — never secrets)

**Rule table (v1 sketch — fail closed):**

| Rule ID | Article | Fail when |
| --- | --- | --- |
| `C-GOV-001` | III / V | Plan claims self-approval or removes human approval for high/critical |
| `C-GOV-002` | V | Scope includes deleting/rewriting audit history paths (`workspace/**/audit*`, provider_executions wipe, etc. — path needles) |
| `C-SEC-001` | X | Paths/strings match Equitify sentinels without explicit `user_authorized_equitify: true` evidence (default false → fail) |
| `C-SEC-002` | X / SECURITY_MODEL | Declared intent includes paid LLM / network model / live provider without `user_authorized_4d2: true` (default false → fail) |
| `C-SEC-003` | X | Declared intent includes reading env secrets, storing API keys, executing generated provider text |
| `C-MEM-001` | VI / IX | Declared intent auto-activates learning / auto-approves memory / wires memory into orchestration (v1: keyword + flag denylist) |
| `C-BIZ-001` | XV | Cross-project merge / Equitify adapter without explicit authorization flag |
| `C-EVO-001` | XIII | Declared “self-rewrite OS constitution/core gates” without amendment evidence |
| `C-ENG-001` | VIII | Major-change plan missing required engineering fields (tests, rollback, docs intent) — see Q4/Q5 overlap |

Missing authorization flags default to **false**. Unknown rule IDs in config → `unsupported_rule` failure class.

**Cannot prove:** that prose “objective” is morally aligned; only that declared structure does not trip known constitutional prohibition needles.

### 2.3 Question 2 — Does it reduce safety?

**Operationalized as:** safety-surface regression checks against SECURITY_MODEL hard prohibitions + existing gate invariants.

**Structured inputs:**

- Plan `prohibited_actions` (must *include* denials of known dangerous acts for high/critical — or evidence must list compensating controls)
- `files_expected_to_change` intersected with safety-critical path prefixes (reuse Round 4A/4E notions: auth, secrets, `safe_exec`, `safe_policy`, provider live gates, CI permissions, approval gates)
- Explicit evidence booleans: `weakens_authz`, `disables_fail_closed`, `enables_shell_true`, `removes_output_caps`, `auto_approve_high_risk` (operator/planner-supplied; default **assume true risk** if safety-critical paths touched and flags absent → `insufficient_evidence`)

**Rule table (v1):**

| Rule ID | Fail when |
| --- | --- |
| `S-001` | Safety-critical paths in scope AND no `safety_impact_declared: true` |
| `S-002` | Any evidence flag `weakens_authz` / `disables_fail_closed` / `auto_approve_high_risk` is true |
| `S-003` | Plan removes or narrows `prohibited_actions` relative to task risk (high/critical must list ≥ N required prohibitions from policy) |
| `S-004` | Touches GitHub workflow permissions / secrets patterns without human_review evidence |

**Cannot prove:** runtime absence of all vulns (no vuln DB — SECURITY_MODEL deferred).

### 2.4 Question 3 — Does it increase risk?

**Operationalized as:** compare declared `risk_level` / `complexity` to blast-radius signals; reject under-classification and unexplained risk jumps.

**Structured inputs:**

- Task + plan `risk_level`, task `complexity`
- Path/count signals: file count, safety-critical hits, public API / schema version bumps declared in evidence
- Prior approved plan fingerprint risk (if superseding)

**Rule table (v1):**

| Rule ID | Fail when |
| --- | --- |
| `R-001` | Signals imply ≥ high (safety-critical paths, equitify, live provider, schema/policy version change) but declared risk is low/medium |
| `R-002` | `risk_level` high/critical but `approval_requirement` is `none` |
| `R-003` | Plan risk < task risk (plan understates task) |
| `R-004` | High/critical without non-empty `risks[]` and `rollback_or_recovery_plan[]` |
| `R-005` | Unresolved questions non-empty on high/critical without `accept_unresolved: true` human flag in evidence (default false → fail for *required* Court) |

**Increase** means: classified risk rises vs baseline task, or undeclared latent high/critical signals. Court does not invent a numeric risk score beyond enum + rule hits.

### 2.5 Question 4 — Is it reproducible?

**Operationalized as:** presence of commit lock, fingerprints, and enough procedure to re-run without private chat state.

**Structured inputs:**

- `starting_commit` present and well-formed
- Plan/task content fingerprints (computed, not trusted from input alone)
- `implementation_steps[]`, `testing_plan[]` non-empty for major changes
- Evidence: `fixture_or_seed_refs[]` when claim depends on synthetic data; `commands_are_argv_only: true` default expectation for OS-owned automation

**Rule table (v1):**

| Rule ID | Fail when |
| --- | --- |
| `P-001` | Missing/blank `starting_commit` |
| `P-002` | Major change with empty `implementation_steps` or empty `testing_plan` |
| `P-003` | Evidence claims network/live model required for success (`requires_network` / `requires_live_model` true) while 4D2 unauthorized |
| `P-004` | Steps reference only “ask the model” / chat paste with no file/fixture/command identity (denylist phrases on steps — conservative) |

**Cannot prove:** that another machine will get bit-identical results; proves **declared** reproducibility artifacts exist.

### 2.6 Question 5 — Is it measurable?

**Operationalized as:** Article XII / VIII — every change must declare how success is measured.

**Structured inputs:**

- `testing_plan[]`
- Evidence: `metrics_declared[]` from allowlist (`tests_pass`, `ci_check_ok`, `repair_count`, `latency`, `cost`, `human_corrections`, `accepted_outputs`, `failures`, `behavioral_report`)
- Acceptance criteria on task non-empty for major changes

**Rule table (v1):**

| Rule ID | Fail when |
| --- | --- |
| `M-001` | Major change with empty task `acceptance_criteria` |
| `M-002` | Empty `testing_plan` (overlaps P-002; double-coded as measurement gap) |
| `M-003` | No `metrics_declared` and no mapping from testing_plan to allowlisted metric tokens |
| `M-004` | Claims `vulnerability_scan` success without `vuln_db_queried: true` (default false → fail) — aligns with reporting honesty |

**Cannot prove:** that metrics will improve; only that measurement hooks are declared.

---

## 3. How answers are produced WITHOUT an LLM

```text
EvidenceEnvelope (JSON)
        + Task + Plan (+ optional path list)
        ↓
Load rule tables (version-pinned)
        ↓
Deterministic evaluators (pure functions)
        ↓
Per-question CheckResult + Finding[]
        ↓
Aggregate CourtRecord (verdict, fingerprints)
        ↓
Persist under workspace/ (gitignored runtime) + optional stdout JSON
```

| Mechanism | Role |
| --- | --- |
| Structured evidence envelope | Planner/operator supplies booleans, refs, metric lists — no prose judgment required for pass |
| Versioned rule tables | YAML/JSON under `config/` (future) with `court_rules_version`; unknown version → fail closed |
| Path / sentinel needles | Reuse Equitify sentinels, prohibited substrings, safety-critical prefixes (ci / safe_policy style) |
| Fingerprints | `fingerprints.py` over task/plan/evidence/court payload |
| Fail-closed defaults | Missing optional evidence fields → `insufficient_evidence` on required runs |
| No network | CLI argv + local files only; no model calls |

Independence (Article XIV “independent review”): Court code must not be the same agent identity as `planner_agent` for **required** runs on high/critical (mirror `approval.py` self-approval ban). Record `court_agent` / `evaluated_by` must differ from planner when `risk_level ∈ {high, critical}` OR human operator runs CLI.

---

## 4. Record model / schema sketch

Align with `ReviewReport` + CI result patterns: enums, findings, fingerprints, schema version, failure classes, `to_dict` / `from_dict`.

### 4.1 Proposed schema version

`court_schema_version`: **`14.1`** (Article XIV, first deterministic court)

### 4.2 Enums

```text
CourtVerdict:
  pass
  pass_with_notes      # no failing checks; minor/note findings only
  rejected             # any question fail / insufficient_evidence
  blocked              # config/registry/integrity failure — cannot evaluate
  advisory_only        # optional run recorded; lifecycle not gated

CourtCheckId:
  constitution_violation
  safety_regression
  risk_increase
  reproducibility
  measurability

CourtCheckResult: pass | fail | insufficient_evidence

CourtFindingSeverity: blocker | major | minor | note   # mirror FindingSeverity

CourtFailureClass:
  none
  constitution_violation
  safety_regression
  risk_underclassified
  risk_increase
  not_reproducible
  not_measurable
  insufficient_evidence
  self_review_forbidden
  unsupported_schema_version
  unsupported_rules_version
  equitify_boundary
  live_provider_locked
  registry_incompatible
  fingerprint_mismatch
  internal_error
```

### 4.3 Dataclass sketch (design only)

```text
CourtFinding:
  check_id: CourtCheckId
  rule_id: str              # e.g. S-002
  severity: CourtFindingSeverity
  summary: str
  evidence_refs: list[str]  # keys/paths into envelope or plan fields
  path: str | None

CourtCheckOutcome:
  check_id: CourtCheckId
  result: CourtCheckResult
  findings: list[CourtFinding]

CourtRecord:
  schema_version: "14.1"
  court_rules_version: str
  record_id: str
  task_id: str
  plan_id: str
  project_id: str
  required: bool            # major-change gate vs advisory
  evaluated_by: str
  evaluated_at: str         # utc iso
  starting_commit: str
  verdict: CourtVerdict
  checks: list[CourtCheckOutcome]  # exactly five
  findings: list[CourtFinding]     # flat union
  failure_classes: list[str]
  notes: str | None
  task_fingerprint: str
  plan_fingerprint: str
  evidence_fingerprint: str
  content_fingerprint: str  # fingerprint of stable court payload
  next_action: str          # e.g. "fix findings and re-run" | "approve-plan allowed"
```

### 4.4 Evidence envelope sketch

```text
CourtEvidenceEnvelope:
  schema_version: "14.1"
  user_authorized_equitify: bool = false
  user_authorized_4d2: bool = false
  safety_impact_declared: bool = false
  weakens_authz: bool = false
  disables_fail_closed: bool = false
  enables_shell_true: bool = false
  removes_output_caps: bool = false
  auto_approve_high_risk: bool = false
  accept_unresolved: bool = false
  requires_network: bool = false
  requires_live_model: bool = false
  commands_are_argv_only: bool = true
  vuln_db_queried: bool = false
  metrics_declared: list[str] = []
  fixture_or_seed_refs: list[str] = []
  safety_critical_paths_touched: list[str] = []  # optional override/supplement
  authorization_note: str | None                 # human prose; not parsed for pass
```

Persistence (implementation later): `workspace/court_records/<record_id>.json` (runtime, gitignored), analogous to reports/CI artifacts.

---

## 5. When Court is required vs optional — “major change”

### 5.1 Operational definition of major change

A change is **major** (Court **required** before `approve-plan`) if **any** of:

| Signal | Source |
| --- | --- |
| `task.risk_level` or `plan.risk_level` ∈ `{high, critical}` | models + risk_levels.yaml (`auto_approve_forbidden`) |
| `task.complexity` == `high_risk` | models.Complexity |
| Safety-critical path intersection non-empty | plan `files_expected_to_change` ∩ policy prefixes |
| Declared intents touching locked domains | evidence or prohibited needle hits for 4D2 / Equitify / self-improvement / secret handling |
| Schema/policy/constitution amendment scope | paths under `docs/CONSTITUTION.md`, `config/*policy*`, `approval.py`, `lifecycle_gates.py`, `safe_policy.py`, provider live gates |
| `task_type` ∈ `{architecture}` OR plan scope lists “rewrite core lifecycle” | conservative |

Otherwise Court is **optional / advisory** (`required=false`, verdict may be `advisory_only` even if checks fail — does not block `approve-plan` by default).

**Medium** risk: advisory recommended; not hard-required in v1 (keeps friction aligned with existing human approval already required for medium in risk_levels.yaml).

**Low** risk: optional only.

### 5.2 Interaction with existing approval

- High/critical already ban planner self-approval (`approval.py`).
- Court adds a **second** independent artifact: passing `CourtRecord` fingerprint locked into task metadata at approval time (e.g. `court_record_id`, `court_content_fingerprint`), similar to `approved_plan_fingerprint`.
- Human may still reject a Court `pass` (authority). Human override of Court `rejected` on required runs is **out of band** for v1 (no soft bypass flag); fix evidence/plan and re-run. (Future: explicit `ceo_override` with audit — deferred.)

---

## 6. Lifecycle integration (no 4D2 unlock)

```text
create-task → plan → submit-plan
                         ↓
              [constitutional-check]  ← NEW (local, deterministic)
                         ↓
         required+rejected → stop (do not approve-plan)
         required+pass     → approve-plan (existing human gate)
         advisory          → approve-plan allowed regardless
                         ↓
              prepare-handoff / implement / validate
                         ↓
              review_gate (implementation review)
                         ↓
              ready_to_commit / complete
```

| Stage | Court role |
| --- | --- |
| Before `submit-plan` | Optional dry-run |
| After `submit-plan`, before `approve-plan` | **Required** if major; gate in `approve_plan` (future) reads latest Court record + fingerprints |
| During implement | Not re-run unless plan content fingerprint changes (invalidate like approval invalidation) |
| At `review_gate` | Orthogonal — code review; may *consume* Court record id as context later (not required v1) |
| CI `validate-change` / `ci-check` | Optional future hook; **not** mandatory STAGE_ORDER insert in first implementation |
| Orchestration / providers | **No** wiring; Court does not call providers |
| Memory | **No** auto-store of Court prose; optional later “approved fact” propose is deferred |

Handoff packets may include Court verdict summary (fingerprint + verdict only) without unlocking live models.

---

## 7. CLI sketch — `constitutional-check`

Local, argv/JSON, **no network**.

```text
ai-dev-os constitutional-check
  --task-id ID
  --plan-id ID
  [--evidence PATH.json]
  [--evaluated-by NAME]
  [--required | --advisory]
  [--output PATH.json]
  [--json]                  # stdout machine record
```

Behavior:

1. Load task + plan from stores; validate registry (Equitify still refused).
2. Load evidence envelope (default empty → fail-closed on required).
3. Infer `required` from §5 unless flag overrides (`--advisory` forces optional; `--required` forces required evaluation semantics).
4. Evaluate five checks; write `CourtRecord`.
5. Exit codes: `0` pass / pass_with_notes; `2` rejected; `3` blocked; `4` usage/validation error.
6. Never invokes providers, never reads `.env` secrets, never touches Equitify paths for content (sentinel fail only).

Show helper (optional later): `show-court-record --record-id …`

---

## 8. Failure classes / verdict vocabulary

### 8.1 Verdicts (operator-facing)

| Verdict | Lifecycle effect (required run) |
| --- | --- |
| `pass` | Approval allowed (still needs human `approve-plan`) |
| `pass_with_notes` | Approval allowed; notes/minor findings recorded |
| `rejected` | Approval blocked until new passing record on same plan fingerprint |
| `blocked` | Cannot evaluate — fix registry/schema/rules/self-review |
| `advisory_only` | Informational; approval not blocked by Court |

### 8.2 Failure classes

See §4.2. Multiple classes may appear; any blocker/major finding under a failed check → `rejected`.

Article XIV mapping:

| Question | Primary failure classes |
| --- | --- |
| Violate Constitution? | `constitution_violation`, `equitify_boundary`, `live_provider_locked` |
| Reduce safety? | `safety_regression` |
| Increase risk? | `risk_underclassified`, `risk_increase` |
| Reproducible? | `not_reproducible`, `insufficient_evidence` |
| Measurable? | `not_measurable`, `insufficient_evidence` |

---

## 9. Test matrix (for future implementation)

| Case | Expect |
| --- | --- |
| Low-risk plan, empty evidence, advisory | `advisory_only` or pass with notes; exit 0 |
| High-risk, empty evidence, required | `rejected` / `insufficient_evidence` |
| High-risk, planner == evaluated_by | `blocked` / `self_review_forbidden` |
| Equitify path in files_expected | `rejected` / `equitify_boundary` unless authorized flag (still no file read of Equitify) |
| `requires_live_model: true` without 4D2 auth | `rejected` / `live_provider_locked` |
| Safety-critical path, no safety_impact_declared | `rejected` |
| Risk low but safety-critical paths | `rejected` / `risk_underclassified` |
| High-risk, full evidence, steps+tests+metrics+rollback | `pass` |
| Plan fingerprint change after pass | Old record not valid for approve (fingerprint mismatch) |
| Unsupported schema/rules version | `blocked` |
| Malformed evidence JSON | validation error exit 4 |
| No network sockets in unit tests | enforced by pure functions / monkeypatch absence |
| Medium risk required override `--required` | insufficient evidence fails |

Golden fixtures: JSON task/plan/evidence → expected verdict + rule_ids (deterministic).

---

## 10. Explicitly deferred

| Item | Status |
| --- | --- |
| LLM / multi-model “Court justices” | Deferred |
| Auto-blocking git merge / push / GitHub required check | Deferred |
| Memory wiring into orchestration or auto-propose Court outcomes | Deferred |
| Equitify adapter / inspection | Deferred (fail closed only) |
| Round 4D2 live models / paid APIs | **LOCKED** |
| CEO override soft-bypass of rejected Court | Deferred |
| Mandatory `ci-check` STAGE_ORDER insertion | Deferred |
| Vuln-DB-backed safety claims | Deferred (honesty: unavailable) |
| Production Python modules / CLI / version bump | **After design approval** |

---

## 11. Honesty — what Court can and cannot prove

**Can:**

- Enforce declared structure against versioned rule tables.
- Fail closed on missing evidence for major changes.
- Detect under-classified risk vs path/intent signals.
- Block known locked domains (Equitify, 4D2, secret handling, auto self-improvement) when declared or needle-matched.
- Produce auditable fingerprints for approval binding.
- Remain fully offline and deterministic.

**Cannot:**

- Prove the plan is the *right* product decision.
- Prove implementation will be correct (that is review + tests).
- Prove absence of novel security holes or prompt-injection in future live providers.
- Interpret natural-language intent beyond denylist/allowlist heuristics (those heuristics will have false positives/negatives).
- Replace Taha’s authority or Article XVII amendment process.
- Claim “constitutional compliance” as moral certainty — only **rule-table non-violation under supplied evidence**.

---

## 12. Implementation outline (after approval only)

1. Add models + pure `constitutional_court.py` evaluators (mirror `ci_boundaries` purity).
2. Add `constitutional-check` CLI; persist records under `workspace/`.
3. Gate `approve_plan` for major changes on fresh matching Court pass fingerprint.
4. Tests per §9; no version bump until green.
5. Docs: ROADMAP/CHRONICLE note — capability is governance gate, not 4D2.

**Recommended next step:** approve this design, then implement.

---

## 13. Baseline confirmation

| Item | Value |
| --- | --- |
| HEAD | `92f1378` (`Adopt Constitution and Self-Build Strategy as governance docs`) |
| Package | `0.8.12` |
| Branch | `master` |
| Push | Not performed |
| This document | Design-only; left **uncommitted** for human review |
