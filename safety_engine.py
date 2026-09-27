"""Pure, assumption-led planning logic for the Track 3 prototype.

This module deliberately models an educational planning gate, not an engineering
repair procedure or a vehicle release decision.  Historical replay data never
flows into the calculations except as a user-selected source reference.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

from career_data import CATEGORIES


ASSUMPTIONS_PATH = Path(__file__).with_name("data") / "safety_planning_assumptions.json"
RULES_ENGINE_VERSION = "1.1"


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


def catalog_identity(catalog):
    """Return a stable provenance fingerprint for one validated catalog.

    The fingerprint identifies the exact editable assumptions document used to
    create a record.  It is not a claim that those assumptions are verified
    engineering or team data.
    """
    try:
        canonical = json.dumps(
            catalog, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise AssumptionError(
            f"The local prototype assumptions cannot be fingerprinted: {error}"
        ) from error
    return {
        "model_name": str(catalog.get("model_name") or "Unnamed prototype assumptions"),
        "version": str(catalog.get("version") or "unversioned"),
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "rules_engine_version": RULES_ENGINE_VERSION,
    }


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


def frozen_profile_snapshot(profile, option_id):
    """Freeze just the selected profile/option basis for an audit record.

    Future edits to the local catalog cannot silently reinterpret a saved
    decision.  The frozen data remains a transparent prototype assumption,
    never a real repair instruction.
    """
    option = option_for(profile, option_id)
    keys = (
        "id", "label", "description", "ledger_category",
        "default_available_spares", "default_hours_to_next_session",
        "default_reserve_floor_cad",
    )
    frozen = {key: copy.deepcopy(profile.get(key)) for key in keys}
    frozen["options"] = [copy.deepcopy(option)]
    try:
        validate_assumptions({"profiles": [frozen]})
    except AssumptionError as error:
        raise ValueError(f"Cannot freeze an invalid prototype rule basis: {error}") from error
    return frozen


def profile_from_frozen_snapshot(snapshot, profile_id, option_id):
    """Validate and restore one previously frozen selected-option profile."""
    if not isinstance(snapshot, dict):
        raise ValueError("The saved prototype rule snapshot is missing or invalid.")
    frozen = copy.deepcopy(snapshot)
    try:
        validate_assumptions({"profiles": [frozen]})
    except AssumptionError as error:
        raise ValueError(f"The saved prototype rule snapshot is invalid: {error}") from error
    profile = profile_for(str(profile_id or ""), [frozen])
    option_for(profile, str(option_id or ""))
    return profile


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
            if not isinstance(option.get("can_request_review"), bool):
                raise AssumptionError(
                    f"Response option '{option_id}' needs can_request_review set to true or false."
                )
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
            if option["can_request_review"] and not actions:
                raise AssumptionError(
                    f"Review-request option '{option_id}' needs at least one human-record action."
                )
        ledger_category = profile.get("ledger_category")
        if ledger_category not in CATEGORIES:
            raise AssumptionError(
                f"Planning profile '{profile_id}' needs a valid local ledger category."
            )
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
    gaps = []

    def add_gap(code, label, category, required=None, available=None, shortfall=None, detail=None):
        gap = {"code": code, "label": label, "category": category}
        if required is not None:
            gap["required"] = required
        if available is not None:
            gap["available"] = available
        if shortfall is not None:
            gap["shortfall"] = shortfall
        if detail is not None:
            gap["detail"] = detail
        gaps.append(gap)

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
    for problem in input_problems:
        add_gap("INVALID_INPUT", problem, "input", detail=problem)
    for problem in (cost_problem, hours_problem, spare_problem):
        if problem:
            blockers.append(f"Editable option assumption problem: {problem}")
            add_gap(
                "INVALID_OPTION_ASSUMPTION", f"Editable option assumption problem: {problem}",
                "assumption", detail=problem,
            )
    if not option.get("can_request_review", False):
        blockers.append("This prototype option is deliberately a hold-only path.")
        add_gap(
            "HOLD_ONLY", "This prototype option is deliberately a hold-only path.",
            "workflow",
        )
    if option.get("can_request_review", False) and estimated_cost <= 0:
        blockers.append("A review-request option needs a positive editable modelled cost.")
        add_gap(
            "NONPOSITIVE_COST", "A review-request option needs a positive editable modelled cost.",
            "assumption", required="positive", available=estimated_cost,
        )
    if available_spares < spares_required:
        shortfall = spares_required - available_spares
        blockers.append(f"Prototype spare assumption is short by {shortfall}.")
        add_gap(
            "SPARES_SHORT", "Prototype spare assumption is short.", "spares",
            required=spares_required, available=available_spares, shortfall=shortfall,
        )
    if hours_available < estimated_hours:
        shortfall = estimated_hours - hours_available
        blockers.append(f"Prototype work-window assumption is short by {shortfall:.1f} hours.")
        add_gap(
            "WORK_WINDOW_SHORT", "Prototype work-window assumption is short.", "time",
            required=estimated_hours, available=hours_available, shortfall=shortfall,
        )
    if planned_transfer < transfer_required:
        shortfall = transfer_required - planned_transfer
        blockers.append(
            f"Planned funding transfer is short by CAD ${shortfall:,.0f} "
            "to protect the selected reserve floor."
        )
        add_gap(
            "TRANSFER_SHORT", "Planned funding transfer is short for the selected reserve floor.",
            "reserve", required=transfer_required, available=planned_transfer, shortfall=shortfall,
        )
    elif planned_transfer > transfer_required + 0.01:
        excess = planned_transfer - transfer_required
        blockers.append(
            f"Planned funding transfer exceeds the calculated reserve-floor need by CAD ${excess:,.0f}. "
            "Increase the selected reserve floor if that extra local reserve is intentional."
        )
        add_gap(
            "TRANSFER_EXCESS", "Planned transfer exceeds the calculated reserve-floor need.",
            "reserve", required=transfer_required, available=planned_transfer, shortfall=excess,
            detail="Increase the selected local reserve floor to record an intentional larger reserve target.",
        )
    if planned_transfer > funding_capacity:
        shortfall = planned_transfer - funding_capacity
        blockers.append(
            f"Planned funding transfer exceeds the selected source capacity by CAD ${shortfall:,.0f}."
        )
        add_gap(
            "SOURCE_CAPACITY_SHORT", "Planned funding transfer exceeds selected source capacity.",
            "funding_source", required=planned_transfer, available=funding_capacity, shortfall=shortfall,
        )
    if projected_reserve < reserve_floor:
        shortfall = reserve_floor - projected_reserve
        blockers.append(f"Projected reserve is CAD ${shortfall:,.0f} below the selected floor.")
        add_gap(
            "RESERVE_FLOOR_SHORT", "Projected reserve is below the selected floor.", "reserve",
            required=reserve_floor, available=projected_reserve, shortfall=shortfall,
        )
    if net_cap_change > cap_headroom:
        shortfall = net_cap_change - cap_headroom
        blockers.append(
            f"Local cap headroom is short by CAD ${shortfall:,.0f} after the selected transfer."
        )
        add_gap(
            "CAP_HEADROOM_SHORT", "Local cap headroom is short after the selected transfer.",
            "cap", required=net_cap_change, available=cap_headroom, shortfall=shortfall,
        )
    if missing_actions:
        labels = [action.get("label", action.get("id", "action")) for action in missing_actions]
        blockers.append("Prototype checklist is incomplete: " + ", ".join(labels) + ".")
        add_gap(
            "CHECKLIST_INCOMPLETE", "Prototype human-record checklist is incomplete.", "checklist",
            required=len(required_actions), available=len(required_actions) - len(missing_actions),
            shortfall=len(missing_actions), detail=", ".join(labels),
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
        "gaps": gaps,
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


def evaluate_resource_contention(cases, shared_envelope):
    """Evaluate aggregate fictional resource demand for two or more prototype cases.

    ``cases`` is a list of dictionaries with a selected ``profile`` object and
    ``option_id``. A case may optionally supply ``case_id``, ``case_label``,
    and ``case_inputs`` containing the same ``option_overrides`` shape used by
    :func:`evaluate_option`. ``shared_envelope`` contains these editable,
    generic shared inputs:

    ``available_spares``, ``hours_available``, ``reserve_before``,
    ``reserve_floor``, ``planned_transfer``, ``funding_capacity``, and
    ``cap_headroom``.

    This is deliberately a read-only *prototype resource-contention* check.
    It aggregates transparent fictional costs, hours, spares, reserve, source,
    and cap assumptions; it does not determine safety, authorise vehicle use,
    or replace human engineering judgement.
    """
    case_rows = []
    gaps = []
    blockers = []

    def add_gap(code, label, category, required=None, available=None, shortfall=None, detail=None):
        gap = {"code": code, "label": label, "category": category}
        if required is not None:
            gap["required"] = required
        if available is not None:
            gap["available"] = available
        if shortfall is not None:
            gap["shortfall"] = shortfall
        if detail is not None:
            gap["detail"] = detail
        gaps.append(gap)

    if not isinstance(cases, (list, tuple)):
        case_items = []
        blockers.append("Selected prototype cases must be a list containing at least two cases.")
        add_gap(
            "INVALID_CASE_COLLECTION", "Selected prototype cases must be a list containing at least two cases.",
            "input", detail="Provide at least two selected prototype cases.",
        )
    else:
        # Copy the outer sequence only: individual inputs are read but never
        # mutated, so callers can safely retain them for their own UI state.
        case_items = list(cases)
        if len(case_items) < 2:
            blockers.append("At least two selected prototype cases are required for a contention check.")
            add_gap(
                "CASE_COUNT_SHORT", "At least two selected prototype cases are required.",
                "input", required=2, available=len(case_items), shortfall=2 - len(case_items),
            )

    envelope_is_mapping = isinstance(shared_envelope, dict)
    envelope = shared_envelope if envelope_is_mapping else {}
    if not envelope_is_mapping:
        blockers.append("Shared prototype resource envelope must be an object.")
        add_gap(
            "INVALID_SHARED_ENVELOPE", "Shared prototype resource envelope must be an object.",
            "input", detail="Provide editable generic shared resource values.",
        )

    normalised_envelope = {}

    def shared_value(key, label, whole_number=False):
        value, problem = _finite_nonnegative(envelope.get(key), label, whole_number)
        if problem:
            blockers.append(problem)
            add_gap("INVALID_SHARED_INPUT", problem, "input", detail=problem)
        normalised_envelope[key] = int(value) if whole_number else value
        return normalised_envelope[key]

    available_spares = shared_value("available_spares", "Shared available spares", whole_number=True)
    hours_available = shared_value("hours_available", "Shared available work hours")
    reserve_before = shared_value("reserve_before", "Shared reserve before")
    reserve_floor = shared_value("reserve_floor", "Shared reserve floor")
    planned_transfer = shared_value("planned_transfer", "Shared planned transfer")
    funding_capacity = shared_value("funding_capacity", "Shared source capacity")
    cap_headroom = shared_value("cap_headroom", "Shared local cap headroom")

    for index, case in enumerate(case_items, start=1):
        default_case_id = f"case-{index}"
        if not isinstance(case, dict):
            problem = "Selected prototype case must be an object with a profile and option id."
            row = {
                "case_index": index,
                "case_id": default_case_id,
                "case_label": default_case_id,
                "state": "CASE_HOLD",
                "included_in_aggregate": False,
                "estimated_cost_cad": None,
                "estimated_work_hours": None,
                "spares_required": None,
                "blockers": [problem],
                "gaps": [{
                    "code": "MALFORMED_CASE", "label": problem, "category": "case", "detail": problem,
                }],
            }
            gaps.append({
                **row["gaps"][0], "scope": "case", "case_id": default_case_id,
            })
            case_rows.append(row)
            continue

        case_id = str(case.get("case_id") or default_case_id)
        case_label = str(case.get("case_label") or case_id)
        row = {
            "case_index": index,
            "case_id": case_id,
            "case_label": case_label,
            "state": "CASE_HOLD",
            "included_in_aggregate": False,
            "estimated_cost_cad": None,
            "estimated_work_hours": None,
            "spares_required": None,
            "blockers": [],
            "gaps": [],
        }

        def add_case_gap(code, label, category="case", required=None, available=None, shortfall=None, detail=None):
            gap = {"code": code, "label": label, "category": category}
            if required is not None:
                gap["required"] = required
            if available is not None:
                gap["available"] = available
            if shortfall is not None:
                gap["shortfall"] = shortfall
            if detail is not None:
                gap["detail"] = detail
            row["gaps"].append(gap)
            row["blockers"].append(label)
            gaps.append({**gap, "scope": "case", "case_id": case_id})

        profile = case.get("profile")
        option_id = case.get("option_id")
        if not isinstance(profile, dict) or not isinstance(option_id, str) or not option_id.strip():
            add_case_gap(
                "MALFORMED_CASE",
                "Selected prototype case needs a valid profile object and non-empty option id.",
                detail="Profile and option id are required for a resource contention case.",
            )
            case_rows.append(row)
            continue

        # Validate a private copy so an unexpectedly malformed profile never
        # crashes this aggregate evaluator or changes the caller's object.
        try:
            profile_copy = copy.deepcopy(profile)
            validate_assumptions({"profiles": [profile_copy]})
            option = option_for(profile, option_id)
        except (AssumptionError, ValueError, TypeError, AttributeError, copy.Error) as error:
            add_case_gap(
                "MALFORMED_CASE",
                "Selected prototype case has an invalid profile or option.",
                detail=str(error),
            )
            case_rows.append(row)
            continue

        row.update({
            "profile_id": profile.get("id"),
            "profile_label": profile.get("label"),
            "option_id": option.get("id"),
            "option_label": option.get("label"),
        })
        if not option.get("can_request_review", False):
            add_case_gap(
                "HOLD_ONLY_OPTION",
                "The selected prototype option is deliberately hold-only for this resource contention model.",
                category="workflow",
            )

        case_inputs_valid = True
        if "case_inputs" in case:
            case_inputs = case.get("case_inputs")
            if not isinstance(case_inputs, dict):
                add_case_gap(
                    "MALFORMED_CASE_INPUTS",
                    "Case inputs must be an object when supplied.",
                    detail="Use the option_overrides mapping shape from the single-case prototype model.",
                )
                case_inputs = {}
                case_inputs_valid = False
        elif "option_overrides" in case:
            supplied_overrides = case.get("option_overrides")
            if not isinstance(supplied_overrides, dict):
                add_case_gap(
                    "MALFORMED_CASE_INPUTS",
                    "Case option overrides must be an object when supplied.",
                    detail="Use a mapping keyed by the selected option id.",
                )
                case_inputs = {}
                case_inputs_valid = False
            else:
                case_inputs = {"option_overrides": supplied_overrides}
        else:
            case_inputs = {}

        supplied_overrides = case_inputs.get("option_overrides")
        if supplied_overrides is not None:
            if not isinstance(supplied_overrides, dict):
                add_case_gap(
                    "MALFORMED_CASE_INPUTS",
                    "Case option overrides must be an object when supplied.",
                    detail="Use a mapping keyed by the selected option id.",
                )
                case_inputs_valid = False
            elif option_id in supplied_overrides and not isinstance(supplied_overrides[option_id], dict):
                add_case_gap(
                    "MALFORMED_CASE_INPUTS",
                    "Selected option override must be an object when supplied.",
                    detail="Use estimated_cost_cad, estimated_work_hours, and spares_required fields.",
                )
                case_inputs_valid = False

        override = _option_override(case_inputs, option_id)
        cost_label = "Editable case cost" if "estimated_cost_cad" in override else "Assumed case cost"
        hours_label = "Editable case work hours" if "estimated_work_hours" in override else "Assumed case work hours"
        spares_label = "Editable case spare requirement" if "spares_required" in override else "Assumed case spare requirement"
        cost, cost_problem = _assumed_nonnegative(
            override.get("estimated_cost_cad", option.get("estimated_cost_cad")), cost_label
        )
        hours, hours_problem = _assumed_nonnegative(
            override.get("estimated_work_hours", option.get("estimated_work_hours")), hours_label
        )
        spare_value, spares_problem = _finite_nonnegative(
            override.get("spares_required", option.get("spares_required")), spares_label, whole_number=True
        )
        spares = int(spare_value)
        row.update({
            "estimated_cost_cad": cost,
            "estimated_work_hours": hours,
            "spares_required": spares,
        })
        for problem in (cost_problem, hours_problem, spares_problem):
            if problem:
                add_case_gap(
                    "INVALID_CASE_ASSUMPTION",
                    f"Selected prototype case assumption problem: {problem}",
                    category="assumption", detail=problem,
                )
        if option.get("can_request_review", False) and cost <= 0:
            add_case_gap(
                "NONPOSITIVE_CASE_COST",
                "A resource contention case needs a positive editable modelled cost.",
                category="assumption", required="positive", available=cost,
            )
        # A hold-only option still has known fictional demand and is included
        # in the aggregate. Malformed assumptions are deliberately excluded
        # instead of being silently treated as a zero-cost/zero-time case.
        assumptions_are_usable = (
            case_inputs_valid
            and not any((cost_problem, hours_problem, spares_problem))
            and cost > 0
        )
        if assumptions_are_usable:
            row["included_in_aggregate"] = True
        else:
            row.update({
                "estimated_cost_cad": None,
                "estimated_work_hours": None,
                "spares_required": None,
            })
        if not row["blockers"]:
            row["state"] = "RESOURCE_CONTRIBUTES"
        case_rows.append(row)

    case_id_counts = {}
    for row in case_rows:
        case_id_counts[row["case_id"]] = case_id_counts.get(row["case_id"], 0) + 1
    for row in case_rows:
        if case_id_counts[row["case_id"]] <= 1:
            continue
        label = "Each selected prototype case needs a unique case id."
        if not any(gap.get("code") == "DUPLICATE_CASE_ID" for gap in row["gaps"]):
            gap = {
                "code": "DUPLICATE_CASE_ID", "label": label, "category": "case",
                "detail": f"Duplicate case id: {row['case_id']}",
            }
            row["gaps"].append(gap)
            row["blockers"].append(label)
            gaps.append({**gap, "scope": "case", "case_id": row["case_id"]})
        row["state"] = "CASE_HOLD"

    total_cost = sum(
        float(row["estimated_cost_cad"])
        for row in case_rows if row.get("included_in_aggregate")
    )
    total_hours = sum(
        float(row["estimated_work_hours"])
        for row in case_rows if row.get("included_in_aggregate")
    )
    total_spares = sum(
        int(row["spares_required"])
        for row in case_rows if row.get("included_in_aggregate")
    )
    transfer_required = max(0.0, total_cost + reserve_floor - reserve_before)
    projected_reserve = reserve_before + planned_transfer - total_cost
    net_cap_change = total_cost - planned_transfer
    resource_checks_apply = bool(case_rows)

    if any(row["state"] != "RESOURCE_CONTRIBUTES" for row in case_rows):
        blockers.append("One or more selected prototype cases is invalid or uses a hold-only option.")
        add_gap(
            "CASE_NOT_RESOURCE_READY",
            "One or more selected prototype cases is invalid or uses a hold-only option.",
            "case", required=len(case_rows),
            available=sum(row["state"] == "RESOURCE_CONTRIBUTES" for row in case_rows),
            shortfall=sum(row["state"] != "RESOURCE_CONTRIBUTES" for row in case_rows),
        )

    if resource_checks_apply:
        if available_spares < total_spares:
            shortfall = total_spares - available_spares
            label = "Shared prototype spare assumption is short across the selected cases."
            blockers.append(f"{label} Short by {shortfall}.")
            add_gap(
                "SHARED_SPARES_SHORT", label, "spares", required=total_spares,
                available=available_spares, shortfall=shortfall,
            )
        if hours_available < total_hours:
            shortfall = total_hours - hours_available
            label = "Shared prototype work-hour assumption is short across the selected cases."
            blockers.append(f"{label} Short by {shortfall:.1f} hours.")
            add_gap(
                "SHARED_WORK_HOURS_SHORT", label, "time", required=total_hours,
                available=hours_available, shortfall=shortfall,
            )
        if planned_transfer < transfer_required:
            shortfall = transfer_required - planned_transfer
            label = "Shared planned transfer is short for the selected reserve floor."
            blockers.append(f"{label} Short by CAD ${shortfall:,.0f}.")
            add_gap(
                "SHARED_TRANSFER_SHORT", label, "reserve", required=transfer_required,
                available=planned_transfer, shortfall=shortfall,
            )
        elif planned_transfer > transfer_required + 0.01:
            excess = planned_transfer - transfer_required
            label = "Shared planned transfer exceeds the calculated reserve-floor need."
            blockers.append(f"{label} Excess CAD ${excess:,.0f}.")
            add_gap(
                "SHARED_TRANSFER_EXCESS", label, "reserve", required=transfer_required,
                available=planned_transfer, shortfall=excess,
                detail="Increase the shared reserve floor to make an intentional larger reserve explicit.",
            )
        if planned_transfer > funding_capacity:
            shortfall = planned_transfer - funding_capacity
            label = "Shared planned transfer exceeds the selected source capacity."
            blockers.append(f"{label} Short by CAD ${shortfall:,.0f}.")
            add_gap(
                "SHARED_SOURCE_CAPACITY_SHORT", label, "funding_source", required=planned_transfer,
                available=funding_capacity, shortfall=shortfall,
            )
        if projected_reserve < reserve_floor:
            shortfall = reserve_floor - projected_reserve
            label = "Shared projected reserve is below the selected floor."
            blockers.append(f"{label} Short by CAD ${shortfall:,.0f}.")
            add_gap(
                "SHARED_RESERVE_FLOOR_SHORT", label, "reserve", required=reserve_floor,
                available=projected_reserve, shortfall=shortfall,
            )
        if net_cap_change > cap_headroom:
            shortfall = net_cap_change - cap_headroom
            label = "Shared local cap headroom is short after the selected transfer."
            blockers.append(f"{label} Short by CAD ${shortfall:,.0f}.")
            add_gap(
                "SHARED_CAP_HEADROOM_SHORT", label, "cap", required=net_cap_change,
                available=cap_headroom, shortfall=shortfall,
            )

    feasible = not blockers
    totals = {
        "case_count": len(case_rows),
        "included_in_aggregate_case_count": sum(
            bool(row.get("included_in_aggregate")) for row in case_rows
        ),
        "resource_contributing_case_count": sum(
            row["state"] == "RESOURCE_CONTRIBUTES" for row in case_rows
        ),
        "held_case_count": sum(row["state"] != "RESOURCE_CONTRIBUTES" for row in case_rows),
        "estimated_cost_cad": total_cost,
        "estimated_work_hours": total_hours,
        "spares_required": total_spares,
        "available_spares": available_spares,
        "hours_available": hours_available,
        "reserve_before_cad": reserve_before,
        "reserve_floor_cad": reserve_floor,
        "planned_transfer_cad": planned_transfer,
        "funding_capacity_cad": funding_capacity,
        "cap_headroom_cad": cap_headroom,
        "transfer_required_cad": transfer_required,
        "projected_reserve_cad": projected_reserve,
        "net_cap_change_cad": net_cap_change,
    }
    return {
        "schema_version": "1.0",
        "scope": "prototype_resource_contention_only",
        "status": "RESOURCE_FEASIBLE" if feasible else "RESOURCE_HOLD",
        "resource_feasible": feasible,
        "case_rows": case_rows,
        "totals": totals,
        "shared_envelope": normalised_envelope,
        "blockers": blockers,
        "gaps": gaps,
        "disclaimer": (
            "Prototype resource-contention result only. It does not determine safety, authorise vehicle use, "
            "or replace human engineering judgement."
        ),
    }
