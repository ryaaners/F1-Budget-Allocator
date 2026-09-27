"""Persistence and finance-boundary tests for prototype planning records."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

import career_engine as season
import safety_engine


class PrototypeSafetyDecisionTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        season.migrate(self.con)
        allocations = {category: 10_000_000 for category in season.CATEGORIES}
        season.create_career(
            self.con, next(iter(season.TEAMS)), allocations, crash_reserve_target=5_000_000
        )
        self.profile = safety_engine.profile_for("suspension_steering")
        self.option_id = "assumed_spare_replacement"

    def tearDown(self):
        self.con.close()

    def complete_inputs(self, **overrides):
        actions = [
            action["id"]
            for action in safety_engine.option_for(self.profile, self.option_id)["required_actions"]
        ]
        values = {
            "available_spares": 1,
            "hours_available": 10,
            "reserve_before": season.crash_contingency(self.con)["remaining"],
            "reserve_floor": 5_000_000,
            "planned_transfer": 1_500_000,
            "funding_capacity": season.funding_source_capacity(self.con, "Aero"),
            "cap_headroom": max(0, season.CAP - season.total_spend(self.con)),
            "completed_actions": actions,
        }
        values.update(overrides)
        return values

    def record_eligible(self):
        return season.record_safety_decision(
            self.con,
            "prototype:unit-test",
            "Unit-test suspension case",
            {"reference": "prototype:unit-test", "display_label": "Unit-test prototype context"},
            "Aero",
            self.profile["id"],
            self.option_id,
            self.complete_inputs(),
        )

    def test_record_recomputes_status_and_repeated_click_is_idempotent(self):
        first = self.record_eligible()
        second = self.record_eligible()

        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["evaluation"]["status"], "REVIEW_ELIGIBLE")
        self.assertEqual(len(season.safety_decisions(self.con)), 1)

    def test_record_overrides_caller_supplied_finance_values_with_live_ledger_values(self):
        self.con.execute(
            "DELETE FROM career_ledger WHERE category = ? AND kind = 'preseason_rnd'", ("Aero",)
        )
        self.con.commit()

        record = self.record_eligible()
        saved = season.safety_decisions(self.con)[0]

        self.assertEqual(season.funding_source_capacity(self.con, "Aero"), 0)
        self.assertEqual(record["evaluation"]["status"], "HOLD")
        self.assertEqual(saved["status"], "HOLD")
        self.assertEqual(saved["snapshot"]["funding_capacity_cad"], 0)

    def test_record_preserves_a_lower_user_modelled_source_capacity(self):
        inputs = self.complete_inputs(funding_capacity=0)
        record = season.record_safety_decision(
            self.con,
            "prototype:protected-source",
            "Protected source capacity",
            {"reference": "prototype:protected-source", "display_label": "Protected source context"},
            "Aero",
            self.profile["id"],
            self.option_id,
            inputs,
        )
        saved = season.safety_decisions(self.con)[0]

        self.assertGreater(season.funding_source_capacity(self.con, "Aero"), 0)
        self.assertEqual(record["evaluation"]["status"], "HOLD")
        self.assertEqual(saved["status"], "HOLD")
        self.assertEqual(saved["snapshot"]["funding_capacity_cad"], 0)

    def test_funding_records_once_and_balances_reserve_source_and_cap(self):
        record = self.record_eligible()
        before = season.finance_summary(self.con)

        funded = season.fund_safety_decision(self.con, record["id"])
        repeated = season.fund_safety_decision(self.con, record["id"])
        after = season.finance_summary(self.con)
        decision = season.safety_decisions(self.con)[0]
        repair_rows = self.con.execute(
            "SELECT * FROM career_ledger WHERE kind = 'prototype_repair_plan'"
        ).fetchall()
        transfer_rows = self.con.execute(
            "SELECT * FROM career_ledger WHERE kind = 'prototype_funding_reallocation'"
        ).fetchall()

        self.assertFalse(funded["already_funded"])
        self.assertTrue(repeated["already_funded"])
        self.assertEqual(funded["repair_ledger_id"], repeated["repair_ledger_id"])
        self.assertEqual(len(repair_rows), 1)
        self.assertEqual(len(transfer_rows), 1)
        self.assertEqual(decision["status"], "REVIEW_REQUESTED")
        self.assertEqual(decision["repair_ledger_id"], funded["repair_ledger_id"])
        self.assertEqual(after["crash_contingency"]["target"], 6_500_000)
        self.assertEqual(after["crash_contingency"]["used"], 1_500_000)
        self.assertEqual(after["crash_contingency"]["remaining"], 5_000_000)
        self.assertEqual(after["spend"], before["spend"])
        self.assertEqual(season.funding_source_capacity(self.con, "Aero"), 8_500_000)
        audit = season.audit(self.con)
        cap_lines = [
            line["Amount"] for line in audit["financial_lines"]
            if line["Line item"] != "Unspent crash contingency"
        ]
        reprioritisation = next(
            line["Amount"] for line in audit["financial_lines"]
            if line["Line item"] == "Prototype source reprioritisation"
        )
        self.assertEqual(sum(cap_lines), after["spend"])
        self.assertEqual(reprioritisation, -1_500_000)

    def test_funding_uses_the_recorded_editable_option_snapshot(self):
        inputs = self.complete_inputs(
            planned_transfer=2_000_000,
            option_overrides={
                self.option_id: {
                    "estimated_cost_cad": 2_000_000,
                    "estimated_work_hours": 9,
                    "spares_required": 1,
                }
            },
        )
        record = season.record_safety_decision(
            self.con,
            "prototype:override-test",
            "Override snapshot case",
            {"reference": "prototype:override-test", "display_label": "Override prototype context"},
            "Aero",
            self.profile["id"],
            self.option_id,
            inputs,
        )

        funded = season.fund_safety_decision(self.con, record["id"])
        charge = self.con.execute(
            "SELECT amount FROM career_ledger WHERE id = ?", (funded["repair_ledger_id"],)
        ).fetchone()[0]

        self.assertEqual(record["evaluation"]["estimated_cost_cad"], 2_000_000)
        self.assertEqual(charge, 2_000_000)

    def test_funding_does_not_alter_historical_replay_tables(self):
        self.con.execute(
            "INSERT INTO career_sessions(round_number, session_name, results_json, created_at) VALUES (?,?,?,?)",
            (1, "Grand Prix", '{"results": []}', "2025-01-01"),
        )
        self.con.execute(
            "INSERT INTO career_incidents(round_number, title, amount, category, state, created_at) VALUES (?,?,?,?,?,?)",
            (1, "Historical context sentinel", 0, "Other", "pending", "2025-01-01"),
        )
        self.con.commit()
        before = {
            table: [dict(row) for row in self.con.execute(f"SELECT * FROM {table} ORDER BY 1")]
            for table in ("career_sessions", "career_standings", "career_incidents")
        }

        season.fund_safety_decision(self.con, self.record_eligible()["id"])

        after = {
            table: [dict(row) for row in self.con.execute(f"SELECT * FROM {table} ORDER BY 1")]
            for table in ("career_sessions", "career_standings", "career_incidents")
        }
        self.assertEqual(after, before)

    def test_funding_rechecks_live_conditions_and_holds_when_source_is_gone(self):
        record = self.record_eligible()
        self.con.execute(
            """INSERT INTO career_ledger
            (round_number, session_name, category, amount, kind, note, future_car, created_at, effect, counts_to_cap)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (1, "Unit test", "Aero", -10_000_000, "prototype_funding_reallocation", "test", 0, "2025-01-01", "test", 1),
        )
        self.con.commit()

        with self.assertRaisesRegex(ValueError, "Local conditions changed"):
            season.fund_safety_decision(self.con, record["id"])

        decision = season.safety_decisions(self.con)[0]
        repair_count = self.con.execute(
            "SELECT COUNT(*) FROM career_ledger WHERE kind = 'prototype_repair_plan'"
        ).fetchone()[0]
        self.assertEqual(decision["status"], "HOLD")
        self.assertEqual(repair_count, 0)

    def test_future_car_upgrades_are_not_available_as_a_current_source(self):
        initial_capacity = season.funding_source_capacity(self.con, "Aero")
        self.con.execute("UPDATE career_state SET current_round = 17 WHERE id = 1")
        self.con.commit()
        self.assertTrue(season.commit_investment(self.con, "Aero", 1_000_000))

        self.assertEqual(season.funding_source_capacity(self.con, "Aero"), initial_capacity)

    def test_negative_corrupt_prototype_repair_cannot_increase_the_reserve(self):
        self.con.execute(
            """INSERT INTO career_ledger
            (round_number, session_name, category, amount, kind, note, future_car, created_at, effect, counts_to_cap)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (1, "Corrupt test", "Other", -2_000_000, "prototype_repair_plan", "test", 0, "2025-01-01", "test", 1),
        )
        self.con.commit()

        reserve = season.crash_contingency(self.con)

        self.assertEqual(reserve["used"], 0)
        self.assertEqual(reserve["remaining"], 5_000_000)

    def test_busy_second_connection_cannot_duplicate_funding(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "prototype-lock-test.db"
            first = sqlite3.connect(database_path)
            first.row_factory = sqlite3.Row
            season.migrate(first)
            allocations = {category: 10_000_000 for category in season.CATEGORIES}
            season.create_career(
                first, next(iter(season.TEAMS)), allocations, crash_reserve_target=5_000_000
            )
            profile = safety_engine.profile_for("suspension_steering")
            option_id = "assumed_spare_replacement"
            actions = [action["id"] for action in safety_engine.option_for(profile, option_id)["required_actions"]]
            record = season.record_safety_decision(
                first,
                "prototype:lock-test",
                "Lock test",
                {"reference": "prototype:lock-test", "display_label": "Lock test context"},
                "Aero",
                profile["id"],
                option_id,
                {
                    "available_spares": 1,
                    "hours_available": 10,
                    "reserve_before": 5_000_000,
                    "reserve_floor": 5_000_000,
                    "planned_transfer": 1_500_000,
                    "funding_capacity": 10_000_000,
                    "cap_headroom": season.CAP,
                    "completed_actions": actions,
                },
            )
            second = sqlite3.connect(database_path, timeout=0)
            second.row_factory = sqlite3.Row
            second.execute("PRAGMA busy_timeout = 0")
            first.execute("BEGIN IMMEDIATE")
            try:
                with self.assertRaisesRegex(ValueError, "ledger is busy"):
                    season.fund_safety_decision(second, record["id"])
            finally:
                first.rollback()
            funded = season.fund_safety_decision(first, record["id"])
            repeated = season.fund_safety_decision(second, record["id"])
            repair_count = first.execute(
                "SELECT COUNT(*) FROM career_ledger WHERE kind = 'prototype_repair_plan'"
            ).fetchone()[0]
            first.close()
            second.close()

        self.assertFalse(funded["already_funded"])
        self.assertTrue(repeated["already_funded"])
        self.assertEqual(repair_count, 1)

    def test_reset_clears_records_and_rebase_retains_self_contained_audit_snapshot(self):
        self.record_eligible()
        season.reset_career(self.con)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM career_safety_decisions").fetchone()[0], 0
        )

        allocations = {category: 0 for category in season.CATEGORIES}
        season.create_career(self.con, next(iter(season.TEAMS)), allocations)
        recorded = self.record_eligible()
        self.con.execute("UPDATE career_state SET replay_version = 0 WHERE id = 1")
        self.con.commit()
        season.rebase_active_replay(self.con)

        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM career_safety_decisions").fetchone()[0], 1
        )
        restored = season.safety_decisions(self.con)[0]
        self.assertEqual(restored["id"], recorded["id"])
        self.assertEqual(restored["source_context"]["display_label"], "Unit-test prototype context")


if __name__ == "__main__":
    unittest.main()
