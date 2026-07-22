# Round 3A — Safe Execution Design

**Status:** Approved for implementation in this round  
**Scope:** Isolated sessions, confined worktrees, allowlisted local subprocess (targeted pytest), audit envelopes  
**Not in scope:** Provider CLI spawn (Claude/Cursor/Codex), Equitify, network models, dashboards, auto-merge/push

---

## Self-review vs existing boundaries

| Existing rule | Round 3A stance |
| --- | --- |
| Manual handoff adapters only | Unchanged. Adapters stay `manual_handoff_required`. Safe exec is a separate local lane. |
| Inspect-only `git_safety.py` | Unchanged. Worktree create/remove lives in a **separate** allowlisted module; no reset/push/merge/commit. |
| No executing generated agent code | Round 3A runs only **policy-allowlisted** argv arrays (primarily `python -m pytest`), never freeform shell. |
| Registry + Equitify sentinels | Sessions and cwd must resolve through registry; Equitify names/paths rejected. |
| No new dependencies | Stdlib + existing PyYAML/pytest only. |
| No network / paid APIs / browser | No change. |
| Workspace artifacts under this repo | Sessions, worktrees, audits under `workspace/sessions/` and `workspace/executions/`. |

No contradictions remain after this separation of concerns.

---

## 1. Session and isolated-worktree lifecycle

**States:** `created` → `active` → `cleaned_up` (terminal). Failures may land in `failed` then still allow cleanup.

**Create session**

1. Require registered, active project (synthetic; primarily `calculator-demo`).
2. Reject Equitify sentinels in project id/name/root.
3. Require project root to be a Git repository with a resolvable HEAD.
4. Freeze `project_id`, `starting_commit` (HEAD at create), optional `task_id`.
5. Allocate `session_id` and paths under `workspace/sessions/<session_id>/`.
6. Create linked worktree at `workspace/sessions/<session_id>/worktree` pointing at `starting_commit`.
7. Persist session YAML; append audit record.

**Active use**

- All safe executions for the session use the session worktree as the only allowed working directory root.
- `project_id` and `starting_commit` are immutable after create.

**Cleanup**

- `git worktree remove` (allowlisted) for the session worktree path.
- Mark session `cleaned_up`; do not delete the main project checkout or its `.git`.
- Persist cleanup audit; refuse further execution on cleaned sessions.

---

## 2. Worktrees bound to registered synthetic projects

- Worktree create is refused for unregistered or inactive projects.
- Worktree path must resolve under this OS repo’s `workspace/sessions/<session_id>/`.
- Project root must remain the registered `root_path`; sessions cannot retarget to another project.
- Equitify path prefixes and sentinel strings are rejected at session create and path checks.
- Primary validation target: `demo_projects/calculator-demo` (or temp synthetic clones in tests).

---

## 3. Safe command policy / allowlisting

**Executable allowlist (basename, case-insensitive on Windows):**

- `python`, `python.exe` (resolved to `sys.executable` when invoking)
- `git`, `git.exe` — **only** inside the worktree module for `worktree add|list|remove`

**Execution profiles (Round 3A):**

| Profile | Argv shape | Notes |
| --- | --- | --- |
| `pytest` | `[python, "-m", "pytest", ...safe flags..., ...paths...]` | Only targeted tests |

**Rejected always**

- `shell=True` or any string passed to a shell
- Shell operators / metacharacters in argv tokens (`|`, `&`, `;`, `` ` ``, `$`, `>`, `<`, newlines)
- Unsupported executables (`cmd`, `powershell`, `bash`, `claude`, `cursor`, `codex`, `npm`, …)
- Freeform `python -c` / `-m` modules other than `pytest`
- Destructive git verbs (reuse `FORBIDDEN_ACTIONS` from inspect policy; worktree module allows only worktree subcommands)

---

## 4. Working-directory confinement + symlink-escape protection

1. Normalize requested cwd to absolute via `Path.resolve()`.
2. Require resolved cwd to be under the session worktree root (also resolved).
3. Reject if worktree root or cwd string matches Equitify sentinels.
4. Reject path traversal tokens that escape after resolve.
5. Symlink escape: because `resolve()` follows links, a link pointing outside the worktree fails the under-root check.

---

## 5. Environment-variable filtering

Child processes receive a **minimal allowlist**, not `os.environ` wholesale:

- Kept (when present): `PATH`, `PATHEXT`, `SYSTEMROOT`, `SYSTEMDRIVE`, `WINDIR`, `TEMP`, `TMP`, `HOME`, `USERPROFILE`, `LANG`, `LC_ALL`, `PYTHONUTF8`, `PYTHONIOENCODING`
- Explicitly dropped: any key matching secret-like patterns (`API_KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `OPENAI`, `ANTHROPIC`, `AWS_`, `CREDENTIAL`, …) even if somehow listed
- `PYTHONPATH` is not inherited (avoids unexpected module injection)

---

## 6. Timeout and cancellation

- Default timeout: 30 seconds; hard ceiling: 120 seconds (caller may request lower).
- `subprocess.run(..., timeout=…)`; on `TimeoutExpired`, record `timeout_status=true`, `execution_status=timeout`, best-effort captured partial output.
- No background daemons; no silent restart.

---

## 7. stdout/stderr size limits

- Default cap: 65_536 bytes per stream (UTF-8, replacement on decode errors).
- Over-cap streams are truncated; envelope sets `stdout_truncated` / `stderr_truncated`.
- Full unbounded logs are never written to audit payloads.

---

## 8. Targeted test-command selection

- CLI/API accepts optional relative test paths (files/dirs/node ids).
- Each path must resolve under the session worktree.
- Default: `tests` if present under worktree, else `.` is **not** used blindly — require explicit `tests` directory or caller paths.
- Allowed pytest flags only: `-q`, `-v`, `--tb=short`, `--tb=line`, `-x`, `-k <expr>` where `<expr>` passes metacharacter checks.
- Result envelope records `tests_requested` and `tests_executed` (executed = requested paths that were included in argv after policy acceptance).

---

## 9. Normalized execution-result envelope

Minimum fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | `3a.1` |
| `session_id` | Session key |
| `task_id` | Optional task linkage |
| `project_id` | Frozen project |
| `executable` | Resolved executable path/name |
| `argument_array` | Full argv list |
| `sanitized_working_directory` | Resolved confined cwd |
| `started_at` / `finished_at` | UTC ISO timestamps |
| `duration_seconds` | Float seconds |
| `exit_code` | int or null if not started |
| `timeout_status` | bool |
| `stdout_truncated` / `stderr_truncated` | bool |
| `stdout` / `stderr` | Possibly truncated text |
| `execution_status` | `success` \| `failed` \| `timeout` \| `rejected` \| `error` |
| `tests_requested` / `tests_executed` | lists |
| `starting_commit` | Frozen at session create |
| `resulting_commit` | HEAD after run if readable; else null |
| `policy_decision` | `allow` \| `deny` |
| `rejection_reason` | null or string |
| `automation_status` | `local_allowlisted_execution` |

Rejected invocations still produce an envelope with `policy_decision=deny` and empty/null run fields as appropriate.

---

## 10. Audit records + deterministic serialization

- Persist each envelope under `workspace/executions/<execution_id>.json`.
- Session records under `workspace/sessions/<session_id>/session.yaml`.
- Serialization: `json.dumps(..., sort_keys=True, indent=2, ensure_ascii=False)` plus stable dataclass `to_dict()` key sets.
- Durations rounded to 6 decimal places for stability in tests where needed; timestamps are wall-clock (not frozen) but schema keys are deterministic.

---

## 11. Failure states and recovery

| Condition | Behavior |
| --- | --- |
| Policy deny | Envelope `rejected`; no subprocess |
| Timeout | Process killed by subprocess; status `timeout` |
| Non-zero exit | `failed` with exit_code |
| Spawn OSError | `error` with rejection/reason text |
| Session missing / cleaned | Refuse execution |
| Worktree remove failure | Surface error; do not claim cleanup success |
| Main checkout dirty | Irrelevant to cleanup; cleanup must not reset/clean main tree |

Recovery is operator-driven: fix inputs, create a new session, or retry cleanup. No automatic merge or force-push.

---

## 12. Explicitly deferred capabilities (Round 3B+)

- Spawning Claude, Cursor, or Codex CLIs
- MCO-style multi-provider adapters with real process fan-out
- Arbitrary command profiles beyond pytest
- Network model calls / paid APIs
- Browser / dashboard / daemon supervisor
- Auto-merge, auto-push, deploy
- Equitify connection
- Executing model-generated shell scripts
- Self-modifying safety policy

---

## 13. Security threats and controls

| Threat | Control |
| --- | --- |
| Shell injection | `shell=False`; argv arrays; metacharacter reject |
| Unauthorized project | Registry require + Equitify sentinels |
| Path escape / symlink | `resolve()` + under-worktree check |
| Secret leakage via env | Minimal env allowlist; secret-name deny |
| Resource exhaustion | Timeouts + output caps |
| Destructive git | Separate worktree-only mutator; inspect-only elsewhere |
| Silent session retarget | Immutable `project_id` / `starting_commit` |
| Provider CLI surprise | Exec allowlist excludes agent CLIs |
| Cleanup collateral | Worktree remove only session path |

---

## 14. Acceptance criteria and test matrix

| # | Case | Expected |
| --- | --- | --- |
| 1 | Unregistered project session | Reject |
| 2 | Equitify name/path | Reject |
| 3 | Path traversal / symlink escape | Reject |
| 4 | Unsupported executable | Reject |
| 5 | Shell operator in argv | Reject |
| 6 | Timeout | `timeout_status` true |
| 7 | Oversized stdout | Truncation flags |
| 8 | Secret env vars | Not present in child |
| 9 | Targeted pytest | Runs under worktree; envelope ok |
| 10 | Deterministic JSON keys/sort | Stable serialization |
| 11 | Mutate session project/commit | Rejected |
| 12 | Cleanup | Worktree gone; main checkout intact |
| 13 | Round 1+2 regression | Existing pytest suite green |

CLI must expose create/show/cleanup session and run-tests (plus show-execution) without accepting freeform shell strings.
