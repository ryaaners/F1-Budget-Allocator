"""Pure, assumption-led planning logic for the Track 3 prototype.

This module deliberately models an educational planning gate, not an engineering
repair procedure or a vehicle release decision.  Historical replay data never
flows into the calculations except as a user-selected source reference.
"""
from __future__ import annotations

import json
import math
from pathlib import Path


ASSUMPTIONS_PATH = Path(__file__).with_name("data") / "safety_planning_assumptions.json"


class AssumptionError(ValueError):
    """An editable prototype-assumptions file cannot be safely rendered."""


def load_assumptions():
    """Load the editable, local prototype assumptions without network access."""
    try:
        with ASSUMPTIONS_PATH.open(encoding="utf-8") as assumptions_file:
            data = json.load(assumptions_file)
    except (OSError, UnicodeError) as error:
        raise AssumptionError(f"Could not open the local prototype assumptions file: {error}") from error
    except json.JSONDecodeError as error:
        raise AssumptionError(f"The local prototype assumptions file is not valid JSON: {error.msg}.") from error
    return validate_assumptions(data)


def profiles():
    return load_assumptions().get("profiles", [])


def profile_for(profile_id, catalog=None):
    for profile in (catalog if catalog is not None else profiles()):
        if profile.get("id") == profile_id:
            return profile
    raise ValueError("Choose a valid prototype planning profile.")


def option_for(profile, option_id):
    for option in profile.get("options", []):
        if option.get("id") == option_id:
            return option
    raise ValueError("Choose a valid prototype response option.")


def _finite_nonnegative(value, field_name, whole_number=False):
    """Return a safe value plus a validation message when an editable input is bad.

    The Streamlit controls normally prevent these values, but the planning engine
    is deliberately usable without the UI as well.  It must therefore reject
    NaN, infinity, negatives, and fractional spare counts rather than silently
    turning an invalid scenario into a viable-looking plan.
    """
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = None
    if numeric is None or not math.isfinite(numeric) or numeric < 0:
        kind = "a finite, non-negative whole number" if whole_number else "a finite, non-negative number"
        return 0.0, f"{field_name} must be {kind}."
    if whole_number and not numeric.is_integer():
        return 0.0, f"{field_name} must be a whole number."
    return numeric, None


def _assumed_nonnegative(value, label):
    """Protect against a malformed editable assumptions file without crashing."""
    numeric, problem = _finite_nonnegative(value, label)
    return numeric, problem


def validate_assumptions(data):
    """Validate the small editable catalog before the Streamlit UI renders it."""
    if not isinstance(data, dict):
        raise AssumptionError("The local prototype assumptions file must contain a JSON object.")
    catalog = data.get("profiles")
    if not isinstance(catalog, list) or not catalog:
        raise AssumptionError("The local prototype assumptions file needs at least one planning profile.")
    profile_ids = set()
    for profile_index, profile in enumerate(catalog, start=1):
        if not isinstance(profile, dict):
            raise AssumptionError(f"Planning profile {profile_index} must be a JSON object.")
        profile_id = profile.get("id")
        if not isinstance(profile_id, str) or not profile_id.strip() or profile_id in profile_ids:
            raise AssumptionError(f"Planning profile {profile_index} needs a unique non-empty id.")
        profile_ids.add(profile_id)
        if not isinstance(profile.get("label"), str) or not profile["label"].strip():
            raise AssumptionError(f"Planning profile '{profile_id}' needs a non-empty label.")
        for key, label, whole in (
            ("default_available_spares", "default available spares", True),
            ("default_hours_to_next_session", "default hours to next session", False),
            ("default_reserve_floor_cad", "default reserve floor", False),
        ):
            _, problem = _finite_nonnegative(profile.get(key), label, whole)
            if problem:
                raise AssumptionError(f"Planning profile '{profile_id}': {problem}")
        options = profile.get("options")
        if not isinstance(options, list) or not options:
            raise AssumptionError(f"Planning profile '{profile_id}' needs at least one response option.")
        option_ids = set()
        for option_index, option in enumerate(options, start=1):
            if not isinstance(option, dict):
                raise AssumptionError(
                    f"Response option {option_index} in '{profile_id}' must be a JSON object."
                )
            option_id = option.get("id")
            if not isinstance(option_id, str) or not option_id.strip() or option_id in option_ids:
                raise AssumptionError(
                    f"Response option {option_index} in '{profile_id}' needs a unique non-empty id."
                )
            option_ids.add(option_id)
            if not isinstance(option.get("label"), str) or not option["label"].strip():
                raise AssumptionError(f"Response option '{option_id}' needs a non-empty label.")
            for key, label, whole in (
                ("estimated_cost_cad", "estimated cost", False),
                ("estimated_work_hours", "estimated work hours", False),
                ("spares_required", "spares required", True),
            ):
                _, problem = _finite_nonnegative(option.get(key), label, whole)
                if problem:
                    raise AssumptionError(f"Response option '{option_id}': {problem}")
            actions = option.get("required_actions")
            if not isinstance(actions, list):
                raise AssumptionError(f"Response option '{option_id}' needs a required_actions list.")
            action_ids = set()
            for action in actions:
                if not isinstance(action, dict):
                    raise AssumptionError(f"Response option '{option_id}' has an invalid action entry.")
                action_id = action.get("id")
                if not isinstance(action_id, str) or not action_id.strip() or action_id in action_ids:
                    raise AssumptionError(
                        f"Response option '{option_id}' has an action without a unique non-empty id."
                    )
                action_ids.add(action_id)
                if not isinstance(action.get("label"), str) or not action["label"].strip():
                    raise AssumptionError(f"Action '{action_id}' needs a non-empty label.")
    return data


def _completed_action_ids(value):
    if isinstance(value, dict):
        return {str(key) for key, completed in value.items() if completed}
    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value}
    return set()


def _option_override(case_inputs, option_id):
    """Read a per-option session override without letting it affect other options."""
    overrides = case_inputs.get("option_overrides")
    if not isinstance(overrides, dict):
        return {}
    override = overrides.get(option_id)
    return override if isinstance(override, dict) else {}


def evaluate_option(profile, option_id, case_inputs):
    """Evaluate one transparent prototype option against editable inputs.

    ``REVIEW_ELIGIBLE`` means only that the prototype's stated assumptions and
    checklist are complete. It never means a car is safe to race or released.
    """
    option = option_for(profile, option_id)
    case_inputs = case_inputs if isinstance(case_inputs, dict) else {}
    override = _option_override(case_inputs, option_id)
    input_problems = []

    def editable(key, label, whole_number=False):
        value, problem = _finite_nonnegative(case_inputs.get(key), label, whole_number)
        if problem:
            input_problems.append(problem)
        return int(value) if whole_number else value

    available_spares = editable("available_spares", "Available spares", whole_number=True)
    hours_available = editable("hours_available", "Hours available")
    reserve_before = editable("reserve_before", "Current crash reserve")
    reserve_floor = editable("reserve_floor", "Selected reserve floor")
    planned_transfer = editable("planned_transfer", "Planned funding transfer")
    funding_capacity = editable("funding_capacity", "Selected source capacity")
    cap_headroom = editable("cap_headroom", "Local cap headroom")
    completed = _completed_action_ids(case_inputs.get("completed_actions"))

    cost_label = "Editable option cost" if "estimated_cost_cad" in override else "Assumed option cost"
    hours_label = "Editable option work hours" if "estimated_work_hours" in override else "Assumed option work hours"
    spares_label = "Editable option spare requirement" if "spares_required" in override else "Assumed spare requirement"
    estimated_cost, cost_problem = _assumed_nonnegative(
        override.get("estimated_cost_cad", option.get("estimated_cost_cad")), cost_label
    )
    estimated_hours, hours_problem = _assumed_nonnegative(
        override.get("estimated_work_hours", option.get("estimated_work_hours")), hours_label
    )
    spare_value, spare_problem = _finite_nonnegative(
        override.get("spares_required", option.get("spares_required")), spares_label, whole_number=True
    )
    spares_required = int(spare_value)
    required_actions = option.get("required_actions", [])
    missing_actions = [
        action for action in required_actions if str(action.get("id")) not in completed
    ]

    transfer_required = max(0.0, estimated_cost + reserve_floor - reserve_before)
    projected_reserve = reserve_before - estimated_cost + planned_transfer
    reserve_used = min(reserve_before, estimated_cost)
    spend_outside_reserve = max(0.0, estimated_cost - reserve_before)
    net_cap_change = estimated_cost - planned_transfer
    blockers = list(input_problems)
    for problem in (cost_problem, hours_problem, spare_problem):
        if problem:
            blockers.append(f"Editable option assumption problem: {problem}")
    if not option.get("can_request_review", False):
        blockers.append("This prototype option is deliberately a hold-only path.")
    if option.get("can_request_review", False) and estimated_cost <= 0:
        blockers.append("A review-request option needs a positive editable modelled cost.")
    if available_spares < spares_required:
        blockers.append(
            f"Prototype spare assumption is short by {spares_required - available_spares}."
        )
    if hours_available < estimated_hours:
        blockers.append(
            f"Prototype work-window assumption is short by {estimated_hours - hours_available:.1f} hours."
        )
    if planned_transfer < transfer_required:
        blockers.append(
            f"Planned funding transfer is short by CAD ${transfer_required - planned_transfer:,.0f} "
            "to protect the selected reserve floor."
        )
    if planned_transfer > funding_capacity:
        blockers.append(
            f"Planned funding transfer exceeds the selected source capacity by "
            f"CAD ${planned_transfer - funding_capacity:,.0f}."
        )
    if projected_reserve < reserve_floor:
        blockers.append(
            f"Projected reserve is CAD ${reserve_floor - projected_reserve:,.0f} below the selected floor."
        )
    if net_cap_change > cap_headroom:
        blockers.append(
            f"Local cap headroom is short by CAD ${net_cap_change - cap_headroom:,.0f} after the selected transfer."
        )
    if missing_actions:
        blockers.append(
            "Prototype checklist is incomplete: "
            + ", ".join(action.get("label", action.get("id", "action")) for action in missing_actions)
            + "."
        )

    eligible = not blockers
    return {
        "profile_id": profile.get("id"),
        "profile_label": profile.get("label"),
        "option_id": option.get("id"),
        "option_label": option.get("label"),
        "option_description": option.get("description", ""),
        "option_assumptions": {
            "estimated_cost_cad": estimated_cost,
            "estimated_work_hours": estimated_hours,
            "spares_required": spares_required,
        },
        "estimated_cost_cad": estimated_cost,
        "estimated_work_hours": estimated_hours,
        "spares_required": spares_required,
        "available_spares": available_spares,
        "hours_available": hours_available,
        "reserve_before_cad": reserve_before,
        "reserve_floor_cad": reserve_floor,
        "reserve_used_cad": reserve_used,
        "spend_outside_reserve_cad": spend_outside_reserve,
        "planned_transfer_cad": planned_transfer,
        "funding_capacity_cad": funding_capacity,
        "cap_headroom_cad": cap_headroom,
        "transfer_required_cad": transfer_required,
        "projected_reserve_cad": projected_reserve,
        "net_cap_change_cad": net_cap_change,
        "required_actions": required_actions,
        "missing_actions": missing_actions,
        "blockers": blockers,
        "status": "REVIEW_ELIGIBLE" if eligible else "HOLD",
        "eligible_for_review": eligible,
        "case_inputs": {
            "available_spares": available_spares,
            "hours_available": hours_available,
            "reserve_before": reserve_before,
            "reserve_floor": reserve_floor,
            "planned_transfer": planned_transfer,
            "funding_capacity": funding_capacity,
            "cap_headroom": cap_headroom,
            "funding_source": str(case_inputs.get("funding_source") or ""),
            "completed_actions": sorted(completed),
            "option_overrides": {
                str(option_id): {
                    "estimated_cost_cad": estimated_cost,
                    "estimated_work_hours": estimated_hours,
                    "spares_required": spares_required,
                }
            },
        },
        "disclaimer": (
            "Prototype planning result only. Human engineering review remains required; "
            "this does not certify, release, or predict the safety of a vehicle."
        ),
    }


def compare_options(profile, case_inputs):
    """Return every model option, sorted with eligible lower-cost plans first."""
    results = [evaluate_option(profile, option["id"], case_inputs) for option in profile.get("options", [])]
    return sorted(
        results,
        key=lambda result: (
            not result["eligible_for_review"],
            len(result["blockers"]),
            result["estimated_cost_cad"],
        ),
    )
