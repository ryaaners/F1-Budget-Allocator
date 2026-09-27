"""Persistence and exact historical-replay logic for the offline 2025 F1 tool.

On-track classifications are copied from the bundled 2025 result data.  Financial
decisions remain interactive, but they never alter a replayed race result.
"""
from __future__ import annotations

import json
import hashlib
import math
import sqlite3
from datetime import date
from statistics import median

import safety_engine
from career_data import (
    CAP,
    CALENDAR,
    CATEGORIES,
    TEAMS,
    historical_weather,
    incidents_for,
    replay_available,
    replay_session_names,
    replay_weekend,
    strategy_for,
)

CURRENT_CAR_CATEGORIES = {"Aero", "Powertrain", "Chassis / structures", "Testing"}
PROTOTYPE_FUNDING_KINDS = (
    "prototype_repair_plan",
    "prototype_funding_reallocation",
    "prototype_reserve_transfer",
)
# Version 3 also rebuilds source-backed incident rows for older exact-replay saves.
REPLAY_VERSION = 3

# A launcher deliberately keeps only an app-preserved, non-relational copy of
# facts already stored in a historical incident record.  It is not a repair
# specification or a reference back to a mutable incident row.
HISTORICAL_INCIDENT_CONTEXT_SCHEMA = "f1-budget-allocator/historical-incident-context/v1"
HISTORICAL_INCIDENT_CONTEXT_ORIGIN = "app_preserved_historical_incident"


def money(value):
    return f"CAD ${float(value) / 1_000_000:,.1f}M"


def connect(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    migrate(con)
    return con


def _columns(con, table):
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}


def _add_column(con, table, name, definition):
    if name not in _columns(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _ensure_prototype_funding_unique_index(con):
    """Add a duplicate-funding backstop without mutating a legacy ledger.

    A database containing an old duplicate must remain readable for audit; the
    runtime preflight will still refuse any new charge for that decision.  In a
    clean ledger, the partial unique index is a second guard in addition to the
    transaction and correlated-row check in ``fund_safety_decision``.
    """
    duplicate = con.execute(
        """SELECT safety_decision_id, kind
        FROM career_ledger
        WHERE safety_decision_id IS NOT NULL AND kind IN (?,?,?)
        GROUP BY safety_decision_id, kind
        HAVING COUNT(*) > 1
        LIMIT 1""",
        PROTOTYPE_FUNDING_KINDS,
    ).fetchone()
    if duplicate:
        return False
    con.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS career_ledger_prototype_decision_kind_unique
        ON career_ledger(safety_decision_id, kind)
        WHERE safety_decision_id IS NOT NULL
          AND kind IN ('prototype_repair_plan', 'prototype_funding_reallocation',
                       'prototype_reserve_transfer')"""
    )
    return True


def migrate(con):
    """Create the replay schema and non-destructively upgrade older local saves."""
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS career_state (
            id INTEGER PRIMARY KEY CHECK (id = 1), team_id TEXT NOT NULL,
            current_round INTEGER NOT NULL DEFAULT 1, session_index INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active', theme TEXT NOT NULL DEFAULT 'team',
            switch_round INTEGER NOT NULL DEFAULT 16, seed INTEGER NOT NULL DEFAULT 2025,
            created_at TEXT NOT NULL, crash_reserve_target REAL NOT NULL DEFAULT 0,
            replay_version INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS career_allocations (
            category TEXT PRIMARY KEY, amount REAL NOT NULL, rate REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS career_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT, round_number INTEGER, session_name TEXT,
            category TEXT NOT NULL, amount REAL NOT NULL, kind TEXT NOT NULL, note TEXT,
            future_car INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
            effect TEXT NOT NULL DEFAULT '', counts_to_cap INTEGER NOT NULL DEFAULT 1,
            safety_decision_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS career_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, round_number INTEGER NOT NULL,
            session_name TEXT NOT NULL, results_json TEXT NOT NULL, created_at TEXT NOT NULL,
            UNIQUE(round_number, session_name)
        );
        CREATE TABLE IF NOT EXISTS career_standings (
            team_id TEXT PRIMARY KEY, points INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS career_incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT, round_number INTEGER NOT NULL,
            title TEXT NOT NULL, amount REAL NOT NULL DEFAULT 0, category TEXT NOT NULL DEFAULT 'Other',
            penalty REAL NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'pending',
            reason TEXT, responsible TEXT, source TEXT, created_at TEXT NOT NULL,
            session_name TEXT, driver_id TEXT, kind TEXT, components TEXT,
            cost_low REAL NOT NULL DEFAULT 0, cost_high REAL NOT NULL DEFAULT 0,
            estimate_label TEXT, safety_critical INTEGER NOT NULL DEFAULT 0,
            repair_required INTEGER NOT NULL DEFAULT 0, chosen_amount REAL NOT NULL DEFAULT 0,
            source_url TEXT, reviewed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS career_preferences (
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS career_safety_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_number INTEGER NOT NULL, source_ref TEXT,
            source_label TEXT NOT NULL, source_context_json TEXT NOT NULL DEFAULT '{}',
            profile_id TEXT NOT NULL,
            option_id TEXT NOT NULL, funding_source TEXT,
            status TEXT NOT NULL, blockers_json TEXT NOT NULL,
            snapshot_json TEXT NOT NULL, repair_ledger_id INTEGER,
            transfer_ledger_id INTEGER, reserve_transfer_ledger_id INTEGER,
            funded_at TEXT, funded_round_number INTEGER,
            review_requested_at TEXT, created_at TEXT NOT NULL,
            assumption_catalog_json TEXT NOT NULL DEFAULT '{}',
            profile_snapshot_json TEXT NOT NULL DEFAULT '{}',
            funding_snapshot_json TEXT NOT NULL DEFAULT '{}',
            decision_fingerprint TEXT
        );
        """
    )
    for table, name, definition in (
        ("career_state", "crash_reserve_target", "REAL NOT NULL DEFAULT 0"),
        ("career_state", "replay_version", "INTEGER NOT NULL DEFAULT 0"),
        ("career_ledger", "effect", "TEXT NOT NULL DEFAULT ''"),
        ("career_ledger", "counts_to_cap", "INTEGER NOT NULL DEFAULT 1"),
        ("career_ledger", "safety_decision_id", "INTEGER"),
        ("career_incidents", "session_name", "TEXT"),
        ("career_incidents", "driver_id", "TEXT"),
        ("career_incidents", "kind", "TEXT"),
        ("career_incidents", "components", "TEXT"),
        ("career_incidents", "cost_low", "REAL NOT NULL DEFAULT 0"),
        ("career_incidents", "cost_high", "REAL NOT NULL DEFAULT 0"),
        ("career_incidents", "estimate_label", "TEXT"),
        ("career_incidents", "safety_critical", "INTEGER NOT NULL DEFAULT 0"),
        ("career_incidents", "repair_required", "INTEGER NOT NULL DEFAULT 0"),
        ("career_incidents", "chosen_amount", "REAL NOT NULL DEFAULT 0"),
        ("career_incidents", "source_url", "TEXT"),
        ("career_incidents", "reviewed_at", "TEXT"),
        ("career_safety_decisions", "repair_ledger_id", "INTEGER"),
        ("career_safety_decisions", "transfer_ledger_id", "INTEGER"),
        ("career_safety_decisions", "reserve_transfer_ledger_id", "INTEGER"),
        ("career_safety_decisions", "funded_at", "TEXT"),
        ("career_safety_decisions", "funded_round_number", "INTEGER"),
        ("career_safety_decisions", "review_requested_at", "TEXT"),
        ("career_safety_decisions", "source_context_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("career_safety_decisions", "assumption_catalog_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("career_safety_decisions", "profile_snapshot_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("career_safety_decisions", "funding_snapshot_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("career_safety_decisions", "decision_fingerprint", "TEXT"),
    ):
        _add_column(con, table, name, definition)
    con.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS career_safety_decision_fingerprint_unique "
        "ON career_safety_decisions(decision_fingerprint)"
    )
    _ensure_prototype_funding_unique_index(con)
    _backfill_ledger_effects(con)
    con.commit()


def active_state(con):
    row = con.execute("SELECT * FROM career_state WHERE id = 1").fetchone()
    return dict(row) if row else None


def reset_career(con):
    for table in (
        "career_state", "career_allocations", "career_ledger", "career_sessions",
        "career_standings", "career_incidents", "career_preferences", "career_safety_decisions",
    ):
        con.execute(f"DELETE FROM {table}")
    con.commit()


def _insert_ledger(
    con, round_number, session_name, category, amount, kind, note, effect,
    future_car=0, counts_to_cap=True, safety_decision_id=None,
):
    cursor = con.execute(
        """INSERT INTO career_ledger
        (round_number, session_name, category, amount, kind, note, future_car, created_at, effect,
         counts_to_cap, safety_decision_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            round_number, session_name, category, float(amount), kind, note, int(future_car),
            date.today().isoformat(), effect, int(counts_to_cap), safety_decision_id,
        ),
    )
    return int(cursor.lastrowid)


def _investment_effect(category, future_car):
    target = "future-car funding" if future_car else "2025 budget commitment"
    planning = {
        "Personnel": "Planning classification: personnel allocation recorded.",
        "Operations": "Planning classification: operations allocation recorded.",
        "Testing": "Planning classification: testing allocation recorded.",
        "Chassis / structures": "Planning classification: chassis and structures allocation recorded.",
    }.get(category, "Planning classification: no direct operational outcome is calculated.")
    return f"{target}; {planning} No safety outcome or historical replay result is calculated."


def _backfill_ledger_effects(con):
    """Give legacy financial choices the same explicit Effects descriptions as new rows."""
    if "effect" not in _columns(con, "career_ledger"):
        return
    rows = con.execute(
        "SELECT id, category, amount, kind, future_car, effect FROM career_ledger WHERE COALESCE(effect, '') = ''"
    ).fetchall()
    for row in rows:
        item = dict(row)
        kind = item["kind"]
        if kind in {"preseason_rnd", "upgrade"}:
            effect = _investment_effect(item["category"], bool(item["future_car"]))
        elif kind == "operating_base":
            effect = "Cap spend: modelled fixed operating base; historical replay results are unchanged."
        elif kind == "crash_reserve_allocation":
            effect = f"Crash contingency: {money(item['amount'])} reserved for local repair charges and explicitly committed prototype plans."
        elif kind.startswith("repair"):
            effect = "Local repair-finance record; historical replay results are unchanged."
        else:
            effect = "Legacy financial entry retained; historical replay results are unchanged."
        con.execute("UPDATE career_ledger SET effect = ? WHERE id = ?", (effect, item["id"]))


def create_career(con, team_id, allocations, crash_reserve_target=5_000_000, switch_round=16, theme="team", seed=2025):
    if team_id not in TEAMS:
        raise ValueError("Choose a valid 2025 constructor.")
    reset_career(con)
    clean = {category: max(0.0, float(allocations.get(category, 0))) for category in CATEGORIES}
    team = TEAMS[team_id]
    con.execute(
        """INSERT INTO career_state
        (id,team_id,current_round,session_index,status,theme,switch_round,seed,created_at,crash_reserve_target,replay_version)
        VALUES (1,?,?,?,?,?,?,?,?,?,?)""",
        (
            team_id, 1, 0, "active", theme, int(switch_round), int(seed), date.today().isoformat(),
            max(0.0, float(crash_reserve_target)), REPLAY_VERSION,
        ),
    )
    con.executemany(
        "INSERT INTO career_allocations(category, amount, rate) VALUES (?,?,?)",
        [(category, clean[category], 0.0) for category in CATEGORIES],
    )
    _insert_ledger(
        con, 0, "Pre-season", "Operations", team["fixed_cost"], "operating_base",
        "Modelled fixed 2025 operating base", "Cap spend: fixed operating base.", counts_to_cap=True,
    )
    for category, amount in clean.items():
        if amount:
            _insert_ledger(
                con, 0, "Pre-season", category, amount, "preseason_rnd",
                "Pre-season allocation", _investment_effect(category, False), counts_to_cap=True,
            )
    _insert_ledger(
        con, 0, "Pre-season", "Other", max(0.0, float(crash_reserve_target)),
        "crash_reserve_allocation", "Dedicated crash contingency allocation",
        f"Crash contingency: {money(crash_reserve_target)} reserved for local repair charges and explicitly committed prototype plans.",
        counts_to_cap=False,
    )
    _initialize_standings(con)
    con.commit()


def _initialize_standings(con):
    for team_id in TEAMS:
        con.execute("INSERT OR IGNORE INTO career_standings(team_id, points) VALUES (?,0)", (team_id,))


def total_spend(con):
    return float(con.execute("SELECT COALESCE(SUM(amount),0) FROM career_ledger WHERE counts_to_cap = 1").fetchone()[0])


def ledger(con):
    items = [dict(row) for row in con.execute("SELECT * FROM career_ledger ORDER BY id DESC").fetchall()]
    for item in items:
        if not item.get("effect"):
            item["effect"] = "Legacy entry retained during historical replay migration."
    return items


def spend_by_category(con):
    output = {category: 0.0 for category in CATEGORIES}
    for row in con.execute(
        "SELECT category, COALESCE(SUM(amount),0) amount FROM career_ledger WHERE counts_to_cap = 1 GROUP BY category"
    ):
        if row["category"] in output:
            output[row["category"]] = float(row["amount"])
    return output


def sanction_for(spend):
    breach = max(0.0, float(spend) - CAP)
    breach_pct = breach / CAP if CAP else 0.0
    if breach <= 0:
        return {
            "label": "Within gameplay cap", "breach": 0.0, "breach_pct": 0.0,
            "fine": 0.0, "wind_tunnel_cut": 0, "point_deduction": 0,
        }
    if breach_pct <= 0.05:
        return {
            "label": "Illustrative gameplay tier 1", "breach": breach, "breach_pct": breach_pct,
            "fine": 5_000_000.0, "wind_tunnel_cut": 10, "point_deduction": 0,
        }
    return {
        "label": "Illustrative gameplay tier 2", "breach": breach, "breach_pct": breach_pct,
        "fine": 10_000_000.0, "wind_tunnel_cut": 20, "point_deduction": 10,
    }


def breach_preview(con, extra_spend=0.0):
    spend = total_spend(con) + max(0.0, float(extra_spend))
    reserve = crash_contingency(con)
    sanction = sanction_for(spend)
    remaining = CAP - spend
    discretionary_remaining = remaining - reserve["remaining"]
    return {
        "spend": spend, "remaining": remaining, "over_cap": max(0.0, spend - CAP),
        "reserve_remaining": reserve["remaining"],
        "discretionary_remaining": discretionary_remaining,
        "contingency_at_risk": max(0.0, -discretionary_remaining),
        "sanction": sanction,
    }


def crash_contingency(con):
    state = active_state(con)
    if not state:
        return {"target": 0.0, "used": 0.0, "remaining": 0.0, "uncovered": 0.0}
    used = float(con.execute(
        """SELECT COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END),0) FROM career_ledger
        WHERE kind IN (
            'repair_full','repair_minimum','repair_custom','repair_manual','repair',
            'prototype_repair_plan'
        )"""
    ).fetchone()[0])
    target = max(0.0, float(state.get("crash_reserve_target", 0)))
    return {
        "target": target, "used": used, "remaining": max(0.0, target - used),
        "uncovered": max(0.0, used - target),
    }


def set_crash_reserve(con, target):
    state = active_state(con)
    if not state:
        raise ValueError("Start a simulation before setting a crash contingency.")
    target = max(0.0, float(target))
    con.execute("UPDATE career_state SET crash_reserve_target = ? WHERE id = 1", (target,))
    existing = con.execute(
        "SELECT id FROM career_ledger WHERE kind = 'crash_reserve_allocation' ORDER BY id LIMIT 1"
    ).fetchone()
    effect = f"Crash contingency: {money(target)} reserved for local repair charges and explicitly committed prototype plans."
    if existing:
        con.execute(
            "UPDATE career_ledger SET amount = ?, note = ?, effect = ? WHERE id = ?",
            (target, "Dedicated crash contingency allocation", effect, existing["id"]),
        )
    else:
        _insert_ledger(con, 0, "Pre-season", "Other", target, "crash_reserve_allocation", "Dedicated crash contingency allocation", effect, counts_to_cap=False)
    con.commit()


def commit_investment(con, category, amount, note="Race-weekend package"):
    """Record a budget decision without blocking it at the gameplay cap."""
    state = active_state(con)
    if not state or state["status"] != "active":
        raise ValueError("Start a simulation before committing an upgrade.")
    if category not in CATEGORIES or float(amount) <= 0:
        raise ValueError("Choose a category and a positive CAD amount.")
    future = int(state["current_round"] > state["switch_round"] and category in CURRENT_CAR_CATEGORIES)
    target = "future car" if future else "2025 budget"
    _insert_ledger(
        con, state["current_round"], "Pre-race", category, amount, "upgrade",
        f"{note} — {target}", _investment_effect(category, future), future_car=future,
    )
    con.commit()
    return bool(future)


def ordered_sessions(round_number):
    if replay_available():
        return replay_session_names(round_number)
    return ["Sprint Qualifying", "Sprint", "Qualifying", "Grand Prix"] if CALENDAR[round_number - 1]["sprint"] else ["Qualifying", "Grand Prix"]


def next_session(con):
    state = active_state(con)
    if not state or state["status"] != "active":
        return None
    return f"Advance {CALENDAR[state['current_round'] - 1]['name']} weekend"


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalise_row(row):
    result = dict(row)
    result["points"] = _int(result.get("points"), 0)
    result["position"] = result.get("position") or result.get("position_display") or ""
    result.setdefault("position_display", str(result["position"]))
    result.setdefault("gap_display", result.get("gap") or result.get("time_display") or result.get("status") or "")
    result.setdefault("time_display", result.get("status") or "")
    result.setdefault("status", result.get("time_display") or "")
    return result


def _store_weekend_sessions(con, state, round_number):
    weekend = replay_weekend(round_number)
    sessions = weekend.get("sessions", {})
    for session_name in replay_session_names(round_number):
        session = sessions.get(session_name, {})
        rows = [_normalise_row(row) for row in session.get("rows", [])]
        payload = {
            "results": rows,
            "notes": session.get("notes", []),
            "source": session.get("source_url") or session.get("source") or weekend.get("source_url") or weekend.get("source") or "Local 2025 historical replay bundle",
        }
        con.execute(
            """INSERT OR REPLACE INTO career_sessions(round_number, session_name, results_json, created_at)
            VALUES (?,?,?,?)""",
            (round_number, session_name, json.dumps(payload), date.today().isoformat()),
        )
        if session_name in {"Sprint", "Grand Prix"}:
            for row in rows:
                team_id = row.get("team_id")
                points = _int(row.get("points"), 0)
                if team_id in TEAMS and points:
                    con.execute("UPDATE career_standings SET points = points + ? WHERE team_id = ?", (points, team_id))


def _category_for_incident(event):
    components = " ".join(event.get("components") or []).lower()
    if any(word in components for word in ("floor", "wing", "suspension", "chassis", "bodywork", "sidepod", "gearbox")):
        return "Chassis / structures"
    return "Other"


def _record_historical_incidents(con, state, round_number):
    for event in incidents_for(state["team_id"], round_number):
        title = event.get("title") or f"{event.get('driver', 'Team')} weekend review"
        exists = con.execute(
            "SELECT 1 FROM career_incidents WHERE round_number = ? AND title = ?", (round_number, title)
        ).fetchone()
        if exists:
            continue
        low = max(0.0, float(event.get("cost_low_cad", 0) or 0))
        high = max(low, float(event.get("cost_high_cad", low) or low))
        con.execute(
            """INSERT INTO career_incidents
            (round_number,title,amount,category,penalty,state,reason,responsible,source,created_at,
             session_name,driver_id,kind,components,cost_low,cost_high,estimate_label,safety_critical,
             repair_required,chosen_amount,source_url)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                round_number, title, low, _category_for_incident(event), 0.0, "pending",
                event.get("reason", "Official result status recorded."),
                event.get("responsible", "Not officially assigned"),
                event.get("source", "Historical 2025 incident bundle"), date.today().isoformat(),
                event.get("session", "Grand Prix"), event.get("driver_id"), event.get("kind", "incident"),
                ", ".join(event.get("components") or ["Damage components not publicly confirmed"]),
                low, high, event.get("estimate_label", "No repair cost established"),
                int(bool(event.get("safety_critical", False))), int(bool(event.get("repair_required", False))),
                0.0, event.get("source_url", event.get("source", "")),
            ),
        )


def rebase_active_replay(con):
    """Move a legacy active save to exact historical results without losing finance rows."""
    state = active_state(con)
    if not state or int(state.get("replay_version", 0)) >= REPLAY_VERSION or not replay_available():
        return False
    completed = max(0, min(len(CALENDAR), int(state["current_round"]) - 1))
    con.execute("DELETE FROM career_sessions")
    con.execute("DELETE FROM career_standings")
    # Prototype decisions store an immutable text/source snapshot rather than a
    # foreign key to the rebuilt incident rows, so their local audit trail and
    # corresponding ledger entries remain internally consistent across a rebase.
    # Synthetic incidents cannot be reconciled with source-backed history.
    con.execute("DELETE FROM career_incidents")
    _initialize_standings(con)
    for round_number in range(1, completed + 1):
        _store_weekend_sessions(con, state, round_number)
        _record_historical_incidents(con, state, round_number)
    reserve = float(state.get("crash_reserve_target", 0) or 0)
    if reserve <= 0:
        reserve = min(5_000_000.0, max(0.0, CAP - total_spend(con)))
    con.execute(
        "UPDATE career_state SET session_index = 0, replay_version = ?, crash_reserve_target = ? WHERE id = 1",
        (REPLAY_VERSION, reserve),
    )
    row = con.execute("SELECT id FROM career_ledger WHERE kind = 'crash_reserve_allocation' LIMIT 1").fetchone()
    effect = f"Crash contingency: {money(reserve)} reserved for local repair charges and explicitly committed prototype plans."
    if row:
        con.execute("UPDATE career_ledger SET amount = ?, note = ?, effect = ?, counts_to_cap = 0 WHERE id = ?", (reserve, "Dedicated crash contingency allocation", effect, row["id"]))
    else:
        _insert_ledger(con, 0, "Pre-season", "Other", reserve, "crash_reserve_allocation", "Dedicated crash contingency allocation", effect, counts_to_cap=False)
    con.commit()
    return True


def run_weekend(con):
    """Persist every official session from the current weekend in one action."""
    state = active_state(con)
    if not state or state["status"] != "active":
        raise ValueError("No active 2025 replay is available.")
    if not replay_available():
        raise ValueError("The local exact-2025 replay data is unavailable.")
    round_number = int(state["current_round"])
    overdue_critical = unresolved_critical_incidents(con, before_round=round_number)
    if overdue_critical:
        names = ", ".join(row["title"] for row in overdue_critical)
        raise ValueError(f"Record the project's required repair decision before advancing: {names}.")
    _store_weekend_sessions(con, state, round_number)
    _record_historical_incidents(con, state, round_number)
    if round_number >= len(CALENDAR):
        con.execute("UPDATE career_state SET current_round = ?, session_index = 0, status = 'complete', replay_version = ? WHERE id = 1", (round_number, REPLAY_VERSION))
    else:
        con.execute("UPDATE career_state SET current_round = ?, session_index = 0, replay_version = ? WHERE id = 1", (round_number + 1, REPLAY_VERSION))
    con.commit()
    return {"round": round_number, "sessions": session_results(con, round_number)}


def session_results(con, round_number=None):
    query = "SELECT * FROM career_sessions"
    params = ()
    if round_number is not None:
        query += " WHERE round_number = ?"
        params = (round_number,)
    query += " ORDER BY round_number DESC, id ASC"
    records = []
    for row in con.execute(query, params):
        item = dict(row)
        payload = json.loads(item.pop("results_json"))
        item["results"] = payload.get("results", payload if isinstance(payload, list) else [])
        item["notes"] = payload.get("notes", []) if isinstance(payload, dict) else []
        item["source"] = payload.get("source", "Local 2025 historical replay bundle") if isinstance(payload, dict) else "Local 2025 historical replay bundle"
        records.append(item)
    return records


def last_completed_round(con):
    row = con.execute("SELECT MAX(round_number) AS round_number FROM career_sessions").fetchone()
    return int(row["round_number"]) if row and row["round_number"] is not None else None


def standings(con):
    rows = []
    for row in con.execute("SELECT team_id, points FROM career_standings"):
        if row["team_id"] not in TEAMS:
            continue
        team = TEAMS[row["team_id"]]
        rows.append({
            "Team": team["name"], "team_id": row["team_id"], "Points": int(row["points"]),
            "Historical 2025 points": team["historical_points"],
        })
    rows.sort(key=lambda item: (-item["Points"], TEAMS[item["team_id"]]["historical_rank"]))
    for position, item in enumerate(rows, start=1):
        item["Position"] = position
    return rows


def pending_incidents(con):
    return [
        dict(row) for row in con.execute(
            "SELECT * FROM career_incidents WHERE state IN ('pending','deferred') ORDER BY round_number, id"
        ).fetchall()
    ]


def unresolved_critical_incidents(con, before_round=None):
    """Return project-flagged critical records that still hold the replay gate.

    This is a workflow rule for the local historical replay. It is deliberately
    not a real-world vehicle release, inspection, or safety certification.
    """
    query = """SELECT * FROM career_incidents
        WHERE safety_critical = 1 AND state IN ('pending', 'deferred')"""
    params = []
    if before_round is not None:
        query += " AND round_number < ?"
        params.append(int(before_round))
    query += " ORDER BY round_number, id"
    return [dict(row) for row in con.execute(query, params).fetchall()]


def safety_planning_snapshot(con):
    """Expose only the safety-planning evidence already stored by the replay.

    The first planning view intentionally does not calculate a readiness score,
    repair duration, spare availability, risk probability, or release outcome.
    Those inputs are not present in the bundled public data.
    """
    state = active_state(con)
    if not state:
        return None
    records = [
        dict(row) for row in con.execute(
            "SELECT * FROM career_incidents ORDER BY round_number, id"
        ).fetchall()
    ]
    manual_records = [item for item in records if item.get("kind") == "manual"]
    historical_records = [item for item in records if item.get("kind") != "manual"]
    open_records = [item for item in records if item["state"] in {"pending", "deferred"}]
    open_repair_records = [item for item in open_records if bool(item.get("repair_required"))]
    open_critical_records = [item for item in open_records if bool(item.get("safety_critical"))]
    source_linked_records = [
        item for item in historical_records
        if str(item.get("source_url") or "").startswith(("https://", "http://"))
    ]
    return {
        "state": state,
        "records": records,
        "historical_records": historical_records,
        "manual_records": manual_records,
        "open_records": open_records,
        "open_repair_records": open_repair_records,
        "open_critical_records": open_critical_records,
        "replay_hold_incidents": unresolved_critical_incidents(
            con, before_round=state["current_round"]
        ),
        "source_linked_records": source_linked_records,
        "crash_contingency": crash_contingency(con),
        "readiness_model": {
            "state": "not_modelled",
            "reason": (
                "Verified spare inventory, repair duration, inspection/sign-off, and release approval "
                "are not available in the bundled public record."
            ),
        },
    }


def funding_source_capacity(con, category):
    """Return local planned spend that can be explicitly reprioritised.

    This is intentionally a local finance model: it represents planned R&D or
    operating spend recorded in this app, minus earlier prototype
    reprioritisations. It is not a team cash balance or an FIA accounting rule.
    """
    if category not in CATEGORIES:
        raise ValueError("Choose a valid local funding source category.")
    amount = float(con.execute(
        """SELECT COALESCE(SUM(amount),0) FROM career_ledger
        WHERE category = ? AND (
            (kind IN ('preseason_rnd', 'upgrade') AND future_car = 0)
            OR kind = 'prototype_funding_reallocation'
        )""",
        (category,),
    ).fetchone()[0])
    return max(0.0, amount)


def _safety_snapshot_value(value, fallback):
    """Decode an older malformed saved snapshot without crashing the app."""
    return value if isinstance(value, dict) else fallback


def _bounded_modelled_capacity(value, live_capacity):
    """Keep a user-protected planning capacity, but never exceed live capacity.

    Invalid values are deliberately passed through for the pure safety engine to
    report as a HOLD input error instead of silently becoming an affordable
    plan.
    """
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return value
    if not math.isfinite(numeric) or numeric < 0:
        return value
    return min(numeric, max(0.0, float(live_capacity)))


def _canonical_json(value):
    """Serialize local audit values deterministically and reject non-finite data."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    )


def _historical_context_text(value):
    """Normalise an app-stored display field without adding a new fact."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _historical_context_number(value):
    """Keep a finite non-negative pre-existing local estimate, if one exists."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return max(0.0, number)


def _historical_context_flag(value):
    """Read SQLite-style flags without treating arbitrary non-empty text as true."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def historical_incident_source_context(incident):
    """Create a pure, bounded context snapshot for a historical repair record.

    The snapshot intentionally has no incident id or database foreign key.  It
    copies only a fixed list of app-held historical/context fields, labels the
    existing cost band as a *local estimate*, and fingerprints that exact
    payload.  It never adds a repair method, cost, duration, spare count,
    inspection result, completion claim, or release decision.
    """
    try:
        record = dict(incident)
    except (TypeError, ValueError) as error:
        raise ValueError("A historical incident record is required for this launcher.") from error

    if (_historical_context_text(record.get("kind")) or "").lower() == "manual":
        raise ValueError("A local manual entry cannot be used as historical incident context.")
    if not _historical_context_flag(record.get("repair_required")):
        raise ValueError("Only historical records marked repair-required can start a prototype case.")
    try:
        round_number = int(record.get("round_number"))
    except (TypeError, ValueError) as error:
        raise ValueError("The historical record has no valid round number.") from error
    title = _historical_context_text(record.get("title"))
    if not title:
        raise ValueError("The historical record has no title to preserve.")

    low = _historical_context_number(record.get("cost_low"))
    high = _historical_context_number(record.get("cost_high"))
    if low is not None and high is not None:
        high = max(low, high)
    facts = {
        "round_number": round_number,
        "title": title,
        "session_name": _historical_context_text(record.get("session_name")),
        "driver_id": _historical_context_text(record.get("driver_id")),
        "incident_kind": _historical_context_text(record.get("kind")),
        "reason": _historical_context_text(record.get("reason")),
        "responsible": _historical_context_text(record.get("responsible")),
        "damage_area": _historical_context_text(record.get("components")),
        "source": _historical_context_text(record.get("source")),
        "source_url": _historical_context_text(record.get("source_url")),
        "record_state_at_launch": _historical_context_text(record.get("state")),
        "repair_required": True,
        "project_safety_critical": _historical_context_flag(record.get("safety_critical")),
        "app_local_category": _historical_context_text(record.get("category")),
        "preexisting_local_estimate": {
            "low_cad": low,
            "high_cad": high,
            "label": _historical_context_text(record.get("estimate_label")),
        },
    }
    payload = {
        "schema": HISTORICAL_INCIDENT_CONTEXT_SCHEMA,
        "origin": HISTORICAL_INCIDENT_CONTEXT_ORIGIN,
        "display_label": f"Historical incident context · Round {round_number} · {title}",
        "facts": facts,
        "data_boundary": (
            "App-preserved historical context only. It does not establish repair method, cost, "
            "duration, spare inventory, component condition, inspection/sign-off, completion, "
            "or vehicle release."
        ),
    }
    return {
        **payload,
        "sha256": hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest(),
    }


def _validate_historical_context_reference(source_ref, source_context):
    """Validate the bounded launcher snapshot before it becomes a decision basis.

    This verifies only that the app-preserved context has not been detached from
    its own schema/origin/hash convention. It does not turn local context into
    external source verification or a claim about a real repair.
    """
    reference = str(source_ref or "")
    context = source_context if isinstance(source_context, dict) else None
    is_historical_reference = reference.startswith("historical-context:")
    is_historical_context = bool(context) and (
        context.get("schema") == HISTORICAL_INCIDENT_CONTEXT_SCHEMA
        or context.get("origin") == HISTORICAL_INCIDENT_CONTEXT_ORIGIN
    )
    if reference.startswith("historical:"):
        raise ValueError(
            "Historical source references must use a bounded historical-context launcher snapshot."
        )
    if not is_historical_reference and not is_historical_context:
        return
    if not is_historical_reference:
        raise ValueError(
            "An app-preserved historical context must use its matching historical-context source reference."
        )
    if context is None:
        raise ValueError("A historical-context source reference needs its bounded context snapshot.")

    expected_keys = {
        "schema", "origin", "display_label", "facts", "data_boundary", "sha256",
    }
    if set(context) != expected_keys:
        raise ValueError(
            "The historical-context snapshot has unexpected or missing fields and cannot be recorded."
        )
    if context.get("schema") != HISTORICAL_INCIDENT_CONTEXT_SCHEMA:
        raise ValueError("The historical-context snapshot has an unsupported schema.")
    if context.get("origin") != HISTORICAL_INCIDENT_CONTEXT_ORIGIN:
        raise ValueError("The historical-context snapshot has an unsupported origin.")
    if not isinstance(context.get("facts"), dict):
        raise ValueError("The historical-context snapshot has no readable app-preserved facts.")

    payload = {
        "schema": context["schema"],
        "origin": context["origin"],
        "display_label": context["display_label"],
        "facts": context["facts"],
        "data_boundary": context["data_boundary"],
    }
    recorded_hash = context.get("sha256")
    if not isinstance(recorded_hash, str) or len(recorded_hash) != 64:
        raise ValueError("The historical-context snapshot has no valid SHA-256 fingerprint.")
    try:
        computed_hash = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"The historical-context snapshot cannot be fingerprinted. ({error})"
        ) from error
    if computed_hash != recorded_hash.lower():
        raise ValueError(
            "The historical-context snapshot does not match its recorded SHA-256 fingerprint."
        )
    if reference != f"historical-context:{computed_hash}":
        raise ValueError(
            "The historical-context source reference does not match its bounded snapshot fingerprint."
        )


def _decision_fingerprint(
    round_number, source_ref, source_label, source_context, profile_id, option_id,
    funding_source, evaluation, catalog_identity, profile_snapshot,
):
    """Return a stable unique identity for one immutable local decision basis."""
    payload = {
        "round_number": int(round_number),
        "source_ref": str(source_ref or ""),
        "source_label": str(source_label or "Prototype case"),
        "source_context": source_context if isinstance(source_context, dict) else {},
        "profile_id": str(profile_id or ""),
        "option_id": str(option_id or ""),
        "funding_source": str(funding_source or ""),
        "evaluation": evaluation,
        "assumption_catalog": catalog_identity,
        "profile_snapshot": profile_snapshot,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _decision_fingerprint_check(decision):
    """Recompute a saved plan's local decision-basis fingerprint.

    The prototype uses a local SQLite database, so this is deliberately a
    *consistency/tamper-evidence* check rather than a claim of tamper-proof or
    externally verified storage.  It makes an accidental or untracked change
    to the frozen fields visible before they can be used to create funding
    ledger entries.
    """
    if not isinstance(decision, dict):
        return {
            "state": "UNVERIFIABLE",
            "matches": False,
            "recorded_fingerprint": None,
            "recomputed_fingerprint": None,
            "message": "The saved prototype decision is not a readable record, so its local fingerprint cannot be checked.",
        }

    recorded = decision.get("decision_fingerprint")
    if not isinstance(recorded, str) or not recorded.strip():
        return {
            "state": "LEGACY_UNVERIFIABLE",
            "matches": False,
            "recorded_fingerprint": recorded,
            "recomputed_fingerprint": None,
            "message": (
                "This saved prototype record has no decision-basis fingerprint. Re-record it under the "
                "current local prototype workflow before funding."
            ),
        }
    recorded = recorded.strip().lower()
    if len(recorded) != 64 or any(character not in "0123456789abcdef" for character in recorded):
        return {
            "state": "UNVERIFIABLE",
            "matches": False,
            "recorded_fingerprint": recorded,
            "recomputed_fingerprint": None,
            "message": "The saved prototype decision has an invalid decision-basis fingerprint format.",
        }

    warnings = decision.get("integrity_warnings")
    if warnings:
        return {
            "state": "UNVERIFIABLE",
            "matches": False,
            "recorded_fingerprint": recorded,
            "recomputed_fingerprint": None,
            "message": (
                "The saved prototype decision has unreadable frozen data, so its local fingerprint cannot be "
                "recomputed. Re-record the plan before funding."
            ),
        }

    frozen_values = {
        "source_context": decision.get("source_context"),
        "evaluation": decision.get("snapshot"),
        "assumption_catalog": decision.get("assumption_catalog"),
        "profile_snapshot": decision.get("profile_snapshot"),
    }
    invalid_values = [name for name, value in frozen_values.items() if not isinstance(value, dict)]
    if invalid_values:
        return {
            "state": "UNVERIFIABLE",
            "matches": False,
            "recorded_fingerprint": recorded,
            "recomputed_fingerprint": None,
            "message": (
                "The saved prototype decision is missing readable frozen "
                f"{', '.join(invalid_values)} data, so its local fingerprint cannot be recomputed."
            ),
        }

    try:
        recomputed = _decision_fingerprint(
            decision.get("round_number"),
            decision.get("source_ref"),
            decision.get("source_label"),
            frozen_values["source_context"],
            decision.get("profile_id"),
            decision.get("option_id"),
            decision.get("funding_source"),
            frozen_values["evaluation"],
            frozen_values["assumption_catalog"],
            frozen_values["profile_snapshot"],
        )
    except (TypeError, ValueError) as error:
        return {
            "state": "UNVERIFIABLE",
            "matches": False,
            "recorded_fingerprint": recorded,
            "recomputed_fingerprint": None,
            "message": (
                "The saved prototype decision contains values that cannot be checked against its local "
                f"fingerprint. Re-record the plan before funding. ({error})"
            ),
        }

    if recomputed != recorded:
        return {
            "state": "MISMATCH",
            "matches": False,
            "recorded_fingerprint": recorded,
            "recomputed_fingerprint": recomputed,
            "message": (
                "The saved prototype decision fields no longer match their recorded local fingerprint. "
                "Do not fund this record; re-record the plan from the displayed assumptions."
            ),
        }
    return {
        "state": "MATCHED",
        "matches": True,
        "recorded_fingerprint": recorded,
        "recomputed_fingerprint": recomputed,
        "message": "Saved plan fields match the recorded local decision-basis fingerprint.",
    }


def _append_external_hold(evaluation, code, label, category="integrity", detail=None):
    """Add a durable non-engineering hold condition to a rule-engine result."""
    updated = dict(evaluation)
    blockers = list(updated.get("blockers") or [])
    gaps = list(updated.get("gaps") or [])
    if not any(item.get("code") == code for item in gaps if isinstance(item, dict)):
        gap = {"code": code, "label": label, "category": category}
        if detail:
            gap["detail"] = detail
        gaps.append(gap)
    if label not in blockers:
        blockers.append(label)
    updated.update({
        "blockers": blockers,
        "gaps": gaps,
        "status": "HOLD",
        "eligible_for_review": False,
    })
    return updated


def _catalog_check(recorded_identity):
    """Check whether the current editable catalog still matches a saved basis."""
    if not isinstance(recorded_identity, dict) or not recorded_identity.get("sha256"):
        return {
            "state": "LEGACY_UNVERIFIABLE",
            "matches": False,
            "recorded": recorded_identity if isinstance(recorded_identity, dict) else {},
            "current": None,
            "message": (
                "This saved record has no frozen assumptions fingerprint. Re-record it under the current "
                "prototype assumptions before local funding."
            ),
        }
    if recorded_identity.get("rules_engine_version") != safety_engine.RULES_ENGINE_VERSION:
        return {
            "state": "RULES_ENGINE_CHANGED",
            "matches": False,
            "recorded": recorded_identity,
            "current": None,
            "message": (
                "The prototype rule-engine version changed after this record was saved. Re-record the plan "
                "before local funding."
            ),
        }
    try:
        current = safety_engine.catalog_identity(safety_engine.load_assumptions())
    except safety_engine.AssumptionError as error:
        return {
            "state": "CURRENT_CATALOG_UNAVAILABLE",
            "matches": False,
            "recorded": recorded_identity,
            "current": None,
            "message": (
                "The current editable assumptions catalog cannot be verified. Restore a valid matching "
                f"catalog before local funding. ({error})"
            ),
        }
    if current["sha256"] != recorded_identity.get("sha256"):
        return {
            "state": "CATALOG_CHANGED",
            "matches": False,
            "recorded": recorded_identity,
            "current": current,
            "message": (
                "The editable assumptions catalog changed after this plan was recorded. Re-record it under "
                "the current catalog before local funding."
            ),
        }
    return {
        "state": "MATCHED",
        "matches": True,
        "recorded": recorded_identity,
        "current": current,
        "message": "Current catalog fingerprint matches the frozen local planning basis.",
    }


def _saved_profile_for_funding(decision):
    """Restore the selected frozen assumptions; legacy unfrozen rows cannot fund."""
    snapshot = decision.get("profile_snapshot")
    if not isinstance(snapshot, dict) or not snapshot:
        raise ValueError(
            "This saved prototype record has no immutable rule snapshot. Re-record it under the current "
            "assumptions before local funding."
        )
    return safety_engine.profile_from_frozen_snapshot(
        snapshot, decision.get("profile_id"), decision.get("option_id")
    )


def _invalid_live_evaluation(
    reason, code="SAVED_RECORD_INVALID", catalog_check=None, decision_fingerprint_check=None,
):
    return {
        "status": "HOLD",
        "eligible_for_review": False,
        "blockers": [reason],
        "gaps": [{"code": code, "label": reason, "category": "integrity", "detail": reason}],
        "catalog_check": catalog_check,
        "decision_fingerprint_check": decision_fingerprint_check,
        "disclaimer": (
            "Prototype planning result only. Human engineering review remains required; "
            "this does not certify, release, or predict the safety of a vehicle."
        ),
    }


def record_safety_decision(
    con, source_ref, source_label, source_context, funding_source, profile_id, option_id, case_inputs
):
    """Re-evaluate and persist a local prototype planning record.

    A caller cannot submit a hand-written ``REVIEW_ELIGIBLE`` object. The pure
    rules engine calculates it again from the current, visibly editable inputs.
    Repeated clicks with the same round/case/input snapshot are idempotent.
    """
    fingerprint = None
    evaluation = None
    try:
        # The unique fingerprint is the durable backstop; this lock also makes
        # repeated clicks from separate Streamlit tabs deterministic.
        con.execute("BEGIN IMMEDIATE")
        state = active_state(con)
        if not state or state["status"] != "active":
            raise ValueError("Start an active replay before recording a prototype planning decision.")
        funding_source = str(funding_source or "")
        if funding_source not in CATEGORIES:
            raise ValueError("Choose a valid local funding source category.")
        source_ref = str(source_ref or "")
        source_context_value = source_context if isinstance(source_context, dict) else {}
        _validate_historical_context_reference(source_ref, source_context_value)
        catalog = safety_engine.load_assumptions()
        catalog_identity = safety_engine.catalog_identity(catalog)
        profile = safety_engine.profile_for(str(profile_id or ""), catalog["profiles"])
        # An invalid stale Streamlit option must never become a persistent record.
        safety_engine.option_for(profile, str(option_id or ""))
        frozen_profile = safety_engine.frozen_profile_snapshot(profile, str(option_id))
        inputs = dict(case_inputs) if isinstance(case_inputs, dict) else {}
        # These values are never trusted from the UI. They are derived from the
        # live local ledger at the instant the decision is recorded.
        live_source_capacity = funding_source_capacity(con, funding_source)
        inputs.update({
            "funding_source": funding_source,
            "reserve_before": crash_contingency(con)["remaining"],
            "funding_capacity": _bounded_modelled_capacity(
                inputs.get("funding_capacity"), live_source_capacity
            ),
            "live_source_capacity": live_source_capacity,
            "cap_headroom": max(0.0, CAP - total_spend(con)),
        })
        evaluation = safety_engine.evaluate_option(profile, str(option_id), inputs)
        evaluation["assumption_catalog"] = catalog_identity
        evaluation["frozen_rule_basis"] = {
            "profile_id": frozen_profile["id"],
            "option_id": str(option_id),
            "profile_sha256": hashlib.sha256(
                _canonical_json(frozen_profile).encode("utf-8")
            ).hexdigest(),
        }
        source_context_json = _canonical_json(source_context_value)
        snapshot_json = _canonical_json(evaluation)
        catalog_json = _canonical_json(catalog_identity)
        profile_snapshot_json = _canonical_json(frozen_profile)
        fingerprint = _decision_fingerprint(
            state["current_round"], source_ref, source_label, source_context_value,
            profile_id, option_id, funding_source, evaluation, catalog_identity, frozen_profile,
        )
        existing = con.execute(
            "SELECT id FROM career_safety_decisions WHERE decision_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        if existing:
            con.commit()
            return {"id": int(existing["id"]), "evaluation": evaluation, "created": False}
        cursor = con.execute(
            """INSERT INTO career_safety_decisions
            (round_number, source_ref, source_label, source_context_json, profile_id, option_id,
             funding_source, status, blockers_json, snapshot_json, assumption_catalog_json,
             profile_snapshot_json, decision_fingerprint, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                int(state["current_round"]), str(source_ref or ""),
                str(source_label or "Prototype case"), source_context_json, str(profile_id),
                str(option_id), funding_source, evaluation["status"],
                _canonical_json(evaluation["blockers"]), snapshot_json, catalog_json,
                profile_snapshot_json, fingerprint, date.today().isoformat(),
            ),
        )
        con.commit()
        return {"id": int(cursor.lastrowid), "evaluation": evaluation, "created": True}
    except sqlite3.IntegrityError:
        if con.in_transaction:
            con.rollback()
        if fingerprint:
            existing = con.execute(
                "SELECT id FROM career_safety_decisions WHERE decision_fingerprint = ?", (fingerprint,)
            ).fetchone()
            if existing:
                return {"id": int(existing["id"]), "evaluation": evaluation or {}, "created": False}
        raise
    except sqlite3.OperationalError as error:
        if con.in_transaction:
            con.rollback()
        busy_codes = {getattr(sqlite3, "SQLITE_BUSY", None), getattr(sqlite3, "SQLITE_LOCKED", None)}
        if getattr(error, "sqlite_errorcode", None) in busy_codes or "locked" in str(error).lower():
            raise ValueError("The local prototype ledger is busy. Wait a moment and record the plan once more.") from error
        raise
    except Exception:
        if con.in_transaction:
            con.rollback()
        raise


def safety_decisions(con, limit=20):
    """Return the newest saved prototype planning records with decoded evidence."""
    rows = con.execute(
        "SELECT * FROM career_safety_decisions ORDER BY id DESC LIMIT ?", (max(1, int(limit)),)
    ).fetchall()
    records = []
    for row in rows:
        item = dict(row)
        warnings = []

        def decode(column, key, expected_type, fallback):
            raw = item.pop(column, None)
            try:
                value = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                warnings.append(f"{column} is not valid JSON.")
                value = fallback
            if not isinstance(value, expected_type):
                warnings.append(f"{column} has an unexpected JSON type.")
                value = fallback
            item[key] = value

        decode("blockers_json", "blockers", list, [])
        decode("snapshot_json", "snapshot", dict, {})
        decode("source_context_json", "source_context", dict, {})
        decode("assumption_catalog_json", "assumption_catalog", dict, {})
        decode("profile_snapshot_json", "profile_snapshot", dict, {})
        decode("funding_snapshot_json", "funding_snapshot", dict, {})
        item["integrity_warnings"] = warnings
        records.append(item)
    return records


def _live_safety_evaluation(con, decision):
    """Re-check mutable finance against the record's frozen prototype basis."""
    decision_fingerprint_check = _decision_fingerprint_check(decision)
    catalog_check = _catalog_check(decision.get("assumption_catalog"))
    if not decision_fingerprint_check["matches"]:
        if decision.get("integrity_warnings"):
            code = "SAVED_RECORD_INTEGRITY"
        else:
            code = (
                "DECISION_FINGERPRINT_MISMATCH"
                if decision_fingerprint_check["state"] == "MISMATCH"
                else "DECISION_FINGERPRINT_UNVERIFIABLE"
            )
        return _invalid_live_evaluation(
            decision_fingerprint_check["message"], code, catalog_check, decision_fingerprint_check,
        )

    try:
        _validate_historical_context_reference(
            decision.get("source_ref"), decision.get("source_context"),
        )
    except ValueError as error:
        return _invalid_live_evaluation(
            str(error), "HISTORICAL_CONTEXT_INVALID", catalog_check, decision_fingerprint_check,
        )

    snapshot = _safety_snapshot_value(decision.get("snapshot"), {})
    inputs = _safety_snapshot_value(snapshot.get("case_inputs"), {}).copy()
    source = str(decision.get("funding_source") or "")
    if source not in CATEGORIES:
        return _invalid_live_evaluation(
            "The saved prototype record does not have a valid local funding source.",
            "SAVED_SOURCE_INVALID",
            catalog_check,
            decision_fingerprint_check,
        )
    try:
        profile = _saved_profile_for_funding(decision)
    except ValueError as error:
        return _invalid_live_evaluation(
            str(error), "FROZEN_RULE_BASIS_INVALID", catalog_check, decision_fingerprint_check,
        )
    live_source_capacity = funding_source_capacity(con, source)
    inputs.update({
        "funding_source": source,
        "reserve_before": crash_contingency(con)["remaining"],
        "funding_capacity": _bounded_modelled_capacity(
            inputs.get("funding_capacity"), live_source_capacity
        ),
        "live_source_capacity": live_source_capacity,
        "cap_headroom": max(0.0, CAP - total_spend(con)),
    })
    evaluation = safety_engine.evaluate_option(profile, str(decision.get("option_id") or ""), inputs)
    evaluation["assumption_catalog"] = decision.get("assumption_catalog", {})
    evaluation["catalog_check"] = catalog_check
    evaluation["decision_fingerprint_check"] = decision_fingerprint_check
    evaluation["frozen_rule_basis"] = snapshot.get("frozen_rule_basis", {})
    if not catalog_check["matches"]:
        evaluation = _append_external_hold(
            evaluation, "CATALOG_DRIFT", catalog_check["message"], "integrity"
        )
    if int(decision.get("round_number") or 0) != int(active_state(con)["current_round"]):
        evaluation = _append_external_hold(
            evaluation,
            "ROUND_CHANGED",
            "This prototype plan was recorded for an earlier replay round. Re-record it for the current round before local funding.",
            "workflow",
        )
    for warning in decision.get("integrity_warnings", []):
        evaluation = _append_external_hold(
            evaluation, "SAVED_RECORD_INTEGRITY", f"Saved prototype record integrity warning: {warning}",
            "integrity",
        )
    return evaluation


def _correlated_safety_ledger_entries(con, decision_id):
    """Return every local ledger row tied to a decision, including corrupt roles.

    The funding pointers are useful display fields but cannot be the sole
    idempotency authority: a locally editable database can contain correlated
    rows even when those pointers were cleared or damaged.
    """
    return [dict(row) for row in con.execute(
        "SELECT * FROM career_ledger WHERE safety_decision_id = ? ORDER BY id", (int(decision_id),)
    ).fetchall()]


def safety_decision_live_check(con, decision_id):
    """Return a visible current funding check without mutating a saved record."""
    decision = next(
        (item for item in safety_decisions(con, limit=10_000) if item["id"] == int(decision_id)), None
    )
    if not decision:
        raise ValueError("Choose a saved prototype planning record.")
    if decision.get("repair_ledger_id") is not None:
        decision_fingerprint_check = _decision_fingerprint_check(decision)
        return {
            "status": "REVIEW_REQUESTED" if decision_fingerprint_check["matches"] else "CHECK_REQUIRED",
            "eligible_for_review": False,
            "blockers": [] if decision_fingerprint_check["matches"] else [decision_fingerprint_check["message"]],
            "gaps": [],
            "catalog_check": _catalog_check(decision.get("assumption_catalog")),
            "decision_fingerprint_check": decision_fingerprint_check,
            "message": (
                "This local funding record was already created; no second funding action is available."
                if decision_fingerprint_check["matches"]
                else "This already-funded local record needs an integrity check; no second funding action is available."
            ),
        }
    correlated_entries = _correlated_safety_ledger_entries(con, decision["id"])
    if correlated_entries:
        decision_fingerprint_check = _decision_fingerprint_check(decision)
        return _invalid_live_evaluation(
            "This prototype record already has correlated local ledger entries but no repair-funding pointer. "
            "Inspect its receipt; no second funding action is available.",
            "FUNDING_LEDGER_ALREADY_PRESENT",
            _catalog_check(decision.get("assumption_catalog")),
            decision_fingerprint_check,
        )
    return _live_safety_evaluation(con, decision)


def _decision_ledger_entries(con, decision):
    """Return the ledger evidence correlated to one prototype decision."""
    ids = [
        value for value in (
            decision.get("repair_ledger_id"), decision.get("transfer_ledger_id"),
            decision.get("reserve_transfer_ledger_id"),
        ) if value is not None
    ]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    return [dict(row) for row in con.execute(
        f"SELECT * FROM career_ledger WHERE id IN ({placeholders}) ORDER BY id", tuple(ids)
    ).fetchall()]


def _audit_integer(value):
    """Return a SQLite-style integer identifier, or ``None`` when malformed."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or not numeric.is_integer():
        return None
    return int(numeric)


def _audit_amount(value, label, errors, positive=False, allow_negative=False):
    """Decode one audit amount without letting corrupted local rows crash a receipt."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        errors.append(f"{label} is not a numeric CAD amount.")
        return None
    if not math.isfinite(amount):
        errors.append(f"{label} is not a finite CAD amount.")
        return None
    if positive and amount <= 0:
        errors.append(f"{label} must be a positive CAD amount.")
        return None
    if not positive and not allow_negative and amount < 0:
        errors.append(f"{label} cannot be negative.")
        return None
    return amount


def _funding_snapshot_basis_integrity(decision, funding_snapshot, errors):
    """Bind funded amounts to the original fingerprinted planning basis.

    A funding snapshot records mutable live-finance facts at commit time, such
    as reserve and current source capacity.  The selected option, its modelled
    cost/resource values, transfer, and frozen rule basis must still agree with
    the original saved decision.  Otherwise a coordinated local edit to a
    ledger and funding snapshot could appear internally consistent while no
    longer representing the recorded plan.
    """
    recorded = decision.get("snapshot")
    if not isinstance(recorded, dict):
        errors.append("The frozen saved decision snapshot is not a JSON object.")
        return {}

    for field in ("profile_id", "option_id"):
        if funding_snapshot.get(field) != recorded.get(field):
            errors.append(
                f"Funding snapshot {field} does not match the frozen saved decision basis."
            )

    def compare_amount(field, positive=False):
        expected = _audit_amount(
            recorded.get(field), f"Frozen saved decision {field}", errors, positive=positive,
        )
        actual = _audit_amount(
            funding_snapshot.get(field), f"Funding snapshot {field}", errors, positive=positive,
        )
        if expected is not None and actual is not None and not math.isclose(
            expected, actual, rel_tol=0.0, abs_tol=0.01
        ):
            errors.append(
                f"Funding snapshot {field} does not match the frozen saved decision basis."
            )
        return actual

    values = {
        "estimated_cost_cad": compare_amount("estimated_cost_cad", positive=True),
        "planned_transfer_cad": compare_amount("planned_transfer_cad"),
        "estimated_work_hours": compare_amount("estimated_work_hours"),
        "spares_required": compare_amount("spares_required"),
        "reserve_floor_cad": compare_amount("reserve_floor_cad"),
    }
    if funding_snapshot.get("frozen_rule_basis") != recorded.get("frozen_rule_basis"):
        errors.append("Funding snapshot frozen_rule_basis does not match the frozen saved decision basis.")

    recorded_inputs = recorded.get("case_inputs")
    funding_inputs = funding_snapshot.get("case_inputs")
    if not isinstance(recorded_inputs, dict) or not isinstance(funding_inputs, dict):
        errors.append("Funding snapshot case inputs cannot be compared with the frozen saved decision basis.")
    else:
        expected_source = str(recorded_inputs.get("funding_source") or "")
        actual_source = str(funding_inputs.get("funding_source") or "")
        decision_source = str(decision.get("funding_source") or "")
        if expected_source != decision_source or actual_source != decision_source:
            errors.append("Funding snapshot funding source does not match the frozen saved decision basis.")
    return values


def _safety_ledger_link_integrity(con, decision, ledger_entries):
    """Audit a funded prototype record against its stored funding event.

    The local database remains editable, so this is an *evidence consistency*
    check, not tamper-proof accounting.  It deliberately reports malformed or
    older rows as ``CHECK_REQUIRED`` evidence instead of raising while a judge
    opens a receipt.
    """
    errors = list(decision.get("integrity_warnings", []))
    role_to_column = {
        "repair": "repair_ledger_id",
        "transfer": "transfer_ledger_id",
        "reserve_transfer": "reserve_transfer_ledger_id",
    }
    declared_ids = {}
    used_ids = {}
    for role, column in role_to_column.items():
        raw_id = decision.get(column)
        if raw_id is None:
            declared_ids[role] = None
            continue
        ledger_id = _audit_integer(raw_id)
        if ledger_id is None or ledger_id <= 0:
            errors.append(f"Saved decision field {column} is not a valid ledger id.")
            declared_ids[role] = None
            continue
        declared_ids[role] = ledger_id
        if ledger_id in used_ids:
            errors.append(
                f"Ledger entry #{ledger_id} is declared for both {used_ids[ledger_id]} and {role}."
            )
        else:
            used_ids[ledger_id] = role

    entries_by_id = {entry.get("id"): entry for entry in ledger_entries}
    decision_id = _audit_integer(decision.get("id"))
    for role, ledger_id in declared_ids.items():
        if ledger_id is None:
            continue
        entry = entries_by_id.get(ledger_id)
        if entry is None:
            errors.append(f"Missing linked local ledger row for {role}_ledger_id.")
            continue
        if _audit_integer(entry.get("safety_decision_id")) != decision_id:
            errors.append(f"Ledger entry #{ledger_id} is not correlated to this decision id.")

    correlated_entries = []
    if decision_id is not None:
        correlated_entries = [dict(row) for row in con.execute(
            "SELECT * FROM career_ledger WHERE safety_decision_id = ? ORDER BY id", (decision_id,)
        ).fetchall()]
        declared_set = {ledger_id for ledger_id in declared_ids.values() if ledger_id is not None}
        for entry in correlated_entries:
            if entry.get("id") not in declared_set:
                errors.append(
                    f"Ledger entry #{entry['id']} is correlated to this decision but is not declared by its funding record."
                )

    # An unfunded candidate intentionally has neither a funding event nor any
    # ledger rows.  Older funded rows remain viewable, but are flagged below if
    # their event evidence is absent or incomplete.
    has_funding_evidence = (
        any(ledger_id is not None for ledger_id in declared_ids.values())
        or decision.get("status") == "REVIEW_REQUESTED"
        or bool(decision.get("funding_snapshot"))
    )
    if not has_funding_evidence:
        return errors, correlated_entries

    funding_snapshot = decision.get("funding_snapshot")
    if not isinstance(funding_snapshot, dict):
        errors.append("Funding snapshot is not a JSON object.")
        return errors, correlated_entries
    funding_event = funding_snapshot.get("funding_event")
    if not isinstance(funding_event, dict):
        errors.append("Funded prototype record has no valid funding_event snapshot.")
        return errors, correlated_entries
    funding_basis = _funding_snapshot_basis_integrity(decision, funding_snapshot, errors)

    def snapshot_id_matches(field, role, required=False):
        declared_id = declared_ids[role]
        if field not in funding_event:
            errors.append(f"Funding snapshot is missing {field}.")
            return
        event_id = _audit_integer(funding_event.get(field))
        raw_event_id = funding_event.get(field)
        if raw_event_id is not None and (event_id is None or event_id <= 0):
            errors.append(f"Funding snapshot {field} is not a valid ledger id.")
            return
        if required and (declared_id is None or event_id is None):
            errors.append(f"Funded prototype record is missing required {field} linkage.")
            return
        if event_id != declared_id:
            errors.append(f"Funding snapshot {field} does not match the saved decision linkage.")

    snapshot_id_matches("repair_ledger_id", "repair", required=True)
    snapshot_id_matches("transfer_ledger_id", "transfer")
    snapshot_id_matches("reserve_transfer_ledger_id", "reserve_transfer")

    funded_round = _audit_integer(decision.get("funded_round_number"))
    event_round = _audit_integer(funding_event.get("funded_round_number"))
    decision_round = _audit_integer(decision.get("round_number"))
    if decision_round is None or decision_round < 0:
        errors.append("Saved decision round_number is not a valid replay round.")
    if funded_round is None or funded_round < 0:
        errors.append("Saved decision funded_round_number is not a valid replay round.")
    if event_round is None or event_round < 0:
        errors.append("Funding snapshot funded_round_number is not a valid replay round.")
    elif funded_round != event_round:
        errors.append("Funding snapshot funded_round_number does not match the saved decision.")
    if decision_round is not None and funded_round is not None and decision_round != funded_round:
        errors.append("Saved decision funded_round_number does not match the frozen decision round.")
    if decision_round is not None and event_round is not None and decision_round != event_round:
        errors.append("Funding snapshot funded_round_number does not match the frozen decision round.")

    expected_cost = funding_basis.get("estimated_cost_cad")
    expected_transfer = funding_basis.get("planned_transfer_cad")
    expected_repair_category = None
    frozen_profile = decision.get("profile_snapshot")
    if isinstance(frozen_profile, dict) and frozen_profile.get("ledger_category") in CATEGORIES:
        expected_repair_category = frozen_profile["ledger_category"]
    else:
        errors.append("Frozen prototype profile has no valid local repair ledger category.")
    funding_source = str(decision.get("funding_source") or "")
    if funding_source not in CATEGORIES:
        errors.append("Saved decision has no valid local funding source category.")

    def check_entry(role, expected_kind, expected_amount, expected_category, counts_to_cap):
        ledger_id = declared_ids[role]
        if ledger_id is None:
            return
        entry = entries_by_id.get(ledger_id)
        if entry is None:
            return
        if entry.get("kind") != expected_kind:
            errors.append(
                f"Ledger entry #{ledger_id} kind is {entry.get('kind')!r}; expected {expected_kind!r}."
            )
        if expected_category is not None and entry.get("category") != expected_category:
            errors.append(
                f"Ledger entry #{ledger_id} category is {entry.get('category')!r}; expected {expected_category!r}."
            )
        actual_amount = _audit_amount(
            entry.get("amount"), f"Ledger entry #{ledger_id} amount", errors, allow_negative=True
        )
        if actual_amount is not None and expected_amount is not None and not math.isclose(
            actual_amount, expected_amount, rel_tol=0.0, abs_tol=0.01
        ):
            errors.append(
                f"Ledger entry #{ledger_id} amount does not match the funding snapshot."
            )
        try:
            actual_counts_to_cap = int(entry.get("counts_to_cap"))
        except (TypeError, ValueError):
            actual_counts_to_cap = None
        if actual_counts_to_cap != int(counts_to_cap):
            errors.append(
                f"Ledger entry #{ledger_id} counts_to_cap does not match its prototype funding role."
            )
        entry_round = _audit_integer(entry.get("round_number"))
        if event_round is not None and entry_round != event_round:
            errors.append(
                f"Ledger entry #{ledger_id} round_number does not match the funding snapshot."
            )

    check_entry(
        "repair", "prototype_repair_plan", expected_cost, expected_repair_category, counts_to_cap=True
    )
    if expected_transfer is not None:
        if expected_transfer > 0:
            if declared_ids["transfer"] is None:
                errors.append("Funding snapshot requires a source-reallocation ledger row, but none is linked.")
            if declared_ids["reserve_transfer"] is None:
                errors.append("Funding snapshot requires a reserve-transfer ledger row, but none is linked.")
            check_entry(
                "transfer", "prototype_funding_reallocation", -expected_transfer, funding_source,
                counts_to_cap=True,
            )
            check_entry(
                "reserve_transfer", "prototype_reserve_transfer", expected_transfer, funding_source,
                counts_to_cap=False,
            )
        elif declared_ids["transfer"] is not None or declared_ids["reserve_transfer"] is not None:
            errors.append(
                "Funding snapshot records no transfer, but the saved decision links transfer ledger rows."
            )
    return errors, correlated_entries


def safety_decision_packet(con, decision_id):
    """Build a read-only JSON-ready local review-handoff receipt.

    This is an auditable app record, not a message sent to a reviewer and not a
    safety approval.  It deliberately includes the frozen planning basis and
    linked ledger rows so a judge can inspect what the prototype actually did.
    """
    decision = next(
        (item for item in safety_decisions(con, limit=10_000) if item["id"] == int(decision_id)), None
    )
    if not decision:
        raise ValueError("Choose a saved prototype planning record.")
    ledger_entries = _decision_ledger_entries(con, decision)
    integrity_errors, correlated_entries = _safety_ledger_link_integrity(con, decision, ledger_entries)
    decision_fingerprint_check = _decision_fingerprint_check(decision)
    if not decision_fingerprint_check["matches"]:
        integrity_errors.append(
            "Decision-basis local consistency check: " + decision_fingerprint_check["message"]
        )
    return {
        "packet_schema_version": "1.1",
        "packet_type": "local_prototype_review_handoff",
        "decision": decision,
        "recorded_evaluation": decision.get("snapshot", {}),
        "funding_recheck": decision.get("funding_snapshot", {}),
        "current_catalog_check": _catalog_check(decision.get("assumption_catalog")),
        "decision_fingerprint_check": decision_fingerprint_check,
        "linked_local_ledger_entries": ledger_entries,
        "correlated_local_ledger_entries": correlated_entries,
        "ledger_link_integrity": {
            "state": "OK" if not integrity_errors else "CHECK_REQUIRED",
            "errors": integrity_errors,
        },
        "disclaimer": (
            "This is a local prototype decision receipt. It is not sent to a human reviewer and does not "
            "certify, release, approve, or predict the safety of a vehicle."
        ),
    }


def fund_safety_decision(con, decision_id):
    """Commit one eligible prototype plan to the local ledger exactly once.

    This creates a repair charge plus a matching local planning
    reprioritisation. It affects only this app's cap/reserve ledger; it cannot
    repair a real car, clear a historical incident, or change 2025 results.
    """
    try:
        # Reserve the write lock before reading the funding state. A second
        # Streamlit tab waits here, then sees the first tab's ledger ID instead
        # of charging the same plan a second time.
        con.execute("BEGIN IMMEDIATE")
        state = active_state(con)
        if not state or state["status"] != "active":
            raise ValueError("Start an active replay before committing prototype funding.")
        raw = con.execute(
            "SELECT * FROM career_safety_decisions WHERE id = ?", (int(decision_id),)
        ).fetchone()
        if not raw:
            raise ValueError("Choose a saved prototype planning record.")
        raw_decision = dict(raw)
        if raw_decision.get("repair_ledger_id") is not None:
            result = {
                "decision_id": int(raw_decision["id"]),
                "repair_ledger_id": int(raw_decision["repair_ledger_id"]),
                "transfer_ledger_id": raw_decision.get("transfer_ledger_id"),
                "reserve_transfer_ledger_id": raw_decision.get("reserve_transfer_ledger_id"),
                "funded_round_number": raw_decision.get("funded_round_number"),
                "already_funded": True,
            }
            con.commit()
            return result
        correlated_entries = _correlated_safety_ledger_entries(con, raw_decision["id"])
        if correlated_entries:
            entry_ids = ", ".join(f"#{entry['id']}" for entry in correlated_entries)
            raise ValueError(
                "This prototype record already has correlated local ledger entries "
                f"({entry_ids}) but no repair-funding pointer. Inspect its receipt; no second funding "
                "entry was created."
            )
        if raw_decision.get("status") != "REVIEW_ELIGIBLE":
            raise ValueError("Only a saved prototype review-eligible plan can receive local modelled funding.")
        records = safety_decisions(con, limit=10_000)
        decision = next((item for item in records if item["id"] == int(decision_id)), None)
        if not decision:
            raise ValueError("The saved prototype planning snapshot could not be read.")
        evaluation = _live_safety_evaluation(con, decision)
        if not evaluation["eligible_for_review"]:
            raise ValueError(
                "The current local funding check is HOLD; no ledger entry was created: "
                + " ".join(evaluation["blockers"])
            )

        profile = _saved_profile_for_funding(decision)
        repair_category = str(profile.get("ledger_category") or "")
        if repair_category not in CATEGORIES:
            raise ValueError(
                "The frozen prototype rule basis has an invalid local ledger category. Re-record the plan."
            )
        source = str(decision["funding_source"])
        cost = float(evaluation["estimated_cost_cad"])
        transfer = float(evaluation["planned_transfer_cad"])
        if cost <= 0:
            raise ValueError("The selected prototype option has no positive modelled repair cost to commit.")

        repair_ledger_id = _insert_ledger(
            con, int(state["current_round"]), "Prototype repair planner", repair_category,
            cost, "prototype_repair_plan",
            f"Modelled prototype plan: {evaluation['profile_label']} — {evaluation['option_label']}",
            "Editable prototype scenario cost recorded in the local ledger only; human review remains required and historical results are unchanged.",
            counts_to_cap=True, safety_decision_id=int(decision_id),
        )
        transfer_ledger_id = None
        reserve_transfer_ledger_id = None
        if transfer > 0:
            transfer_ledger_id = _insert_ledger(
                con, int(state["current_round"]), "Prototype repair planner", source,
                -transfer, "prototype_funding_reallocation",
                f"Modelled reprioritisation for prototype plan #{decision_id}",
                f"Local planning transfer from {source}; it reduces only this app's planned-spend ledger and does not alter the historical replay.",
                counts_to_cap=True, safety_decision_id=int(decision_id),
            )
            reserve_transfer_ledger_id = _insert_ledger(
                con, int(state["current_round"]), "Prototype repair planner", source,
                transfer, "prototype_reserve_transfer",
                f"Modelled reserve transfer for prototype plan #{decision_id}",
                "Local prototype reserve top-up recorded for the selected planning floor; it is not real team accounting or a safety approval.",
                counts_to_cap=False, safety_decision_id=int(decision_id),
            )
            con.execute(
                "UPDATE career_state SET crash_reserve_target = crash_reserve_target + ? WHERE id = 1",
                (transfer,),
        )
        today = date.today().isoformat()
        funding_snapshot = dict(evaluation)
        funding_snapshot["funding_event"] = {
            "funded_round_number": int(state["current_round"]),
            "repair_ledger_id": repair_ledger_id,
            "transfer_ledger_id": transfer_ledger_id,
            "reserve_transfer_ledger_id": reserve_transfer_ledger_id,
        }
        con.execute(
            """UPDATE career_safety_decisions
            SET status = ?, blockers_json = ?, repair_ledger_id = ?, transfer_ledger_id = ?,
                reserve_transfer_ledger_id = ?, funded_at = ?, funded_round_number = ?,
                review_requested_at = ?, funding_snapshot_json = ?
            WHERE id = ?""",
            (
                "REVIEW_REQUESTED", _canonical_json([]), repair_ledger_id, transfer_ledger_id,
                reserve_transfer_ledger_id, today, int(state["current_round"]), today,
                _canonical_json(funding_snapshot), int(decision_id),
            ),
        )
        con.commit()
        return {
            "decision_id": int(decision_id),
            "repair_ledger_id": repair_ledger_id,
            "transfer_ledger_id": transfer_ledger_id,
            "reserve_transfer_ledger_id": reserve_transfer_ledger_id,
            "funded_round_number": int(state["current_round"]),
            "already_funded": False,
            "evaluation": evaluation,
        }
    except sqlite3.OperationalError as error:
        if con.in_transaction:
            con.rollback()
        busy_codes = {getattr(sqlite3, "SQLITE_BUSY", None), getattr(sqlite3, "SQLITE_LOCKED", None)}
        if getattr(error, "sqlite_errorcode", None) in busy_codes or "locked" in str(error).lower():
            raise ValueError("The local prototype ledger is busy. Wait a moment and try funding once more.") from error
        raise
    except Exception:
        if con.in_transaction:
            con.rollback()
        raise


def resolve_incident(con, incident_id, choice, chosen_amount=None):
    row = con.execute("SELECT * FROM career_incidents WHERE id = ?", (incident_id,)).fetchone()
    if not row or row["state"] not in {"pending", "deferred"}:
        return
    incident = dict(row)
    repair_required = bool(incident.get("repair_required"))
    safety_critical = bool(incident.get("safety_critical"))
    # Public records sometimes establish an event but not a supported repair band.
    # Acknowledge it without fabricating a cost or forcing an unsupported choice.
    if choice == "review":
        if safety_critical:
            raise ValueError("This event carries the project's critical-repair flag and needs a recorded repair decision before the next race.")
        con.execute("UPDATE career_incidents SET state = 'reviewed', reviewed_at = ? WHERE id = ?", (date.today().isoformat(), incident_id))
        con.commit()
        return
    if not repair_required:
        con.execute("UPDATE career_incidents SET state = 'reviewed', reviewed_at = ? WHERE id = ?", (date.today().isoformat(), incident_id))
        con.commit()
        return
    if choice == "old_spec":
        if safety_critical:
            raise ValueError("This event carries the project's critical-repair flag and cannot use the replay's deferred-parts option.")
        if incident["state"] == "deferred":
            return
        _insert_ledger(
            con, incident["round_number"], "Repair decision", incident["category"], 0.0,
            "repair_deferred", f"Older-spec components retained for {incident['title']}",
            "Local repair record: older-spec components retained; historical replay results are unchanged.",
        )
        con.execute("UPDATE career_incidents SET state = 'deferred', chosen_amount = 0 WHERE id = ?", (incident_id,))
        con.commit()
        return
    low, high = float(incident.get("cost_low", 0)), float(incident.get("cost_high", 0))
    if choice == "source_limited":
        if not safety_critical or high > 0:
            raise ValueError("This acknowledgement is available only for a project-critical record without a supported repair-cost band.")
        _insert_ledger(
            con, incident["round_number"], "Repair decision", incident["category"], 0.0,
            "repair_source_limited", f"Source limitation acknowledged for {incident['title']}",
            "Source limitation acknowledged; no repair cost, safety outcome, or vehicle release is claimed.",
        )
        con.execute(
            "UPDATE career_incidents SET state = 'source_limited', chosen_amount = 0, reviewed_at = ? WHERE id = ?",
            (date.today().isoformat(), incident_id),
        )
        con.commit()
        return
    if choice == "full":
        amount, kind = high, "repair_full"
    elif choice == "minimum":
        amount, kind = low, "repair_minimum"
    elif choice == "custom":
        if chosen_amount is None:
            raise ValueError("Choose a repair amount inside the stated estimate range.")
        amount, kind = max(low, min(high, float(chosen_amount))), "repair_custom"
    else:
        raise ValueError("Choose a valid repair decision.")
    choice_label = {
        "full": "high-end local estimate",
        "minimum": "low-end local estimate",
        "custom": "custom local estimate",
    }[choice]
    reserve_before = crash_contingency(con)["remaining"]
    reserve_used = min(reserve_before, amount)
    uncovered = max(0.0, amount - reserve_used)
    effect = f"Crash contingency used: {money(reserve_used)}."
    if uncovered:
        effect += f" {money(uncovered)} charged beyond the planned crash allocation."
    else:
        effect += " Repair stays within the planned crash allocation."
    effect += " Historical replay results are unchanged."
    _insert_ledger(
        con, incident["round_number"], "Repair decision", incident["category"], amount, kind,
        f"{incident['title']} — {choice_label}", effect,
    )
    con.execute(
        "UPDATE career_incidents SET state = 'funded', chosen_amount = ?, amount = ?, reviewed_at = ? WHERE id = ?",
        (amount, amount, date.today().isoformat(), incident_id),
    )
    con.commit()


def add_manual_incident(con, title, amount, category, reason="Manual local repair event"):
    state = active_state(con)
    if not state:
        raise ValueError("Start a simulation before adding a repair event.")
    amount = max(0.0, float(amount))
    con.execute(
        """INSERT INTO career_incidents
        (round_number,title,amount,category,state,reason,responsible,source,created_at,kind,components,
         cost_low,cost_high,estimate_label,repair_required,source_url)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            state["current_round"], title, amount, category, "pending", reason, "Manual entry", "Spend Ledger",
            date.today().isoformat(), "manual", "Manual component declaration", amount, amount,
            "User-entered estimate", 1, "Local manual entry",
        ),
    )
    con.commit()


def historical_context(con):
    state = active_state(con)
    if not state:
        return None
    round_number = min(max(1, int(state["current_round"])), len(CALENDAR))
    return {
        "round": CALENDAR[round_number - 1],
        "weather": historical_weather(round_number),
        "strategy": strategy_for(state["team_id"], round_number),
        "events": incidents_for(state["team_id"], round_number),
        "weekend": replay_weekend(round_number) if replay_available() else {},
    }


def finance_summary(con):
    spend = total_spend(con)
    reserve = crash_contingency(con)
    remaining = CAP - spend
    return {
        "state": active_state(con), "spend": spend, "remaining": remaining,
        "discretionary_remaining": remaining - reserve["remaining"],
        "breakdown": spend_by_category(con), "crash_tax": reserve["used"],
        "crash_contingency": reserve,
        "planned_rnd": float(con.execute(
            """SELECT COALESCE(SUM(amount),0) FROM career_ledger
            WHERE (kind IN ('preseason_rnd','upgrade') AND future_car = 0)
               OR kind = 'prototype_funding_reallocation'"""
        ).fetchone()[0]),
        "future_car": float(con.execute(
            "SELECT COALESCE(SUM(amount),0) FROM career_ledger WHERE future_car = 1"
        ).fetchone()[0]),
        "sanction": sanction_for(spend),
    }


def development_outlook(con):
    state = active_state(con)
    if not state:
        return None
    future = float(con.execute("SELECT COALESCE(SUM(amount),0) FROM career_ledger WHERE future_car = 1").fetchone()[0])
    return {
        "switch_round": int(state["switch_round"]),
        "future_capital": future,
        "current_capital": finance_summary(con)["planned_rnd"],
        "note": "Financial planning only. No pace delta is calculated or applied to the historical replay.",
    }


def audit(con):
    state = active_state(con)
    if not state:
        return None
    team = TEAMS[state["team_id"]]
    summary = finance_summary(con)
    board = standings(con)
    player = next(row for row in board if row["team_id"] == state["team_id"])
    sanction = summary["sanction"]
    if player["Position"] == 1 and sanction["breach"] <= 0:
        verdict = "World Champions — Clean Audit"
    elif player["Position"] == 1:
        verdict = "Pyrrhic Victory — Over-cap Review"
    elif sanction["breach"] > 0:
        verdict = "Underperforming & Overbudget"
    elif player["Position"] < team["board_target_rank"] and summary["remaining"] > 5_000_000:
        verdict = "Financial Masterclass"
    else:
        verdict = "Competitive Season — Board Review"
    categories = spend_by_category(con)
    best_category = max(categories, key=categories.get) if categories else "Other"
    entries = ledger(con)
    upgrades = [item for item in entries if item["kind"] == "upgrade"]
    largest_upgrade = max(upgrades, key=lambda item: item["amount"], default=None)
    incidents = [dict(row) for row in con.execute("SELECT * FROM career_incidents ORDER BY chosen_amount DESC, cost_high DESC").fetchall()]
    crisis = next((item for item in incidents if item.get("chosen_amount", 0) > 0), None)
    cancelled_upgrade = next((item for item in entries if item["kind"] in {"upgrade_cancelled", "upgrade_reduced"}), None)
    readiness_entries = [
        item for item in entries
        if item["category"] in {"Personnel", "Operations", "Testing", "Chassis / structures"}
        and item["kind"] in {"preseason_rnd", "upgrade"}
    ]
    best_readiness = max(readiness_entries, key=lambda item: item["amount"], default=None)
    category_lines = [
        {"Category": category, "Cap spend": float(categories.get(category, 0.0))}
        for category in CATEGORIES
    ]
    operating_base = sum(float(item["amount"]) for item in entries if item["kind"] == "operating_base")
    current_commitments_before_reallocation = sum(
        float(item["amount"])
        for item in entries
        if item["kind"] in {"preseason_rnd", "upgrade"} and not item["future_car"]
    )
    prototype_reallocation = sum(
        float(item["amount"])
        for item in entries if item["kind"] == "prototype_funding_reallocation"
    )
    classified_repairs = summary["crash_tax"]
    accounted = (
        operating_base + current_commitments_before_reallocation + prototype_reallocation
        + summary["future_car"] + classified_repairs
    )
    financial_lines = [
        {"Line item": "Modelled operating base", "Amount": operating_base},
        {"Line item": "2025 development / operations commitments", "Amount": current_commitments_before_reallocation},
        {"Line item": "Prototype source reprioritisation", "Amount": prototype_reallocation},
        {"Line item": "Future-car commitments", "Amount": summary["future_car"]},
        {"Line item": "Funded crash repairs (including prototype plans)", "Amount": classified_repairs},
        {"Line item": "Other cap commitments", "Amount": summary["spend"] - accounted},
        {"Line item": "Unspent crash contingency", "Amount": summary["crash_contingency"]["remaining"]},
    ]
    comparators = []
    for team_id, competitor in TEAMS.items():
        modelled_cost = float(sum(competitor["model_cost_2024"].values()))
        comparators.append({
            "Team": competitor["name"],
            "Modelled CAD / point": modelled_cost / max(1, competitor["historical_points"]),
            "team_id": team_id,
        })
    grid_median = median(item["Modelled CAD / point"] for item in comparators)
    unused_cap = max(0.0, summary["remaining"])
    return {
        "team": team, "summary": summary, "standings": board, "player": player,
        "verdict": verdict, "sanction": sanction, "breach": sanction["breach"],
        "cost_per_point": summary["spend"] / max(1, player["Points"]),
        "best_category": best_category, "largest_upgrade": largest_upgrade, "crisis": crisis,
        "cancelled_upgrade": cancelled_upgrade, "best_readiness": best_readiness,
        "category_lines": category_lines, "financial_lines": financial_lines,
        "grid_comparators": comparators, "grid_median_cost_per_point": grid_median,
        "historical_rank": team["historical_rank"], "historical_points": team["historical_points"],
        "board_target_rank": team["board_target_rank"],
        "development_switch_round": int(state["switch_round"]),
        "development_proxy_round": team["development_proxy_round"],
        "development_proxy_note": "Local inferred public-season proxy; real internal development switch dates are not public.",
        "future_capital": summary["future_car"],
        "unused_cap_credit": unused_cap,
        "next_year_aero_allowance": 100 - sanction["wind_tunnel_cut"],
        "next_year_note": "Game rule: each unspent CAD dollar becomes one starter R&D credit. No 2026 pace delta is calculated.",
    }
