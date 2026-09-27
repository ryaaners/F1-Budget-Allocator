from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import career_engine as season
from career_data import CALENDAR, CAP, CATEGORIES, TEAMS, canonical_driver_id, driver_directory, drivers_for_team_round, portrait_path

DB = Path(__file__).with_name("f1_budget.db")
DEFAULT_ALLOC = dict(zip(CATEGORIES, [48, 62, 32, 28, 18, 17, 10]))
DEFAULT_RATES = dict(zip(CATEGORIES, [.18, .12, .10, .05, .04, .08, .02]))
DEFAULT_FACTORS = dict(zip(CATEGORIES, [.95, .55, .80, .50, .65, 1.05, .35]))


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY, cap_allocation REAL, rate REAL)")
    con.execute("CREATE TABLE IF NOT EXISTS spend_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, amount REAL, entry_date TEXT, race_weekend TEXT, note TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS scenarios (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, category TEXT, adjustment REAL, mode TEXT, lap_delta REAL, remaining_cap REAL, created_at TEXT)")
    if con.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        con.executemany("INSERT INTO categories VALUES (?, ?, ?)", [(item, DEFAULT_ALLOC[item] * 1e6, DEFAULT_RATES[item]) for item in CATEGORIES])
    if con.execute("SELECT COUNT(*) FROM spend_entries").fetchone()[0] == 0:
        entries = []
        for quarter, share in [("Q1", 1 / 3), ("Q2", 1 / 3), ("Q3", 1 / 3)]:
            for category in CATEGORIES:
                entries.append((category, DEFAULT_ALLOC[category] * 1e6 * DEFAULT_FACTORS[category] * share, date.today().isoformat(), quarter, "Synthetic starter data"))
        con.executemany("INSERT INTO spend_entries(category, amount, entry_date, race_weekend, note) VALUES (?,?,?,?,?)", entries)
    season.migrate(con)
    # This preserves an existing budget ledger while replacing legacy synthetic
    # classifications with sourced 2025 replay data through its current round.
    season.rebase_active_replay(con)
    con.commit()
    return con


def load_budget(con):
    return (
        pd.read_sql_query("SELECT * FROM categories", con),
        pd.read_sql_query("SELECT * FROM spend_entries ORDER BY entry_date DESC, id DESC", con),
    )


def money(value):
    return f"CAD ${float(value) / 1_000_000:,.1f}M"


def signed_money(value):
    return f"{'-' if value < 0 else '+'}CAD ${abs(float(value)) / 1_000_000:,.1f}M"


def rerun_app():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def navigate(destination):
    """Update the sidebar radio through a pre-run Streamlit callback."""
    st.session_state["workspace"] = destination


def reset_active_replay():
    """Clear only the replay tables, then return the sidebar to the homepage."""
    reset_con = season.connect(DB)
    try:
        season.reset_career(reset_con)
    finally:
        reset_con.close()
    st.session_state["workspace"] = "Home"


def show_chart(figure):
    st.plotly_chart(figure)


def show_table(frame):
    st.dataframe(frame)


def cad_table(frame, money_columns=(), percent_columns=(), decimal_columns=()):
    display = frame.copy()
    for column in money_columns:
        if column in display:
            display[column] = display[column].map(lambda value: f"CAD ${float(value):,.0f}")
    for column in percent_columns:
        if column in display:
            display[column] = display[column].map(lambda value: f"{float(value):.0%}")
    for column in decimal_columns:
        if column in display:
            display[column] = display[column].map(lambda value: f"{float(value):.3f}")
    return display


def range_text(values, unit, digits=1):
    """Format a bundled source range without creating a value for missing data."""
    if not isinstance(values, dict):
        return "Not supplied"
    low, high = values.get("min"), values.get("max")
    if low is None and high is None:
        return "Not supplied"
    if low is None:
        return f"{float(high):.{digits}f}{unit}"
    if high is None or float(low) == float(high):
        return f"{float(low):.{digits}f}{unit}"
    return f"{float(low):.{digits}f}–{float(high):.{digits}f}{unit}"


def budget_gain(rate, spend):
    return rate * (1 - np.exp(-max(0.0, spend) / 6_000_000.0))


def livery_css(primary, secondary, mode):
    accent = primary if mode == "team" else "#E10600"
    accent_two = secondary if mode == "team" else "#F5F5F5"
    return f"""<style>
    :root {{ --team-primary:{accent}; --team-secondary:{accent_two}; --panel:#121721; --ink:#EAF0F5; --muted:#AEB8C4; }}
    [data-testid="stAppViewContainer"] {{
        background-color:#080A0E;
        background-image:linear-gradient(45deg,rgba(255,255,255,.018) 25%,transparent 25%),linear-gradient(-45deg,rgba(255,255,255,.018) 25%,transparent 25%),linear-gradient(45deg,transparent 75%,rgba(255,255,255,.018) 75%),linear-gradient(-45deg,transparent 75%,rgba(255,255,255,.018) 75%);
        background-size:10px 10px;background-position:0 0,0 5px,5px -5px,-5px 0;
    }}
    .block-container {{padding-top:1.8rem;padding-bottom:3rem;max-width:1440px;}}
    h1,h2,h3,h4 {{font-family:"Arial Narrow","Aptos Display",sans-serif;letter-spacing:.035em;text-transform:uppercase;}}
    [data-testid="stMetric"] {{background:rgba(18,23,33,.94);border-left:3px solid var(--team-primary);padding:.72rem .85rem;}}
    [data-testid="stSidebar"] {{background:#0E1117;}}
    .finish-line {{height:10px;margin:.4rem 0 1.35rem;background-color:var(--team-primary);background-image:conic-gradient(from 90deg at 1px 1px,#fff 90deg,transparent 0);background-size:18px 18px;}}
    .team-panel,.session-panel {{background:linear-gradient(120deg,rgba(255,255,255,.065),rgba(0,0,0,.18));border-left:4px solid var(--team-primary);padding:1rem 1.2rem;margin:.5rem 0 1rem;}}
    .team-panel h2 {{white-space:nowrap;font-size:clamp(1.2rem,2vw,2rem);}}
    .telemetry-label {{color:var(--muted);text-transform:uppercase;letter-spacing:.09em;font-size:.74rem;}}
    .portrait-card {{text-align:center;background:rgba(12,16,22,.88);padding:.75rem;border-bottom:2px solid var(--team-secondary);min-height:145px;}}
    .home-hero {{padding:2.2rem 2.3rem 2.5rem;margin:.3rem 0 1.5rem;border:1px solid rgba(255,255,255,.16);border-top:5px solid var(--team-primary);background:linear-gradient(120deg,rgba(18,24,35,.96),rgba(8,10,14,.82));position:relative;overflow:hidden;}}
    .home-hero:after {{content:"";position:absolute;right:-5%;bottom:-35%;height:220px;width:50%;opacity:.16;background:repeating-linear-gradient(90deg,var(--team-primary) 0 8px,transparent 8px 18px);transform:rotate(-12deg);}}
    .home-kicker {{font-size:.75rem;letter-spacing:.16em;color:var(--team-secondary);font-weight:800;}}
    .home-title {{font-size:clamp(2.2rem,5vw,4.8rem);font-family:"Arial Narrow","Aptos Display",sans-serif;font-weight:900;line-height:.92;letter-spacing:.04em;margin:.45rem 0 1rem;max-width:850px;}}
    .home-copy {{font-size:1.05rem;color:#D7DFE8;max-width:660px;line-height:1.55;}}
    .status-chip {{display:inline-block;margin:.2rem .25rem .2rem 0;padding:.25rem .55rem;border:1px solid rgba(255,255,255,.2);font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;}}
    .stButton > button {{border-color:var(--team-primary);}}
    [data-baseweb="tab"] {{font-weight:700;letter-spacing:.05em;}}
    </style>"""


def show_portrait(driver, team, width=78):
    path = portrait_path(driver["id"])
    if path.exists():
        st.image(str(path), width=width)
        return
    initials = "".join(part[0] for part in driver["name"].split()[:2])
    st.markdown(f"<div style='background:{team['primary']};height:{width}px;width:{width}px;border-radius:50%;display:grid;place-items:center;font-weight:800'>{initials}</div>", unsafe_allow_html=True)


def team_driver_strip(team_id, round_number, width=60):
    team = TEAMS[team_id]
    drivers = drivers_for_team_round(team_id, round_number)
    columns = st.columns(len(drivers))
    for column, driver in zip(columns, drivers):
        with column:
            show_portrait(driver, team, width)
            st.caption(driver["name"])


def historic_driver(driver_id, fallback_name="Driver"):
    """Resolve a changing 2025 entrant to the local photo pack or its fallback."""
    driver_id = canonical_driver_id(driver_id)
    return driver_directory().get(
        driver_id,
        {"id": driver_id or "driver", "name": fallback_name or "Driver"},
    )


def display_team_dossier(team_id):
    team = TEAMS[team_id]
    left, middle, right = st.columns([1.1, 1.4, 1.4])
    with left:
        st.markdown(f"<div class='team-panel'><div class='telemetry-label'>2025 constructor</div><h2 style='margin:.2rem 0'>{team['name']}</h2><div>Historical position: P{team['historical_rank']} · {team['historical_points']} points<br>Local board target: P{team['board_target_rank']}</div></div>", unsafe_allow_html=True)
        st.metric("Historical opening delta", f"+{team['base_delta']:.2f}s")
        st.metric("Modelled fixed cost", money(team["fixed_cost"]))
    with middle:
        st.markdown("#### Round 1 drivers")
        team_driver_strip(team_id, 1, 78)
        st.caption("Driver cards follow the actual 2025 entrant list at each race weekend.")
    with right:
        costs = pd.DataFrame({"Category": list(team["model_cost_2024"]), "Modelled 2024 CAD": list(team["model_cost_2024"].values())})
        figure = px.bar(costs, x="Modelled 2024 CAD", y="Category", orientation="h", color_discrete_sequence=[team["primary"]], title="Modelled 2024 cost profile")
        figure.update_layout(height=290, margin=dict(l=0, r=0, t=45, b=0))
        show_chart(figure)
        st.caption("Modelled planning profile. FIA team cost-cap filings are confidential.")


def render_breach_preview(preview, label="Budget status"):
    sanction = preview["sanction"]
    if preview["over_cap"] <= 0:
        protected = float(preview.get("reserve_remaining", 0.0))
        free_capital = float(preview.get("discretionary_remaining", preview["remaining"]))
        if free_capital < 0:
            st.warning(
                f"{label}: this uses {money(abs(free_capital))} of the protected crash contingency. "
                "There is no current cap breach because repair cover remains unspent, but a later repair could create one."
            )
        elif protected:
            st.success(f"{label}: {money(free_capital)} remains free after holding {money(protected)} for crash repairs.")
        else:
            st.success(f"{label}: {money(preview['remaining'])} remains inside the CAD $215M gameplay cap.")
    else:
        st.warning(
            f"{label}: {money(preview['over_cap'])} over cap. {sanction['label']} at the illustrative gameplay audit: "
            f"{money(sanction['fine'])} fine, {sanction['wind_tunnel_cut']}% 2026 aero allowance reduction"
            + (f", and {sanction['point_deduction']} audit-only constructor points withheld." if sanction["point_deduction"] else ".")
        )


def render_home(con, state):
    team = TEAMS[state["team_id"]] if state else {"name": "2025 Grid", "primary": "#E10600", "secondary": "#FFFFFF"}
    season_label = "Continue exact replay" if state else "Start exact replay"
    st.markdown(
        f"""<section class='home-hero'>
        <div class='home-kicker'>FIA-inspired finance desk · local historical replay</div>
        <div class='home-title'>F1 Budget<br>Operations</div>
        <p class='home-copy'>Manage capital, crash contingency, repair decisions and cost-cap exposure while the 2025 timing record remains exactly as recorded.</p>
        <span class='status-chip'>24 rounds</span><span class='status-chip'>60 sessions</span><span class='status-chip'>CAD $215M gameplay cap</span>
        </section>""",
        unsafe_allow_html=True,
    )
    first, second, third = st.columns(3)
    with first:
        st.metric("Replay format", "Exact 2025")
        st.caption("No budget decision changes a historical result.")
    with second:
        st.metric("Current focus", team["name"])
        st.caption("Team colour and actual drivers follow the selected weekend.")
    with third:
        if state:
            st.metric("Next round", f"R{state['current_round']} of 24")
        else:
            st.metric("Start point", "Pre-season")
        st.caption("Crash contingency and cap choices remain interactive.")
    if state:
        finance = season.finance_summary(con)
        first, second, third = st.columns(3)
        first.metric("Cap spend to date", money(finance["spend"]))
        second.metric("Crash cover held", money(finance["crash_contingency"]["remaining"]))
        third.metric("Free capital after reserve", money(finance["discretionary_remaining"]))
    st.button(season_label, on_click=navigate, args=("2025 Season Budget Replay",))
    st.button("Open Budget Workspace", on_click=navigate, args=("Budget Workspace",))
    st.markdown("#### 2025 calendar")
    calendar = pd.DataFrame(CALENDAR)[["round", "name", "date", "sprint", "venue"]].rename(columns={"round": "Round", "name": "Grand Prix", "date": "Date", "sprint": "Sprint", "venue": "Circuit"})
    calendar["Sprint"] = calendar["Sprint"].map(lambda value: "Sprint" if value else "")
    show_table(calendar)


def render_setup(con):
    st.title("2025 F1 Season Budget Replay")
    st.markdown("<div class='finish-line'></div>", unsafe_allow_html=True)
    st.subheader("Pre-season command desk")
    st.caption("Classifications replay the recorded 2025 season. Financial decisions change the local ledger and illustrative audit only; historical results stay locked.")
    selected_id = st.selectbox("Select your constructor", list(TEAMS), format_func=lambda key: TEAMS[key]["name"])
    team = TEAMS[selected_id]
    display_team_dossier(selected_id)
    st.markdown("#### Allocate pre-season capital")
    defaults = {"Aero": 12., "Powertrain": 5., "Chassis / structures": 6., "Personnel": 4., "Operations": 2., "Testing": 3., "Other": 1.}
    allocation = {}
    columns = st.columns(2)
    for index, category in enumerate(CATEGORIES):
        with columns[index % 2]:
            allocation[category] = st.number_input(f"{category} pre-season allocation (CAD $M)", min_value=0.0, max_value=150.0, value=defaults[category], step=.5, key=f"setup_{category}") * 1_000_000
    crash_reserve = st.number_input("Crash contingency allocation (CAD $M)", min_value=0.0, max_value=30.0, value=5.0, step=.25, help="A protected repair envelope. It is not counted as spent until a sourced repair is recorded.") * 1_000_000
    committed = team["fixed_cost"] + sum(allocation.values())
    preview = {"remaining": CAP - committed, "over_cap": max(0.0, committed - CAP), "sanction": season.sanction_for(committed)}
    first, second, third = st.columns(3)
    first.metric("Pre-season cap spend", money(committed))
    second.metric("Crash contingency", money(crash_reserve))
    third.metric("Free capital after reserve", money(CAP - committed - crash_reserve))
    preview["reserve_remaining"] = crash_reserve
    preview["discretionary_remaining"] = CAP - committed - crash_reserve
    render_breach_preview(preview, "Pre-season preview")
    switch_round = st.slider("Future-car switch round", 1, 24, 16, help="After this round, Aero, Powertrain, Chassis and Testing commitments are labelled as future-car funding. They do not change the 2025 replay.")
    if st.button("Begin exact 2025 replay"):
        season.create_career(con, selected_id, allocation, crash_reserve, switch_round=switch_round, theme="team")
        rerun_app()


def render_incident_decisions(con):
    incidents = season.pending_incidents(con)
    if not incidents:
        return
    state = season.active_state(con)
    team = TEAMS[state["team_id"]]
    st.markdown("#### Historical repair planning")
    st.warning("These are historical 2025 event records for your selected team. Repair choices change the budget ledger, not the replayed classification.")
    st.caption("This records a local finance-planning decision from a historical incident. It is not an engineering repair instruction, vehicle-safety certification, or FIA decision.")
    for incident in incidents:
        title = f"{incident.get('session_name') or 'Weekend'} · {incident['title']}"
        with st.expander(title, expanded=incident["state"] == "pending"):
            driver = historic_driver(incident.get("driver_id"), incident.get("title", "Driver").split(" · ")[0])
            left, right = st.columns([.16, .84])
            with left:
                show_portrait(driver, team, 54)
            with right:
                st.caption(driver["name"])
            st.write(incident.get("reason") or "Historical event record.")
            st.caption(f"Responsible party: {incident.get('responsible') or 'Not officially assigned'}")
            st.caption(f"Damage area: {incident.get('components') or 'Not publicly confirmed'}")
            source_url = incident.get("source_url") or incident.get("source")
            if source_url and str(source_url).startswith("http"):
                st.markdown(f"[Source record]({source_url})")
            if not bool(incident.get("repair_required")):
                st.info("No repair amount is established by the available public record. No repair cost will be invented.")
                if st.button("Acknowledge event", key=f"ack_{incident['id']}"):
                    season.resolve_incident(con, incident["id"], "review")
                    rerun_app()
                continue
            low, high = float(incident.get("cost_low", 0)), float(incident.get("cost_high", 0))
            if high <= 0:
                if bool(incident.get("safety_critical")):
                    st.error("Project critical-repair flag: the replay needs a source-limitation acknowledgement before the next race. The public record does not support a cost estimate.")
                    action_label, action = "Acknowledge source limitation", "source_limited"
                else:
                    st.info("A repair was required, but public sources do not support a cost range. Record it without a fabricated invoice.")
                    action_label, action = "Record source limitation", "review"
                if st.button(action_label, key=f"limit_{incident['id']}"):
                    season.resolve_incident(con, incident["id"], action)
                    rerun_app()
                continue
            st.metric("Local repair estimate range", f"CAD ${low:,.0f} – CAD ${high:,.0f}")
            st.caption(incident.get("estimate_label") or "Public estimate; not a team invoice.")
            options = ["Record low-end estimate", "Choose repair amount", "Record high-end current-spec estimate"]
            if not bool(incident.get("safety_critical")):
                options.append("Reuse older-spec parts (local ledger choice)")
            else:
                st.error("Project critical-repair flag: the replay requires a local finance record before advancing. This is not a vehicle release decision.")
            decision = st.radio("Local finance record", options, key=f"decision_{incident['id']}")
            selected_amount = None
            if decision == "Choose repair amount":
                selected_amount = st.number_input("Repair amount (CAD)", min_value=low, max_value=high, value=(low + high) / 2, step=max(1_000.0, (high - low) / 20), key=f"amount_{incident['id']}")
            if st.button("Record local finance decision", key=f"repair_{incident['id']}"):
                action = {
                    "Record low-end estimate": "minimum",
                    "Choose repair amount": "custom",
                    "Record high-end current-spec estimate": "full",
                    "Reuse older-spec parts (local ledger choice)": "old_spec",
                }[decision]
                try:
                    season.resolve_incident(con, incident["id"], action, selected_amount)
                    rerun_app()
                except ValueError as error:
                    st.error(str(error))


def dataframe_results(results, session_name):
    frame = pd.DataFrame(results)
    if frame.empty:
        st.info("No classification is available yet.")
        return
    qualifying = "Qualifying" in session_name
    if qualifying:
        stage_columns = [column for column in ("sq1", "sq2", "sq3") if column in frame and frame[column].notna().any()]
        if not stage_columns:
            stage_columns = [column for column in ("q1", "q2", "q3") if column in frame and frame[column].notna().any()]
        cols = [column for column in ("position_display", "driver", "team", *stage_columns, "gap_display") if column in frame]
        display = frame[cols].rename(columns={
            "position_display": "Pos.", "driver": "Driver", "team": "Team", "q1": "Q1", "q2": "Q2", "q3": "Q3",
            "sq1": "SQ1", "sq2": "SQ2", "sq3": "SQ3", "gap_display": "Gap to pole",
        })
    else:
        cols = [column for column in ("position_display", "driver", "team", "laps", "time_display", "gap_display", "points") if column in frame]
        display = frame[cols].rename(columns={
            "position_display": "Pos.", "driver": "Driver", "team": "Team", "laps": "Laps",
            "time_display": "Time / status", "gap_display": "Gap", "points": "Points",
        })
    show_table(display)


def render_weekend_classification(records, team_id, heading):
    if not records:
        return
    team = TEAMS[team_id]
    st.markdown(f"#### {heading}")
    for record in records:
        session_name = record["session_name"]
        st.markdown(f"<div class='session-panel'><div class='telemetry-label'>Exact 2025 classification</div><h3 style='margin:.15rem 0'>{session_name}</h3></div>", unsafe_allow_html=True)
        dataframe_results(record["results"], session_name)
        selected_rows = [row for row in record["results"] if row.get("team_id") == team_id]
        if selected_rows:
            columns = st.columns(len(selected_rows))
            for column, row in zip(columns, selected_rows):
                with column:
                    show_portrait({"id": row["driver_id"], "name": row["driver"]}, team, 52)
                    st.caption(f"{row['driver']} · P{row.get('position_display', row.get('position', ''))}")
        for note in record.get("notes") or []:
            st.caption(f"Official note: {note}")
        st.caption(f"Source: {record.get('source', 'Local 2025 historical replay bundle')}")


def render_race_control(con, state):
    context = season.historical_context(con)
    track, team = context["round"], TEAMS[state["team_id"]]
    race_weather = context.get("weather", {}).get("primary")
    if race_weather:
        air = range_text(race_weather.get("air_temperature_c"), "°C")
        rain = "rain observed" if race_weather.get("rainfall_observed") else "no rain sample recorded"
        weather_line = f"{race_weather['session']} weather · air {air} · {rain}"
    else:
        weather_line = "Race-session weather is not available in the local context bundle"
    finance = season.finance_summary(con)
    reserve = finance["crash_contingency"]
    st.markdown(f"<div class='team-panel'><div class='telemetry-label'>Upcoming round {track['round']} of 24 · {'Sprint weekend' if track['sprint'] else 'Grand Prix weekend'}</div><h2 style='margin:.15rem 0'>{track['name']} — {track['venue']}</h2><div>{track['date']} · {weather_line}</div></div>", unsafe_allow_html=True)
    st.caption("Selected weekend entrants")
    team_driver_strip(state["team_id"], track["round"], 58)
    first, second, third, fourth = st.columns(4)
    first.metric("Cap headroom", money(finance["remaining"]))
    second.metric("Crash contingency remaining", money(reserve["remaining"]))
    third.metric("Free capital after reserve", money(finance["discretionary_remaining"]))
    fourth.metric("Crash repairs recorded", money(reserve["used"]))
    if reserve["uncovered"]:
        st.warning(f"{money(reserve['uncovered'])} of repair spend sits outside the original crash contingency allocation.")
    render_breach_preview({
        "remaining": finance["remaining"],
        "over_cap": max(0.0, -finance["remaining"]),
        "reserve_remaining": reserve["remaining"],
        "discretionary_remaining": finance["discretionary_remaining"],
        "sanction": finance["sanction"],
    })
    render_incident_decisions(con)
    st.markdown("#### Pre-race capital decision")
    first, second, third = st.columns(3)
    category = first.selectbox("Investment category", CATEGORIES, key="race_investment_category")
    amount = second.number_input("Package size (CAD $M)", min_value=0.0, max_value=100.0, value=2.0, step=.5, key="race_investment_amount")
    note = third.text_input("Package note", f"{track['name']} package", key="race_investment_note")
    target = "future-car funding" if track["round"] > state["switch_round"] and category in season.CURRENT_CAR_CATEGORIES else "2025 budget"
    st.caption(f"This commitment is labelled as **{target}**. It will not change the historical 2025 classification.")
    if amount > 0:
        render_breach_preview(season.breach_preview(con, amount * 1_000_000), "Package preview")
    if st.button("Commit package", key="commit_race_package") and amount > 0:
        season.commit_investment(con, category, amount * 1_000_000, note)
        rerun_app()
    st.markdown("#### Weekend replay")
    st.caption("One action stores every recorded session for the race weekend. Financial decisions remain in the ledger and cannot change the replay.")
    if st.button(f"Advance {track['name']} weekend"):
        try:
            season.run_weekend(con)
            rerun_app()
        except ValueError as error:
            st.error(str(error))
    completed = season.last_completed_round(con)
    if completed:
        records = season.session_results(con, completed)
        completed_track = CALENDAR[completed - 1]
        render_weekend_classification(records, state["team_id"], f"Latest complete weekend · Round {completed} {completed_track['name']}")


def render_telemetry(con, state):
    finance = season.finance_summary(con)
    outlook = season.development_outlook(con)
    left, right = st.columns([1, 1.3])
    with left:
        st.subheader("Constructors’ standings")
        standings = pd.DataFrame(season.standings(con)).drop(columns=["team_id"])
        show_table(standings)
    with right:
        items = pd.DataFrame(season.ledger(con))
        if not items.empty:
            actual = items[items["counts_to_cap"] == 1].groupby("round_number", as_index=False)["amount"].sum().sort_values("round_number")
            actual["Cumulative spend"] = actual["amount"].cumsum()
            actual = actual.rename(columns={"round_number": "Round"})
            base = TEAMS[state["team_id"]]["fixed_cost"]
            trajectory = pd.DataFrame({"Round": list(range(25))})
            trajectory["Permitted cap trajectory"] = base + (CAP - base) * trajectory["Round"] / 24
            figure = go.Figure()
            figure.add_scatter(x=trajectory["Round"], y=trajectory["Permitted cap trajectory"], name="Permitted trajectory", mode="lines", line=dict(dash="dot", color="#AAB2BD"))
            figure.add_scatter(x=actual["Round"], y=actual["Cumulative spend"], name="Actual cap spend", mode="lines+markers", line=dict(color=TEAMS[state["team_id"]]["primary"], width=4))
            figure.update_layout(title="Cap utilisation burn-down", xaxis_title="Round", yaxis_title="CAD", margin=dict(l=0, r=0, t=45, b=0))
            show_chart(figure)
    st.markdown("#### Financial health")
    health = max(0, min(100, finance["remaining"] / CAP * 100 + 50))
    gauge = go.Figure(go.Indicator(mode="gauge+number", value=health, number={"suffix": "%"}, title={"text": "Abu Dhabi cap health"}, gauge={"axis": {"range": [0, 100]}, "bar": {"color": TEAMS[state["team_id"]]["primary"]}, "steps": [{"range": [0, 35], "color": "#501515"}, {"range": [35, 65], "color": "#514718"}, {"range": [65, 100], "color": "#173D2A"}]}))
    first, second = st.columns([1, 2])
    with first:
        show_chart(gauge)
    with second:
        reserve = finance["crash_contingency"]
        st.metric("Forecast cap balance", money(finance["remaining"]))
        st.metric("Free capital after reserve", money(finance["discretionary_remaining"]))
        st.metric("Crash contingency", money(reserve["remaining"]), f"{money(reserve['used'])} used")
        st.metric("Future-car funding", money(outlook["future_capital"]))
        st.caption("Financial planning only. The replay uses the recorded 2025 classification and has no pace modifier.")
    st.markdown("#### Current versus future capital")
    first, second, third = st.columns(3)
    first.metric("Current-car commitments", money(outlook["current_capital"]))
    second.metric("Future-car commitments", money(outlook["future_capital"]))
    third.metric("Development switch point", f"Round {outlook['switch_round']}")
    st.info(outlook["note"])


def render_history_weather(con, state):
    context = season.historical_context(con)
    track, weather, strategy, events = context["round"], context["weather"], context["strategy"], context["events"]
    st.subheader("Historical weekend reference")
    st.caption("Selected weekend entrants")
    team_driver_strip(state["team_id"], track["round"], 50)
    left, right = st.columns(2)
    with left:
        st.markdown("#### Actual race-session weather")
        primary = weather.get("primary")
        if not primary:
            st.info("Historical weather was not available from the local source bundle for this race session.")
        else:
            first, second, third = st.columns(3)
            first.metric("Air", range_text(primary.get("air_temperature_c"), "°C"))
            second.metric("Track", range_text(primary.get("track_temperature_c"), "°C"))
            third.metric("Wind", range_text(primary.get("wind_speed_kph"), " km/h"))
            st.info(
                f"OpenF1 {primary['session']} samples: "
                + ("rain observed." if primary.get("rainfall_observed") else "no rain sample recorded.")
            )
            meteo = primary.get("open_meteo") or {}
            if meteo.get("available"):
                precipitation = meteo.get("precipitation_mm_in_window")
                if precipitation is not None:
                    st.caption(
                        f"Open-Meteo three-hour Grand Prix window: {float(precipitation):.1f} mm precipitation "
                        "(weather-grid reanalysis estimate)."
                    )
            if primary.get("source_url"):
                st.markdown(f"[OpenF1 weather record]({primary['source_url']})")
            samples = primary.get("representative_samples") or []
            if samples:
                with st.expander("Start, middle, and end weather samples"):
                    sample_frame = pd.DataFrame(samples).rename(columns={
                        "timestamp_utc": "UTC", "air_temperature_c": "Air (°C)",
                        "track_temperature_c": "Track (°C)", "humidity_percent": "Humidity (%)",
                        "wind_speed_mps": "Wind (m/s)", "rainfall_observed": "Rain observed",
                    })
                    show_table(sample_frame)
        sprint_weather = [item for item in weather.get("sessions", []) if item.get("session") == "Sprint"]
        for item in sprint_weather:
            with st.expander("Sprint-session weather"):
                st.write(
                    f"Air: {range_text(item.get('air_temperature_c'), '°C')} · "
                    f"Track: {range_text(item.get('track_temperature_c'), '°C')} · "
                    f"Wind: {range_text(item.get('wind_speed_kph'), ' km/h')}"
                )
                st.caption("Rain observed." if item.get("rainfall_observed") else "No rain sample recorded.")
                if item.get("source_url"):
                    st.markdown(f"[OpenF1 Sprint weather record]({item['source_url']})")
    with right:
        st.markdown("#### Actual tyre and pit operations")
        if not strategy.get("available"):
            st.info("Historical tyre and pit data was not available in the local source bundle for this weekend.")
        for session in strategy.get("sessions", []):
            with st.expander(f"{session['session']} tyre and pit timeline", expanded=True):
                if session.get("source_url"):
                    st.markdown(f"[OpenF1 stint record]({session['source_url']})")
                if session.get("pit_source_url"):
                    st.markdown(f"[OpenF1 pit-lane record]({session['pit_source_url']})")
                if not session.get("drivers"):
                    st.caption("No selected-team entrant record is available for this session.")
                for driver_record in session.get("drivers", []):
                    driver = historic_driver(driver_record["driver_id"], driver_record["driver"])
                    driver_left, driver_right = st.columns([.15, .85])
                    with driver_left:
                        show_portrait(driver, TEAMS[state["team_id"]], 44)
                    with driver_right:
                        st.markdown(f"**{driver['name']}**")
                        if driver_record.get("stints_available"):
                            stints = pd.DataFrame(driver_record.get("stints") or []).rename(columns={
                                "stint_number": "Stint", "compound": "Compound", "lap_start": "Start lap",
                                "lap_end": "End lap", "tyre_age_at_start": "Tyre age at start",
                            })
                            if stints.empty:
                                st.caption("The source returned no stint rows.")
                            else:
                                show_table(stints)
                        else:
                            st.caption("Tyre-stint record not supplied by the source.")
                        if driver_record.get("pit_stops_available"):
                            pit_stops = pd.DataFrame(driver_record.get("pit_stops") or []).rename(columns={
                                "timestamp_utc": "UTC", "lap": "Lap", "lane_duration_seconds": "Pit lane (s)",
                                "stationary_duration_seconds": "Stationary (s)",
                            })
                            if pit_stops.empty:
                                st.caption("No pit stop was recorded for this driver.")
                            else:
                                show_table(pit_stops)
                        else:
                            st.caption("Pit-lane record not supplied by the source.")
        st.caption(strategy.get("note", ""))
    st.markdown("#### Selected-team event reference")
    if events:
        for event in events:
            with st.expander(event.get("title", "Historical event"), expanded=True):
                driver = historic_driver(event.get("driver_id"), event.get("title", "Driver").split(" · ")[0])
                left, right = st.columns([.16, .84])
                with left:
                    show_portrait(driver, TEAMS[state["team_id"]], 50)
                with right:
                    st.caption(driver["name"])
                st.write(event.get("reason", "Historical record."))
                st.caption(f"Session: {event.get('session', 'Grand Prix')} · Driver: {event.get('driver_id', 'Team')} · Responsible party: {event.get('responsible', 'Not officially assigned')}")
                if event.get("source_url"):
                    st.markdown(f"[Source record]({event['source_url']})")
                if event.get("cost_high_cad", 0):
                    st.caption(f"Public estimate range: CAD ${event['cost_low_cad']:,.0f} – CAD ${event['cost_high_cad']:,.0f}. {event.get('estimate_label', '')}")
                else:
                    st.caption("No repair cost is claimed where public records do not establish one.")
    else:
        st.success("No selected-team incident, DNF, or penalty record is scheduled for this weekend.")


def render_season_ledger(con, state):
    st.subheader("Simulation financial ledger")
    items = pd.DataFrame(season.ledger(con))
    if not items.empty:
        display = items.rename(columns={
            "round_number": "Round", "session_name": "Session", "category": "Category", "amount": "Amount (CAD)",
            "kind": "Entry type", "note": "Note", "future_car": "Future car", "created_at": "Recorded",
            "effect": "Effects", "counts_to_cap": "Counts toward cap",
        })
        display["Future car"] = display["Future car"].map(lambda value: "Yes" if value else "")
        display["Counts toward cap"] = display["Counts toward cap"].map(lambda value: "Yes" if value else "Planning reserve")
        show_table(cad_table(display, money_columns=("Amount (CAD)",)))
        st.download_button("Download season ledger CSV", items.to_csv(index=False).encode(), "2025_season_budget_ledger.csv", "text/csv")
    reserve = season.crash_contingency(con)
    first, second, third = st.columns(3)
    first.metric("Crash contingency allocated", money(reserve["target"]))
    second.metric("Crash repairs charged", money(reserve["used"]))
    third.metric("Contingency remaining", money(reserve["remaining"]))
    updated_reserve = st.number_input("Update crash contingency allocation (CAD $M)", min_value=0.0, max_value=30.0, value=reserve["target"] / 1_000_000, step=.25)
    if st.button("Save crash contingency allocation"):
        season.set_crash_reserve(con, updated_reserve * 1_000_000)
        rerun_app()
    with st.expander("Add manual crash or repair event"):
        with st.form("manual_career_incident"):
            first, second, third = st.columns(3)
            title = first.text_input("Event", "Manual component damage")
            amount = second.number_input("Estimated repair (CAD)", min_value=0.0, value=1_000_000.0, step=100_000.0)
            category = third.selectbox("Category", CATEGORIES, index=2)
            if st.form_submit_button("Add pending repair") and amount > 0:
                season.add_manual_incident(con, title, amount, category)
                rerun_app()


def render_safety_planning(con, state):
    """Show the evidence available for the next safety-planning phase.

    This deliberately remains a record-and-boundary view until source data or
    user-approved prototype assumptions can support a real planning model.
    """
    snapshot = season.safety_planning_snapshot(con)
    if not snapshot:
        st.info("Start an exact replay to view its historical incident evidence.")
        return
    st.subheader("Safety planning foundation")
    st.caption(
        "Historical records remain locked. This screen does not issue a safety release, prescribe a repair, or change a 2025 result."
    )
    reserve = snapshot["crash_contingency"]
    first, second, third, fourth = st.columns(4)
    first.metric("Historical incident cases", len(snapshot["historical_records"]))
    second.metric("Open repair records", len(snapshot["open_repair_records"]))
    third.metric("Open project-critical records", len(snapshot["open_critical_records"]))
    fourth.metric("Crash cover remaining", money(reserve["remaining"]))

    held_records = snapshot["replay_hold_incidents"]
    if held_records:
        names = ", ".join(item["title"] for item in held_records)
        st.warning(
            "Replay advance held: a project-critical repair record remains unresolved. "
            f"Record the required local repair decision in Race control before advancing: {names}. "
            "This is a replay workflow gate, not a safe-to-race assessment."
        )
    else:
        st.info(
            "No prior project-critical repair record is holding the replay advance. "
            "This does not establish vehicle readiness or authorise a car release."
        )

    st.markdown("#### Historical incident evidence")
    historical_records = snapshot["historical_records"]
    if not historical_records:
        st.info("No selected-team incident case has been revealed in this replay yet.")
    else:
        evidence_rows = []
        for record in historical_records:
            low = float(record.get("cost_low") or 0)
            high = float(record.get("cost_high") or 0)
            estimate = (
                f"CAD ${low:,.0f} – CAD ${high:,.0f} (local estimate)"
                if high > 0 else "Not established by the public record"
            )
            evidence_rows.append({
                "Round": record["round_number"],
                "Historical record": record["title"],
                "Damage area": record.get("components") or "Not publicly confirmed",
                "Project critical-repair flag": "Yes" if record.get("safety_critical") else "",
                "Repair record": str(record.get("state") or "").replace("_", " ").title(),
                "Pre-existing repair band": estimate,
                "Source link": "Available" if str(record.get("source_url") or "").startswith(("https://", "http://")) else "Not recorded",
            })
        show_table(pd.DataFrame(evidence_rows))
        linked_records = snapshot["source_linked_records"]
        if linked_records:
            with st.expander("Open historical source records"):
                for record in linked_records:
                    st.markdown(
                        f"[Round {record['round_number']} · {record['title']}]({record['source_url']})"
                    )
        st.caption(
            "Repair bands are pre-existing local financial estimates where public damage context exists; they are not team invoices, engineering instructions, or proof of repair quality."
        )

    manual_records = snapshot["manual_records"]
    if manual_records:
        st.markdown("#### Local manual planning entries")
        st.caption("These are user-entered local ledger entries, not historical incident evidence.")
        manual_rows = []
        for record in manual_records:
            manual_rows.append({
                "Round": record["round_number"],
                "Local entry": record["title"],
                "Category": record["category"],
                "Repair record": str(record.get("state") or "").replace("_", " ").title(),
                "User-entered estimate": money(record.get("cost_high") or 0),
                "Entry source": record.get("source") or "Local manual entry",
            })
        show_table(pd.DataFrame(manual_rows))

    st.markdown("#### Evidence boundary")
    left, right = st.columns(2)
    with left:
        st.markdown(
            """**Available in the local historical record**

- Incident description, event/session, driver, and damaged-area summary where public reporting provides them.
- Source links where the bundled record includes one.
- A project critical-repair flag, repair-record status, and the existing crash-contingency ledger.
"""
        )
    with right:
        st.markdown(
            """**Not yet modelled**

- Verified spare inventory or component condition.
- Repair duration, staffing, inspection/sign-off, or release approval.
- Risk probabilities, a readiness score, predicted incidents, or a safe-to-race outcome.
"""
        )
    readiness_model = snapshot["readiness_model"]
    st.info(f"Readiness outcome unavailable: {readiness_model['reason']}")
    st.caption("Use Race control to record the existing local repair-finance decision. A later, separate phase can add editable, clearly labelled prototype assumptions after data review.")


def render_audit(con):
    audit = season.audit(con)
    team = audit["team"]
    summary, sanction = audit["summary"], audit["sanction"]
    st.title("Board Audit & FIA-Inspired Review")
    st.markdown("<div class='finish-line'></div>", unsafe_allow_html=True)
    st.header(audit["verdict"])
    st.caption("Abu Dhabi race entrants")
    team_driver_strip(team["id"], 24, 58)
    first, second, third = st.columns(3)
    first.metric("Historical 2025 constructor result", f"P{audit['player']['Position']} · {audit['player']['Points']} pts")
    second.metric("Final cap spend", money(summary["spend"]))
    third.metric("Cap balance", money(summary["remaining"]))
    st.markdown("#### Local gameplay audit")
    a, b, c, d = st.columns(4)
    a.metric("Crash tax", money(summary["crash_tax"]))
    b.metric("Planned R&D", money(summary["planned_rnd"]))
    c.metric("Cost per constructor point", f"CAD ${audit['cost_per_point']:,.0f}")
    d.metric("Future-car funding", money(audit["future_capital"]))
    left, right = st.columns(2)
    with left:
        st.markdown("##### Line-item breakdown")
        show_table(cad_table(pd.DataFrame(audit["financial_lines"]), money_columns=("Amount",)))
    with right:
        st.markdown("##### Cap spend by category")
        show_table(cad_table(pd.DataFrame(audit["category_lines"]), money_columns=("Cap spend",)))
    st.caption(
        f"Crash cover began at {money(summary['crash_contingency']['target'])}; "
        f"{money(summary['crash_contingency']['remaining'])} remained unspent at the finish."
    )
    if sanction["breach"]:
        st.warning(f"{sanction['label']}: {money(sanction['breach'])} over cap. Illustrative game outcome: {money(sanction['fine'])} fine, {sanction['wind_tunnel_cut']}% 2026 aero allowance reduction" + (f", {sanction['point_deduction']} audit-only points withheld." if sanction["point_deduction"] else "."))
        st.caption("The historical 2025 replay table is never rewritten; point withholding is shown only as a game audit consequence.")
    else:
        st.success("Within the local gameplay cap. No illustrative game outcome applies.")
    sanction_matrix = pd.DataFrame([
        {"Gameplay cap position": "At or below CAD $215M", "Game audit consequence": "Within gameplay cap"},
        {"Gameplay cap position": "More than CAD $215M, up to and including 5% over", "Game audit consequence": "CAD $5M fine · 10% aero allowance reduction"},
        {"Gameplay cap position": "More than 5% over", "Game audit consequence": "CAD $10M fine · 20% reduction · 10 audit-only points"},
    ])
    st.markdown("##### Illustrative gameplay outcome matrix")
    show_table(sanction_matrix)
    st.caption("This CAD $215M budget and fixed outcome matrix are local gameplay rules. They do not calculate FIA Relevant Costs, determine an FIA breach, or predict an FIA sanction. [2025 FIA Financial Regulations](https://www.fia.com/system/files/documents/2025_fia_formula_1_financial_regulations_-_issue_25_-_2025-07-31.pdf)")
    st.markdown("#### Replay integrity")
    comparison = pd.DataFrame([
        {"Measure": "Constructor position", "Recorded 2025": f"P{team['historical_rank']}", "Replay": f"P{audit['player']['Position']}"},
        {"Measure": "Constructor points", "Recorded 2025": team["historical_points"], "Replay": audit["player"]["Points"]},
        {"Measure": "Local board target", "Recorded 2025": f"P{audit['board_target_rank']} target", "Replay": f"P{audit['player']['Position']}"},
    ])
    show_table(comparison)
    st.caption("Replay values are sourced historical outcomes. Financial decisions do not modify them.")
    first, second = st.columns(2)
    with first:
        st.metric("Player switch point", f"Round {audit['development_switch_round']}")
    with second:
        st.metric("Inferred team proxy", f"Round {audit['development_proxy_round']}")
    st.caption(audit["development_proxy_note"])
    comparator_frame = pd.DataFrame(audit["grid_comparators"]).drop(columns=["team_id"])
    st.markdown("##### Modelled cost-per-point grid comparator")
    show_table(cad_table(comparator_frame, money_columns=("Modelled CAD / point",)))
    st.caption(f"Your replay budget: CAD ${audit['cost_per_point']:,.0f} per point. Modelled grid median: CAD ${audit['grid_median_cost_per_point']:,.0f} per point.")
    st.markdown("#### Key financial moments")
    if audit["largest_upgrade"]:
        upgrade = audit["largest_upgrade"]
        st.info(f"Largest development commitment: Round {upgrade['round_number']} · {upgrade['category']} · {money(upgrade['amount'])}. It is a finance-only record in the locked replay.")
    else:
        st.info("No race-weekend development commitment was recorded.")
    if audit["crisis"]:
        crisis = audit["crisis"]
        st.warning(f"Largest funded repair: Round {crisis['round_number']} · {crisis['title']} · {money(crisis['chosen_amount'])}.")
    else:
        st.success("No sourced repair charge was funded during the replay.")
    if audit["best_readiness"]:
        readiness = audit["best_readiness"]
        st.info(f"Largest operational planning commitment: Round {readiness['round_number']} · {readiness['category']} · {money(readiness['amount'])}. No safety outcome or lap-time value is calculated for historical replay funding.")
    if audit["cancelled_upgrade"]:
        cancelled = audit["cancelled_upgrade"]
        st.warning(f"Cancelled or reduced package: Round {cancelled['round_number']} · {cancelled['note']}.")
    else:
        st.caption("No planned upgrade was cancelled or reduced in this replay.")
    st.markdown("#### 2026 carrying value")
    first, second, third = st.columns(3)
    first.metric("Unspent-cap starter credits", money(audit["unused_cap_credit"]))
    second.metric("Future-car funding carried", money(audit["future_capital"]))
    third.metric("2026 aero allowance", f"{audit['next_year_aero_allowance']}%")
    st.caption(audit["next_year_note"])


def render_simulation(con, state):
    if not state:
        render_setup(con)
        return
    if state["status"] == "complete":
        render_audit(con)
        st.button("Reset simulation", on_click=reset_active_replay)
        return
    team = TEAMS[state["team_id"]]
    st.title(f"{team['name']} · 2025 F1 Budget Replay")
    st.markdown("<div class='finish-line'></div>", unsafe_allow_html=True)
    tabs = st.tabs(["Race control", "Telemetry", "History & weather", "Season ledger", "Safety planning"])
    with tabs[0]:
        render_race_control(con, state)
    with tabs[1]:
        render_telemetry(con, state)
    with tabs[2]:
        render_history_weather(con, state)
    with tabs[3]:
        render_season_ledger(con, state)
    with tabs[4]:
        render_safety_planning(con, state)


def render_budget_overview(con):
    cats, spend = load_budget(con)
    total = float(spend.amount.sum())
    periods = max(1, spend.race_weekend.nunique())
    projected = total / periods * 4
    st.subheader("Budget Tracker")
    first, second, third, fourth = st.columns(4)
    first.metric("Spent to date", money(total), f"{total / CAP:.1%} of cap")
    second.metric("Cap remaining", money(CAP - total))
    third.metric("Projected season spend", money(projected))
    fourth.metric("Run-rate headroom", money(CAP - projected), "At risk" if projected > CAP else "On plan", delta_color="inverse" if projected > CAP else "normal")
    by_cat = cats.merge(spend.groupby("category", as_index=False).amount.sum(), left_on="name", right_on="category", how="left").fillna({"amount": 0})
    by_cat["used"] = by_cat.amount / by_cat.cap_allocation
    by_cat["projected"] = by_cat.amount / periods * 4
    left, right = st.columns([1.2, 1])
    with left:
        show_chart(px.bar(by_cat, x="name", y="amount", color="used", color_continuous_scale="RdYlGn_r", labels={"name": "Category", "amount": "Spend (CAD)", "used": "Used"}, title="Spend by category"))
    with right:
        display = by_cat[["name", "cap_allocation", "amount", "projected", "used"]].rename(columns={"name": "Category", "cap_allocation": "Allocation (CAD)", "amount": "Spent (CAD)", "projected": "Projected (CAD)", "used": "Used"})
        show_table(cad_table(display, money_columns=("Allocation (CAD)", "Spent (CAD)", "Projected (CAD)"), percent_columns=("Used",)))
        risks = by_cat[by_cat.projected > by_cat.cap_allocation]
        if len(risks):
            st.warning("Run-rate alert: " + ", ".join(risks.name) + " are projected to exceed allocation.")
    history = spend.groupby("race_weekend", as_index=False).amount.sum()
    show_chart(px.line(history, x="race_weekend", y="amount", markers=True, title="Historical spend by quarter / race weekend", labels={"amount": "Spend (CAD)", "race_weekend": "Period"}))


def render_budget_ledger(con):
    cats, spend = load_budget(con)
    st.subheader("Spend Ledger")
    with st.expander("Add a budget spend entry", expanded=True):
        with st.form("legacy_add"):
            first, second, third = st.columns(3)
            category = first.selectbox("Category", CATEGORIES, key="ledger_category")
            amount = second.number_input("Amount (CAD)", min_value=0.0, step=10_000.0, key="ledger_amount")
            period = third.text_input("Quarter / race weekend", "Q4")
            note = st.text_input("Note")
            if st.form_submit_button("Add spend") and amount > 0:
                con.execute("INSERT INTO spend_entries(category, amount, entry_date, race_weekend, note) VALUES (?,?,?,?,?)", (category, amount, date.today().isoformat(), period, note))
                con.commit()
                rerun_app()
    st.download_button("Download budget ledger CSV", spend.to_csv(index=False).encode(), "f1_budget_ledger.csv", "text/csv")
    upload = st.file_uploader("Import CSV (category, amount, entry_date, race_weekend, note)", type="csv")
    if upload and st.button("Import CSV"):
        incoming = pd.read_csv(upload)
        if not {"category", "amount"}.issubset(incoming.columns):
            st.error("CSV needs category and amount columns.")
        else:
            for key, value in [("entry_date", date.today().isoformat()), ("race_weekend", "Imported"), ("note", "")]:
                if key not in incoming:
                    incoming[key] = value
            incoming[["category", "amount", "entry_date", "race_weekend", "note"]].to_sql("spend_entries", con, if_exists="append", index=False)
            rerun_app()
    st.markdown("#### Past expenditures")
    periods = ["All periods"] + sorted(spend.race_weekend.dropna().unique().tolist())
    selected = st.selectbox("Filter past expenditure", periods)
    past = spend if selected == "All periods" else spend[spend.race_weekend == selected]
    st.metric("Past expenditure total", money(float(past.amount.sum())))
    past_display = past.rename(columns={"amount": "Amount (CAD)", "entry_date": "Date", "race_weekend": "Quarter / race weekend", "category": "Category"})
    show_table(cad_table(past_display, money_columns=("Amount (CAD)",)))
    st.markdown("#### Category allocations and performance curves")
    changed = []
    for _, row in cats.iterrows():
        first, second = st.columns(2)
        allocation = first.number_input(f"{row['name']} allocation (CAD)", value=float(row["cap_allocation"]), step=100_000.0, key=f"legacy_alloc_{row['name']}")
        rate = second.number_input(f"{row['name']} lap gain rate", value=float(row["rate"]), step=.01, format="%.3f", key=f"legacy_rate_{row['name']}")
        changed.append((row["name"], allocation, rate))
    if st.button("Save allocation model"):
        con.executemany("UPDATE categories SET cap_allocation = ?, rate = ? WHERE name = ?", [(allocation, rate, name) for name, allocation, rate in changed])
        con.commit()
        st.success("Budget model saved.")


def render_scenario_lab(con):
    cats, spend = load_budget(con)
    total = float(spend.amount.sum())
    st.subheader("What-if Scenario Lab")
    first, second = st.columns(2)
    category = first.selectbox("Investment category", CATEGORIES, key="scenario_category")
    mode = second.radio("Budget treatment", ["Add to cap", "Reallocate from other categories"])
    amount = st.slider("Quarter adjustment (CAD $M)", 0.0, 25.0, 5.0, .5) * 1_000_000
    source, source_loss = None, 0.0
    rate = float(cats.loc[cats.name == category, "rate"].iloc[0])
    if mode.startswith("Reallocate"):
        source = st.selectbox("Move budget from", [item for item in CATEGORIES if item != category])
        source_loss = budget_gain(float(cats.loc[cats.name == source, "rate"].iloc[0]), amount)
    gain = budget_gain(rate, amount) - source_loss
    total_after = total + amount if source is None else total
    name = st.text_input("Scenario name", f"{category} push")
    first, second, third = st.columns(3)
    first.metric("Projected lap-time gain", f"-{gain:.3f}s")
    second.metric("Remaining cap", money(CAP - total_after), signed_money((CAP - total_after) - (CAP - total)))
    third.metric("Scenario spend", money(total_after))
    line = pd.DataFrame({"Added spend (CAD $M)": np.linspace(0, 25, 51)})
    line["Lap-time gain (s)"] = [budget_gain(rate, item * 1_000_000) for item in line["Added spend (CAD $M)"]]
    show_chart(px.line(line, x="Added spend (CAD $M)", y="Lap-time gain (s)", title=f"Diminishing returns: {category}"))
    st.caption("This analytical workspace is independent of the exact historical season replay.")
    if st.button("Save scenario"):
        con.execute("INSERT INTO scenarios(name, category, adjustment, mode, lap_delta, remaining_cap, created_at) VALUES (?,?,?,?,?,?,?)", (name, category, amount, mode, gain, CAP - total_after, date.today().isoformat()))
        con.commit()
        st.success("Scenario saved.")
    saved = pd.read_sql_query("SELECT name, category, adjustment, mode, lap_delta, remaining_cap, created_at FROM scenarios ORDER BY id DESC LIMIT 3", con)
    if not saved.empty:
        st.markdown("#### Saved comparisons")
        columns = st.columns(len(saved))
        for column, (_, row) in zip(columns, saved.iterrows()):
            with column:
                st.metric(row["name"], f"-{row['lap_delta']:.3f}s", money(float(row["remaining_cap"])))
        saved_display = saved.rename(columns={"name": "Scenario", "category": "Category", "adjustment": "Adjustment (CAD)", "mode": "Treatment", "lap_delta": "Net gain (s)", "remaining_cap": "Cap remaining (CAD)", "created_at": "Saved"})
        show_table(cad_table(saved_display, money_columns=("Adjustment (CAD)", "Cap remaining (CAD)"), decimal_columns=("Net gain (s)",)))


def render_budget_workspace(con):
    st.title("Budget Workspace")
    st.markdown("<div class='finish-line'></div>", unsafe_allow_html=True)
    page = st.radio("Budget view", ["Budget Tracker", "Spend Ledger", "What-if Scenario Lab"])
    if page == "Budget Tracker":
        render_budget_overview(con)
    elif page == "Spend Ledger":
        render_budget_ledger(con)
    else:
        render_scenario_lab(con)


st.set_page_config(page_title="2025 F1 Budget Operations", page_icon="🏁", layout="wide")
con = db()
state = season.active_state(con)
palette = TEAMS[state["team_id"]] if state else {"primary": "#E10600", "secondary": "#F5F5F5"}
mode = state["theme"] if state else "neutral"
st.markdown(livery_css(palette["primary"], palette["secondary"], mode), unsafe_allow_html=True)
st.sidebar.markdown("## 🏁 Race Operations")
if "workspace" not in st.session_state:
    st.session_state["workspace"] = "Home"
workspace = st.sidebar.radio("Workspace", ["Home", "2025 Season Budget Replay", "Budget Workspace"], key="workspace")
if state:
    appearance = st.sidebar.selectbox("Appearance", ["Team Livery", "Race Operations"], index=0 if state["theme"] == "team" else 1)
    desired = "team" if appearance == "Team Livery" else "neutral"
    if desired != state["theme"]:
        con.execute("UPDATE career_state SET theme = ? WHERE id = 1", (desired,))
        con.commit()
        rerun_app()
    st.sidebar.metric("Selected constructor", TEAMS[state["team_id"]]["name"])
    st.sidebar.metric("Simulation cap", money(CAP))
    st.sidebar.button("Reset active simulation", on_click=reset_active_replay)
else:
    st.sidebar.metric("Simulation cap", money(CAP))
    st.sidebar.caption("Choose a constructor when you are ready to start the exact 2025 replay.")

if workspace == "Home":
    render_home(con, state)
elif workspace == "2025 Season Budget Replay":
    render_simulation(con, state)
else:
    render_budget_workspace(con)
