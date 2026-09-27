"""Local reference data for the 2025 F1 Season Budget Replay.

The simulator is intentionally offline.  Championship results, weather and weekend
notes are stored as compact local reference data; financial values and incident costs
are gameplay estimates, not FIA filings or team accounts.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

CAP = 215_000_000.0
RETURN_SCALE = 6_000_000.0
CATEGORIES = [
    "Aero", "Powertrain", "Chassis / structures", "Personnel",
    "Operations", "Testing", "Other",
]
GP_POINTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
SPRINT_POINTS = [8, 7, 6, 5, 4, 3, 2, 1]
ASSET_ROOT = Path(__file__).with_name("assets") / "drivers"
DATA_ROOT = Path(__file__).with_name("data")
with (DATA_ROOT / "historical_2025.json").open(encoding="utf-8") as historical_file:
    HISTORICAL_2025 = json.load(historical_file)

# The replay bundle is deliberately separate from the compact legacy reference data.
# It contains the full, immutable 20-car classifications used by the historical-replay
# mode.  Keeping it local means that running the app never makes a network request.
REPLAY_PATH = DATA_ROOT / "historical_2025_replay.json"
INCIDENTS_PATH = DATA_ROOT / "incidents_2025.json"
WEEKEND_CONTEXT_PATH = DATA_ROOT / "historical_weekend_context_2025.json"
REPLAY_2025 = json.loads(REPLAY_PATH.read_text(encoding="utf-8")) if REPLAY_PATH.exists() else {"rounds": {}}
INCIDENTS_2025 = json.loads(INCIDENTS_PATH.read_text(encoding="utf-8")) if INCIDENTS_PATH.exists() else {"incidents": []}
WEEKEND_CONTEXT_2025 = (
    json.loads(WEEKEND_CONTEXT_PATH.read_text(encoding="utf-8"))
    if WEEKEND_CONTEXT_PATH.exists()
    else {"rounds": {}}
)


def _driver_name_key(value):
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return "".join(character.lower() for character in value if character.isalnum())


_REPLAY_DRIVER_IDS_BY_NAME = {
    _driver_name_key(details.get("name", driver_id)): driver_id
    for driver_id, details in REPLAY_2025.get("drivers", {}).items()
}
_DRIVER_ID_ALIASES = {
    "alex_albon": "alexander_albon",
    "kimi_antonelli": "andrea_kimi_antonelli",
}
for _legacy_id, _legacy_name in HISTORICAL_2025.get("drivers", {}).items():
    _canonical_id = _REPLAY_DRIVER_IDS_BY_NAME.get(_driver_name_key(_legacy_name))
    if _canonical_id:
        _DRIVER_ID_ALIASES[_legacy_id] = _canonical_id


def canonical_driver_id(driver_id):
    """Map legacy result-feed slugs to the replay bundle's per-session entrant IDs."""
    if driver_id is None:
        return None
    value = str(driver_id)
    return _DRIVER_ID_ALIASES.get(value, value)


def _costs(total_millions):
    weights = [0.28, 0.16, 0.15, 0.18, 0.09, 0.09, 0.05]
    return {category: round(total_millions * weight * 1_000_000) for category, weight in zip(CATEGORIES, weights)}


TEAM_LIST = [
    ("mclaren", "McLaren", 833, 1, 0.00, 138, "#FF8000", "#47C7FC", "Lando Norris", "lando_norris", 94, "Oscar Piastri", "oscar_piastri", 93, 202),
    ("mercedes", "Mercedes", 469, 2, 0.22, 132, "#00D2BE", "#B9FFFF", "George Russell", "george_russell", 91, "Kimi Antonelli", "kimi_antonelli", 84, 196),
    ("red_bull", "Red Bull Racing", 451, 3, 0.27, 134, "#1E41FF", "#E10600", "Max Verstappen", "max_verstappen", 97, "Yuki Tsunoda", "yuki_tsunoda", 82, 199),
    ("ferrari", "Ferrari", 398, 4, 0.35, 131, "#E8002D", "#FFF200", "Charles Leclerc", "charles_leclerc", 93, "Lewis Hamilton", "lewis_hamilton", 91, 197),
    ("williams", "Williams", 137, 5, 0.62, 112, "#005AFF", "#64C4FF", "Alex Albon", "alex_albon", 86, "Carlos Sainz", "carlos_sainz", 88, 171),
    ("racing_bulls", "Racing Bulls", 92, 6, 0.77, 106, "#6692FF", "#FFFFFF", "Isack Hadjar", "isack_hadjar", 79, "Liam Lawson", "liam_lawson", 80, 158),
    ("aston_martin", "Aston Martin", 89, 7, 0.80, 111, "#229971", "#CEDC00", "Fernando Alonso", "fernando_alonso", 92, "Lance Stroll", "lance_stroll", 78, 173),
    ("haas", "Haas", 79, 8, 0.87, 98, "#B6BABD", "#E10600", "Esteban Ocon", "esteban_ocon", 83, "Oliver Bearman", "oliver_bearman", 80, 150),
    ("sauber", "Kick Sauber", 70, 9, 0.93, 96, "#52E252", "#000000", "Nico Hulkenberg", "nico_hulkenberg", 85, "Gabriel Bortoleto", "gabriel_bortoleto", 77, 146),
    ("alpine", "Alpine", 22, 10, 1.12, 91, "#FF87BC", "#0090FF", "Pierre Gasly", "pierre_gasly", 84, "Franco Colapinto", "franco_colapinto", 76, 140),
]

TEAMS = {}
for row in TEAM_LIST:
    (
        key, name, points, rank, base_delta, fixed_cost, primary, secondary,
        driver_one, driver_one_id, driver_one_skill, driver_two, driver_two_id,
        driver_two_skill, model_cost,
    ) = row
    TEAMS[key] = {
        "id": key,
        "name": name,
        "historical_points": points,
        "historical_rank": rank,
        # A conservative local board expectation used only for the financial audit.
        # It is intentionally less ambitious than the recorded season for midfield teams.
        "board_target_rank": 1 if rank == 1 else min(10, rank + 1),
        "base_delta": base_delta,
        "fixed_cost": fixed_cost * 1_000_000,
        "primary": primary,
        "secondary": secondary,
        "model_cost_2024": _costs(model_cost),
        "development_proxy_round": min(22, 11 + rank),
        "drivers": [
            {"name": driver_one, "id": driver_one_id, "skill": driver_one_skill},
            {"name": driver_two, "id": driver_two_id, "skill": driver_two_skill},
        ],
    }


# Date, venue, Sprint flag, and track-planning characteristics.  Actual race-session
# weather is loaded from historical_weekend_context_2025.json, not from this schedule.
_ROUND_ROWS = [
    ("Australia", "Albert Park, Melbourne", "2025-03-16", False, .58, .56, .64, .12, "Rain showers", 18, 2.6, 27),
    ("China", "Shanghai International Circuit", "2025-03-23", True, .60, .61, .55, .08, "Dry", 21, .0, 16),
    ("Japan", "Suzuka International Racing Course", "2025-04-06", False, .78, .48, .72, .10, "Cool and dry", 16, .0, 19),
    ("Bahrain", "Bahrain International Circuit", "2025-04-13", False, .52, .72, .46, .07, "Warm and dry", 29, .0, 18),
    ("Saudi Arabia", "Jeddah Corniche Circuit", "2025-04-20", False, .45, .82, .38, .16, "Warm and dry", 31, .0, 20),
    ("Miami", "Miami International Autodrome", "2025-05-04", True, .55, .67, .52, .12, "Humid, chance of showers", 27, .4, 22),
    ("Emilia-Romagna", "Imola", "2025-05-18", False, .74, .48, .70, .10, "Mild and dry", 20, .0, 13),
    ("Monaco", "Circuit de Monaco", "2025-05-25", False, .92, .22, .81, .28, "Warm and dry", 22, .0, 12),
    ("Spain", "Circuit de Barcelona-Catalunya", "2025-06-01", False, .78, .42, .70, .09, "Warm and breezy", 25, .0, 25),
    ("Canada", "Circuit Gilles-Villeneuve", "2025-06-15", False, .50, .61, .70, .20, "Cool, variable", 18, .8, 24),
    ("Austria", "Red Bull Ring", "2025-06-29", False, .48, .66, .59, .13, "Hot and dry", 27, .0, 15),
    ("Great Britain", "Silverstone", "2025-07-06", False, .75, .54, .68, .21, "Cool, mixed conditions", 17, .6, 30),
    ("Belgium", "Spa-Francorchamps", "2025-07-27", True, .68, .64, .62, .19, "Rain risk", 16, 1.3, 23),
    ("Hungary", "Hungaroring", "2025-08-03", False, .82, .30, .76, .09, "Hot and dry", 31, .0, 13),
    ("Netherlands", "Circuit Zandvoort", "2025-08-31", False, .79, .36, .73, .15, "Windy coastal conditions", 20, .2, 33),
    ("Italy", "Monza", "2025-09-07", False, .22, .95, .36, .09, "Warm and dry", 25, .0, 14),
    ("Azerbaijan", "Baku City Circuit", "2025-09-21", False, .38, .89, .48, .22, "Windy and dry", 23, .0, 31),
    ("Singapore", "Marina Bay Street Circuit", "2025-10-05", False, .76, .38, .77, .18, "Hot, humid, rain risk", 29, .7, 14),
    ("United States", "Circuit of the Americas", "2025-10-19", True, .66, .55, .71, .11, "Warm and dry", 24, .0, 17),
    ("Mexico", "Autodromo Hermanos Rodriguez", "2025-10-26", False, .64, .72, .51, .10, "Thin air and dry", 22, .0, 18),
    ("Sao Paulo", "Interlagos", "2025-11-09", True, .71, .47, .70, .21, "Rain risk", 20, 1.1, 21),
    ("Las Vegas", "Las Vegas Strip Circuit", "2025-11-22", False, .25, .91, .34, .14, "Cold and dry", 13, .0, 12),
    ("Qatar", "Lusail International Circuit", "2025-11-30", True, .68, .65, .57, .11, "Warm and dry", 27, .0, 17),
    ("Abu Dhabi", "Yas Marina Circuit", "2025-12-07", False, .54, .68, .54, .08, "Dry twilight", 25, .0, 11),
]

CALENDAR = [
    {
        "round": index,
        "name": row[0], "venue": row[1], "date": row[2], "sprint": row[3],
        "aero": row[4], "powertrain": row[5], "chassis": row[6], "risk": row[7],
        "weather": {
            "condition": "See local historical race-session context.",
            "temperature_c": None, "rain_mm": None, "wind_kph": None,
        },
    }
    for index, row in enumerate(_ROUND_ROWS, start=1)
]


def team(team_id):
    return TEAMS[team_id]


def drivers():
    return [driver for details in TEAMS.values() for driver in details["drivers"]]


def avatar_path(driver_id):
    return ASSET_ROOT / f"{driver_id}.svg"


def historical_round(team_id, round_number):
    """Return only a team's locally bundled verified Grand Prix/Sprint result facts."""
    payload = HISTORICAL_2025["team_round_results"][team_id][str(round_number)]
    sessions = []
    for session_key, label in (("qualifying", "Qualifying"), ("sprint", "Sprint"), ("gp", "Grand Prix")):
        for driver_id, position, points, status in payload[session_key]:
            sessions.append({
                "session": label,
                "driver_id": driver_id,
                "driver": HISTORICAL_2025["drivers"].get(driver_id, driver_id.replace("_", " ").title()),
                "position": position,
                "points": points,
                "status": status,
            })
    return {
        "points": HISTORICAL_2025["team_round_points"][team_id][round_number - 1],
        "results": sessions,
        "source": HISTORICAL_2025["source"],
    }


def historical_round_form(team_id, round_number):
    """Normalize a real 2025 team's round points around its own season average."""
    points = HISTORICAL_2025["team_round_points"][team_id]
    average = sum(points) / len(points)
    return max(-1.0, min(1.0, (points[round_number - 1] - average) / max(10.0, average)))


def weekend_context(round_number):
    """Return locally bundled OpenF1/Open-Meteo context for one exact replay round."""
    return WEEKEND_CONTEXT_2025.get("rounds", {}).get(str(int(round_number)), {})


def _weather_summary(session_name, raw_weather, round_weather):
    """Normalise a source record for display without estimating missing fields."""
    raw_weather = raw_weather or {}
    meteo = (round_weather or {}).get("open_meteo", {}) if session_name == "Grand Prix" else {}
    def source_range(value):
        if isinstance(value, dict):
            return value
        if value is None:
            return {}
        return {"min": value, "max": value, "mean": value}

    wind = source_range(raw_weather.get("wind_speed_mps"))
    return {
        "session": session_name,
        "available": bool(raw_weather.get("available")),
        "source_url": raw_weather.get("source_url"),
        "sample_count": raw_weather.get("sample_count"),
        "air_temperature_c": source_range(raw_weather.get("air_temperature_c")),
        "track_temperature_c": source_range(raw_weather.get("track_temperature_c")),
        "humidity_percent": source_range(raw_weather.get("humidity_percent")),
        "wind_speed_kph": {
            key: (value * 3.6 if value is not None else None)
            for key, value in wind.items()
        },
        "rainfall_observed": raw_weather.get("rainfall_observed"),
        "representative_samples": raw_weather.get("representative_samples", []),
        "open_meteo": meteo,
    }


def historical_weather(round_number):
    """Return actual local weather summaries for race and Sprint sessions when held."""
    record = weekend_context(round_number)
    round_weather = record.get("weather", {})
    summaries = []
    for session_name, session in record.get("sessions", {}).items():
        weather = session.get("weather")
        # Older context rows keep the Grand Prix observation at round level.
        if not weather and session_name == "Grand Prix":
            weather = round_weather.get("openf1")
        if weather:
            summaries.append(_weather_summary(session_name, weather, round_weather))
    primary = next((item for item in summaries if item["session"] == "Grand Prix"), summaries[0] if summaries else None)
    return {
        "available": bool(primary),
        "primary": primary,
        "sessions": summaries,
        "source_note": "OpenF1 race-session observations; Open-Meteo precipitation is a local weather-grid reanalysis estimate.",
    }


def strategy_for(team_id, round_number):
    """Return actual source-backed selected-team stint and pit records, never estimates."""
    record = weekend_context(round_number)
    entries = []
    for session_name in ("Sprint", "Grand Prix"):
        session = record.get("sessions", {}).get(session_name, {})
        drivers = []
        for driver_id, driver in session.get("drivers", {}).items():
            if driver.get("team_id") != team_id:
                continue
            drivers.append({
                "driver_id": canonical_driver_id(driver_id),
                "driver": driver.get("driver", driver_id.replace("_", " ").title()),
                "stints": list(driver.get("stints") or []),
                "pit_stops": list(driver.get("pit_stops") or []),
                "stints_available": bool(driver.get("stints_available")),
                "pit_stops_available": bool(driver.get("pit_stops_available")),
            })
        if session:
            entries.append({
                "session": session_name,
                "available": bool(session.get("available")),
                "source_url": session.get("source_url"),
                "pit_source_url": session.get("pit_source_url"),
                "drivers": drivers,
            })
    return {
        "available": bool(entries),
        "sessions": entries,
        "note": "Actual OpenF1 tyre-stint and pit-lane records. Empty source-returned pit lists mean no stop was recorded; unavailable fields are not inferred.",
    }


# --- Exact historical replay helpers ---------------------------------------

TEAM_NAME_TO_ID = {
    "mclaren": "mclaren",
    "mercedes": "mercedes",
    "red bull racing": "red_bull",
    "red bull": "red_bull",
    "ferrari": "ferrari",
    "williams": "williams",
    "racing bulls": "racing_bulls",
    "rb": "racing_bulls",
    "aston martin": "aston_martin",
    "aston martin aramco": "aston_martin",
    "haas f1 team": "haas",
    "haas": "haas",
    "kick sauber": "sauber",
    "stake f1 team kick sauber": "sauber",
    "sauber": "sauber",
    "alpine": "alpine",
    "bwt alpine f1 team": "alpine",
}


def _round_record(round_number):
    return REPLAY_2025.get("rounds", {}).get(str(round_number), {})


def replay_available():
    return bool(REPLAY_2025.get("rounds"))


def replay_weekend(round_number):
    """Return the immutable local result payload for one 2025 race weekend."""
    record = _round_record(round_number)
    if not record:
        raise ValueError("The local exact-2025 replay data has not been installed yet.")
    return record


def replay_session_names(round_number):
    record = replay_weekend(round_number)
    sessions = record.get("sessions", {})
    canonical = ["Sprint Qualifying", "Sprint", "Grand Prix Qualifying", "Qualifying", "Grand Prix"]
    result = []
    for name in canonical:
        if name in sessions:
            result.append(name)
    return result


def replay_rows(round_number, session_name):
    session = replay_weekend(round_number).get("sessions", {}).get(session_name, {})
    return session.get("rows", [])


def driver_directory():
    """A stable driver directory, including drivers who changed seats during 2025."""
    directory = {
        driver_id: {"id": driver_id, "name": details.get("name", driver_id.replace("_", " ").title())}
        for driver_id, details in REPLAY_2025.get("drivers", {}).items()
    }
    for legacy_id, name in HISTORICAL_2025.get("drivers", {}).items():
        canonical_id = canonical_driver_id(legacy_id)
        directory.setdefault(canonical_id, {"id": canonical_id, "name": name})
        directory[legacy_id] = directory[canonical_id]
    for details in TEAMS.values():
        for driver in details["drivers"]:
            canonical_id = canonical_driver_id(driver["id"])
            directory.setdefault(canonical_id, {"id": canonical_id, "name": driver["name"]})
            directory[driver["id"]] = directory[canonical_id]
    for round_data in REPLAY_2025.get("rounds", {}).values():
        for session in round_data.get("sessions", {}).values():
            for row in session.get("rows", []):
                driver_id = row.get("driver_id")
                if driver_id:
                    directory.setdefault(driver_id, {"id": driver_id, "name": row.get("driver", driver_id.replace("_", " ").title())})
    return directory


def portrait_path(driver_id):
    """Prefer a locally bundled photo, then fall back to the original SVG badge."""
    driver_id = canonical_driver_id(driver_id)
    photo_aliases = {
        "alexander_albon": "alex_albon",
        "andrea_kimi_antonelli": "kimi_antonelli",
    }
    photo_id = photo_aliases.get(driver_id, driver_id)
    for extension in ("webp", "jpg", "jpeg", "png"):
        candidate = ASSET_ROOT / "photos" / f"{photo_id}.{extension}"
        if candidate.exists():
            return candidate
    return avatar_path(driver_id)


def drivers_for_team_round(team_id, round_number):
    """Return the actual race entrants for a constructor in a historical weekend."""
    try:
        weekend = replay_weekend(round_number)
    except ValueError:
        return TEAMS[team_id]["drivers"]
    found = {}
    for session in weekend.get("sessions", {}).values():
        for row in session.get("rows", []):
            row_team = row.get("team_id") or TEAM_NAME_TO_ID.get(str(row.get("team", "")).lower())
            if row_team == team_id and row.get("driver_id"):
                found[row["driver_id"]] = {"id": row["driver_id"], "name": row.get("driver", row["driver_id"].replace("_", " ").title())}
    return list(found.values()) or TEAMS[team_id]["drivers"]


def incidents_for(team_id, round_number):
    """Return only sourced selected-team records for the given historical weekend."""
    items = INCIDENTS_2025.get("incidents", INCIDENTS_2025 if isinstance(INCIDENTS_2025, list) else [])
    results = []
    for item in items:
        if item.get("team_id") != team_id or int(item.get("round", 0)) != int(round_number):
            continue
        result = dict(item)
        result["driver_id"] = canonical_driver_id(result.get("driver_id"))
        results.append(result)
    return results
