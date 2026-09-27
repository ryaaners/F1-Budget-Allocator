"""Pure-rule tests for the editable prototype repair planner."""

import copy
import unittest
from unittest.mock import Mock, patch

import safety_engine


class PrototypeSafetyEngineTests(unittest.TestCase):
    def setUp(self):
        self.profile = safety_engine.profile_for("suspension_steering")
        self.option_id = "assumed_spare_replacement"
        self.bodywork_profile = safety_engine.profile_for("bodywork_structures")
        self.bodywork_option_id = "assumed_replacement_plan"
        self.complete_actions = [
            action["id"]
            for action in safety_engine.option_for(self.profile, self.option_id)["required_actions"]
        ]

    def inputs(self, **overrides):
        values = {
            "available_spares": 1,
            "hours_available": 10,
            "reserve_before": 5_000_000,
            "reserve_floor": 1_000_000,
            "planned_transfer": 0,
            "funding_capacity": 10_000_000,
            "cap_headroom": 10_000_000,
            "completed_actions": self.complete_actions,
        }
        values.update(overrides)
        return values

    def test_complete_viable_path_is_review_eligible_not_a_release(self):
        result = safety_engine.evaluate_option(self.profile, self.option_id, self.inputs())

        self.assertEqual(result["status"], "REVIEW_ELIGIBLE")
        self.assertTrue(result["eligible_for_review"])
        self.assertEqual(result["blockers"], [])
        self.assertIn("does not certify", result["disclaimer"])

    def test_hold_only_option_is_never_review_eligible(self):
        hold_option = "hold_for_inspection"
        actions = [
            action["id"]
            for action in safety_engine.option_for(self.profile, hold_option)["required_actions"]
        ]

        result = safety_engine.evaluate_option(
            self.profile, hold_option, self.inputs(completed_actions=actions)
        )

        self.assertEqual(result["status"], "HOLD")
        self.assertIn("hold-only", " ".join(result["blockers"]))

    def test_zero_spares_and_time_hold_the_plan(self):
        result = safety_engine.evaluate_option(
            self.profile, self.option_id, self.inputs(available_spares=0, hours_available=0)
        )

        self.assertEqual(result["status"], "HOLD")
        joined = " ".join(result["blockers"])
        self.assertIn("spare assumption is short", joined)
        self.assertIn("work-window assumption is short", joined)
        codes = {gap["code"] for gap in result["gaps"]}
        self.assertIn("SPARES_SHORT", codes)
        self.assertIn("WORK_WINDOW_SHORT", codes)

    def test_reserve_floor_and_transfer_shortfall_hold_the_plan(self):
        result = safety_engine.evaluate_option(
            self.profile,
            self.option_id,
            self.inputs(reserve_before=0, reserve_floor=1_000_000, planned_transfer=1_000_000),
        )

        self.assertEqual(result["transfer_required_cad"], 2_500_000)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("Planned funding transfer is short", " ".join(result["blockers"]))

    def test_cap_headroom_and_source_capacity_can_hold_the_plan(self):
        result = safety_engine.evaluate_option(
            self.profile,
            self.option_id,
            self.inputs(cap_headroom=1_000_000, funding_capacity=0, planned_transfer=1),
        )

        self.assertEqual(result["status"], "HOLD")
        joined = " ".join(result["blockers"])
        self.assertIn("selected source capacity", joined)
        self.assertIn("Local cap headroom is short", joined)

    def test_incomplete_human_record_checklist_holds_the_plan(self):
        result = safety_engine.evaluate_option(
            self.profile, self.option_id, self.inputs(completed_actions=[])
        )

        self.assertEqual(result["status"], "HOLD")
        self.assertIn("Prototype checklist is incomplete", " ".join(result["blockers"]))

    def test_invalid_numeric_inputs_never_crash_or_become_eligible(self):
        result = safety_engine.evaluate_option(
            self.profile,
            self.option_id,
            self.inputs(
                available_spares="inf",
                hours_available="nan",
                reserve_before=-1,
                reserve_floor=float("inf"),
                planned_transfer="not a number",
                funding_capacity=-5,
                cap_headroom=float("nan"),
            ),
        )

        self.assertEqual(result["status"], "HOLD")
        joined = " ".join(result["blockers"])
        self.assertIn("Available spares must be", joined)
        self.assertIn("Hours available must be", joined)
        self.assertIn("Current crash reserve must be", joined)

    def test_non_mapping_inputs_do_not_crash(self):
        result = safety_engine.evaluate_option(self.profile, self.option_id, None)

        self.assertEqual(result["status"], "HOLD")
        self.assertTrue(result["blockers"])

    def test_malformed_editable_catalog_is_rejected_with_a_contained_error(self):
        with self.assertRaisesRegex(safety_engine.AssumptionError, "at least one planning profile"):
            safety_engine.validate_assumptions({"profiles": []})
        with self.assertRaisesRegex(safety_engine.AssumptionError, "at least one response option"):
            safety_engine.validate_assumptions({
                "profiles": [{
                    "id": "broken",
                    "label": "Broken",
                    "default_available_spares": 0,
                    "default_hours_to_next_session": 0,
                    "default_reserve_floor_cad": 0,
                    "options": [],
                }]
            })

    def test_non_utf8_catalog_error_is_contained(self):
        fake_path = Mock()
        fake_path.open.side_effect = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

        with patch.object(safety_engine, "ASSUMPTIONS_PATH", fake_path):
            with self.assertRaisesRegex(safety_engine.AssumptionError, "Could not open"):
                safety_engine.load_assumptions()

    def test_selected_option_override_is_snapshot_ready_and_does_not_apply_to_other_options(self):
        overridden = self.inputs(option_overrides={
            self.option_id: {
                "estimated_cost_cad": 2_000_000,
                "estimated_work_hours": 9,
                "spares_required": 2,
            }
        })

        selected = safety_engine.evaluate_option(self.profile, self.option_id, overridden)
        other = safety_engine.evaluate_option(self.profile, "hold_for_inspection", overridden)

        self.assertEqual(selected["estimated_cost_cad"], 2_000_000)
        self.assertEqual(selected["estimated_work_hours"], 9)
        self.assertEqual(selected["spares_required"], 2)
        self.assertEqual(other["estimated_cost_cad"], 250_000)
        self.assertEqual(selected["case_inputs"]["option_overrides"][self.option_id]["spares_required"], 2)

    def test_excess_transfer_is_held_until_the_explicit_reserve_floor_is_updated(self):
        result = safety_engine.evaluate_option(
            self.profile, self.option_id, self.inputs(planned_transfer=2_000_000)
        )

        self.assertEqual(result["status"], "HOLD")
        self.assertIn("TRANSFER_EXCESS", {gap["code"] for gap in result["gaps"]})
        self.assertIn("exceeds the calculated reserve-floor need", " ".join(result["blockers"]))

    def test_catalog_identity_is_stable_for_key_order_and_changes_for_semantic_edits(self):
        catalog = safety_engine.load_assumptions()
        reordered = {key: copy.deepcopy(catalog[key]) for key in reversed(list(catalog))}
        baseline = safety_engine.catalog_identity(catalog)

        self.assertEqual(baseline["sha256"], safety_engine.catalog_identity(reordered)["sha256"])
        changed = copy.deepcopy(catalog)
        changed["profiles"][0]["options"][1]["estimated_cost_cad"] += 1
        self.assertNotEqual(baseline["sha256"], safety_engine.catalog_identity(changed)["sha256"])

    def test_invalid_boolean_and_ledger_category_are_rejected_before_a_hold_only_path_can_flip(self):
        string_boolean = copy.deepcopy(safety_engine.load_assumptions())
        string_boolean["profiles"][0]["options"][0]["can_request_review"] = "false"
        with self.assertRaisesRegex(safety_engine.AssumptionError, "true or false"):
            safety_engine.validate_assumptions(string_boolean)

        bad_category = copy.deepcopy(safety_engine.load_assumptions())
        bad_category["profiles"][0]["ledger_category"] = "Not a local category"
        with self.assertRaisesRegex(safety_engine.AssumptionError, "valid local ledger category"):
            safety_engine.validate_assumptions(bad_category)

    def test_frozen_profile_snapshot_contains_only_the_selected_valid_option(self):
        frozen = safety_engine.frozen_profile_snapshot(self.profile, self.option_id)
        restored = safety_engine.profile_from_frozen_snapshot(
            frozen, self.profile["id"], self.option_id
        )

        self.assertEqual([option["id"] for option in frozen["options"]], [self.option_id])
        self.assertEqual(restored["ledger_category"], self.profile["ledger_category"])

    def resource_cases(self):
        return [
            {
                "case_id": "suspension-example",
                "case_label": "Fictional suspension example",
                "profile": self.profile,
                "option_id": self.option_id,
            },
            {
                "case_id": "bodywork-example",
                "case_label": "Fictional bodywork example",
                "profile": self.bodywork_profile,
                "option_id": self.bodywork_option_id,
            },
        ]

    def resource_envelope(self, **overrides):
        envelope = {
            "available_spares": 2,
            "hours_available": 15,
            "reserve_before": 5_000_000,
            "reserve_floor": 1_000_000,
            "planned_transfer": 0,
            "funding_capacity": 10_000_000,
            "cap_headroom": 10_000_000,
        }
        envelope.update(overrides)
        return envelope

    def test_two_review_capable_cases_can_be_resource_feasible(self):
        result = safety_engine.evaluate_resource_contention(
            self.resource_cases(), self.resource_envelope()
        )

        self.assertEqual(result["scope"], "prototype_resource_contention_only")
        self.assertEqual(result["status"], "RESOURCE_FEASIBLE")
        self.assertTrue(result["resource_feasible"])
        self.assertEqual(result["totals"]["case_count"], 2)
        self.assertEqual(result["totals"]["estimated_cost_cad"], 2_400_000)
        self.assertEqual(result["totals"]["estimated_work_hours"], 15)
        self.assertEqual(result["totals"]["spares_required"], 2)
        self.assertEqual(
            [row["state"] for row in result["case_rows"]],
            ["RESOURCE_CONTRIBUTES", "RESOURCE_CONTRIBUTES"],
        )
        self.assertEqual(result["gaps"], [])
        self.assertIn("does not determine safety", result["disclaimer"])

    def test_shared_spare_time_reserve_and_source_conflicts_hold_the_cases(self):
        result = safety_engine.evaluate_resource_contention(
            self.resource_cases(),
            self.resource_envelope(
                available_spares=1,
                hours_available=10,
                reserve_before=0,
                reserve_floor=1_000_000,
                planned_transfer=1_000_000,
                funding_capacity=500_000,
                cap_headroom=1_000_000,
            ),
        )

        self.assertEqual(result["status"], "RESOURCE_HOLD")
        self.assertFalse(result["resource_feasible"])
        codes = {gap["code"] for gap in result["gaps"]}
        self.assertTrue({
            "SHARED_SPARES_SHORT",
            "SHARED_WORK_HOURS_SHORT",
            "SHARED_TRANSFER_SHORT",
            "SHARED_SOURCE_CAPACITY_SHORT",
            "SHARED_RESERVE_FLOOR_SHORT",
            "SHARED_CAP_HEADROOM_SHORT",
        }.issubset(codes))
        self.assertEqual(result["totals"]["transfer_required_cad"], 3_400_000)

    def test_hold_only_and_malformed_cases_are_contained_as_resource_hold(self):
        result = safety_engine.evaluate_resource_contention(
            [
                {
                    "case_id": "hold-only",
                    "profile": self.profile,
                    "option_id": "hold_for_inspection",
                },
                {"case_id": "broken", "profile": {"id": "broken"}, "option_id": "missing"},
            ],
            self.resource_envelope(),
        )

        self.assertEqual(result["status"], "RESOURCE_HOLD")
        self.assertEqual(result["totals"]["held_case_count"], 2)
        self.assertIn("CASE_NOT_RESOURCE_READY", {gap["code"] for gap in result["gaps"]})
        row_codes = {gap["code"] for row in result["case_rows"] for gap in row["gaps"]}
        self.assertIn("HOLD_ONLY_OPTION", row_codes)
        self.assertIn("MALFORMED_CASE", row_codes)

    def test_resource_contention_never_mutates_case_or_envelope_inputs(self):
        cases = self.resource_cases()
        cases[0]["case_inputs"] = {
            "option_overrides": {
                self.option_id: {
                    "estimated_cost_cad": 1_500_000,
                    "estimated_work_hours": 8,
                    "spares_required": 1,
                }
            }
        }
        envelope = self.resource_envelope()
        original_cases = copy.deepcopy(cases)
        original_envelope = copy.deepcopy(envelope)

        safety_engine.evaluate_resource_contention(cases, envelope)

        self.assertEqual(cases, original_cases)
        self.assertEqual(envelope, original_envelope)


if __name__ == "__main__":
    unittest.main()
