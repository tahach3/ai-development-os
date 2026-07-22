# Round 3C — Bounded Orchestration & Deterministic Stalemate Detection

**Status:** Approved for implementation in this round  
**Scope:** Resumable implementation → test → review → repair orchestration over the Round 3B **simulated** provider; deterministic progress/stalemate; fail-closed bindings; operator CLI  
**Not in scope:** Live provider calls, arbitrary patch/command execution from provider text, Equitify, paid APIs, LangChain/CrewAI/AutoGen, dashboards, daemons, auto commit/merge/push/deploy

**Verified baseline commit (pre-implementation):** `87068fd1d7cf06a825ca914a184ed0e50c065490`  
(descendant of Round 3B `305c0d7`; post-305c0d7 only smoke-record docs; package was `0.4.0`; baseline tests 80 passed / 1 skipped)

**Package version target:** `0.5.0` (schema `3c.1`; Round 3A `3a.1` and 3B `3b.1` preserved)

---

## Self-review vs existing controls (contradictions resolved)

| Existing control | Round 3C resolution |
| --- | --- |
| Task lifecycle (`TaskStatus`) | Orchestration has its **own** state machine. Task status is updated only through existing `apply_status_transition` when orchestration reaches compatible milestones (e.g. implementing / ready_for_review / blocked). Orchestration never assigns arbitrary task states. |
| Plan approval + fingerprints | Every orchestration step re-validates approved plan fingerprint and approval validity via lifecycle/binding gates. |
| RepairRoundStore + `max_repair_rounds` | Orchestration **reuses** repair-round counting semantics; orchestration config may set a ceiling ≤ global safety; never resets counters; never rewrites plan/scope. |
| Round 3A safe pytest runner | Targeted tests always go through `session_exec` / allowlisted argv; provider output never chooses executables. |
| Round 3B provider policy | Default mode **simulated**; live modes refused by orchestration config + existing `assert_live_gates`. |
| Manual handoff adapters | Unchanged; orchestration does not replace prepare-handoff. |
| No provider-text execution | No patch engine; synthetic worktree mutations are **harness/fixture-controlled** only. |
| Equitify / registry sentinels | Bindings call existing registry + `assert_not_equitify_blob`; no Equitify path checks beyond sentinels. |
| Terminal task reopen rules | Terminal orchestration states do not silently reopen; cancel/complete/human_review require new record or explicit human action. |

No contradictions remain after separating: (1) task lifecycle, (2) orchestration lifecycle, (3) provider simulation lane, (4) harness mutations vs provider text.

---

## 1. Round 3C scope and non-goals

**In scope:** durable orchestration records/events/round evidence; allowlisted state machine; binding/staleness fail-closed checks; role-separated simulated impl/review; Round 3A tests in-loop; repair policy + deterministic stalemate; resume/idempotency; CLI; schemas; calculator-demo synthetic E2E.

**Non-goals:** live multi-agent automation claims; real Claude/Cursor/Codex model calls; executing provider text; unbounded retries; auto merge/push; Equitify; new OSS deps.

---

## 2. Orchestration lifecycle and state machine

States (schema `3c.1`):

| State | Meaning |
| --- | --- |
| `created` | Record persisted; not yet validated |
| `ready` | Bindings validated; eligible to start |
| `implementation_pending` | Next action is implementation request |
| `implementation_running` | Simulated implementation in progress |
| `implementation_result_pending_validation` | Result received; validating envelope |
| `testing_pending` | Ready for targeted tests |
| `testing_running` | Safe pytest running |
| `review_pending` | Ready for independent review |
| `review_running` | Simulated review in progress |
| `repair_required` | Verdict/tests require repair; awaiting repair start |
| `repair_pending` | Repair round opened; next impl pending |
| `completed` | Terminal success |
| `blocked` | Terminal / hard stop (policy, limits, failures) |
| `cancelled` | Terminal cancel |
| `human_review_required` | Terminal stalemate / escalation |

Transitions are allowlisted in code (`ORCH_TRANSITIONS`). Callers use engine methods only — no direct arbitrary state assignment. Each transition validates bindings, appends an event, persists atomically, and is idempotent on retry of a completed event ID.

Terminal states (`completed`, `cancelled`, `blocked`, `human_review_required`) do not reopen silently.

---

## 3. Durable orchestration records

`OrchestrationRecord` fields include schema/policy versions, IDs (orch/task/plan/approval/project/session/worktree), fingerprints (task/plan/impl-context/review-context), commits, roles, provider IDs/adapter versions/modes, counters (step/repair/retry), verdict/test/progress/stalemate statuses, stop reason, human-action requirement, timestamps, latest event ID, automation status.

No credentials or raw private transcripts — only sanitized request/result IDs and bounded artifacts.

---

## 4. Per-step and per-round records

- **Events:** unique `event_id`, from/to state, step number, failure class, refs, timestamp, notes (sanitized).
- **Round evidence:** one durable record per impl→test→review cycle with structured findings, fingerprints, progress/stalemate evidence (see §7 / §12).

---

## 5. Bindings

Immutable (or fail-closed if changed): task ID + fingerprint, plan ID + approved fingerprint, approval validity, project ID + registered root identity, session ID, worktree ID/path identity, starting commit, provider roles, adapter version compatibility, context fingerprints, invocation mode (simulated).

Revalidated **before every step**.

---

## 6. Implementation / reviewer role separation

Implementation role default: `cursor`. Review role default: `codex`. Same simulated adapter may serve both, but distinct request IDs, role bindings, and context fingerprints. Audit `automation_status` remains `simulated_provider_execution` — never claims two real independent providers.

---

## 7. Fresh-context requirements

Review context is rebuilt from: approved plan, acceptance criteria, bounded diff/files, implementation report refs, test results, current round unresolved findings. Not private impl chain-of-thought. Implementation result is never accepted as its own review.

---

## 8. Test execution placement

Flow: validate impl result → verify worktree → Round 3A targeted tests → normalize → fresh review context → simulated review → verdict.

Test argv from project/session policy only — never from provider payload.

---

## 9. Review verdict handling

Reuse `ReviewVerdict` / structured findings. Map:

- `pass` / `pass_with_notes` (if config allows) → toward `completed` (after counters)
- `changes_required` → repair path if eligible else block
- `blocked` → orchestration `blocked`

---

## 10. Repair-round creation and completion

May begin only when: changes_required **or** repairable test failure; no policy violation; no scope change; approval valid; repair count &lt; max; no stalemate.

Must not rewrite plan, broaden scope, change project/policy, disable tests, suppress findings, reset counters, or erase history.

At max: stop → `blocked` or `human_review_required`; persist reason; no further provider request.

Existing `RepairRoundStore` is updated for compatibility when a repair is recorded.

---

## 11. Progress evidence

Structured signals: diff fingerprint change, failing-test set shrink, test status improve, findings resolved, verdict improve, acceptance newly satisfied.

No-progress: identical diff / failing-test / findings fingerprints; empty file changes; repeated same `changes_required` evidence.

---

## 12. Deterministic stalemate detection

Not LLM-based. Detect:

- **A** Exact consecutive stalemate (threshold consecutive identical evidence tuples)
- **B** No-change repair (claimed success, no source/test/finding improvement)
- **C** Oscillation A→B→A in progress-state fingerprint window
- **D** Repeated malformed/unusable output

Config: `max_repair_rounds`, `max_total_steps`, `consecutive_no_progress_threshold`, `oscillation_history_window`. Missing required evidence → fail closed.

On detection: stop; preserve evidence; `human_review_required` (or `blocked` per config); no live escalate.

---

## 13. Oscillation detection

Maintain ring buffer of progress-state fingerprints; if length ≥ 3 and pattern `X,Y,X` without net improvement → stalemate class `oscillation_detected`.

---

## 14. Maximum repair rounds

From versioned orchestration config (default 3), aligned with `config/repair_rounds.yaml`. Task input cannot raise the global ceiling.

---

## 15. Maximum orchestration steps

Default conservative (e.g. 40). Hitting limit → `blocked` / `step_limit_reached`; no further provider calls.

---

## 16. Cancellation

Explicit cancel → `cancelled`; timestamp + event; survives restart; resume refused without new orchestration / explicit human redesign (not implemented as silent reopen).

---

## 17. Crash recovery and resume

Resume loads record; revalidates bindings; continues from current state; does not recreate missing artifacts under new fingerprints; does not reset counters. Partial writes use temp + atomic replace.

---

## 18. Idempotency

Completed step/event IDs return stored outcome. Duplicate provider request fingerprints reuse Round 3B duplicate detection. Duplicate step after crash does not re-execute side effects.

---

## 19. Duplicate-step prevention

Engine tracks `consumed_request_ids` / last completed event; refusing re-advance when already past.

---

## 20. Failure classification

Orchestration failure classes include (equivalent set):  
`policy_rejected`, `stale_binding`, `approval_invalid`, `project_not_registered`, `prohibited_path`, `session_invalid`, `worktree_invalid`, `starting_commit_mismatch`, `context_mismatch`, `provider_unavailable`, `provider_failed`, `provider_timeout`, `provider_cancelled`, `malformed_provider_result`, `duplicate_request`, `implementation_result_invalid`, `test_command_rejected`, `tests_failed`, `review_result_invalid`, `changes_required`, `repair_limit_reached`, `no_progress`, `oscillation_detected`, `step_limit_reached`, `scope_change_detected`, `reapproval_required`, `orchestration_cancelled`, `internal_persistence_error`.

Transient process failure ≠ repair round.

---

## 21. Human-escalation conditions

Stalemate, repair limit, scope/reapproval, policy hard denies, step limit, explicit blocked review → human action required; surfaced in status/`human_action_requirement`.

---

## 22. Atomic persistence

Write YAML/JSON via temporary sibling + `os.replace`. Events append then record replace in a defined order; crash mid-write fails closed on next load/validate.

---

## 23. Audit records

Orchestration events + Round 3B provider audit refs. Bounded, sanitized, no secrets/prompts.

---

## 24. Deterministic serialization

`sort_keys=True`, stable field ordering in `to_dict`, canonical fingerprints via existing `fingerprints` helpers.

---

## 25. Security threat model

Threats: unregistered/Equitify project, binding swap mid-loop, provider-text RCE, arbitrary tests, secret leakage, live call sneak-in, counter reset, continue-after-cancel/stalemate. Mitigations: registry sentinels, binding checks, no patch engine, safe runner, env filter, simulated-only default, immutable counters, terminal enforcement.

---

## 26. Compatibility and schema versioning

- Orchestration schema `3c.1`
- Unsupported schema version → fail closed
- Round 1–3B artifacts remain readable; not rewritten in place
- Package `0.5.0`

---

## 27. CLI design

Commands (names consistent with existing CLI):

- `create-orchestration`
- `validate-orchestration`
- `preview-orchestration`
- `orchestration-step`
- `run-orchestration` (until boundary; simulated default)
- `resume-orchestration`
- `show-orchestration`
- `orchestration-history`
- `show-stalemate-evidence`
- `cancel-orchestration`

No force/ignore-policy/reset-counter flags. Extend `project-status` with active orch fields.

---

## 28. Test matrix

Categories A–I per Round 3C brief; four calculator-demo simulated scenarios (direct success, one repair, stalemate, repair limit). Temporary synthetic repos only.

---

## 29. Explicitly deferred capabilities

Live provider orchestration; multi-real-provider independence; general patch application; auto merge/push/PR/deploy; Equitify connection; dashboards; unbounded agent fleets; LLM-based stalemate judges.

---

## 30. Acceptance criteria

- Baseline preserved; design recorded; simulated full loops work; stalemate/repair limits stop deterministically; bindings fail closed; tests A–I green with prior rounds; docs honest; one commit; zero live calls; Equitify untouched; final report complete.
