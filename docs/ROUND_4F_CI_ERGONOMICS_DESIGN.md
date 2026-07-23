# Round 4F — CI Ergonomics (Flaky Isolation, Coverage Notes, Workflow Wiring)

**Status:** Design + implementation (local only)  
**Scope:** Three additive, **opt-in** CI ergonomics features. Defaults stay byte-for-byte unchanged.  
**Package version target:** `0.8.6` (baseline `0.8.5` / commit `c55ca5d`, Round 4E)  
**CI schema/policy:** remains **`4a.1`** (no schema bump; no `STAGE_ORDER` reorder/remove/insert)

**Not in scope (LOCKED):** Round 4D2 live model/network/paid-API calls; Equitify open/reference/integrate; new **runtime** dependencies; GitHub Actions permission/secret changes; auto-merge/deploy; coverage as a gate; silent flaky retries; mandatory new CI stage

**Verified baseline (pre-implementation):** `HEAD = c55ca5d` on `master`; untracked memory/SQLite WIP must **not** be staged. Full suite green excluding that WIP (`265 passed, 2 skipped`).

---

## 1. Goals

1. **Flaky-test isolation (opt-in):** `--isolate-flaky` on `ci-check` and `ci-targeted` re-runs only failed pytest node ids once, in isolation, under the existing timeout — with a non-negotiable honesty rule (below).
2. **Coverage notes (opt-in):** `--coverage` on `ci-check` emits measured coverage as **notes only**; never affects verdict. Optional `[cov]` extra only.
3. **Workflow wiring:** PR-only `ci-targeted --base <PR base ref>` for fast signal, while full `pytest` + `ci-check` remain authoritative. Permissions stay `contents: read`.

---

## 2. Honesty rule (flaky isolation)

| First run | Isolated re-run | Outcome |
| --- | --- | --- |
| Pass | (n/a) | Unchanged pass |
| Fail | Fail (any of the retried nodes) | **`tests_failed`**, blocker, verdict **fail** — real failure |
| Fail | All retried nodes pass | Stage **passed** with loud notes; failure class **`flaky_test_detected`** (non-blocking); run verdict **`pass_with_notes`**; exit 0 — **never** a silent pass |
| Without `--isolate-flaky` | — | First fail → **`tests_failed`** (byte-for-byte same argv/behavior as today) |

**Non-negotiable:** Fail-then-pass is visible. Operators must see every flaky node id in notes and in `failure_classes`. No automatic “greenwash.”

Re-run constraints:

- At most **one** isolated re-run of the failed node id set.
- Same timeout clamp as the primary pytest stage (`policy.pytest_timeout_seconds`).
- Argv-only via existing `run_ci_command` (no shell).
- If failed node ids cannot be parsed → treat as real **`tests_failed`** (fail closed; do not invent a pass).

---

## 3. Feature A — `--isolate-flaky`

### 3.1 CLI

- `ai-dev-os ci-check --isolate-flaky`
- `ai-dev-os ci-targeted --isolate-flaky` (same semantics on the targeted pytest invocation)

Default off. When off, `pytest_suite` argv remains `[python, "-m", "pytest", "-q"]` (+ optional path args for targeted only).

### 3.2 Behavior inside pytest stage / targeted runner

1. Run primary pytest (quiet).
2. If exit 0 → unchanged success path (coverage notes may still attach if requested on `ci-check`).
3. If fail and flag set:
   - Parse node ids from output (`FAILED <nodeid>` / short-test-summary lines).
   - Re-run `python -m pytest -q <nodeid>…` once.
   - Apply honesty rule table in §2.
4. New enum value: `CIFailureClass.FLAKY_TEST_DETECTED = "flaky_test_detected"` (additive on existing failure-class set; schema version stays `4a.1`).

### 3.3 Verdict interaction

- `flaky_test_detected` is recorded on the stage and rolled into `CIRun.failure_classes`.
- Stage `blocker=False`, `validation_status=passed`.
- Existing `_apply_verdict`: notes → `pass_with_notes`; hard fail only when blockers / failed statuses present.

---

## 4. Feature B — `--coverage` (notes only)

### 4.1 Packaging

```toml
[project.optional-dependencies]
dev = ["pytest>=7.4"]
cov = ["coverage>=7"]   # OPTIONAL — never a runtime dependency
```

Install: `pip install -e ".[cov]"` (or `.[dev,cov]`). Not required for package install or CI pass.

### 4.2 CLI

- `ai-dev-os ci-check --coverage` only (targeted path may omit coverage in Round 4F to keep PR signal fast; deferred if needed).

### 4.3 Graceful degradation

| `coverage` importable? | Behavior |
| --- | --- |
| Yes | Run pytest under coverage (e.g. `python -m coverage run -m pytest …` then `coverage report -m` / total parse). Append note(s): total %; if `--base` / compared base available and changed `.py` files exist, also changed-file % when feasible. |
| No | Append note: `coverage not measured (install optional extra)`. No crash. No gate. |

**Verdict:** coverage notes must **never** flip pass↔fail, never set blocker, never add a blocking failure class. Missing coverage is informational only.

### 4.4 Determinism

- Fixed argv arrays; sanitized env via existing runner.
- Coverage data written under a disposable path when needed (e.g. temp / workspace-local, not committed).
- Do not require network; do not download plugins.

---

## 5. Feature C — `ci-targeted` + workflow

### 5.1 Command

`ai-dev-os ci-targeted --base <ref> [--isolate-flaky]`

- Resolves changed paths via `git diff --name-only <base>...HEAD` (argv-only).
- Selects a **targeted** pytest path set:
  - Changed files under `tests/` that look like tests (`test_*.py` / `*_test.py`).
  - Heuristic: for changed `src/**/*.py`, include existing sibling-style tests under `tests/` when a deterministic name match exists (e.g. module stem → `tests/test_<stem>.py` or `tests/**/test_<stem>.py` if present).
  - If no targets → emit pass-with-notes / informational note `no targeted tests for change set` (not a silent authority substitute).
- Runs allowlisted pytest on those paths only (reuse CI runner + flaky helper).
- Prints normalized JSON compatible with CI run shape (or a thin CIRun with a single pytest-equivalent stage) and uses the same exit-code mapping (`pass` / `pass_with_notes` → 0).

**Authority:** `ci-targeted` is a **fast signal only**. Full `pytest` and `ci-check` remain the merge-quality gates.

### 5.2 Workflow (`.github/workflows/ci.yml`)

Additive PR-only step; keep existing steps:

1. Checkout (may set `fetch-depth: 0` so base SHA exists — **not** a permission change).
2. Setup Python 3.11 + `pip install -e ".[dev]"`.
3. **New (PR only):** `python -m ai_dev_os.cli ci-targeted --base ${{ github.event.pull_request.base.sha }}`
4. Full `pytest -q` (authoritative).
5. `ci-check --skip-stages pytest_suite` (authoritative).
6. `git diff --check`.

Constraints unchanged:

- `permissions: contents: read`
- Official actions by version tag (`actions/checkout@v4`, `actions/setup-python@v5`)
- No secrets, no auto-merge, no deploy, no artifact upload requiring write

---

## 6. Determinism & reuse

| Concern | Approach |
| --- | --- |
| Subprocess | Existing `run_ci_command` — argv only, filtered env, timeout, output cap |
| Stage order | Unchanged `STAGE_ORDER` |
| Schema | `4a.1`; additive failure class + CLI flags only |
| Default path | No flag → identical pytest argv and fail semantics as Round 4E |
| Equitify / 4D2 | Untouched / LOCKED |

---

## 7. Tests (`tests/test_round4f_ci_ergonomics.py`)

1. **Flaky fixture:** deterministically fails once then passes → with `--isolate-flaky`, `flaky_test_detected`, loud notes, `pass_with_notes`; not a hidden pass.
2. **Genuine fail:** fails both times → `tests_failed`.
3. **Default:** without flag, fail stays `tests_failed` (unchanged).
4. **Coverage present:** non-blocking note; verdict unaffected by coverage %.
5. **Coverage absent:** graceful note; no crash; no gate.
6. **Workflow parse:** `contents: read`, no secrets, full pytest + ci-check still present; PR `ci-targeted` step present.

Plus version bump guards → `0.8.6`.

---

## 8. Docs / version deliverables

- Bump `0.8.5` → `0.8.6` (`pyproject.toml`, `__init__.py`, version assertion tests).
- Update README, ROADMAP, PROJECT_CHRONICLE for Round 4F.
- One clean local commit; **do not push** Round 4F unless separately requested.

---

## 9. Deferred (explicit)

- Coverage as a blocking gate or required status check
- pytest-xdist / plugin-based flaky quarantine databases
- Changing GitHub Actions permissions or SHA-pinning actions (later round)
- Round 4D2 / live providers / paid APIs
- Equitify integration
- Mandatory `STAGE_ORDER` stage for coverage or flaky detection
- Auto-re-run of the **full** suite on flaky detect
- Committing coverage XML/HTML artifacts from CI
- Staging or completing untracked memory/SQLite WIP

---

## 10. Acceptance checklist

- [ ] Design covers all three features + honesty rule + coverage degradation + deferred
- [ ] `--isolate-flaky` honesty upheld; default path unchanged
- [ ] `--coverage` notes-only; `[cov]` optional; no runtime dep
- [ ] Workflow PR `ci-targeted`; authoritative pytest + ci-check kept; `contents: read`
- [ ] `STAGE_ORDER` / `4a.1` unchanged
- [ ] Focused + full suite green; `ci-check` e2e
- [ ] Version `0.8.6`; docs updated; one local commit; Equitify untouched; 4D2 LOCKED
