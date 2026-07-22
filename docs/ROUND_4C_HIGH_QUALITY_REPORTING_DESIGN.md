# Round 4C — High-Quality, Evidence-First Reporting System

**Status:** Design for Round 4C implementation  
**Scope:** Canonical evidence + claim-status model, audience/detail renderers, deterministic relevance, integrity fingerprints, CLI, local immutable report storage  
**Not in scope:** Live providers, LLM summaries, dashboards, SaaS, vuln DB queries, auto-merge/deploy, Equitify, rewriting historical reports  

**Verified baseline commit (pre-implementation):** `9f7ec38410c4758e53bb7d4f561bdd2aff839b64`  
(Round 4B closeout; package `0.6.0`; baseline tests 134 passed / 2 skipped; remote CI `29932471573`)

**Package version target:** `0.7.0`  
**Schema / policy IDs:** evidence `4c.1`, report `4c.1`, report_policy `4c.1`, relevance_policy `4c.1`, redaction_policy `4c.1`, renderer `4c.1`

---

## Self-review vs existing controls (contradictions resolved)

| Existing control | Round 4C resolution |
| --- | --- |
| Legacy `ImplementationReport` / `ReviewReport` / behavioral | Preserved as evidence sources via adapters; never mutated; claim status defaults to `reported` unless backed by authoritative artifacts |
| `TokenUsageMode` (measured/estimated/unavailable) | Reporting usage fields use richer evidence states (`measured`/`provider_reported`/`estimated`/`unavailable`/`not_applicable`); legacy maps without inventing zeros |
| CI dependency-policy vs vuln scan | Reports must emit `vulnerability_scan: unavailable` unless a real vuln DB was queried (Round 4C never queries one) |
| Orch/provider simulation | Always labeled simulation; never presented as live model results |
| `ReportStore` non-atomic writes | New canonical/rendered stores use `atomic_io`; legacy store unchanged |
| Fingerprints exclude volatile timestamps | Report/source-set fingerprints exclude `generated_at` and rendering-only fields |
| No LLM / no network for report build | Relevance + executive summary are rule/template based; build from persisted records only |
| Equitify / prohibited paths | Build/render refuse Equitify identifiers and escapes; reuse registry sentinels |
| Free-form acceptance criteria strings | Matrix rows require claim status + evidence IDs; `passed` needs ≥1 acceptable evidence item |

No contradictions remain after separating: (1) canonical facts/evidence, (2) relevance decisions, (3) rendered Markdown, (4) task/review/CI verdicts vs report status.

---

## 1. Reporting goals

Produce audience-appropriate reports from one canonical evidence set that never invents data, never promotes `reported` → `verified` silently, and never hides critical blockers.

## 2. Non-goals

LLM summaries; dashboards; cloud upload; auto purge; live GitHub polling during render; rewriting Round 1–4B artifacts; connecting Equitify; vulnerability database scanning.

## 3. Report audiences

`executive` | `operator` | `developer` | `independent_reviewer` | `auditor` — each with mandatory section sets defined in relevance policy (Phase 4 brief).

## 4. Report detail levels

`summary` | `standard` | `full` | `audit` — independent of audience; unsupported combinations rejected only when logically invalid (none currently forbidden).

## 5. Canonical evidence architecture

Evidence items are versioned records (`schema_version=4c.1`) with IDs, types, source locators/fingerprints, authority, verification, claim links, structured values, safe summaries, sensitivity, redaction/truncation flags, integrity hash, producer/policy versions. Reports reference evidence; they do not embed raw records wholesale.

## 6. Report lifecycle

`build` (gather → validate bindings → snapshot) → `persist canonical` → `render` (audience/detail) → `persist rendered` → `validate` / `show`. Finalized canonical records are immutable; regeneration creates a new report ID or rendering artifact.

## 7. Evidence lifecycle

Collect → normalize via adapter → redact → integrity-hash → attach to manifest → freeze with report. Stale when source fingerprints diverge after freeze.

## 8. Claim-status model

`verified` | `reported` | `inferred` | `conflicting` | `unavailable` | `not_applicable` with Phase 6 rules. Legacy `"unknown"` normalizes to `unavailable`.

## 9. Evidence-source model

`source_type` / `source_record_type` / `source_record_id` / safe locator. Authority levels: `authoritative_persisted` > `deterministic_derived` > `agent_reported` > `operator_supplied` > `external_unverified`.

## 10. Relevance-selection rules

Deterministic rule table (section ID → audiences, detail levels, mandatory conditions, include/omit/collapse, priority, evidence requirements, order). Critical blockers/high risks/failed CI/missing approval/conflicts always included. Decisions stored with rule IDs.

## 11. Section ordering

Fixed global order (renderer `4c.1`): status_glance → executive_summary → objective_scope → outcome → acceptance → changes → validation → tests → ci → review → security_deps → failures_repairs → provider_orch → usage → risks → approvals → next_action → evidence_summary → audit_appendix. Empty headings omitted.

## 12. Executive-summary rules

Template-only; banned vague phrases (`perfect`, `fully secure`, `production ready`, `completely tested`, `all good`) unless precise policy+evidence (none in 4C). Confidence derived from claim/evidence completeness.

## 13. Technical-detail rules

Developer/full includes files, tests, CI, repairs, reproduction. Executive never dumps raw logs or long file lists.

## 14. Audit-appendix rules

Auditor/audit includes fingerprints, policy versions, evidence manifest, redaction events, timeline, unresolved conflicts. Completeness over brevity; still readable.

## 15. Git evidence

From `git_safety` / supplied records: identity, branch, commits, dirty, worktree, file change classes, safety-critical/deps/workflow/schema/test/docs classification. No full raw diffs in normal reports.

## 16. Code-change evidence

Added/modified/deleted/renamed when available; line stats when available; documentation-only classification when all changes are docs.

## 17. Test evidence

Normalized counts; never fabricate; preserve skipped/xfail; distinguish targeted vs full; preserve attempt history; coverage only when measured.

## 18. CI evidence

Local/remote from persisted `CIRun` / operator records; no network required to render. Remote unavailable → explicit `unavailable`.

## 19. Security evidence

Findings severity `critical|high|medium|low|informational`; clean scan ≠ “secure”.

## 20. Dependency evidence

Policy verdict separate from vuln scan; vuln scan defaults `unavailable`.

## 21. Provider and orchestration evidence

Simulation labeled; no raw prompts/transcripts/secrets.

## 22. Usage / token / cost / latency

Each field has evidence state; never zero-fill unavailable; monetary cost requires currency + pricing source.

## 23. Approval evidence

Type, approver (safe id), timestamps, fingerprints, validity, invalidation, supersession, high-risk self-approval check.

## 24. Failure and repair evidence

Repair rounds with triggering findings, files, tests, progress fingerprint, scope/reapproval, outcome.

## 25. Root-cause model

Confidence vocabulary: `confirmed|strongly_supported|probable|possible|unresolved`. Confirmed requires direct evidence.

## 26. Risk model

Canonical risks with severity counts; no invented overall numeric score.

## 27. Unresolved-issue model

Explicit list with claim status, evidence, blocking flag.

## 28. Next-action model

Specific, ordered, typed, required/optional, linked to blockers/risks; never recommend Equitify.

## 29. Redaction model

Fail-closed; before persistence of user-facing fields; record category/event; never store removed secret elsewhere; reuse `ci_secrets.redact_secrets` + extra path/prompt rules.

## 30. Privacy classification

`public_safe` | `internal` | `restricted` | `audit_only` on reports and evidence.

## 31. Report-integrity fingerprints

- **source_set_fingerprint:** sorted evidence integrity hashes + binding IDs (task/plan/orch/commits/policy versions)  
- **report_fingerprint:** semantic snapshot excluding `generated_at`, rendered paths, volatile show metadata  
Documented in code constants `REPORT_FP_EXCLUDE` / `SOURCE_SET_FIELDS`.

## 32. Deterministic serialization

`canonical_json` / sorted keys / stable list sorts by ID.

## 33. Atomic persistence

`atomic_write_json` / `atomic_write_text` for canonical and rendered artifacts.

## 34. Schema versioning

Evidence schema `4c.1`; report schema `4c.1`; unsupported versions → `invalid` / `unsupported_version` legacy mark.

## 35. Renderer versioning

`renderer_version=4c.1`; wording-only renderer bumps do not invalidate evidence schema.

## 36. Policy versioning

`report_policy_version`, `relevance_policy_version`, `redaction_policy_version` independently `4c.1`.

## 37. Backward compatibility

Legacy reports readable via adapters; marks `legacy_supported` / `partially_supported` / `insufficient_evidence` / `unsupported_version`. No silent verified promotion of missing fields.

## 38. Stale-evidence handling

Validate compares frozen source fingerprints to current sources; mismatch → report status `stale`.

## 39. Conflicting-evidence handling

Material conflicts → claim `conflicting` and report status `conflicting_evidence`; authoritative test/CI evidence preferred over agent success claims.

## 40. Partial-report handling

Missing mandatory evidence → `incomplete`; `--allow-incomplete-diagnostic` permits diagnostic render of incomplete/stale.

## 41. Retention and archival policy

Classifications: `ephemeral` | `task_lifetime` | `project_history` | `audit_required`. No automatic deletion in 4C.

## 42. CLI design

`build-report`, `render-report`, `validate-report`, `show-report` with project/task/orch/report IDs, audience, detail, format, output, json, allow-incomplete-diagnostic.

## 43. Failure classes

`schema_invalid`, `integrity_mismatch`, `stale_source`, `missing_mandatory_evidence`, `dangling_reference`, `duplicate_evidence_id`, `unsupported_version`, `prohibited_path`, `redaction_required`, `conflicting_material`, `blocked_workflow`, `internal_error`.

## 44. Test matrix

Ten synthetic scenarios (Phase 29) + Phase 30 unit/integration list; calculator-demo + temp repos only.

## 45. Migration strategy

No rewrite of historical JSON; importers only; new paths under `workspace/reports/{canonical,rendered,manifests}/`.

## 46. Explicitly deferred

Interactive dashboards; auto retention purge; live remote CI refresh; LLM narrative; vulnerability DB; multi-format PDF/HTML; cloud sync; Equitify project reports; mutating legacy fingerprints.

---

## Storage layout (adapted)

```
workspace/reports/
  implementation/   # legacy (unchanged)
  review/           # legacy (unchanged)
  canonical/        # Round 4C snapshots (gitignored)
  rendered/         # Markdown/JSON views (gitignored)
  manifests/        # optional evidence manifests (gitignored)
```

## Package decision

Significant new subsystem → package **`0.7.0`**. Schema/policy/renderer versions remain independently `4c.1`.
