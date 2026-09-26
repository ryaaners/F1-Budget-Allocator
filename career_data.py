"""Local reference data for the 2025 F1 Season Budget Simulation.

The simulator is intentionally offline.  Championship results, weather and weekend
notes are stored as compact local reference data; financial values and incident costs
are gameplay estimates, not FIA filings or team accounts.
"""
from __future__ import annotations

import json
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


# date, venue, sprint, aero, power, chassis, baseline risk, historic weather.
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
        "weather": {"condition": row[8], "temperature_c": row[9], "rain_mm": row[10], "wind_kph": row[11]},
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


def strategy_for(team_id, round_number):
    """A compact local historical-strategy reference for the selected team's view."""
    track = CALENDAR[round_number - 1]
    wet = track["weather"]["rain_mm"] >= .5
    compounds = "Intermediate → Intermediate" if wet else ("Medium → Hard" if round_number % 3 else "Soft → Hard → Medium")
    first_stop = 18 + ((round_number * 3 + TEAMS[team_id]["historical_rank"]) % 12)
    second_stop = first_stop + 18 if "→" in compounds and compounds.count("→") > 1 else None
    stops = [first_stop] + ([second_stop] if second_stop else [])
    return {
        "compounds": compounds,
        "pit_laps": stops,
        "note": "Local historical strategy reference. Team intent is only shown where explicitly published.",
    }


def events_for(team_id, round_number):
    """Local curated event prompts. Costs are gameplay estimates, not published team costs."""
    events = []
    team_name = TEAMS[team_id]["name"]
    if round_number == 8:
        events.append({
            "kind": "wall_contact", "session": "Grand Prix", "title": "Monaco wall contact",
            "amount": 2_200_000, "category": "Chassis / structures", "probability": .86,
            "reason": "High-risk street-circuit wall contact", "responsible": "Not officially assigned",
            "source": "Local historical-risk template", "penalty": .350,
        })
    if round_number == 12:
        events.append({
            "kind": "assembly_replacement", "session": "Grand Prix", "title": "Silverstone suspension / aero assembly",
            "amount": 800_000, "category": "Chassis / structures", "probability": .66,
            "reason": "High-speed gravel and kerb exposure", "responsible": "Not officially assigned",
            "source": "Local historical-risk template", "penalty": .180,
        })
    for result in historical_round(team_id, round_number)["results"]:
        if result["session"] not in {"Grand Prix", "Sprint"} or result["status"] in {"Finished", "Lapped"}:
            continue
        events.append({
            "kind": "historical_result_status", "session": result["session"],
            "title": f"{result['driver']} {result['session']} status: {result['status']}",
            "amount": 0, "category": "Other", "probability": 1.0,
            "reason": f"Official archived session status: {result['status']}.",
            "responsible": "Not officially assigned", "source": "Jolpica historical results archive",
            "penalty": 0.0, "historical_only": True,
        })
    # A smaller team-specific local reference event to make the weekend history useful.
    trigger = (TEAMS[team_id]["historical_rank"] * 3) % 19 + 2
    if round_number == trigger and round_number not in (8, 12):
        events.append({
            "kind": "historical_reference", "session": "Grand Prix", "title": f"{team_name} weekend incident review",
            "amount": 650_000 + TEAMS[team_id]["historical_rank"] * 75_000,
            "category": "Operations", "probability": .58,
            "reason": "Local curated 2025 weekend reference", "responsible": "Not officially assigned",
            "source": "Local curated reference", "penalty": .120,
        })
    return events
