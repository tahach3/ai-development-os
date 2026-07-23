# Round 4G — ci-targeted Selection Quality

**Status:** Design + implementation (local only)  
**Scope:** Upgrade `select_targeted_test_paths` / `ci-targeted` selection quality in place — import-string detection + broad-impact fail-safe. No second competing implementation.  
**Package version target:** `0.8.8` (baseline `0.8.7` / commit `dc93d59`, Round 4A hardening + 4F)  
**CI schema/policy:** remains **`4a.1`** (no schema bump; no `STAGE_ORDER` reorder/remove/insert)

**Not in scope (LOCKED):** Round 4D2 live model/network/paid-API calls; Equitify open/reference/integrate; new **runtime** dependencies; GitHub Actions permission/secret changes; auto-merge/deploy; coverage as a gate; silent flaky retries; mandatory new CI stage; staging untracked memory/SQLite WIP

**Verified baseline (pre-implementation):** `HEAD = dc93d59` on `master`; package `0.8.7`; untracked memory/SQLite WIP must **not** be staged. Full suite green excluding that WIP (`~306 passed, 2 skipped`).

---

## 1. Goals

1. **Import-based selection:** when a `src/**/*.py` module changes, also select tests under `tests/` whose source text references that module’s dotted import path — not only same-named `test_<stem>.py` files.
2. **Broad-impact fail-safe:** changes to high-fanout surfaces (`__init__.py`, `cli.py`, `models.py`, `config/**`, `schemas/**`) must **never** produce a silent empty-green or silently narrow “fast signal: pass.” Emit an explicit **“broad impact, full suite recommended”** note/flag on the `CIRun`.
3. **Keep Round 4F ergonomics intact:** `--isolate-flaky`, `--coverage` notes, `CIRun` envelope, `--format md`, PR-only workflow step, exit-code mapping — unchanged for callers.

---

## 2. Current selection algorithm and gaps

### 2.1 Current algorithm (`select_targeted_test_paths`)

For each path in `git diff --name-only <base>...HEAD`:

1. If under `tests/` and named `test_*.py` / `*_test.py` → include it.
2. If under `src/` and ends with `.py`:
   - Skip `__init__.py` entirely.
   - Include existing `tests/test_<stem>.py`, `tests/<stem>_test.py`, and recursive `tests/**/test_<stem>.py` / `*_test.py` when those files exist.
3. If the resulting list is empty → `ci-targeted` emits a single passed stage with note `no targeted tests for change set` (exit 0 / `pass_with_notes`).

### 2.2 Gap A — no import-based detection (false-clean example)

- Change: `src/ai_dev_os/widget.py` (behavior break).
- Existing test: `tests/test_orchestration.py` contains `from ai_dev_os.widget import X` but is **not** named `test_widget.py`.
- Today: selection misses that test → stage passes with “no targeted tests” or a too-small set → **fast signal: pass** while full suite would fail.
- Worth eliminating: a wrong green fast signal is worse than a slow/honest one.

### 2.3 Gap B — no broad-impact fail-safe (false-clean example)

- Change: `src/ai_dev_os/cli.py` or `config/ci_policy.yaml` or `schemas/ci_run.schema.json`.
- Today: `__init__.py` is skipped; `cli.py` / `models.py` may map only to `tests/test_cli.py` / `tests/test_models.py` if those exist (often absent or incomplete); `config/**` / `schemas/**` produce **zero** targets.
- Result: empty selection → passed stage + `no targeted tests for change set` → reads as clean success for a change that needs the **full** suite.

---

## 3. Import-based detection

### 3.1 Approach (stdlib text/regex — preferred)

For each changed `src/**/*.py` that is **not** classified as broad-impact:

1. Map file path → dotted module path under the package root, e.g.  
   `src/ai_dev_os/foo/bar.py` → `ai_dev_os.foo.bar`  
   `src/ai_dev_os/foo/__init__.py` is broad-impact (see §4), not import-scanned for narrow selection.
2. Scan candidate test files under `tests/**/*.py` (read as text; skip binary/unreadable).
3. Conservative match if the source contains the dotted path as an import reference, e.g.:
   - `from ai_dev_os.foo.bar import …`
   - `import ai_dev_os.foo.bar`
   - `import ai_dev_os.foo.bar as …`
   - Regex anchored to import statements / word boundaries so incidental prose mentions are uncommon; false positives (extra tests selected) are acceptable; **false negatives are not**.
4. Union those hits with the existing direct-name matches. Deterministic sort / insertion order preserved via an ordered set (same style as today).

**AST:** not required. Text/regex matches existing codebase style (`ci_pytest_ergonomics`, boundary checker import-string scans) and needs no new dependency. AST may be revisited later if false positives become noisy.

### 3.2 Scope limits

- Only scan under `tests/` (not `src/`, not `workspace/`).
- Only for changed modules under `src/` that look like Python packages/modules.
- Non-`src` / non-test changes (docs, markdown) still produce empty selection with the existing informational note when no tests map — unchanged unless they hit broad-impact paths (`config/**`, `schemas/**`).

---

## 4. Broad-impact list and behavior

### 4.1 Paths (fail-safe list)

A changed path is **broad-impact** when (normalized `/`):

| Pattern | Rationale |
| --- | --- |
| `src/**/__init__.py` | Package surface / re-exports |
| `src/**/cli.py` | CLI entry / argv surface |
| `src/**/models.py` | Shared domain models |
| `config/**` | CI/policy/runtime config |
| `schemas/**` | Contract schemas |

Exact filenames `cli.py` / `models.py` apply under `src/` trees; `__init__.py` any depth under `src/`.

### 4.2 Behavior (chosen: explicit report — not silent partial, not silent empty)

When **any** changed path is broad-impact:

1. **Do not** run a narrow name/import guess as if it were sufficient.
2. Set selection result flag `broad_impact=True`.
3. Emit note (exact phrase for tests/operators): **`broad impact, full suite recommended`**.
4. Attach that note on the `CIRun` via the stage `notes` (so `_apply_verdict` rolls it into `sanitized_notes` and yields `pass_with_notes` when no hard failure). Optional: also keep the phrase in the stage `sanitized_output_summary` / `command_identity` for grepability.
5. **Do not** invent a silent empty-green “no targeted tests for change set” for these paths.
6. **Do not** silently run a partial suite that looks authoritative.

**Select everything vs report-only:** Round 4G **reports** the fail-safe and **skips** the narrow pytest invocation (targets empty **with** the broad-impact note). Full `pytest` + `ci-check` remain the authoritative gates (already true for PR workflow). Running the entire suite inside `ci-targeted` would duplicate the next workflow step and blur “fast signal” vs authority; the honesty win is the loud note/flag, not a second full run.

If broad-impact paths are mixed with ordinary module changes, broad-impact **wins** (fail-safe dominates).

### 4.3 Non-broad empty selection (unchanged)

When there is **no** broad-impact path and still no targets after name + import selection → keep existing note `no targeted tests for change set` (docs-only / unmatched paths). Still `pass_with_notes`, but **not** the broad-impact phrase.

---

## 5. Interaction with `--isolate-flaky` and `--coverage`

| Feature | Interaction |
| --- | --- |
| `--isolate-flaky` | Unchanged. Applies only when a targeted pytest stage actually runs. Broad-impact advisory path does not invoke pytest, so flaky isolation is N/A. |
| `--coverage` | Still `ci-check` only (Round 4F). `ci-targeted` does not add coverage. |
| `CIRun` envelope / `--format md` | Unchanged shape; new notes appear in existing `notes` / `sanitized_notes` fields. |
| Workflow PR step | Still `ci-targeted --base <PR base>`; no permission/secret changes. |

---

## 6. Backward compatibility

| Concern | Guarantee |
| --- | --- |
| JSON shape | Same `CIRun` / stage keys (`4a.1`); additive notes/flag behavior only — no schema version bump |
| Exit codes | `pass` / `pass_with_notes` → 0; failures → non-zero (unchanged mapping) |
| Direct-name match | Preserved (regression-tested) |
| Empty non-broad selection | Same informational note as Round 4F |
| Workflow | PR-only step stays; authoritative pytest + `ci-check` stay; `contents: read` |
| STAGE_ORDER / schema | Unchanged |
| Callers parsing JSON | New note strings may appear; no field removals/renames |

**Implementation shape:** extend `select_targeted_test_paths` and/or a clearly named sibling (e.g. `select_targeted_tests` returning paths + `broad_impact` + notes) inside `ci_pytest_ergonomics.py`; wire through existing `ci_targeted.py`. No parallel selection module.

---

## 7. Test matrix (`tests/test_round4g_ci_targeted_selection.py`)

1. **Import-based detection:** changed module selects a test that only imports it (not same-named).
2. **Broad-impact:** `cli.py` / `__init__.py` / `config/**` / `schemas/**` / `models.py` → note contains `broad impact, full suite recommended`; **never** empty-but-green without that signal.
3. **Direct-name regression:** `src/.../widget.py` → still selects `tests/test_widget.py` when present.
4. **Determinism:** same inputs twice → identical path lists / notes / flag.
5. **CLI e2e:** `ci-targeted --base <ref> --format md` still works (exit 0 path; markdown renders).

Plus version bump guards → `0.8.8` in the five existing `__version__` assertion tests.

---

## 8. Docs / version deliverables

- Bump `0.8.7` → `0.8.8` (`pyproject.toml`, `__init__.py`, five version-guard tests).
- Update README, ROADMAP, PROJECT_CHRONICLE for Round 4G.
- One clean local commit; **do not push** unless separately requested.
- Do **not** stage untracked memory/SQLite WIP.

---

## 9. Deferred (explicit)

- Full-suite auto-execution inside `ci-targeted` when broad-impact is detected
- AST-based import graph / dependency closure across `src/`
- Coverage-guided or historical flaky-aware selection
- Changing GitHub Actions permissions or SHA-pinning actions
- Round 4D2 / live providers / paid APIs
- Equitify integration
- Staging or completing untracked memory/SQLite WIP
- Schema bump or new CI stage for selection quality
- Selecting non-test support modules under `tests/` that are not `test_*.py`

---

## 10. Acceptance checklist

- [x] Design covers gaps, import scan, broad-impact fail-safe, flaky/coverage interaction, compat, tests, deferred
- [x] Import-string scanning selects cross-named importers
- [x] Broad-impact never silent empty green; loud “full suite recommended” note/flag
- [x] Direct-name match preserved; determinism held
- [x] `--isolate-flaky` / `--coverage` / `--format md` / CIRun envelope unchanged in role
- [x] `STAGE_ORDER` / `4a.1` unchanged; no second competing implementation
- [x] Focused + full suite green; `ci-check` e2e
- [x] Version `0.8.8`; docs updated; one local commit; Equitify untouched; 4D2 LOCKED
