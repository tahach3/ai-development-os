# Reporting Standard (Round 4C)

**Package:** `0.7.0`  
**Schema / policy / renderer:** `4c.1`  
**Principle:** Canonical structured evidence → deterministic validation → relevance selection → audience-specific rendering → readable report → audit appendix.

## Canonical evidence

Evidence items (`schemas/evidence_item.schema.json`) reference persisted sources by ID/fingerprint. Reports do not copy raw secret-bearing records.

## Claim statuses

| Status | Meaning |
| --- | --- |
| `verified` | Deterministic check or authoritative artifact |
| `reported` | Stated but not independently verified |
| `inferred` | Deterministic rule + input evidence IDs required |
| `conflicting` | Unresolved disagreement |
| `unavailable` | Relevant but missing (never zero-filled) |
| `not_applicable` | Requires applicability reason |

## Audiences and detail levels

Audiences: `executive`, `operator`, `developer`, `independent_reviewer`, `auditor`  
Detail: `summary`, `standard`, `full`, `audit` (independent axes)

## Report statuses

`complete` | `complete_with_notes` | `incomplete` | `conflicting_evidence` | `blocked` | `invalid` | `stale`

Distinct from task / review / CI verdicts.

## Relevance

Deterministic rules in `reporting_relevance.py`. Critical blockers always included. Decisions logged with rule IDs.

## Integrity

- `source_set_fingerprint`: evidence integrity hashes + bindings + policy versions  
- `report_fingerprint`: semantic snapshot excluding `generated_at` / rendered paths  

## Redaction

Fail-closed via `reporting_redaction.py` + `ci_secrets.redact_secrets`. Events recorded; secrets never re-stored.

## Backward compatibility

Legacy implementation/review/behavioral reports remain readable via adapters as `reported` / `legacy_supported`. Historical records are never rewritten.

## CLI

```text
ai-dev-os build-report --evidence-bundle PATH --audience developer --detail-level standard
ai-dev-os render-report --report-id RID [--audience ...] [--detail-level ...]
ai-dev-os validate-report --report-id RID [--current-bindings PATH]
ai-dev-os show-report --report-id RID [--json]
```

## Storage

```text
workspace/reports/canonical/
workspace/reports/rendered/
workspace/reports/manifests/
```

Runtime reports are gitignored. No cloud upload. No automatic purge.

## Limitations (Round 4C)

- No LLM summaries
- No live providers / paid APIs
- No vulnerability database (`vulnerability_scan: unavailable`)
- No dashboard
- No network required to render persisted reports
- Equitify remains disconnected
