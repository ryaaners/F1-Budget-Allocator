"""Pure-rule tests for the editable prototype repair planner."""

import unittest
from unittest.mock import Mock, patch

import safety_engine


class PrototypeSafetyEngineTests(unittest.TestCase):
    def setUp(self):
        self.profile = safety_engine.profile_for("suspension_steering")
        self.option_id = "assumed_spare_replacement"
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


if __name__ == "__main__":
    unittest.main()
