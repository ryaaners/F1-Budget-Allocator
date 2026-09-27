"""Persistence and deterministic race engine for the offline season simulation."""
from __future__ import annotations

import json
import math
import random
import sqlite3
from datetime import date

from career_data import CAP, CALENDAR, CATEGORIES, GP_POINTS, RETURN_SCALE, SPRINT_POINTS, TEAMS, events_for, historical_round, historical_round_form, strategy_for

CATEGORY_RATES = {
    "Aero": .27, "Powertrain": .19, "Chassis / structures": .17,
    "Personnel": .11, "Operations": .08, "Testing": .13, "Other": .04,
}
CURRENT_CAR_CATEGORIES = {"Aero", "Powertrain", "Chassis / structures", "Testing"}

# Survival-cell safety model. Impact thresholds and costs are gameplay estimates,
# not FIA homologation values or published team invoices.
STRUCTURAL_CATEGORY = "Chassis / structures"
MEDIUM_IMPACT_G = 20.0
BIG_IMPACT_G = 45.0
SEVERITY_LABELS = {"small": "Small hit", "medium": "Medium hit", "big": "Big hit"}
SURVIVAL_CELL_EXTRA_COST = {"small": 0.0, "medium": 800_000.0, "big": 2_500_000.0}
IMPACT_G_FOR_SEVERITY = {"small": 12.0, "medium": 30.0, "big": 55.0}
# A big crash: a replacement survival cell plus typical bodywork and suspension damage.
BIG_CRASH_COST = 4_000_000.0


class SafetyReserveError(ValueError):
    """A package would leave less than one big crash of cap headroom."""


def money(value):
    return f"CAD ${value / 1_000_000:,.1f}M"


def connect(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    migrate(con)
    return con


def migrate(con):
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS career_state (
            id INTEGER PRIMARY KEY CHECK (id = 1), team_id TEXT NOT NULL,
            current_round INTEGER NOT NULL DEFAULT 1, session_index INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active', theme TEXT NOT NULL DEFAULT 'team',
            switch_round INTEGER NOT NULL DEFAULT 16, seed INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS career_allocations (
            category TEXT PRIMARY KEY, amount REAL NOT NULL, rate REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS career_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT, round_number INTEGER, session_name TEXT,
            category TEXT NOT NULL, amount REAL NOT NULL, kind TEXT NOT NULL, note TEXT,
            future_car INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
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
            title TEXT NOT NULL, amount REAL NOT NULL, category TEXT NOT NULL,
            penalty REAL NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'pending',
            reason TEXT, responsible TEXT, source TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS career_preferences (
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        );
        """
    )
    # Survival-cell columns were added after the first release, so older saves gain them here.
    incident_columns = {row[1] for row in con.execute("PRAGMA table_info(career_incidents)")}
    for column, kind in (("impact_g", "REAL"), ("severity", "TEXT")):
        if column not in incident_columns:
            con.execute(f"ALTER TABLE career_incidents ADD COLUMN {column} {kind}")
    con.commit()


def active_state(con):
    row = con.execute("SELECT * FROM career_state WHERE id = 1").fetchone()
    return dict(row) if row else None


def reset_career(con):
    for table in ("career_state", "career_allocations", "career_ledger", "career_sessions", "career_standings", "career_incidents", "career_preferences"):
        con.execute(f"DELETE FROM {table}")
    con.commit()


def create_career(con, team_id, allocations, switch_round=16, theme="team", seed=2025):
    if team_id not in TEAMS:
        raise ValueError("Choose a valid 2025 constructor.")
    team = TEAMS[team_id]
    clean = {category: max(0.0, float(allocations.get(category, 0))) for category in CATEGORIES}
    planned = sum(clean.values()) + team["fixed_cost"]
    if planned > CAP:
        raise ValueError("Pre-season allocation exceeds the CAD $215M simulation cap.")
    reset_career(con)
    con.execute(
        "INSERT INTO career_state VALUES (1,?,?,?,?,?,?,?,?)",
        (team_id, 1, 0, "active", theme, int(switch_round), int(seed), date.today().isoformat()),
    )
    con.executemany(
        "INSERT INTO career_allocations(category, amount, rate) VALUES (?,?,?)",
        [(category, clean[category], CATEGORY_RATES[category]) for category in CATEGORIES],
    )
    con.execute(
        "INSERT INTO career_ledger(round_number, session_name, category, amount, kind, note, future_car, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (0, "Pre-season", "Operations", team["fixed_cost"], "operating_base", "Modelled fixed 2025 operating base", 0, date.today().isoformat()),
    )
    for category, amount in clean.items():
        if amount:
            con.execute(
                "INSERT INTO career_ledger(round_number, session_name, category, amount, kind, note, future_car, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (0, "Pre-season", category, amount, "preseason_rnd", "Pre-season allocation", 0, date.today().isoformat()),
            )
    con.executemany("INSERT INTO career_standings(team_id, points) VALUES (?, 0)", [(team_key,) for team_key in TEAMS])
    con.commit()
    return active_state(con)


def ordered_sessions(round_number):
    return ["Sprint Qualifying", "Sprint", "Grand Prix Qualifying", "Grand Prix"] if CALENDAR[round_number - 1]["sprint"] else ["Qualifying", "Grand Prix"]


def next_session(con):
    state = active_state(con)
    if not state or state["status"] != "active":
        return None
    sessions = ordered_sessions(state["current_round"])
    return sessions[state["session_index"]] if state["session_index"] < len(sessions) else None


def ledger(con):
    return [dict(row) for row in con.execute("SELECT * FROM career_ledger ORDER BY id DESC").fetchall()]


def total_spend(con):
    return float(con.execute("SELECT COALESCE(SUM(amount), 0) FROM career_ledger").fetchone()[0])


def reserve_status(free, owed=0.0):
    """Describe cap headroom as the number of big crashes it could still pay for."""
    crashes = max(0, int(free // BIG_CRASH_COST))
    status = "safe" if crashes >= 2 else ("tight" if crashes == 1 else "at_risk")
    return {"free": free, "owed": owed, "crashes": crashes, "status": status, "crash_cost": BIG_CRASH_COST}


def safety_reserve(con, extra_spend=0.0):
    """Cap headroom left for crashes after unpaid repairs and an optional new package."""
    owed = float(con.execute(
        "SELECT COALESCE(SUM(amount),0) FROM career_incidents WHERE state IN ('pending','deferred')"
    ).fetchone()[0])
    return reserve_status(CAP - total_spend(con) - owed - extra_spend, owed)


def spend_by_category(con):
    output = {category: 0.0 for category in CATEGORIES}
    for row in con.execute("SELECT category, COALESCE(SUM(amount), 0) amount FROM career_ledger GROUP BY category"):
        output[row["category"]] = float(row["amount"])
    return output


def _rd_spend(con, future_car=False):
    data = {category: 0.0 for category in CATEGORIES}
    for row in con.execute("SELECT category, COALESCE(SUM(amount), 0) amount FROM career_ledger WHERE future_car = ? GROUP BY category", (int(future_car),)):
        data[row["category"]] = max(0.0, float(row["amount"]))
    return data


def lap_gain(rate, spend):
    return rate * (1 - math.exp(-max(0.0, spend) / RETURN_SCALE))


def current_performance(con, round_number):
    values = _rd_spend(con, future_car=False)
    track = CALENDAR[round_number - 1]
    category_gains = {category: lap_gain(CATEGORY_RATES[category], values[category]) for category in CATEGORIES}
    track_gain = (
        category_gains["Aero"] * track["aero"] +
        category_gains["Powertrain"] * track["powertrain"] +
        category_gains["Chassis / structures"] * track["chassis"] +
        category_gains["Testing"] * .20 + category_gains["Other"] * .05
    )
    personnel = min(.10, category_gains["Personnel"] * .45)
    operations = min(.06, category_gains["Operations"] * .35)
    pending_penalty = float(con.execute("SELECT COALESCE(SUM(penalty),0) FROM career_incidents WHERE state = 'deferred'").fetchone()[0])
    return {
        "track_gain": track_gain, "personnel": personnel, "operations": operations,
        "damage_penalty": pending_penalty, "category_gains": category_gains,
    }


def development_outlook(con):
    """Give the active dashboard a bounded current-car versus next-car forecast."""
    state = active_state(con)
    if not state:
        return None
    round_number = min(max(1, state["current_round"]), len(CALENDAR))
    details = TEAMS[state["team_id"]]
    current = current_performance(con, round_number)
    future = _rd_spend(con, future_car=True)
    future_gain = (
        lap_gain(CATEGORY_RATES["Aero"], future["Aero"]) * .62
        + lap_gain(CATEGORY_RATES["Powertrain"], future["Powertrain"]) * .42
        + lap_gain(CATEGORY_RATES["Chassis / structures"], future["Chassis / structures"]) * .48
        + lap_gain(CATEGORY_RATES["Testing"], future["Testing"]) * .28
    )
    reserve_draw = float(con.execute(
        "SELECT COALESCE(SUM(amount),0) FROM career_ledger WHERE kind = 'repair_future_reserve'"
    ).fetchone()[0])
    future_gain = max(0.0, future_gain - min(.08, reserve_draw / 120_000_000))
    current_credit = max(0.0, current["track_gain"] + current["personnel"] + current["operations"] - current["damage_penalty"])
    projected_position = max(1, min(10, details["historical_rank"] - int(round(current_credit / .14))))
    return {
        "projected_position": projected_position,
        "current_credit": current_credit,
        "future_credit": future_gain,
        "switch_round": state["switch_round"],
        "reserve_draw": reserve_draw,
    }


def commit_investment(con, category, amount, note="Race-weekend package", override_safety=False):
    state = active_state(con)
    if not state or state["status"] != "active":
        raise ValueError("Start a simulation before committing an upgrade.")
    amount = float(amount)
    if category not in CATEGORIES or amount <= 0:
        raise ValueError("Choose a category and a positive CAD amount.")
    if total_spend(con) + amount > CAP:
        raise ValueError("This package would exceed the CAD $215M simulation cap.")
    after = safety_reserve(con, extra_spend=amount)
    if after["crashes"] < 1 and not override_safety:
        raise SafetyReserveError(
            f"This package would leave {money(after['free'])} for crashes. "
            f"One big crash costs about {money(BIG_CRASH_COST)}, so you could not pay for a new survival cell without breaking the cap."
        )
    future = int(state["current_round"] >= state["switch_round"] and category in CURRENT_CAR_CATEGORIES)
    target = "future car" if future else "current car"
    con.execute(
        "INSERT INTO career_ledger(round_number, session_name, category, amount, kind, note, future_car, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (state["current_round"], "Pre-race", category, amount, "upgrade", f"{note} — {target}", future, date.today().isoformat()),
    )
    con.commit()
    return future


def impact_severity(impact_g):
    if impact_g >= BIG_IMPACT_G:
        return "big"
    return "medium" if impact_g >= MEDIUM_IMPACT_G else "small"


def must_repair(incident):
    """A cracked or destroyed survival cell cannot be raced, so its repair cannot wait."""
    return incident.get("severity") in {"medium", "big"}


def _roll_impact(con, state, round_number, title, penalty):
    """Seeded crash g-load: harder at risky or wet circuits and for heavier damage events."""
    track = CALENDAR[round_number - 1]
    count = con.execute("SELECT COUNT(*) FROM career_incidents").fetchone()[0]
    rng = _rng(state, f"impact:{round_number}:{title}:{count}")
    mean = 4 + track["risk"] * 60 + min(3.0, track["weather"]["rain_mm"]) * 3 + penalty * 50
    return round(min(80.0, max(3.0, rng.gauss(mean, 10))), 1)


def _record_incident(con, state, round_number, title, amount, category, penalty, reason, responsible, source, severity=None):
    """Insert a pending incident, adding a survival-cell check to structural damage."""
    impact_g = None
    if category == STRUCTURAL_CATEGORY:
        impact_g = IMPACT_G_FOR_SEVERITY[severity] if severity else _roll_impact(con, state, round_number, title, penalty)
        severity = impact_severity(impact_g)
        amount = float(amount) + SURVIVAL_CELL_EXTRA_COST[severity]
    else:
        severity = None
    con.execute(
        "INSERT INTO career_incidents(round_number,title,amount,category,penalty,state,reason,responsible,source,impact_g,severity,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (round_number, title, float(amount), category, float(penalty), "pending", reason, responsible, source, impact_g, severity, date.today().isoformat()),
    )


def add_manual_incident(con, title, amount, category, penalty=.15, reason="Manual ledger event", severity=None):
    state = active_state(con)
    if not state:
        raise ValueError("Start a simulation before adding a career incident.")
    if severity is not None and severity not in SEVERITY_LABELS:
        raise ValueError("Choose a valid survival-cell hit size.")
    _record_incident(con, state, state["current_round"], title, amount, category, penalty, reason, "Manual selection", "Spend Ledger", severity)
    con.commit()


def pending_incidents(con):
    return [dict(row) for row in con.execute("SELECT * FROM career_incidents WHERE state = 'pending' OR state = 'deferred' ORDER BY round_number, id").fetchall()]


def resolve_incident(con, incident_id, choice):
    incident = con.execute("SELECT * FROM career_incidents WHERE id = ?", (incident_id,)).fetchone()
    if not incident or incident["state"] not in {"pending", "deferred"}:
        return
    state = active_state(con)
    if choice == "defer":
        if must_repair(dict(incident)):
            raise ValueError("The survival cell is damaged, so this repair cannot be delayed. Choose a way to pay for it.")
        con.execute("UPDATE career_incidents SET state = 'deferred' WHERE id = ?", (incident_id,))
    else:
        if choice not in {"fund", "cancel_upgrade", "future_reserve", "breach"}:
            raise ValueError("Choose a valid repair funding option.")
        if choice == "cancel_upgrade":
            upgrades = [dict(row) for row in con.execute(
                "SELECT * FROM career_ledger WHERE kind = 'upgrade' AND future_car = 0 AND amount > 0 ORDER BY id DESC"
            )]
            available = sum(row["amount"] for row in upgrades)
            if not upgrades:
                raise ValueError("There is no current-car upgrade available to cancel or reduce.")
            if total_spend(con) - available + incident["amount"] > CAP:
                raise ValueError("Cancelling current upgrades still cannot fund this repair inside the CAD $215M cap.")
            remaining_to_redirect = incident["amount"]
            for upgrade in upgrades:
                if remaining_to_redirect <= 0:
                    break
                redirected = min(upgrade["amount"], remaining_to_redirect)
                con.execute(
                    "INSERT INTO career_ledger(round_number, session_name, category, amount, kind, note, future_car, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        state["current_round"], "Repair decision", upgrade["category"], -redirected,
                        "upgrade_reallocation", f"Reduced {upgrade['note']} to fund {incident['title']}", 0,
                        date.today().isoformat(),
                    ),
                )
                remaining_to_redirect -= redirected
        if choice != "breach" and total_spend(con) + incident["amount"] > CAP:
            raise ValueError("Repair cannot be funded inside the CAD $215M cap. Defer it or free budget first.")
        if choice == "future_reserve":
            kind, note = "repair_future_reserve", "Repair funded by drawing from future-car reserve"
        elif choice == "breach":
            kind, note = "repair_breach", "Board-approved emergency repair that exceeds the gameplay cap"
        else:
            kind, note = "repair", "Repair funded from cap headroom"
        if incident["severity"] == "big":
            note += " — includes replacement survival cell"
        elif incident["severity"] == "medium":
            note += " — includes survival-cell repair"
        con.execute(
            "INSERT INTO career_ledger(round_number, session_name, category, amount, kind, note, future_car, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (state["current_round"], "Repair decision", incident["category"], incident["amount"], kind, note, 0, date.today().isoformat()),
        )
        con.execute("UPDATE career_incidents SET state = 'funded', penalty = 0 WHERE id = ?", (incident_id,))
    con.commit()


def _rng(state, label):
    return random.Random(f"{state['seed']}:{label}")


def _simulate_classification(con, state, round_number, session_name):
    track = CALENDAR[round_number - 1]
    user_team = state["team_id"]
    perf = current_performance(con, round_number)
    rng = _rng(state, f"{round_number}:{session_name}")
    rows = []
    for team_id, details in TEAMS.items():
        historic_wave = math.sin((round_number + details["historical_rank"]) * .71) * .025 - historical_round_form(team_id, round_number) * .15
        for driver_index, driver in enumerate(details["drivers"]):
            driver_gap = (100 - driver["skill"]) * .012 + driver_index * .008
            score = details["base_delta"] + historic_wave + driver_gap + rng.gauss(0, .035)
            if team_id == user_team:
                rain_factor = .025 if track["weather"]["rain_mm"] >= .5 else 0
                score -= perf["track_gain"] + perf["personnel"] + perf["operations"] - rain_factor
                score += perf["damage_penalty"]
            rows.append({"team_id": team_id, "team": details["name"], "driver_id": driver["id"], "driver": driver["name"], "score": score})
    rows.sort(key=lambda row: row["score"])
    result = []
    base_time = 80.0 if "Qualifying" in session_name else 90.0
    for position, row in enumerate(rows, start=1):
        result.append({
            **row, "position": position, "gap": round(max(0, row["score"] - rows[0]["score"]), 3),
            "time": round(base_time + row["score"], 3),
        })
    return result


def _rescore_knockout(rows, rng, base_time):
    """Run one knockout stage from the entrants who survived the prior stage."""
    stage = []
    for row in rows:
        refreshed = dict(row)
        refreshed["score"] = row["score"] + rng.gauss(0, .018)
        stage.append(refreshed)
    stage.sort(key=lambda row: row["score"])
    winner = stage[0]["score"]
    for position, row in enumerate(stage, start=1):
        row["position"] = position
        row["gap"] = round(max(0, row["score"] - winner), 3)
        row["time"] = round(base_time + row["score"], 3)
        row["points"] = 0
    return stage


def _simulate_knockout(con, state, round_number, session_name):
    """Simulate Q1/Q2/Q3 or SQ1/SQ2/SQ3 for the complete 20-car grid."""
    is_sprint = session_name == "Sprint Qualifying"
    prefix = "SQ" if is_sprint else "Q"
    base_time = 79.5 if is_sprint else 80.0
    rng = _rng(state, f"{round_number}:{session_name}:knockout")
    q1 = _simulate_classification(con, state, round_number, f"{session_name} {prefix}1")
    q1 = _rescore_knockout(q1, rng, base_time)
    q2 = _rescore_knockout(q1[:15], rng, base_time)
    q3 = _rescore_knockout(q2[:10], rng, base_time)
    final = q3 + q2[10:] + q1[15:]
    winner = final[0]["score"]
    for position, row in enumerate(final, start=1):
        row["position"] = position
        row["gap"] = round(max(0, row["score"] - winner), 3)
        row["time"] = round(base_time + row["score"], 3)
        row["points"] = 0
    return final, [
        {"name": f"{prefix}1", "results": q1},
        {"name": f"{prefix}2", "results": q2},
        {"name": f"{prefix}3", "results": q3},
    ]


def _insert_incidents_for_round(con, state, round_number):
    values = _rd_spend(con)
    mitigation = min(.14, (values["Personnel"] + values["Operations"] + values["Testing"]) / 150_000_000)
    rng = _rng(state, f"incident:{round_number}")
    for event in events_for(state["team_id"], round_number):
        if event.get("historical_only"):
            continue
        exists = con.execute("SELECT 1 FROM career_incidents WHERE round_number = ? AND title = ?", (round_number, event["title"])).fetchone()
        if exists:
            continue
        probability = max(.05, event["probability"] - mitigation)
        if rng.random() < probability:
            _record_incident(
                con, state, round_number, event["title"], event["amount"], event["category"], event["penalty"],
                event["reason"], event["responsible"], event["source"],
            )
    track = CALENDAR[round_number - 1]
    variance_title = f"{track['name']} component exposure review"
    exists = con.execute("SELECT 1 FROM career_incidents WHERE round_number = ? AND title = ?", (round_number, variance_title)).fetchone()
    weather_risk = min(.08, track["weather"]["rain_mm"] * .025)
    probability = max(.02, .08 + track["risk"] * .35 + weather_risk - mitigation)
    if not exists and rng.random() < probability:
        amount = round(500_000 + track["risk"] * 1_500_000 + track["weather"]["rain_mm"] * 100_000, -3)
        _record_incident(
            con, state, round_number, variance_title, amount, STRUCTURAL_CATEGORY, .10,
            "Modelled reliability, kerb, weather, and traffic exposure at this circuit.",
            "Not officially assigned", "Simulation variance",
        )


def simulate_next_session(con):
    state = active_state(con)
    if not state or state["status"] != "active":
        raise ValueError("No active simulation session is available.")
    round_number = state["current_round"]
    session_name = next_session(con)
    if not session_name:
        raise ValueError("No session is available.")
    knockout_stages = None
    if session_name in {"Qualifying", "Sprint Qualifying"}:
        results, knockout_stages = _simulate_knockout(con, state, round_number, session_name)
    else:
        results = _simulate_classification(con, state, round_number, session_name)
    points_map = SPRINT_POINTS if session_name == "Sprint" else (GP_POINTS if session_name == "Grand Prix" else [])
    for row in results:
        row["points"] = points_map[row["position"] - 1] if row["position"] <= len(points_map) else 0
        if row["points"]:
            con.execute("UPDATE career_standings SET points = points + ? WHERE team_id = ?", (row["points"], row["team_id"]))
    if session_name == "Grand Prix":
        fastest = min(results, key=lambda item: item["time"])
        for row in results:
            row["fastest_lap"] = row["driver_id"] == fastest["driver_id"]
        _insert_incidents_for_round(con, state, round_number)
    payload = {"results": results, "stages": knockout_stages} if knockout_stages else results
    con.execute(
        "INSERT INTO career_sessions(round_number,session_name,results_json,created_at) VALUES (?,?,?,?)",
        (round_number, session_name, json.dumps(payload), date.today().isoformat()),
    )
    sessions = ordered_sessions(round_number)
    if state["session_index"] + 1 >= len(sessions):
        if round_number >= len(CALENDAR):
            con.execute("UPDATE career_state SET session_index = 0, status = 'complete' WHERE id = 1")
        else:
            con.execute("UPDATE career_state SET current_round = ?, session_index = 0 WHERE id = 1", (round_number + 1,))
    else:
        con.execute("UPDATE career_state SET session_index = session_index + 1 WHERE id = 1")
    con.commit()
    return {"round": round_number, "session": session_name, "results": results}


def standings(con):
    rows = []
    for row in con.execute("SELECT team_id, points FROM career_standings ORDER BY points DESC, team_id"):
        team = TEAMS[row["team_id"]]
        rows.append({"Team": team["name"], "team_id": row["team_id"], "Points": row["points"], "Historical 2025 points": team["historical_points"]})
    for position, row in enumerate(rows, start=1):
        row["Position"] = position
    return rows


def session_results(con, round_number=None):
    query = "SELECT * FROM career_sessions"
    params = ()
    if round_number is not None:
        query += " WHERE round_number = ?"
        params = (round_number,)
    query += " ORDER BY round_number DESC, id DESC"
    records = []
    for row in con.execute(query, params):
        item = dict(row)
        payload = json.loads(item.pop("results_json"))
        if isinstance(payload, dict):
            item["results"] = payload["results"]
            item["stages"] = payload.get("stages") or []
        else:
            item["results"] = payload
            item["stages"] = []
        records.append(item)
    return records


def historical_context(con):
    state = active_state(con)
    if not state:
        return None
    round_number = min(state["current_round"], len(CALENDAR))
    track = CALENDAR[round_number - 1]
    return {
        "round": track,
        "strategy": strategy_for(state["team_id"], round_number),
        "events": events_for(state["team_id"], round_number),
        "historical_result": historical_round(state["team_id"], round_number),
    }


def finance_summary(con):
    state = active_state(con)
    spend = total_spend(con)
    breakdown = spend_by_category(con)
    crash_tax = float(con.execute("SELECT COALESCE(SUM(amount),0) FROM career_ledger WHERE kind IN ('repair','repair_future_reserve','repair_breach')").fetchone()[0])
    planned_rnd = float(con.execute("SELECT COALESCE(SUM(amount),0) FROM career_ledger WHERE kind IN ('preseason_rnd','upgrade','upgrade_reallocation') AND future_car = 0").fetchone()[0])
    future_car = float(con.execute("SELECT COALESCE(SUM(amount),0) FROM career_ledger WHERE future_car = 1").fetchone()[0])
    future_reserve_draw = float(con.execute("SELECT COALESCE(SUM(amount),0) FROM career_ledger WHERE kind = 'repair_future_reserve'").fetchone()[0])
    return {
        "state": state, "spend": spend, "remaining": CAP - spend, "breakdown": breakdown,
        "crash_tax": crash_tax, "planned_rnd": planned_rnd, "future_car": future_car,
        "future_reserve_draw": future_reserve_draw,
    }


def audit(con):
    state = active_state(con)
    if not state:
        return None
    team = TEAMS[state["team_id"]]
    summary = finance_summary(con)
    board = standings(con)
    player = next(row for row in board if row["team_id"] == state["team_id"])
    spend, remaining = summary["spend"], summary["remaining"]
    breach = max(0.0, spend - CAP)
    breach_pct = breach / CAP if CAP else 0
    if player["Position"] == 1 and breach <= 0:
        verdict = "World Champions — Clean Audit"
    elif player["Position"] == 1:
        verdict = "Pyrrhic Victory — Under FIA Investigation"
    elif breach > 0:
        verdict = "Underperforming & Overbudget"
    elif player["Position"] < team["historical_rank"] and remaining > 5_000_000:
        verdict = "Financial Masterclass"
    else:
        verdict = "Competitive Season — Board Review"
    if breach <= 0:
        sanction = {"label": "Clean audit", "fine": 0, "wind_tunnel_cut": 0, "point_deduction": 0}
    elif breach_pct <= .05:
        sanction = {"label": "Minor gameplay breach", "fine": 5_000_000, "wind_tunnel_cut": 10, "point_deduction": 0}
    else:
        sanction = {"label": "Major gameplay breach", "fine": 10_000_000, "wind_tunnel_cut": 20, "point_deduction": 10}
    sanctioned_standings = [dict(row) for row in board]
    for row in sanctioned_standings:
        if row["team_id"] == state["team_id"]:
            row["Points"] = max(0, row["Points"] - sanction["point_deduction"])
    sanctioned_standings.sort(key=lambda row: (-row["Points"], row["team_id"]))
    for position, row in enumerate(sanctioned_standings, start=1):
        row["Position"] = position
    sanctioned_player = next(row for row in sanctioned_standings if row["team_id"] == state["team_id"])
    categories = spend_by_category(con)
    efficiency = {category: lap_gain(CATEGORY_RATES[category], max(0, amount)) / max(amount, 1) for category, amount in categories.items()}
    best_category = max(efficiency, key=efficiency.get)
    upgrades = [row for row in ledger(con) if row["kind"] == "upgrade" and not row["future_car"]]
    largest_upgrade = max(upgrades, key=lambda row: row["amount"], default=None)
    redirected = [row for row in ledger(con) if row["kind"] == "upgrade_reallocation"]
    cancelled_upgrade = min(redirected, key=lambda row: row["amount"], default=None)
    incidents = [dict(row) for row in con.execute("SELECT * FROM career_incidents ORDER BY amount DESC").fetchall()]
    crisis = incidents[0] if incidents else None
    future = max(0, summary["future_car"] + max(0, remaining) - summary["future_reserve_draw"])
    ending_gain = current_performance(con, min(max(1, state["current_round"]), len(CALENDAR)))["track_gain"]
    next_year_aero_loss = .02 * (sanction["wind_tunnel_cut"] / 10)
    return {
        "team": team, "summary": summary, "standings": board, "player": player,
        "sanctioned_standings": sanctioned_standings, "sanctioned_player": sanctioned_player,
        "verdict": verdict, "breach": breach, "breach_pct": breach_pct, "sanction": sanction,
        "cost_per_point": spend / max(1, player["Points"]), "best_category": best_category,
        "largest_upgrade": largest_upgrade, "cancelled_upgrade": cancelled_upgrade, "crisis": crisis,
        "rank_delta": team["historical_rank"] - player["Position"],
        "points_delta": player["Points"] - team["historical_points"],
        "future_credits": future, "next_baseline": max(0, ending_gain + lap_gain(.25, future) - next_year_aero_loss),
        "next_year_aero_loss": next_year_aero_loss,
        "real_switch_proxy": team["development_proxy_round"],
    }
