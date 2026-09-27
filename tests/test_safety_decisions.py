"""Persistence and finance-boundary tests for prototype planning records."""

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def bounded_historical_context(self):
        return season.historical_incident_source_context({
            "round_number": 1,
            "title": "Bounded historical test context",
            "session_name": "Grand Prix",
            "driver_id": "driver_one",
            "kind": "incident",
            "components": "Front wing",
            "repair_required": 1,
            "safety_critical": 1,
            "source_url": "https://example.test/bounded-context",
        })

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

    def test_record_fingerprints_the_catalog_and_selected_frozen_rule_basis(self):
        record = self.record_eligible()
        saved = season.safety_decisions(self.con)[0]
        identity = safety_engine.catalog_identity(safety_engine.load_assumptions())

        self.assertTrue(record["created"])
        self.assertEqual(saved["assumption_catalog"]["sha256"], identity["sha256"])
        self.assertEqual(saved["assumption_catalog"]["version"], identity["version"])
        self.assertEqual(saved["assumption_catalog"]["rules_engine_version"], safety_engine.RULES_ENGINE_VERSION)
        self.assertEqual(saved["profile_snapshot"]["ledger_category"], "Chassis / structures")
        self.assertEqual(saved["profile_snapshot"]["options"][0]["id"], self.option_id)
        self.assertTrue(saved["decision_fingerprint"])
        self.assertTrue(saved["snapshot"]["frozen_rule_basis"]["profile_sha256"])

    def test_record_rejects_mismatched_or_unbounded_historical_context_references(self):
        context = self.bounded_historical_context()
        tampered_context = copy.deepcopy(context)
        tampered_context["facts"]["title"] = "Changed after launch"
        invalid_schema = copy.deepcopy(context)
        invalid_schema["schema"] = "unsupported-context-schema"

        invalid_cases = (
            (
                f"historical-context:{context['sha256']}",
                tampered_context,
                "SHA-256 fingerprint",
            ),
            (
                "historical-context:" + "0" * 64,
                context,
                "source reference does not match",
            ),
            (
                f"historical-context:{context['sha256']}",
                invalid_schema,
                "unsupported schema",
            ),
            ("historical:legacy-row", context, "bounded historical-context launcher snapshot"),
        )
        for source_ref, source_context, message in invalid_cases:
            with self.subTest(source_ref=source_ref):
                with self.assertRaisesRegex(ValueError, message):
                    season.record_safety_decision(
                        self.con,
                        source_ref,
                        "Invalid historical context",
                        source_context,
                        "Aero",
                        self.profile["id"],
                        self.option_id,
                        self.complete_inputs(),
                    )

        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM career_safety_decisions").fetchone()[0], 0
        )

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
        self.assertEqual(decision["reserve_transfer_ledger_id"], funded["reserve_transfer_ledger_id"])
        self.assertEqual(decision["funded_round_number"], 1)
        self.assertEqual(decision["funding_snapshot"]["funding_event"]["repair_ledger_id"], funded["repair_ledger_id"])
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
        linked_entries = self.con.execute(
            "SELECT safety_decision_id FROM career_ledger WHERE kind LIKE 'prototype_%'"
        ).fetchall()
        self.assertTrue(all(row["safety_decision_id"] == record["id"] for row in linked_entries))
        packet = season.safety_decision_packet(self.con, record["id"])
        self.assertEqual(packet["ledger_link_integrity"]["state"], "OK")
        self.assertEqual(len(packet["linked_local_ledger_entries"]), 3)

    def test_correlated_ledger_rows_block_refunding_when_mutable_pointers_are_cleared(self):
        record = self.record_eligible()
        season.fund_safety_decision(self.con, record["id"])
        self.con.execute(
            """UPDATE career_safety_decisions
            SET status = ?, repair_ledger_id = NULL, transfer_ledger_id = NULL,
                reserve_transfer_ledger_id = NULL, funded_at = NULL, funded_round_number = NULL,
                review_requested_at = NULL, funding_snapshot_json = ?
            WHERE id = ?""",
            ("REVIEW_ELIGIBLE", json.dumps({}), record["id"]),
        )
        self.con.commit()

        live = season.safety_decision_live_check(self.con, record["id"])
        packet = season.safety_decision_packet(self.con, record["id"])

        self.assertEqual(live["status"], "HOLD")
        self.assertIn("FUNDING_LEDGER_ALREADY_PRESENT", {gap["code"] for gap in live["gaps"]})
        self.assertEqual(packet["ledger_link_integrity"]["state"], "CHECK_REQUIRED")
        with self.assertRaisesRegex(ValueError, "already has correlated local ledger entries"):
            season.fund_safety_decision(self.con, record["id"])
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM career_ledger WHERE kind = 'prototype_repair_plan'").fetchone()[0],
            1,
        )

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

    def test_receipt_flags_tampered_ledger_values_and_is_json_serializable(self):
        record = self.record_eligible()
        funded = season.fund_safety_decision(self.con, record["id"])
        self.con.execute(
            """UPDATE career_ledger
            SET kind = ?, category = ?, amount = ?, counts_to_cap = ?
            WHERE id = ?""",
            ("upgrade", "Aero", 123.45, 0, funded["repair_ledger_id"]),
        )
        self.con.commit()

        packet = season.safety_decision_packet(self.con, record["id"])
        errors = "\n".join(packet["ledger_link_integrity"]["errors"])

        self.assertEqual(packet["packet_schema_version"], "1.1")
        self.assertEqual(packet["ledger_link_integrity"]["state"], "CHECK_REQUIRED")
        self.assertIn("expected 'prototype_repair_plan'", errors)
        self.assertIn("category is 'Aero'", errors)
        self.assertIn("amount does not match the funding snapshot", errors)
        self.assertIn("counts_to_cap does not match", errors)
        self.assertEqual(json.loads(json.dumps(packet, allow_nan=False))["decision"]["id"], record["id"])

    def test_receipt_flags_mismatched_decision_and_funding_snapshot_linkage(self):
        record = self.record_eligible()
        funded = season.fund_safety_decision(self.con, record["id"])
        self.con.execute(
            "UPDATE career_safety_decisions SET repair_ledger_id = ? WHERE id = ?",
            (funded["transfer_ledger_id"], record["id"]),
        )
        self.con.commit()

        packet = season.safety_decision_packet(self.con, record["id"])
        errors = "\n".join(packet["ledger_link_integrity"]["errors"])

        self.assertEqual(packet["ledger_link_integrity"]["state"], "CHECK_REQUIRED")
        self.assertIn("Funding snapshot repair_ledger_id does not match the saved decision linkage", errors)
        self.assertIn("declared for both repair and transfer", errors)
        self.assertIn("correlated to this decision but is not declared", errors)
        self.assertEqual(len(packet["correlated_local_ledger_entries"]), 3)
        json.dumps(packet, allow_nan=False)

    def test_receipt_flags_funding_snapshot_and_ledger_amounts_changed_together(self):
        record = self.record_eligible()
        funded = season.fund_safety_decision(self.con, record["id"])
        saved = season.safety_decisions(self.con)[0]
        altered_snapshot = copy.deepcopy(saved["funding_snapshot"])
        altered_snapshot["estimated_cost_cad"] = 2_500_000
        altered_snapshot["planned_transfer_cad"] = 2_500_000
        self.con.execute(
            "UPDATE career_safety_decisions SET funding_snapshot_json = ? WHERE id = ?",
            (json.dumps(altered_snapshot), record["id"]),
        )
        self.con.execute(
            "UPDATE career_ledger SET amount = ? WHERE id = ?",
            (2_500_000, funded["repair_ledger_id"]),
        )
        self.con.execute(
            "UPDATE career_ledger SET amount = ? WHERE id = ?",
            (-2_500_000, funded["transfer_ledger_id"]),
        )
        self.con.execute(
            "UPDATE career_ledger SET amount = ? WHERE id = ?",
            (2_500_000, funded["reserve_transfer_ledger_id"]),
        )
        self.con.commit()

        packet = season.safety_decision_packet(self.con, record["id"])
        errors = "\n".join(packet["ledger_link_integrity"]["errors"])

        self.assertEqual(packet["decision_fingerprint_check"]["state"], "MATCHED")
        self.assertEqual(packet["ledger_link_integrity"]["state"], "CHECK_REQUIRED")
        self.assertIn(
            "Funding snapshot estimated_cost_cad does not match the frozen saved decision basis", errors,
        )
        self.assertIn(
            "Funding snapshot planned_transfer_cad does not match the frozen saved decision basis", errors,
        )

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

        with self.assertRaisesRegex(ValueError, "current local funding check is HOLD"):
            season.fund_safety_decision(self.con, record["id"])

        decision = season.safety_decisions(self.con)[0]
        repair_count = self.con.execute(
            "SELECT COUNT(*) FROM career_ledger WHERE kind = 'prototype_repair_plan'"
        ).fetchone()[0]
        self.assertEqual(decision["status"], "REVIEW_ELIGIBLE")
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

    def test_catalog_drift_blocks_local_funding_without_reinterpreting_the_frozen_option(self):
        record = self.record_eligible()
        changed_catalog = copy.deepcopy(safety_engine.load_assumptions())
        changed_catalog["version"] = "changed-for-test"
        changed_catalog["profiles"][0]["options"][1]["required_actions"] = []

        with patch.object(safety_engine, "load_assumptions", return_value=changed_catalog):
            live = season.safety_decision_live_check(self.con, record["id"])
            self.assertEqual(live["status"], "HOLD")
            self.assertEqual(live["catalog_check"]["state"], "CATALOG_CHANGED")
            self.assertIn("CATALOG_DRIFT", {gap["code"] for gap in live["gaps"]})
            with self.assertRaisesRegex(ValueError, "catalog changed"):
                season.fund_safety_decision(self.con, record["id"])

        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM career_ledger WHERE kind = 'prototype_repair_plan'").fetchone()[0],
            0,
        )
        saved = season.safety_decisions(self.con)[0]
        self.assertEqual(saved["profile_snapshot"]["options"][0]["required_actions"], [
            {"id": "inspection_logged", "label": "Human inspection record added"},
            {"id": "work_recorded", "label": "Prototype work-completion record added"},
        ])

    def test_unavailable_current_catalog_holds_the_saved_plan_without_a_charge(self):
        record = self.record_eligible()

        with patch.object(
            safety_engine,
            "load_assumptions",
            side_effect=safety_engine.AssumptionError("test catalog unavailable"),
        ):
            live = season.safety_decision_live_check(self.con, record["id"])
            self.assertEqual(live["status"], "HOLD")
            self.assertEqual(live["catalog_check"]["state"], "CURRENT_CATALOG_UNAVAILABLE")
            self.assertIn("CATALOG_DRIFT", {gap["code"] for gap in live["gaps"]})
            with self.assertRaisesRegex(ValueError, "cannot be verified"):
                season.fund_safety_decision(self.con, record["id"])

        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM career_ledger WHERE kind = 'prototype_repair_plan'").fetchone()[0],
            0,
        )

    def test_rules_engine_change_holds_the_saved_plan_without_a_charge(self):
        record = self.record_eligible()

        with patch.object(safety_engine, "RULES_ENGINE_VERSION", "test-rule-engine-change"):
            live = season.safety_decision_live_check(self.con, record["id"])
            self.assertEqual(live["status"], "HOLD")
            self.assertEqual(live["catalog_check"]["state"], "RULES_ENGINE_CHANGED")
            self.assertIn("CATALOG_DRIFT", {gap["code"] for gap in live["gaps"]})
            with self.assertRaisesRegex(ValueError, "rule-engine version changed"):
                season.fund_safety_decision(self.con, record["id"])

        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM career_ledger WHERE kind = 'prototype_repair_plan'").fetchone()[0],
            0,
        )

    def test_legacy_unfingerprinted_decision_cannot_create_a_ledger_entry(self):
        record = self.record_eligible()
        self.con.execute(
            "UPDATE career_safety_decisions SET assumption_catalog_json = ?, profile_snapshot_json = ? WHERE id = ?",
            (json.dumps({}), json.dumps({}), record["id"]),
        )
        self.con.commit()

        live = season.safety_decision_live_check(self.con, record["id"])
        self.assertEqual(live["status"], "HOLD")
        self.assertEqual(live["catalog_check"]["state"], "LEGACY_UNVERIFIABLE")
        with self.assertRaisesRegex(ValueError, "current local funding check is HOLD"):
            season.fund_safety_decision(self.con, record["id"])
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM career_ledger WHERE kind = 'prototype_repair_plan'").fetchone()[0],
            0,
        )

    def test_plan_must_be_re_recorded_when_the_replay_round_changes(self):
        record = self.record_eligible()
        self.con.execute("UPDATE career_state SET current_round = 2 WHERE id = 1")
        self.con.commit()

        live = season.safety_decision_live_check(self.con, record["id"])
        self.assertEqual(live["status"], "HOLD")
        self.assertIn("ROUND_CHANGED", {gap["code"] for gap in live["gaps"]})
        with self.assertRaisesRegex(ValueError, "earlier replay round"):
            season.fund_safety_decision(self.con, record["id"])

    def test_wrong_type_saved_json_is_contained_as_an_integrity_warning(self):
        record = self.record_eligible()
        self.con.execute(
            "UPDATE career_safety_decisions SET source_context_json = ? WHERE id = ?",
            (json.dumps([]), record["id"]),
        )
        self.con.commit()

        saved = season.safety_decisions(self.con)[0]
        self.assertEqual(saved["source_context"], {})
        self.assertTrue(saved["integrity_warnings"])
        live = season.safety_decision_live_check(self.con, record["id"])
        self.assertEqual(live["status"], "HOLD")
        self.assertIn("SAVED_RECORD_INTEGRITY", {gap["code"] for gap in live["gaps"]})

    def test_clean_decision_basis_fingerprint_is_matched_in_live_check_and_receipt(self):
        record = self.record_eligible()

        live = season.safety_decision_live_check(self.con, record["id"])
        packet = season.safety_decision_packet(self.con, record["id"])

        self.assertEqual(live["status"], "REVIEW_ELIGIBLE")
        self.assertEqual(live["decision_fingerprint_check"]["state"], "MATCHED")
        self.assertTrue(live["decision_fingerprint_check"]["matches"])
        self.assertEqual(packet["decision_fingerprint_check"]["state"], "MATCHED")
        self.assertEqual(packet["ledger_link_integrity"]["state"], "OK")

    def test_tampered_frozen_snapshot_holds_and_cannot_fund(self):
        record = self.record_eligible()
        saved = season.safety_decisions(self.con)[0]
        altered = copy.deepcopy(saved["snapshot"])
        altered["case_inputs"]["option_overrides"][self.option_id]["estimated_cost_cad"] = 2_000_000
        altered["case_inputs"]["planned_transfer"] = 2_000_000
        self.con.execute(
            "UPDATE career_safety_decisions SET snapshot_json = ? WHERE id = ?",
            (json.dumps(altered), record["id"]),
        )
        self.con.commit()

        live = season.safety_decision_live_check(self.con, record["id"])
        packet = season.safety_decision_packet(self.con, record["id"])

        self.assertEqual(live["status"], "HOLD")
        self.assertEqual(live["decision_fingerprint_check"]["state"], "MISMATCH")
        self.assertIn("DECISION_FINGERPRINT_MISMATCH", {gap["code"] for gap in live["gaps"]})
        self.assertEqual(packet["decision_fingerprint_check"]["state"], "MISMATCH")
        self.assertEqual(packet["ledger_link_integrity"]["state"], "CHECK_REQUIRED")
        with self.assertRaisesRegex(ValueError, "current local funding check is HOLD"):
            season.fund_safety_decision(self.con, record["id"])
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM career_ledger WHERE kind = 'prototype_repair_plan'").fetchone()[0],
            0,
        )

    def test_missing_decision_basis_fingerprint_holds_and_cannot_fund(self):
        record = self.record_eligible()
        self.con.execute(
            "UPDATE career_safety_decisions SET decision_fingerprint = NULL WHERE id = ?",
            (record["id"],),
        )
        self.con.commit()

        live = season.safety_decision_live_check(self.con, record["id"])
        packet = season.safety_decision_packet(self.con, record["id"])

        self.assertEqual(live["status"], "HOLD")
        self.assertEqual(live["decision_fingerprint_check"]["state"], "LEGACY_UNVERIFIABLE")
        self.assertIn("DECISION_FINGERPRINT_UNVERIFIABLE", {gap["code"] for gap in live["gaps"]})
        self.assertEqual(packet["decision_fingerprint_check"]["state"], "LEGACY_UNVERIFIABLE")
        self.assertEqual(packet["ledger_link_integrity"]["state"], "CHECK_REQUIRED")
        with self.assertRaisesRegex(ValueError, "current local funding check is HOLD"):
            season.fund_safety_decision(self.con, record["id"])
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM career_ledger WHERE kind = 'prototype_repair_plan'").fetchone()[0],
            0,
        )

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

    def test_legacy_duplicate_funding_rows_do_not_break_the_migration_backstop(self):
        index_name = "career_ledger_prototype_decision_kind_unique"
        self.assertIsNotNone(self.con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name = ?", (index_name,)
        ).fetchone())
        self.con.execute(f"DROP INDEX {index_name}")
        for _ in range(2):
            self.con.execute(
                """INSERT INTO career_ledger
                (round_number, session_name, category, amount, kind, note, future_car, created_at,
                 effect, counts_to_cap, safety_decision_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (1, "Legacy data", "Chassis / structures", 1_000_000, "prototype_repair_plan",
                 "Legacy duplicate", 0, "2025-01-01", "Legacy data", 1, 99),
            )
        self.con.commit()

        season.migrate(self.con)

        self.assertIsNone(self.con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name = ?", (index_name,)
        ).fetchone())

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

    def test_historical_launcher_context_records_without_mutating_its_incident(self):
        self.con.execute(
            """INSERT INTO career_incidents
            (round_number, title, amount, category, state, reason, responsible, source, created_at,
             session_name, driver_id, kind, components, cost_low, cost_high, estimate_label,
             safety_critical, repair_required, chosen_amount, source_url)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                1, "Historical repair-required record", 0.0, "Chassis / structures", "pending",
                "Bundled historical context", "Not officially assigned", "Local 2025 historical replay bundle",
                "2025-01-01", "Grand Prix", "driver_one", "incident", "Front wing", 100_000.0,
                200_000.0, "Public-context local estimate", 1, 1, 0.0,
                "https://example.test/historical-record",
            ),
        )
        self.con.commit()
        before = [
            dict(row) for row in self.con.execute(
                "SELECT * FROM career_incidents ORDER BY id"
            ).fetchall()
        ]
        context = season.historical_incident_source_context(before[0])

        record = season.record_safety_decision(
            self.con,
            f"historical-context:{context['sha256']}",
            context["display_label"],
            context,
            "Aero",
            self.profile["id"],
            self.option_id,
            self.complete_inputs(),
        )
        after = [
            dict(row) for row in self.con.execute(
                "SELECT * FROM career_incidents ORDER BY id"
            ).fetchall()
        ]
        saved = season.safety_decisions(self.con)[0]

        self.assertTrue(record["created"])
        self.assertEqual(after, before)
        self.assertEqual(saved["source_ref"], f"historical-context:{context['sha256']}")
        self.assertEqual(saved["source_context"], context)
        self.assertEqual(saved["source_context"]["origin"], season.HISTORICAL_INCIDENT_CONTEXT_ORIGIN)
        self.assertEqual(saved["source_context"]["sha256"], context["sha256"])
        self.assertNotIn("record_id_at_selection", saved["source_context"])
        self.assertNotIn("id", saved["source_context"])


if __name__ == "__main__":
    unittest.main()
