"""Regression tests for the evidence-only safety-planning foundation."""

import sqlite3
import unittest

import career_engine as season


class SafetyPlanningSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        season.migrate(self.con)

    def tearDown(self):
        self.con.close()

    def _create_replay(self):
        season.create_career(
            self.con,
            next(iter(season.TEAMS)),
            {category: 0.0 for category in season.CATEGORIES},
        )

    def _add_incident(self, title, round_number, critical=False, state="pending"):
        self.con.execute(
            """INSERT INTO career_incidents
            (round_number, title, amount, category, state, created_at, safety_critical,
             repair_required, cost_low, cost_high, components, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                round_number,
                title,
                0.0,
                "Chassis / structures",
                state,
                "2025-01-01",
                int(critical),
                1,
                0.0,
                0.0,
                "Publicly described component area",
                "https://example.test/source",
            ),
        )
        self.con.commit()

    def test_snapshot_is_unavailable_without_an_active_replay(self):
        self.assertIsNone(season.safety_planning_snapshot(self.con))

    def test_snapshot_does_not_fabricate_a_readiness_score(self):
        self._create_replay()

        snapshot = season.safety_planning_snapshot(self.con)

        self.assertEqual(snapshot["readiness_model"]["state"], "not_modelled")
        self.assertNotIn("readiness_score", snapshot)
        self.assertEqual(snapshot["records"], [])

    def test_only_prior_unresolved_critical_records_hold_replay_advance(self):
        self._create_replay()
        self._add_incident("Prior critical record", 1, critical=True)
        self._add_incident("Prior non-critical record", 1, critical=False)
        self._add_incident("Current-round critical record", 2, critical=True)
        self.con.execute("UPDATE career_state SET current_round = 2 WHERE id = 1")
        self.con.commit()

        with self.assertRaisesRegex(ValueError, "required repair decision"):
            season.run_weekend(self.con)

        snapshot = season.safety_planning_snapshot(self.con)

        self.assertEqual(
            [item["title"] for item in snapshot["replay_hold_incidents"]],
            ["Prior critical record"],
        )
        self.assertEqual(len(snapshot["open_critical_records"]), 2)

        self.con.execute(
            "UPDATE career_incidents SET state = 'funded' WHERE title = 'Prior critical record'"
        )
        self.con.commit()
        self.assertEqual(
            season.safety_planning_snapshot(self.con)["replay_hold_incidents"], []
        )

    def test_source_limited_critical_record_is_not_marked_as_funded(self):
        self._create_replay()
        self._add_incident("Critical record without a cost band", 1, critical=True)
        self.con.execute("UPDATE career_state SET current_round = 2 WHERE id = 1")
        incident_id = self.con.execute(
            "SELECT id FROM career_incidents WHERE title = ?",
            ("Critical record without a cost band",),
        ).fetchone()[0]
        self.con.commit()

        self.assertEqual(len(season.unresolved_critical_incidents(self.con, before_round=2)), 1)
        season.resolve_incident(self.con, incident_id, "source_limited")

        incident = self.con.execute(
            "SELECT state, chosen_amount FROM career_incidents WHERE id = ?", (incident_id,)
        ).fetchone()
        ledger_kind = self.con.execute(
            "SELECT kind FROM career_ledger WHERE kind = 'repair_source_limited'"
        ).fetchone()[0]
        self.assertEqual(incident["state"], "source_limited")
        self.assertEqual(incident["chosen_amount"], 0)
        self.assertEqual(ledger_kind, "repair_source_limited")
        self.assertEqual(season.unresolved_critical_incidents(self.con, before_round=2), [])

    def test_manual_entries_are_not_historical_evidence(self):
        self._create_replay()
        season.add_manual_incident(
            self.con,
            "User-entered component damage",
            250_000,
            "Chassis / structures",
        )

        snapshot = season.safety_planning_snapshot(self.con)

        self.assertEqual(len(snapshot["records"]), 1)
        self.assertEqual(len(snapshot["manual_records"]), 1)
        self.assertEqual(snapshot["historical_records"], [])
        self.assertEqual(snapshot["source_linked_records"], [])

    def test_migration_is_idempotent_for_existing_replay_state_and_evidence(self):
        self._create_replay()
        self._add_incident("Source-linked historical record", 1, critical=True)
        self.con.execute(
            """INSERT INTO career_sessions
            (round_number, session_name, results_json, created_at)
            VALUES (?, ?, ?, ?)""",
            (1, "Grand Prix", "{}", "2025-01-01"),
        )
        self.con.commit()
        tables = (
            "career_state",
            "career_ledger",
            "career_sessions",
            "career_standings",
            "career_incidents",
        )
        before = {
            table: [dict(row) for row in self.con.execute(f"SELECT * FROM {table} ORDER BY 1")]
            for table in tables
        }

        season.migrate(self.con)
        season.migrate(self.con)

        after = {
            table: [dict(row) for row in self.con.execute(f"SELECT * FROM {table} ORDER BY 1")]
            for table in tables
        }
        self.assertEqual(after, before)

    def test_gameplay_tiers_do_not_claim_fia_breach_categories(self):
        at_five_percent = season.sanction_for(season.CAP + season.CAP // 20)
        above_five_percent = season.sanction_for(season.CAP + season.CAP // 20 + 1)

        self.assertEqual(at_five_percent["label"], "Illustrative gameplay tier 1")
        self.assertEqual(above_five_percent["label"], "Illustrative gameplay tier 2")


if __name__ == "__main__":
    unittest.main()
