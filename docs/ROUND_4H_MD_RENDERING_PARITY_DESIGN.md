# Round 4H — Markdown Rendering Parity (`ci-boundaries` / `validate-change`)

**Status:** Design + implementation (local only)  
**Scope:** Add deterministic `--format md` human-readable summaries for `ci-boundaries` and `validate-change`, matching the Round 4A hardening conventions already used by `ci-check` / `ci-targeted` / `ci-compare`.  
**Package version target:** `0.8.10` (baseline `0.8.9` / commit `7064124`, Phase B3.2)  
**CI schema/policy:** remains **`4a.1`** (no schema bump; no `STAGE_ORDER` reorder/remove/insert)

**Not in scope (LOCKED):** Round 4D2 live model/network/paid-API; Equitify open/reference/integrate; new **runtime** dependencies; GitHub Actions permission/secret changes; memory enablement / memory CRUD / wiring memory into CLI-runtime-CI; auto-merge/deploy.

**Verified baseline (pre-implementation):** `HEAD = 7064124` on `master`; package `0.8.9`; only known untracked `workspace/_*` WIP (not staged). Full suite: **346 passed, 2 skipped**.

---

## 1. Goals

1. **Parity:** operators can read boundary and validate-change results as Markdown the same way they already read `ci-check --format md`.
2. **JSON default unchanged:** default `--format json` keeps the same payload shape (`to_dict()`), indentation/`sort_keys`, and exit codes.
3. **Deterministic rendering:** same envelope in → byte-identical Markdown out (stable ordering, no timestamps invented by the renderer).
4. **No schema / stage changes:** renderers consume existing return fields only; no new CI stages; memory remains disabled and untouched.

---

## 2. Real return fields (from code)

### 2.1 `check_project_boundaries()` → `BoundaryCheckResult`

Source: `src/ai_dev_os/ci_boundaries.py`

| Field | Type | Notes |
| --- | --- | --- |
| `ok` | `bool` | `True` iff `findings` empty |
| `findings` | `list[BoundaryFinding]` | sorted/deduped by `(path, project_id, reason, detail)` |
| `failure_classes` | `list[str]` | unique, first-seen order |
| `files_examined` | `list[str]` | normalized unique sorted paths |

Each finding (`BoundaryFinding.to_dict()`):

| Field | Type |
| --- | --- |
| `path` | `str` |
| `project_id` | `str` |
| `reason` | `str` |
| `failure_class` | `str` |
| `detail` | `str` |
| `blocker` | `bool` (default `True`) |

CLI today (`cmd_ci_boundaries`): prints `json.dumps(result.to_dict(), indent=2, sort_keys=True)`; exit `0` if `ok` else `1` (config/git errors → `2`).

### 2.2 `validate_change()` → `PRValidationSummary`

Source: `src/ai_dev_os/ci_validate_change.py` + `PRValidationSummary.to_dict()` in `ci_models.py`

| Field | Type | Notes |
| --- | --- | --- |
| `schema_version` | `str` | CI schema (`4a.1`) |
| `ci_policy_version` | `str` | policy version string |
| `run_id` | `str` | audit id |
| `repository_identity` | `str` | repo root path string |
| `starting_commit` | `str` | HEAD / inspection head |
| `compared_base_commit` | `str \| null` | `--base` when set |
| `trigger_type` | `str` | `validate_change` |
| `started_at` / `finished_at` | `str` | ISO timestamps from the run |
| `duration_seconds` | `float` | measured duration |
| `files_examined` | `list[str]` | change-range paths |
| `findings` | `list[PRValidationFinding]` | blockers / review items |
| `final_verdict` | `str` | `pass` / `fail` / `human_review_required` |
| `failure_classes` | `list[str]` | unique, first-seen order |
| `human_review_required` | `bool` | |
| `blocker` | `bool` | |
| `next_action` | `str` | |
| `policy_decision` | `str` | |
| `auto_approve` | `bool` | always `False` in `to_dict()` |
| `auto_merge` | `bool` | always `False` in `to_dict()` |

Each finding (`PRValidationFinding.to_dict()`):

| Field | Type |
| --- | --- |
| `path` | `str` |
| `category` | `str` |
| `severity` | `str` |
| `summary` | `str` |
| `failure_class` | `str` |
| `human_review_required` | `bool` |
| `blocker` | `bool` |

CLI today (`cmd_validate_change`): prints `json.dumps(summary.to_dict(), indent=2, sort_keys=True)`; exit via `exit_code_for_pr_summary` (`0` for pass / human_review_required; `1` for fail; config/git → `2`).

---

## 3. Markdown mapping (`ci_report.py`)

Reuse the same conventions as `render_ci_summary` / `render_comparison`:

- H1 title + blank line
- Bullet list of key scalar fields (`**Label:** value`, backticks for ids/verdicts)
- Sections with `##` headings for collections (findings, files, failure classes)
- Trailing footer italic line + final `\n`
- Pure functions; accept the typed result **or** its `to_dict()` shape where convenient
- Do **not** invent fields; omit empty optional sections consistently

### 3.1 `render_boundary_summary(result)`

| Markdown element | Source field(s) |
| --- | --- |
| `# Boundary check` | (fixed title) |
| `**OK:**` | `ok` (`true`/`false` lowercase) |
| `**Files examined:**` | `len(files_examined)` |
| `**Failure classes:**` | joined `failure_classes` or `(none)` |
| `## Findings` | each finding: path, project_id, reason, failure_class, detail, blocker |
| `## Files examined` | bullet list of `files_examined` (omit section if empty) |
| Footer | count of findings / files; “No automatic merge or deploy.” |

### 3.2 `render_validate_change_summary(summary)`

| Markdown element | Source field(s) |
| --- | --- |
| `# Validate change \`{run_id}\`` | `run_id` |
| Verdict / trigger / policy / blocker / human review / next action | matching scalars |
| Starting / compared base commits | truncated to 12 chars when present |
| Duration | `_fmt_duration(duration_seconds)` |
| Schema / policy versions | `schema_version`, `ci_policy_version` |
| Auto-approve / auto-merge | always shown as `false` |
| `## Findings` | path, category, severity, failure_class, summary, blocker, human_review_required |
| `## Failure classes` | when non-empty |
| `## Files examined` | when non-empty (cap display list reasonably if huge is not required; full list OK for typical diffs) |
| Footer | finding counts + “No automatic merge or approve.” |

Timestamps (`started_at` / `finished_at`) and `repository_identity` are included as bullets so the Markdown remains a faithful view of the envelope without changing JSON.

---

## 4. CLI wiring

| Command | Flag | Default | Behavior |
| --- | --- | --- | --- |
| `ci-boundaries` | `--format {json,md}` | `json` | `md` → `render_boundary_summary`; else existing JSON dump |
| `validate-change` | `--format {json,md}` | `json` | `md` → `render_validate_change_summary`; else existing JSON dump |

Exit codes and error (`return 2`) paths stay identical. JSON branch keeps `indent=2, sort_keys=True`.

---

## 5. Tests

`tests/test_round4h_md_rendering.py`:

- Deterministic double-call equality for both renderers
- Required tokens present for ok and failing boundary envelopes
- Required tokens present for validate-change envelope (verdict, findings fields, no auto-merge)
- Parser accepts `--format md` for both commands; default remains `json`
- CLI e2e: `ci-boundaries --path … --format md` yields Markdown; default yields parseable JSON
- CLI e2e: `validate-change --base HEAD --format md` yields Markdown; default JSON
- Package version assertion for `0.8.10`

Update **every** `tests/**` `__version__ == "0.8.9"` (and docs package mentions for this round) to `0.8.10`.

---

## 6. Hard boundaries checklist

- [x] No Round 4D2 / live model / network / paid-API
- [x] Equitify untouched
- [x] No new runtime dependency
- [x] No GitHub Actions permission/secret changes
- [x] No `STAGE_ORDER` reorder/remove; no `4a.1` schema bump
- [x] Memory enablement untouched (`src/ai_dev_os/memory/` not modified)
- [x] Unrelated untracked `workspace/_*` WIP not staged

---

## 7. Acceptance

1. Design doc present (this file).
2. Renderers + `--format md` shipped; JSON default unchanged.
3. Focused + full pytest green; `ai-dev-os ci-check` e2e green.
4. Package patch bump `0.8.9` → `0.8.10` in `__init__.py` + `pyproject.toml` + all version asserts + README / ROADMAP / PROJECT_CHRONICLE.
5. One clean commit on `master`, pushed (no force); Actions conclusion reported.
