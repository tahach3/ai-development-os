"""Deterministic task routing to Claude / Cursor / Codex roles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Complexity, ModelRole, RiskLevel, RoutingDecision, Task, TaskType


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_routing_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or (_repo_root() / "config" / "default_routing.yaml")
    with cfg_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError("Routing config must be a mapping")
    return data


def load_token_budgets(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or (_repo_root() / "config" / "token_budgets.yaml")
    with cfg_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError("Token budget config must be a mapping")
    return data


def select_token_budget_band(task: Task) -> Complexity:
    """Map task complexity/risk to a budget band without fabricating usage."""
    if task.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
        return Complexity.HIGH_RISK
    if task.complexity is Complexity.HIGH_RISK:
        return Complexity.HIGH_RISK
    return task.complexity


def get_budget_limits(band: Complexity, budgets_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = budgets_cfg or load_token_budgets()
    budgets = cfg.get("budgets") or {}
    limits = budgets.get(band.value)
    if not isinstance(limits, dict):
        raise KeyError(f"Unknown token budget band: {band.value}")
    return {
        "band": band.value,
        "max_input_tokens": int(limits["max_input_tokens"]),
        "max_output_tokens": int(limits["max_output_tokens"]),
        "description": str(limits.get("description") or ""),
    }


def route_task(task: Task, routing_cfg: dict[str, Any] | None = None) -> RoutingDecision:
    """Deterministic routing with a written explanation."""
    cfg = routing_cfg or load_routing_config()
    rules = list(cfg.get("routing_rules") or [])
    budget = select_token_budget_band(task)

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if "if_risk_in" in rule:
            allowed = {str(x) for x in rule["if_risk_in"]}
            if task.risk_level.value in allowed:
                role = ModelRole(str(rule["prefer"]))
                return RoutingDecision(
                    role=role,
                    explanation=str(rule.get("reason") or f"Matched risk rule → {role.value}"),
                    token_budget_band=budget,
                )
        if "if_complexity_in" in rule:
            allowed = {str(x) for x in rule["if_complexity_in"]}
            if task.complexity.value in allowed:
                role = ModelRole(str(rule["prefer"]))
                return RoutingDecision(
                    role=role,
                    explanation=str(
                        rule.get("reason") or f"Matched complexity rule → {role.value}"
                    ),
                    token_budget_band=budget,
                )
        if "if_task_type_in" in rule:
            allowed = {str(x) for x in rule["if_task_type_in"]}
            if task.task_type.value in allowed:
                role = ModelRole(str(rule["prefer"]))
                return RoutingDecision(
                    role=role,
                    explanation=str(
                        rule.get("reason") or f"Matched task_type rule → {role.value}"
                    ),
                    token_budget_band=budget,
                )
        if "default" in rule:
            role = ModelRole(str(rule["default"]))
            return RoutingDecision(
                role=role,
                explanation=str(rule.get("reason") or f"Default route → {role.value}"),
                token_budget_band=budget,
            )

    # Hard fallback if config omits default.
    if task.task_type in {TaskType.REVIEW, TaskType.INDEPENDENT_REVIEW}:
        return RoutingDecision(
            role=ModelRole.CODEX,
            explanation="Fallback: review tasks prefer Codex second-opinion role.",
            token_budget_band=budget,
        )
    if task.complexity in {Complexity.COMPLEX, Complexity.HIGH_RISK} or task.risk_level in {
        RiskLevel.HIGH,
        RiskLevel.CRITICAL,
    }:
        return RoutingDecision(
            role=ModelRole.CLAUDE,
            explanation="Fallback: complex/high-risk prefers Claude.",
            token_budget_band=budget,
        )
    return RoutingDecision(
        role=ModelRole.CURSOR,
        explanation="Fallback: default daily editing prefers Cursor.",
        token_budget_band=budget,
    )


def apply_routing(task: Task, decision: RoutingDecision | None = None) -> Task:
    decision = decision or route_task(task)
    data = task.to_dict()
    data["assigned_role"] = decision.role.value
    data["routing_explanation"] = decision.explanation
    data["token_budget_band"] = decision.token_budget_band.value
    from .models import utc_now_iso

    data["updated_at"] = utc_now_iso()
    return Task.from_dict(data)
