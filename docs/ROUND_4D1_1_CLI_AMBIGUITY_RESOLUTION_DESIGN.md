# Round 4D1.1 — Trusted Provider CLI Ambiguity Resolution Design

**Package target:** `0.8.1` (hardening of Round 4D1 readiness; not a new major subsystem)  
**Ambiguity-resolution schema:** `4d1.1.1`  
**Executable-identity policy:** `4d1.1.1`  
**Logical-installation policy:** `4d1.1.1`  
**Executable-pinning schema:** `4d1.1.1`  
**Executable-trust policy:** `4d1.1.1` (extends `4d1.1`)  
**Operator-selection schema:** `4d1.1.1`  
**Baseline:** `master` @ `e926712` (package `0.8.0`, Round 4D1 complete)  
**Live model invocations authorized in this round:** **0**

---

## 1. Ambiguity categories

Each discovered candidate receives exactly one primary classification:

| Classification | Meaning |
| --- | --- |
| `same_binary_duplicate_path` | Distinct path strings resolve to one filesystem identity |
| `same_binary_multiple_aliases` | Alias / App Execution Alias / symlink names for one target |
| `wrapper_and_target` | Script/shim deterministically launches a fingerprinted target also discovered |
| `version_manager_shim` | nvm/asdf/pyenv-style shim with static target |
| `package_manager_shim` | npm/pnpm/bun/Scoop/Chocolatey shim with static target |
| `application_launcher` | IDE/app launcher that starts a known CLI target |
| `stale_path_entry` | PATH entry missing or non-executable |
| `broken_executable` | Exists but not runnable / unreadable |
| `unsupported_version_duplicate` | Install present but CLI version out of policy range |
| `distinct_installations_same_version` | Different fingerprints; version text happens to match |
| `distinct_installations_different_versions` | Different fingerprints and versions |
| `trusted_and_untrusted_candidates` | Mix of trust outcomes in the candidate set |
| `multiple_trusted_candidates` | ≥2 trusted distinct logical installations remain |
| `unresolved_provenance` | Cannot prove target / fingerprint / mechanism |
| `unsupported_wrapper` | Wrapper uses dynamic/`%*` / eval / nested shell invocation |
| `invalid_candidate_record` | Malformed or incomplete candidate metadata |

**Non-equivalence (hard rules):** filename match, version-text match, PATH order, shared provider ID, or similar help text alone never prove equivalence.

## 2. Logical-installation identity

A **logical installation** is the collapse unit after identity analysis:

- `logical_installation_id` — deterministic hash of provider + canonical target fingerprint (+ normalized target path class)
- `provider_id`
- member `candidate_ids`
- `canonical_target` (sanitized path label + internal absolute path for pinning only)
- `target_fingerprint`
- `cli_version` (from safe version probe of selected invocation candidate, when run)
- `installation_mechanism` (`standalone_binary` | `cmd_wrapper` | `bat_wrapper` | `ps1_wrapper` | `posix_script` | `symlink` | `package_manager_shim` | `version_manager_shim` | `app_launcher` | `unknown`)
- `provenance` (discovery methods)
- `trust_status` / `compatibility_status`
- `aliases`, `wrappers`, `path_ranks`
- `selected_invocation_candidate` (how operators should invoke once pinned/resolved)
- `equivalence_evidence` (rule IDs + evidence IDs)
- `ambiguity_status` (`collapsed` | `single` | `requires_selection` | `unresolved`)

## 3. Executable identity

Per candidate, collect safely:

- canonical absolute path (internal; never committed)
- normalized path (case-folding on Windows; slash normalization)
- real target path after symlink resolve (bounded; Equitify rejected)
- file type (`.exe` / `.cmd` / `.bat` / `.ps1` / extensionless / other)
- size, mtime (metadata only)
- SHA-256 of file contents when readable as a regular file
- signer/publisher only when available via safe Windows APIs without elevating; otherwise `unavailable`
- wrapper type / wrapper target
- package/version-manager provenance heuristics from path class only
- CLI version (probe later, after selection)
- adapter compatibility / trust-policy result
- executable status (`present` | `missing` | `unreadable` | `broken`)
- PATH rank (informational)
- discovery mechanisms

## 4. Wrapper identity

Wrappers are scripts (`.cmd`, `.bat`, `.ps1`, POSIX shell) whose **contents are untrusted data**.

Rules:

- Read at most `WRAPPER_READ_LIMIT` bytes (default 16 KiB)
- Never execute extracted command text
- Parse only deterministic static patterns (e.g. `"%~dp0cursor.exe"`, `"%~dp0..\.."` relative targets, `"node" "cli.js"` with fixed relative paths)
- Reject `%*`, nested `cmd /c`, `powershell -Command` with dynamic strings, `eval`, backticks, process substitution, environment-variable path composition beyond `%~dp0`

## 5. Shim identity

Shims (npm/pnpm/bun/Scoop/Chocolatey/version managers) are wrappers with known path classes. Classification uses path heuristics + static parse. Dynamic shim bodies → `unsupported_wrapper`.

## 6. Alias identity

Windows Application Execution Aliases (`WindowsApps`) and symlinks:

- Record alias path and resolved target when `Path.resolve()` succeeds within trust policy
- If resolve fails or escapes trust → untrusted / unresolved

## 7. Underlying-target resolution

Resolution order:

1. Symlink / reparse resolve (Python `Path.resolve`, reject Equitify)
2. Static wrapper parse → relative target under same tree
3. Same-directory basename pair (e.g. `cursor.cmd` → `cursor.exe` or extensionless peer) **only when** parse or sibling evidence proves launch of that peer
4. Never invent targets from help text

## 8. File fingerprint requirements

- SHA-256 of the **file contents** of the candidate itself
- Logical installation fingerprint = SHA-256 of the **canonical target** contents
- Wrapper fingerprint ≠ target fingerprint is expected; equivalence is via wrapper→target link, not content equality
- Missing fingerprint → cannot auto-collapse on fingerprint rules

## 9. Version equivalence requirements

Version text is **never** sufficient for collapse. Version may:

- classify `unsupported_version_duplicate`
- inform recommendation ranking
- invalidate pins when version changes

## 10. Provenance requirements

Record discovery methods (`configured`, `python_which`, `where_exe`, `get_command`, `pin`) and installation mechanism. Unresolved provenance blocks automatic collapse when fingerprints differ.

## 11. Trust decisions

Reuse Round 4D1 trust checks (basename allowlist, Equitify rejection, resolve/exists). Extend:

- unsupported wrapper → not selectable for auto-collapse as target
- broken/stale → eligible for exclusion rules
- unknown trust → no auto selection

## 12. Automatic-collapse rules

Auto-resolve **only** when one rule fully applies. Record `rule_id`:

| Rule ID | Condition |
| --- | --- |
| `AC-SAME-TARGET-01` | All remaining candidates resolve to identical underlying absolute target |
| `AC-SAME-FP-PROV-01` | Identical target fingerprint + compatible provenance for all remaining |
| `AC-EXCLUDE-BROKEN-01` | After removing stale/broken, exactly one valid trusted installation |
| `AC-EXCLUDE-UNTRUSTED-01` | After removing untrusted/unsupported, exactly one valid trusted compatible installation |
| `AC-WRAPPER-TARGET-01` | Wrapper statically launches exact fingerprinted target also in candidate set |
| `AC-DUP-DISCOVERY-01` | Multiple discovery methods found one physical executable (same normalized path) |

**Never** auto-resolve when:

- ≥2 distinct trusted target fingerprints remain
- ≥2 supported versions remain as distinct installs
- provenance unresolved for differing candidates
- wrapper resolution dynamic
- trust unknown
- selection would depend only on PATH order
- operator intent cannot be inferred

## 13. Explicit-selection rules

When ≥2 distinct trusted logical installations remain:

1. Emit operator decision record (`operator_selection_required`)
2. Recommend one candidate with evidence IDs / rule IDs
3. Do **not** pin or select automatically
4. Keep live execution blocked

## 14. Local pinning rules

Pin fields: provider_id, canonical executable path, expected fingerprint, expected CLI version/range, adapter_id/version, trust-policy version, optional expiry, host-binding metadata, pin status, pin fingerprint.

Hard rules:

- Path-only pins rejected
- Fingerprint mismatch → invalid
- CLI / adapter / trust-policy / host change → revalidation required
- Pin never enables live mode, never implies auth, never bypasses compatibility/project/approval gates
- Real paths and usernames never committed

## 15. Host-specific configuration rules

Store pins under ignored runtime area:

`workspace/provider_pins/` (gitignored; `.gitkeep` tracked)

Templates/examples may live under `config/provider_pins.example.json`.

## 16. Sensitive path sanitization

Reuse `sanitize_executable_location`. Public outputs use path labels / candidate IDs. Never print full PATH, env, tokens, or credential locations. Username segments redacted in labels when present.

## 17. Staleness rules

Resolution, decision, or pin is stale when any of: executable path/fingerprint/target, wrapper contents hash, CLI version, adapter version, compatibility/trust/readiness policy, host identity, provider config, project registration, live-execution policy, or (when used) PATH order contribution.

Do not silently reuse stale pins.

## 18. Failure classes

Extend Round 4D1 with:

- `ambiguity_unresolved`
- `operator_selection_required`
- `executable_pin_invalid`
- `executable_pin_stale`
- `wrapper_unsupported`
- `logical_installation_invalid`

## 19. Operator decision record

Fields: decision_id, provider_id, host-binding fingerprint, candidate IDs, sanitized path labels, CLI versions, fingerprints, mechanisms, trust/compatibility, PATH ranks, recommended candidate ID, recommendation reasons, per-candidate risks, exact approval statement, decision status, staleness inputs, decision fingerprint.

Approval phrase form:

`Approve provider executable <candidate_id> for local readiness pinning only.`

## 20. Readiness re-evaluation

After collapse or valid pin:

- Re-run readiness (discovery → optional pin filter → probes → verdict)
- Never send prompts
- Possible outcomes include eligible / conditional / operator_selection_required / auth or noninteractive unverified / version unsupported / no_trusted_candidate / ambiguity_unresolved / validation failed

Success of Round 4D1.1 = (A) deterministic resolution + re-eval **or** (B) complete operator decision record without silent choice.

## 21. Backward compatibility

- Round 4D1 records remain loadable
- Discovery without ambiguity module still safe (fail closed to ambiguous)
- Additive CLI flags; default audit behavior enhanced only via deterministic collapse
- Schema versions independent: readiness `4d1.1`, ambiguity `4d1.1.1`
- Package `0.8.1` for additive hardening

## 22. Test matrix

Fake-only: duplicates, wrappers, shims, launchers, fingerprints, versions, stale/broken/untrusted, two trusted installs, dynamic/malicious wrappers, pins, CLI, reports, legacy compatibility. No real PATH/auth/network dependence.

## 23. Round 4D2 boundary

4D1.1 must not enable live mode, send prompts, claim smoke completed, auto-merge/deploy/release, or pin without approval. Round 4D2 requires separate explicit authorization.

---

## Contradiction resolutions

| Tension | Resolution |
| --- | --- |
| Round 4D1 refused same-fingerprint distinct paths as still ambiguous | 4D1.1 may collapse only via **target** identity / wrapper→target rules with rule IDs; content-identical unrelated paths without shared target still require selection if provenance incompatible |
| Prefer PATH winner vs no PATH-only selection | PATH rank is informational and lowest-priority recommendation factor only |
| Configured path vs pin | Configured tracked path remains Round 4D1; host pins are ignored local overlays requiring fingerprint |
| Cursor wrapper vs automation proof | Collapse may yield `installed`; noninteractive/agent proof remains separate Round 4D1 gates |

---

## Implementation map

| Concern | Module |
| --- | --- |
| Classifications / identity / wrappers / collapse | `provider_readiness_ambiguity.py` |
| Pins | `provider_readiness_pins.py` |
| Operator decisions | `provider_readiness_selection.py` |
| Engine / discovery integration | `provider_readiness_engine.py`, `provider_readiness_discovery.py` |
| CLI flags | `cli.py` |
| Reporting | `provider_readiness_reporting.py` |
| Constants / schemas | `provider_readiness_constants.py`, `schemas/` |
| Tests | `tests/test_round4d1_1_cli_ambiguity.py` |
