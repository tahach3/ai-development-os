# Round 4E — Multi-Project Boundary Enforcement Gate

**Status:** Design + implementation (local only)  
**Scope:** Deterministic, argv-only, fail-closed multi-project path/import boundary checks reused by `validate-change` and optional `ci-boundaries` CLI  
**Package version target:** `0.8.5` (baseline at design time was `0.8.3` on `master` with Round 4A already merged; Round 4E ships as `0.8.5`)  
**CI schema/policy:** remains **`4a.1`** (additive `project_boundaries` field only — no schema version bump, no `STAGE_ORDER` change)

**Not in scope (LOCKED):** Round 4D2 live model/network/paid-API calls; Equitify open/reference/integrate; new runtime dependencies; GitHub Actions permission/secret changes; mandatory new CI stage; vulnerability DB; auto-merge/deploy

**Verified baseline (pre-implementation):** Round 4A commit `eeebbe7` is an ancestor of `master`; working tree may contain **untracked** memory/SQLite WIP that must **not** be staged.

---

## 1. Goals

1. Encode **per-project** allowed filesystem roots and forbidden path/import substrings in `config/ci_policy.yaml`.
2. Provide a **pure, deterministic** checker that flags cross-boundary violations without executing change code or contacting networks.
3. Surface findings through **`validate-change`** (existing PR/change gate) and an optional operator CLI **`ci-boundaries`**.
4. Reuse Equitify / prohibited-path sentinels already enforced by Round 4A — do not weaken them.
5. Keep **`STAGE_ORDER` fixed**; do **not** add a mandatory `ci-check` stage in Round 4E.

---

## 2. Boundary model

### 2.1 Concepts

| Term | Meaning |
| --- | --- |
| `project_id` | Stable string id for a logical project under OS control (may align with registry ids; CI policy is authoritative for this gate). |
| `allowed_roots` | Ordered list of path prefixes (POSIX-normalized, `/` separators). A path is **in-scope** for the project if it equals a root or is under it. |
| `forbidden_substrings` | Case-insensitive needles matched against **normalized paths** and **simple import-like strings** in file text. |
| Cross-boundary violation | A path or import string that is in-scope for project A but references another project's root, a forbidden needle, or leaves A's allowed roots via import/path reference. |

### 2.2 What is checked

**Path checks (always):**

- Normalize paths to forward slashes, lowercase for substring compare.
- For each declared project boundary:
  - If path matches any `forbidden_substrings` → **violation**.
  - Global Equitify / `prohibited_path_substrings` from existing policy continue to apply via existing `prohibited_paths` / `validate-change` logic (not duplicated as a new stage).

**Scoped root checks:**

- When a path falls under exactly one project's `allowed_roots`, that project is the **home** project.
- If a path falls under **zero** projects' roots → no multi-project root violation (other gates still apply).
- If a path falls under **two or more** projects' roots → **ambiguous ownership** → fail closed (`boundary_config_ambiguous` / blocker).

**Import-string checks (simple, deterministic):**

- For text files under examination (when content is available on disk), scan lines for import-like patterns:
  - `import …`, `from … import …`
  - quoted path-like fragments containing `/` or `.` module paths converted to slash form
- Flag when an import/path fragment:
  - matches a `forbidden_substring` for the home project (or any project if unscoped), or
  - clearly references another project's `allowed_roots` prefix while the file's home is a different project.

No AST parsing, no package resolution, no network, no executing imports.

### 2.3 Relationship to existing controls

| Existing control | Round 4E relationship |
| --- | --- |
| `prohibited_path_substrings` + `stage_prohibited_paths` | Unchanged; Equitify roots/ids still refused in `ci-check`. |
| `validate-change` Equitify path checks | Unchanged; Round 4E **adds** boundary findings alongside. |
| `ProjectRegistry.ensure_path_allowed` | Runtime/task path scoping; Round 4E is **CI/policy static** and does not replace registry. |
| `STAGE_ORDER` | **Frozen**; Round 4E does not insert a stage. |
| Schema `4a.1` | **No bump**; `project_boundaries` is additive optional key with fail-closed validation when present/malformed. |

---

## 3. Config schema (additive on `4a.1`)

Extend `config/ci_policy.yaml`:

```yaml
# Additive Round 4E — optional; schema_version stays "4a.1"
project_boundaries:
  - project_id: calculator-demo
    allowed_roots:
      - demo_projects/calculator-demo
    forbidden_substrings:
      - equitify-machine
      - equitify_machine
      - /equitify/
  - project_id: ai-dev-os-core
    allowed_roots:
      - src/ai_dev_os
      - tests
      - config
      - schemas
    forbidden_substrings:
      - equitify-machine
      - equitify_machine
```

### 3.1 Validation rules (fail closed)

| Condition | Behavior |
| --- | --- |
| Key `project_boundaries` absent | **Safe default:** empty list — multi-project checker reports no boundary findings; Equitify/`prohibited_paths` still apply elsewhere. |
| Key present but not a list | `CIConfigError` |
| Entry not a mapping | `CIConfigError` |
| Missing/blank `project_id` | `CIConfigError` |
| Duplicate `project_id` | `CIConfigError` |
| `allowed_roots` missing or empty | `CIConfigError` (ambiguous — refuse) |
| `forbidden_substrings` missing | Treat as empty list (allowed) |
| Non-string root/substring entries | `CIConfigError` |
| Overlapping `allowed_roots` across projects that make ownership ambiguous for some prefix | Detected at **check time** for concrete paths (and optionally at load time for identical roots) → fail closed |
| Policy file missing / wrong schema_version | Existing `CIConfigError` paths unchanged |

`CIPolicy` gains:

```text
project_boundaries: list[ProjectBoundaryRule]
```

where `ProjectBoundaryRule` is a small dataclass: `project_id`, `allowed_roots`, `forbidden_substrings`.

---

## 4. Failure classes

Add (additive enum members; no schema file bump required beyond existing string fields):

| Class | When |
| --- | --- |
| `boundary_violation` | Path or import crosses project roots / hits forbidden substring |
| `boundary_config_ambiguous` | Overlapping ownership or malformed/ambiguous boundary evaluation |
| `boundary_config_invalid` | Used when checker is invoked with explicit invalid in-memory config that bypassed load (tests); load path uses `CIConfigError` |

Existing classes remain authoritative for Equitify (`prohibited_path`), secrets, deps, etc.

Findings reuse `PRValidationFinding` shape when surfaced via `validate-change`:

- `category`: `project_boundary`
- `severity`: `blocker` for violations / ambiguity
- `failure_class`: as above
- `blocker`: `true`

---

## 5. Pure checker API

Module (new): `src/ai_dev_os/ci_boundaries.py`

```text
check_project_boundaries(
    *,
    paths: Sequence[str],
    policy: CIPolicy,
    repo_root: Path | None = None,
    read_content: bool = True,
) -> BoundaryCheckResult
```

- **Deterministic:** sorted unique paths; stable finding order (path, then rule id, then reason code).
- **Local only:** reads files under `repo_root` when `read_content` and file exists; never spawns network or models.
- **Argv-only CLI:** operator passes optional `--base`/`--head` (for path list via git name-status) or explicit `--path` repeats; no shell interpolation of policy strings.
- Returns structured result: `ok: bool`, `findings: list[...]`, `failure_classes: list[str]`.

Helpers reused where practical:

- Path normalization patterns from `validation.path_matches_prefix` / `ci_stages` prohibited scan
- `EQUITIFY_SENTINELS` / policy `prohibited_path_substrings` remain available for documentation and tests; Round 4E forbidden lists in YAML should include Equitify needles for declared projects so boundary checks reinforce (not replace) global refusal.

---

## 6. Surfacing

### 6.1 `validate-change`

After collecting changed paths (existing `_git_name_status`), call `check_project_boundaries` and append findings. Verdict aggregation unchanged (any blocker → fail).

### 6.2 CLI `ci-boundaries`

Optional Round 4E command:

```bash
ai-dev-os ci-boundaries [--base REF] [--head REF] [--path REL]...
```

- Default: examine working-tree change set like `validate-change` without base, **or** all `--path` args if provided.
- Prints JSON summary; exit `0` if ok, `1` if boundary blockers, `2` on config/load errors.
- Does **not** alter `ci-check` stage list.

### 6.3 Explicit non-goals for staging

- **No** new entry in `STAGE_ORDER`.
- **No** GitHub workflow step required for Round 4E (local gate; operators may call CLI manually).

---

## 7. Fail-closed and determinism summary

| Principle | Application |
| --- | --- |
| Fail closed | Invalid/ambiguous boundary config → refuse load or emit blocker findings; never “best effort allow”. |
| Safe default | Missing `project_boundaries` key → empty rules (no false multi-project fails); other gates unchanged. |
| Determinism | No time/random/network; stable sort; identical inputs → identical findings. |
| Local only | No live providers; no paid APIs; no Equitify filesystem open. |
| Argv-only | CLI uses argparse; policy values never become shell commands. |

---

## 8. Tests (Round 4E)

`tests/test_round4e_boundary.py`:

1. Clean in-boundary paths/imports → pass.
2. Planted cross-boundary path or import → fail with `boundary_violation`.
3. Equitify still refused (path/sentinel) via existing + boundary forbidden substrings.
4. Same inputs twice → identical finding payloads (determinism).
5. Missing `project_boundaries` → safe default (empty) → no boundary findings from this gate.
6. Ambiguous overlapping roots for a concrete path → fail closed.
7. Malformed boundary entry in YAML validation → `CIConfigError`.

Also: focused suite + full pytest + `ai-dev-os ci-check` end-to-end (with existing skip discipline if nested).

---

## 9. Version / docs

- Bump package **`0.8.3` → `0.8.5`** (`pyproject.toml`, `__init__.py`, three `__version__ == "..."` guards, README, ROADMAP, PROJECT_CHRONICLE).
- Record Round 4E complete; Round **4D2 remains LOCKED**; Equitify remains disconnected.

---

## 10. Deferred items

- Mandatory `ci-check` stage for boundaries (would require STAGE_ORDER change — out of scope).
- Full Python AST / import graph resolution.
- Automatic derivation of boundaries from `projects.yaml` registry (keep CI policy explicit).
- Cross-repo / monorepo symlink following beyond string prefixes.
- Round 4D2 live smoke; Equitify connection; new dependencies; Actions secret/permission expansion.
- Memory/SQLite track (separate WIP — must not mix into Round 4E commit).

---

## 11. Acceptance checklist

- [ ] Design doc present (this file)
- [ ] `project_boundaries` in policy + `CIPolicy` validation
- [ ] Pure checker + validate-change + `ci-boundaries` CLI
- [ ] `STAGE_ORDER` unchanged; schema stays `4a.1`
- [ ] Tests green; full suite + `ci-check`
- [ ] Version `0.8.5`; docs updated
- [ ] Single local commit; memory/SQLite untracked WIP not staged
- [ ] No push required (local-only round)
- [ ] Equitify untouched; 4D2 locked
