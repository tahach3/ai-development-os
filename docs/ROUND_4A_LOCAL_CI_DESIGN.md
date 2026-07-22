# Round 4A — Local CI, Quality Gates, and Pull-Request Validation Foundation

**Status:** Round 4A complete; Round 4B remote validation complete (documentation closeout)
**Scope:** Deterministic local CI engine, normalized CI/PR result schemas, dependency-policy (not vulnerability DB), secret/artifact gates, minimal GitHub Actions definition, sanitized behavioral CI aggregates

**Not in scope (still):** Live provider calls, paid APIs, vulnerability database queries, auto-merge/push/deploy, Equitify, autonomous code-review agents, repository secrets, workflow permission expansion

**Verified baseline commit (pre-implementation):** `734b8c8235b01e9297a25df089cdfd542d9da6aa`  
(Round 3C complete; package was `0.5.0`; baseline tests 111 passed / 1 skipped; remotes unmodified / none required)

**Package version target:** `0.6.0` (schema/policy `4a.1`; prior round schemas preserved) — **unchanged through Round 4B**

### Round 4B remote validation evidence

| Item | Value |
| --- | --- |
| Private repo | `tahach3/ai-development-os` |
| First successful remote CI run | [`29930178622`](https://github.com/tahach3/ai-development-os/actions/runs/29930178622) |
| Conclusion | `success` |
| Head SHA at first success | `a01f6725d415977c982fd3c9ad524ef5656ddce3` |
| Workflow permissions | `contents: read` only (unchanged) |
| Secrets / live providers / deploy / merge | None |
| Equitify | Disconnected |
| Next planned development round | High-quality reporting system upgrade |

---

## Self-review vs existing controls (contradictions resolved)

| Existing control | Round 4A resolution |
| --- | --- |
| Round 3A `safe_exec` / allowlisted pytest | CI pytest stage uses argv arrays, sanitized env, timeouts, output caps — never `shell=True`; never arbitrary config/PR commands. |
| Round 3B provider policy / live gates | CI never invokes providers; workflow forbids provider credentials and live model steps. |
| Round 3C orchestration | CI may **read** sanitized orch aggregates for behavioral reports; never starts live orch or weakens stalemate/repair gates. |
| `git_safety` inspect-only | CI git stages use inspect verbs only (`status`, `diff`, `rev-parse`, `log`, `ls-files`); no commit/push/merge/reset. |
| Project registry / Equitify sentinels | Prohibited-path and registry stages reuse sentinels; no Equitify filesystem access. |
| Approval / lifecycle gates | Unchanged; safety-critical file changes classify as **human_review_required**, not auto-approve. |
| Behavioral `auto_rewrite_rules=false` | CI recommendations remain proposed/versioned/inactive; never auto-route. |
| No `jsonschema` dependency | Schema stage validates JSON Schema **documents** structurally + artifact required-field checks without adding packages. |
| Vulnerability scanning | Explicitly **not** claimed; dependency-policy only (declared deps, pins, prohibited categories). |

No contradictions remain after separating: (1) local CI stages, (2) static PR validation, (3) workflow definition vs execution, (4) dependency-policy vs vulnerability DB.

---

## 1. Local CI lifecycle

States for a CI run record (`4a.1`):

| State | Meaning |
| --- | --- |
| `created` | Run ID allocated; not started |
| `running` | Stages executing in fixed order |
| `completed` | All stages finished; final verdict set |
| `failed` | One or more blocking stages failed (terminal) |
| `blocked` | Policy refused to continue (e.g. identity) |
| `cancelled` | Operator cancel (optional; not auto) |

Flow: create → run stages 1..N deterministically → write normalized result → exit code from final verdict.

CLI: `ai-dev-os ci-check` (optional `--skip-stages`, `--base-ref` for compare metadata only).

---

## 2. Quality-gate ordering

Fixed stage order (never reordered by config/PR text):

1. `repo_identity` — git inspect; record root/branch/HEAD; dirty flag informational unless `--require-clean`
2. `python_compile` — `python -m compileall` on `src` / `tests`
3. `pytest_suite` — full allowlisted pytest
4. `git_diff_check` — `git diff --check` (+ `--cached` when relevant)
5. `schema_validation` — parse/validate `schemas/*.json` structure
6. `config_parse` — YAML/JSON under `config/` parse
7. `project_registry` — load example/registry; Equitify refused
8. `prohibited_paths` — path/id sentinels; no Equitify roots
9. `package_version` — `__version__` ↔ `pyproject.toml` consistency
10. `dependency_policy` — declared deps only; prohibited categories; no URL/Git/editable abs paths
11. `secret_scan` — pattern scan of tracked (or proposed) files; redact in reports
12. `runtime_artifacts` — refuse committing workspace private/runtime paths
13. `doc_consistency` — deterministic version/round markers where checkable
14. `finalize` — assemble normalized CI run + optional persist

Missing stage in policy → fail closed. Unknown stage name in skip list → fail closed.

---

## 3. Pull-request validation contract

Command: `ai-dev-os validate-change [--base REF] [--head REF]`

- Inspects `git diff` / name-status for the range **without executing code from the change**.
- Produces `PRValidationSummary` with findings, failure classes, `human_review_required` flags.
- Never auto-approves or merges.
- May optionally re-run selected static stages against **current** tree (not the remote PR checkout) when local; workflow mirrors by checking out the PR then running `ci-check` (definition only in 4A).

---

## 4. Trusted and untrusted input boundaries

| Input | Trust |
| --- | --- |
| Operator argv to CLI (stage skip names, refs) | Semi-trusted; validated against allowlists |
| Repo tracked files | Untrusted content; scanned, never executed as commands |
| PR title/body / workflow `run:` from untrusted fork | Untrusted; Round 4A local validator does not eval them; workflow uses fixed steps only |
| Config YAML in repo | Trusted for **policy values** after parse; never used as shell command strings |
| Provider/orch transcripts | Out of scope for CI persistence |

---

## 5. Test execution policy

- Only `python -m pytest` with allowlisted flags (reuse Round 3A policy ideas; CI uses fixed argv).
- Working directory = repo root; timeout bounded (default 600s for full suite; clamp max).
- Env filtered (no API keys/tokens forwarded).
- Output truncated; exit non-zero → stage fail `tests_failed`.
- Nested/test harness may skip `pytest_suite` via explicit `--skip-stages` to avoid recursion.

---

## 6. Static Python validation

`python -m compileall -q` on `src` and `tests` (and `demo_projects` optionally). Syntax errors → `python_compile_failed`. No import of changed modules as a substitute for compileall.

---

## 7. Schema and configuration validation

- Every `schemas/*.json` must parse as JSON object with `$schema` and (`properties` or `$ref` or `type`).
- Unsupported CI schema/policy version on load → fail closed.
- `config/*.yaml` and `config/*.json` (tracked examples) must `yaml.safe_load` / `json.load` without error.
- Malformed → `malformed_schema` / `malformed_config`.

---

## 8. Dependency-policy checks

From `pyproject.toml` only (stdlib `tomllib`):

- Enumerate runtime + optional `dev` deps.
- Fail on: unexpected prohibited packages (LangChain, CrewAI, AutoGen, etc.), direct URL/`git+` deps, editable `file://` or absolute path deps, unpinned VCS.
- Consistency: `[project].dependencies` present; `requires-python` matches policy (`>=3.11`).
- **Not** vulnerability scanning — no OSV/NVD/GitHub Advisory query in Round 4A.

---

## 9. Secret-pattern checks

Scan tracked files (and validate-change proposed paths) with conservative regexes (API keys, bearer tokens, private key headers, AWS-like keys). Findings report **path + pattern class**, never raw secret value (redacted). False-positive-safe: skip binary; skip known fixture markers where explicitly labeled `REDACTED` / example placeholders (`YOUR_API_KEY`).

---

## 10. Generated/runtime artifact checks

Refuse or flag presence of should-not-commit paths under git tracking consideration:

- `workspace/**` runtime (except `.gitkeep`)
- `.env`, `.venv/`, `__pycache__/`, `*.pyc`, private CI run dumps if mis-staged
- Provider execution transcripts directories

`validate-change` flags added paths in these categories.

---

## 11. Documentation consistency checks

Deterministic only:

- Package version in `pyproject.toml` == `ai_dev_os.__version__`
- README / ROADMAP / chronicle mention Round 4A when version is `0.6.0` (soft warn vs hard fail: hard-fail version mismatch; soft findings for chronicle package line if mismatched)

---

## 12. Git-diff validation

`git diff --check` and `git diff --check --cached`. Conflict markers / whitespace errors → `git_diff_check_failed`. Inspect-only.

---

## 13. Sanitized reporting

CI/PR summaries store: stage names, statuses, failure classes, truncated sanitized stdout/stderr (secrets redacted), file path lists, policy decisions, next actions. Never: raw env dumps, API keys, private prompts, provider transcripts.

---

## 14. Exit codes and failure classes

| Exit | Meaning |
| --- | --- |
| 0 | `pass` or `pass_with_notes` |
| 1 | `fail` (blocking stage) |
| 2 | `blocked` / usage / policy refused before run |

Failure classes include: `repo_identity_failed`, `python_compile_failed`, `tests_failed`, `git_diff_check_failed`, `malformed_schema`, `malformed_config`, `registry_invalid`, `prohibited_path`, `package_version_mismatch`, `dependency_policy_violated`, `secret_pattern_detected`, `runtime_artifact_detected`, `doc_inconsistency`, `timeout`, `command_rejected`, `unsafe_workflow`, `human_review_required`, `unsupported_schema_version`, `internal_error`.

---

## 15. Deterministic output

- Fixed stage order; `sort_keys=True` JSON; stable `to_dict` field order.
- Timestamps recorded but not used for ordering stages.
- Fingerprints where needed via existing `fingerprints.fingerprint`.

---

## 16. CI result schemas

Versioned JSON schemas:

- `schemas/ci_run.schema.json`
- `schemas/ci_stage_result.schema.json`
- `schemas/pr_validation_summary.schema.json`

Minimum fields: schema/policy version, run ID, repository identity, starting/base commit, trigger type, stage name, command identity, timestamps, duration, exit/timeout/validation status, failure class, sanitized summary, truncation, files examined, policy decision, blocker, next action, final verdict.

---

## 17. GitHub Actions design

Single workflow `.github/workflows/ci.yml`:

- Triggers: `pull_request`, `push` to `master`/`main`, `workflow_dispatch`
- Jobs: checkout → setup-python (3.11+) → `pip install -e ".[dev]"` → `pytest` → `ai-dev-os ci-check` (or `python -m ai_dev_os.cli ci-check`) → `git diff --check`
- Official actions only; version **tags** documented; commit SHA pins deferred (supply-chain residual risk recorded)
- **Not executed or pushed in Round 4A**; **Round 4B** validated private remote execution (first success run `29930178622` on `tahach3/ai-development-os`) without changing permissions or adding secrets

---

## 18. Minimal workflow permissions

```yaml
permissions:
  contents: read
```

No `pull-requests: write`, no `id-token`, no `packages: write`. No `GITHUB_TOKEN` write usage. No `secrets.*` references.

---

## 19. Fork pull-request safety

- Read-only checkout of PR code; no secrets available to fork PRs (none configured).
- Fixed steps only — no `run: ${{ github.event.pull_request.title }}` or similar injection.
- Local `validate-change` never executes diff hunks.

---

## 20. Caching policy

No dependency cache required in 4A. If added later, cache only `pip` wheels from declared files — never credentials. Default: no cache.

---

## 21. Timeouts and concurrency

- Job `timeout-minutes: 30`
- Stage timeouts: compile 120s, pytest 600s, others 60s (clamped)
- `concurrency:` group by workflow+ref; `cancel-in-progress: true`

---

## 22. Artifact-retention policy

Optional upload of **sanitized** CI JSON only (`if: always()`), retention ≤ 7 days, no secrets. Round 4A may omit upload to reduce risk; if present, path is `ci-report.json` sanitized.

---

## 23. Local/remote parity

Same stage names and policy version `4a.1`. Remote workflow invokes the same CLI entrypoints. Divergence (OS path separators) handled by pathlib; no Windows-only stages required for pass.

---

## 24. Threat model

| Threat | Mitigation |
| --- | --- |
| Arbitrary command from config/PR | Fixed argv only; reject shell metacharacters |
| Secret exfiltration via CI logs | Redaction; env filter; no secret workflow vars |
| Equitify access | Sentinels; no path ops |
| Live provider in CI | Workflow + CI policy forbid; no provider invoke |
| Supply-chain action tag move | Documented residual risk; prefer tags until SHA available |
| Auto-merge / deploy | Absent from workflow |
| Symlink escape | Path confinement checks on examined roots |
| Dependency confusion / URL deps | Dependency-policy stage |

---

## 25. Test matrix

Categories: successful local CI (temp repo); stage ordering; serialization; failed pytest; timeout; malformed schema/YAML; version mismatch; dependency addition / unpinned; prohibited path; Equitify rejection; secrets + redaction; runtime artifacts; safety-policy human review; command/shell injection rejection; symlink escape; unsupported schema; partial recovery; workflow permissions/secrets/live/merge/deploy bans; Round 1–3C still pass.

---

## 26. Explicitly deferred functionality

**Round 4B complete:** private remote GitHub workflow execution validated (run `29930178622`). Permissions/secrets/live/deploy posture unchanged.

Still deferred (later rounds only with explicit approval): action SHA pinning verification; vulnerability DB scanning; coverage/quality gates beyond pytest; auto-fix CI; required status checks enforcement; deployment; auto-merge; live provider CI smoke; Equitify; paid API CI; mutable caching of secrets; autonomous review bots; high-quality reporting system upgrade (next planned development round).
