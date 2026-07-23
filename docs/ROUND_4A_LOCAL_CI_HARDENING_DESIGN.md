# Round 4A Hardening — Local CI Ergonomics, Regression Awareness & Cross-Platform Determinism

**Status:** Complete (additive layer on the existing Round 4A/4B local CI foundation)
**Package version target:** `0.8.4` (CI schema/policy unchanged at `4a.1`; prior round schemas preserved)
**Baseline (pre-hardening):** committed `master` HEAD `330ffa3` (Round 4D1.3), branch tip `e15878e`, package `0.8.3`

**Scope:** Cross-platform sanitization fix; deterministic targeted / related-module test selection; CI run
history + regression comparison; deterministic human-readable CI report rendering; two new sanitized artifact
schemas.

**Explicitly NOT in scope (unchanged boundaries):** GitHub Actions changes, cloud runners, external APIs,
automatic PR creation, automatic merge/push/deploy, autonomous model execution, live model prompts (Round 4D2
remains LOCKED), Equitify, new runtime dependencies, vulnerability-database scanning, workflow permission
expansion.

---

## 0. Why this document exists (baseline reality)

The Round 4A brief asked to "build a deterministic local CI system." **That system already exists** and is
remote-validated:

- `eeebbe7` shipped Round 4A (`ci-check`, `validate-change`, workflow definition, package `0.6.0`).
- Round 4B validated it privately on GitHub Actions (first success run `29930178622`; latest `29982270706`).
- The uploaded Round 3A handoff (which says "Round 2 done, commit `a41c0f4`, Round 3A next") is a **stale
  snapshot**. The live repository is at Round 4D1.3 / package `0.8.3`.

Re-implementing Round 4A would destroy working, tested, remote-green code — the opposite of the brief's
"preserve all current behavior." So this round is an **additive hardening pass**: it fills the genuine gaps
the brief lists but the current pipeline lacks, and it fixes the one thing that makes the suite red on Linux
(where CI actually runs). Nothing in the fixed pipeline is reordered, removed, or weakened.

---

## 1. Phase 1 — Repository inspection (read-only findings)

### 1.1 Current execution flow
Config → Schemas → Domain models → Services → CLI. The CLI (`src/ai_dev_os/cli.py`, ~2000 LOC, argparse
subcommands each dispatching `cmd_*` → `args.func(args)`) is the single operator entry point. Runtime
artifacts land under gitignored `workspace/`.

### 1.2 Orchestration entry points
`orchestration_engine.py` + `create-orchestration` / `run-orchestration` / `resume-orchestration` CLI verbs
drive **simulated** impl→test→review→repair rounds with stalemate detection (Round 3C). CI never starts live
orchestration; it may read sanitized aggregates only.

### 1.3 Testing architecture
`pytest` with `pythonpath=["src"]`, `testpaths=["tests"]`. 20 test modules, one per round/subsystem. The
Round 4A CI `pytest_suite` stage runs the **whole** suite via the sanitized argv-only runner.

### 1.4 Report generation flow
Two families: Round 4C evidence-first multi-audience reporting (`reporting_*`, `build-report`/`render-report`)
and the Round 4A CI envelopes (`CIRun`, `PRValidationSummary`) emitted as sorted-key JSON. Neither summarizes
via an LLM.

### 1.5 Review pipeline
`review_gate.py` + lifecycle gates classify safety-critical changes as `human_review_required`; never
auto-approve. `validate-change` mirrors this for diffs (`safety_critical_path_prefixes`).

### 1.6 Repair pipeline
`repair_rounds.py` records bounded repair rounds (Round 3C). Out of CI scope; CI never triggers repair.

### 1.7 Audit pipeline
`execution_audit.py`, `provider_audit.py`, and CI persistence (`workspace/ci_runs/<run_id>.json` via
`atomic_io.atomic_write_json`) provide deterministic, sanitized, replayable records. Persistence is **opt-in**
(`--persist`) and off by default.

### 1.8 Proposed CI insertion points
The fixed `STAGE_ORDER` (14 stages) is deliberately immutable and version-gated. New capabilities therefore
attach as **separate, additive CLI verbs and modules** that reuse the same runner — never as new mandatory
stages. This preserves determinism, schema stability, and historical compatibility.

### 1.9 Compatibility risks (and how this round avoids them)
- Reordering/adding stages would break `test_stage_order_deterministic`, the `ci_run` schema, and old records
  → **avoided** (STAGE_ORDER untouched; asserted by `test_stage_order_unchanged_by_hardening`).
- Bumping the CI schema version would fail-close old persisted runs → **avoided** (CI schema stays `4a.1`;
  new artifacts get their own schemas).
- New runtime deps would trip `dependency_policy` → **avoided** (stdlib only; asserted by a test).

### 1.10 Required tests
Selection mapping (direct/importer/broad/no-impact/unmapped), fail-closed execution, history ordering +
schema-drift tolerance, comparison regression/improvement/no-change, deterministic rendering, CLI
registration, and the compatibility guardrails above. All implemented in `tests/test_round4a_hardening.py`
(37 tests).

---

## 2. Phase 2 — Design of the hardening layer

### 2.1 CI architecture (as extended)
Four additive modules, each pure/deterministic and reusing existing primitives (`run_ci_command`,
`CIPolicy`, `atomic_write_json`, `utc_now_iso`, `fingerprints`):

| Module | Responsibility |
| --- | --- |
| `provider_readiness_discovery.sanitize_executable_location` (fix) | Redact Windows/UNC paths on POSIX too |
| `ci_test_selection.py` | Map changed files → related tests; run them via the safe runner |
| `ci_history.py` | Index persisted runs; compare two runs for regressions |
| `ci_report.py` | Render CI / targeted / comparison envelopes to deterministic Markdown |

### 2.2 Execution stages
The authoritative 14-stage `ci-check` pipeline is **unchanged**. `ci-targeted` is a *separate* fast gate that
runs only the related tests; it never replaces `ci-check` and always tells the operator to run the full
`ci-check` before marking work complete.

### 2.3 Deterministic ordering
Selection sorts changed files and selected tests; rationale keys are sorted; history sorts by
`(started_at, run_id)` descending; comparison emits sorted class lists; rendering is a pure function of its
input. `sort_keys=True` on every JSON emission. No wall-clock value participates in ordering.

### 2.4 Configuration model
No new config file. Broad-impact globs default in-code (`DEFAULT_BROAD_IMPACT_GLOBS`) and are injectable for
tests. Timeouts/output caps come from the existing `CIPolicy` (`config/ci_policy.yaml`), so targeted runs
inherit the same bounds as `pytest_suite`.

### 2.5 Report schema
Two new sanitized schemas at `4a.1`: `schemas/ci_targeted_run.schema.json`,
`schemas/ci_run_comparison.schema.json`. They validate structurally under the existing `schema_validation`
stage and add no required field to the existing `ci_run` schema.

### 2.6 Failure classes
Reuses existing classes (`tests_failed`, `timeout`, `command_rejected`). Targeted runs map: rejected argv →
`command_rejected`; timeout → `timeout`; nonzero pytest → `tests_failed`. No new failure taxonomy.

### 2.7 Retry policy
None. CI is single-shot and fail-closed by design; retries would hide flakiness and break determinism. Flaky
isolation is a **deferred** capability (see §4).

### 2.8 Audit requirements
History/compare are **read-only** over `workspace/ci_runs/`; they never mutate or delete records and tolerate
unreadable / future-schema records by surfacing a note rather than crashing (historical compatibility). Run
persistence remains opt-in and atomic.

### 2.9 Compatibility guarantees
- `STAGE_ORDER` identical; CI schema/policy stays `4a.1`.
- No runtime dependency added (PyYAML only).
- Existing CLI verbs/flags unchanged; `--format json` is the default so existing output/exit semantics hold.
- The sanitize fix only changes the previously-broken case (Windows path on non-Windows host); native
  behavior is byte-identical.

### 2.10 Future GitHub Actions compatibility
`ci-targeted` and `ci-history`/`ci-compare` are local verbs usable in a future workflow **without** new
permissions or secrets (they read the repo and the gitignored `workspace/`). No workflow change is made in
this round; the existing least-privilege (`contents: read`) workflow is untouched.

### 2.11 Deferred capabilities
Flaky-test isolation, coverage gates, vulnerability-DB scanning, SHA-pinned actions, a dedicated `changed`
stage inside `ci-check`, cross-project boundary generalization beyond Equitify, auto-fix, and any live model
or network behavior — all deferred to explicit, separately-gated rounds.

---

## 3. Strategic rationale (the farsighted layer)

A solo builder iterating across many projects is bottlenecked by two things this round targets directly:

1. **Feedback latency.** Running the full suite on every edit is the tax you pay most often. `ci-targeted`
   turns "change one module" into "run the three tests that touch it" while staying fail-safe: any broad-impact
   file (package init, CLI, models, config, schemas) still forces the whole suite, and "no related test found"
   is reported loudly so a change never passes on an empty selection.
2. **Regression blindness.** A pile of `workspace/ci_runs/*.json` is an audit trail nobody reads. `ci-history`
   + `ci-compare` make it answer the only question that matters at completion time: *did this change introduce
   a new failure, or was it already red?* `ci-compare --against-previous` exits non-zero only on a genuine
   regression — a clean, scriptable completion gate.

The cross-platform sanitize fix is the same instinct applied to correctness: the project is authored on
Windows/macOS but validated on Linux, so a redactor that only understands the host OS's path syntax is a
latent privacy leak. Making it deterministic across platforms is what "better at handling my projects" means
in practice.

Everything here compounds the existing safety posture instead of competing with it: argv-only execution,
sanitized env, bounded timeouts, secret redaction, fail-closed defaults, opt-in persistence, and an untouched
Equitify boundary.

---

## 4. Acceptance criteria

- Full suite green on Linux (`291 passed`), including the previously-failing sanitize test.
- `ci-check` end-to-end verdict unchanged (`pass_with_notes`); `STAGE_ORDER` and CI schema unchanged.
- New verbs (`ci-targeted`, `ci-history`, `ci-compare`) registered, deterministic, and fail-closed.
- No new runtime dependency; no workflow/permission/secret/Equitify/live-model change.
- `docs` and package version consistent at `0.8.4` (verified by the `package_version` + `doc_consistency`
  stages).

---

## 5. Recommended Round 4B (next) scope

1. Optional `--changed` fast mode wired into a future workflow job (still `contents: read`).
2. Flaky-test isolation: opt-in re-run of *only* failed targeted tests with an explicit `flaky` flag and audit
   note (never silent).
3. Generalize `prohibited_paths` into a configurable multi-project boundary gate (the FORGE registry's
   "separation line" applies to all projects, not just Equitify) — policy-driven, still fail-closed.
4. Coverage capture as a **non-blocking** note stage, behind a flag, no new hard gate.
