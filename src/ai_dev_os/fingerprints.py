"""Deterministic cryptographic fingerprints for immutable content gates."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(payload: Any) -> str:
    """Stable JSON serialization (sorted keys, no insignificant whitespace)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(payload: Any) -> str:
    raw = canonical_json(payload).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def fingerprint(payload: Any) -> str:
    """Public alias for content fingerprinting."""
    return sha256_hex(payload)


def task_impl_relevant_payload(task_dict: dict[str, Any]) -> dict[str, Any]:
    """Fields that define implementation scope (exclude volatile timestamps)."""
    return {
        "id": task_dict.get("id"),
        "title": task_dict.get("title"),
        "description": task_dict.get("description"),
        "project_id": task_dict.get("project_id"),
        "task_type": task_dict.get("task_type"),
        "complexity": task_dict.get("complexity"),
        "risk_level": task_dict.get("risk_level"),
        "acceptance_criteria": list(task_dict.get("acceptance_criteria") or []),
        "allowed_paths": list(task_dict.get("allowed_paths") or []),
        "prohibited_paths": list(task_dict.get("prohibited_paths") or []),
        "parent_task_id": task_dict.get("parent_task_id"),
    }


def plan_impl_relevant_payload(plan_dict: dict[str, Any]) -> dict[str, Any]:
    """Implementation-relevant plan content (excludes approval/status timestamps)."""
    return {
        "plan_id": plan_dict.get("plan_id"),
        "task_id": plan_dict.get("task_id"),
        "project_id": plan_dict.get("project_id"),
        "planner_agent": plan_dict.get("planner_agent"),
        "starting_commit": plan_dict.get("starting_commit"),
        "objective": plan_dict.get("objective"),
        "assumptions": list(plan_dict.get("assumptions") or []),
        "scope": list(plan_dict.get("scope") or []),
        "prohibited_actions": list(plan_dict.get("prohibited_actions") or []),
        "files_expected_to_change": list(plan_dict.get("files_expected_to_change") or []),
        "implementation_steps": list(plan_dict.get("implementation_steps") or []),
        "testing_plan": list(plan_dict.get("testing_plan") or []),
        "rollback_or_recovery_plan": list(plan_dict.get("rollback_or_recovery_plan") or []),
        "risks": list(plan_dict.get("risks") or []),
        "unresolved_questions": list(plan_dict.get("unresolved_questions") or []),
        "approval_requirement": plan_dict.get("approval_requirement"),
    }


def context_manifest_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    data = dict(manifest)
    data.pop("created_at", None)
    return data


def implementation_report_payload(report_dict: dict[str, Any]) -> dict[str, Any]:
    data = {
        "task_id": report_dict.get("task_id"),
        "summary": report_dict.get("summary"),
        "files_changed": list(report_dict.get("files_changed") or []),
        "tests_run": list(report_dict.get("tests_run") or []),
        "outcome": report_dict.get("outcome"),
        "notes": report_dict.get("notes"),
        "token_usage": report_dict.get("token_usage"),
        "plan_fingerprint": report_dict.get("plan_fingerprint"),
        "task_fingerprint": report_dict.get("task_fingerprint"),
    }
    return data


def review_report_payload(report_dict: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": report_dict.get("task_id"),
        "reviewer_role": report_dict.get("reviewer_role"),
        "verdict": report_dict.get("verdict"),
        "findings": list(report_dict.get("findings") or []),
        "confirmed_findings": list(report_dict.get("confirmed_findings") or []),
        "rejected_findings": list(report_dict.get("rejected_findings") or []),
        "notes": report_dict.get("notes"),
        "implementation_report_fingerprint": report_dict.get(
            "implementation_report_fingerprint"
        ),
    }


def fingerprint_task(task_dict: dict[str, Any]) -> str:
    return fingerprint(task_impl_relevant_payload(task_dict))


def fingerprint_plan(plan_dict: dict[str, Any]) -> str:
    return fingerprint(plan_impl_relevant_payload(plan_dict))


def fingerprint_context_manifest(manifest: dict[str, Any]) -> str:
    return fingerprint(context_manifest_payload(manifest))


def fingerprint_implementation_report(report_dict: dict[str, Any]) -> str:
    return fingerprint(implementation_report_payload(report_dict))


def fingerprint_review_report(report_dict: dict[str, Any]) -> str:
    return fingerprint(review_report_payload(report_dict))
