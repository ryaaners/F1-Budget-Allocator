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
from career_data import CALENDAR, CAP, CATEGORIES, TEAMS, avatar_path

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
        con.executemany("INSERT INTO categories VALUES (?, ?, ?)", [(c, DEFAULT_ALLOC[c] * 1e6, DEFAULT_RATES[c]) for c in CATEGORIES])
    if con.execute("SELECT COUNT(*) FROM spend_entries").fetchone()[0] == 0:
        rows = []
        for quarter, share in [("Q1", 1 / 3), ("Q2", 1 / 3), ("Q3", 1 / 3)]:
            for category in CATEGORIES:
                rows.append((category, DEFAULT_ALLOC[category] * 1e6 * DEFAULT_FACTORS[category] * share, date.today().isoformat(), quarter, "Synthetic starter data"))
        con.executemany("INSERT INTO spend_entries(category, amount, entry_date, race_weekend, note) VALUES (?,?,?,?,?)", rows)
    season.migrate(con)
    con.commit()
    return con


def load_budget(con):
    return (
        pd.read_sql_query("SELECT * FROM categories", con),
        pd.read_sql_query("SELECT * FROM spend_entries ORDER BY entry_date DESC, id DESC", con),
    )


def money(value):
    return f"CAD ${value / 1_000_000:,.1f}M"


def signed_money(value):
    return f"{'-' if value < 0 else '+'}CAD ${abs(value) / 1_000_000:,.1f}M"


def rerun_app():
    """Refresh on both the current Streamlit release and 1.12 on Python 3.9.7."""
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def show_chart(figure):
    """Use the common Plotly API supported by Streamlit 1.12 and newer."""
    st.plotly_chart(figure)


def show_table(frame):
    """Avoid newer dataframe sizing/index arguments unavailable in Streamlit 1.12."""
    st.dataframe(frame)


def cad_table(frame, money_columns=(), percent_columns=(), decimal_columns=()):
    """Return a plain, version-safe display frame with Canadian-dollar labels."""
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


def budget_gain(rate, spend):
    return rate * (1 - np.exp(-max(0.0, spend) / 6_000_000.0))


def livery_css(primary, secondary, mode):
    accent = primary if mode == "team" else "#E10600"
    accent_two = secondary if mode == "team" else "#F5F5F5"
    return f"""<style>
    :root {{ --team-primary:{accent}; --team-secondary:{accent_two}; }}
    [data-testid="stAppViewContainer"] {{background-color:#080A0E;background-image:linear-gradient(45deg,rgba(255,255,255,.018) 25%,transparent 25%),linear-gradient(-45deg,rgba(255,255,255,.018) 25%,transparent 25%),linear-gradient(45deg,transparent 75%,rgba(255,255,255,.018) 75%),linear-gradient(-45deg,transparent 75%,rgba(255,255,255,.018) 75%);background-size:10px 10px;background-position:0 0,0 5px,5px -5px,-5px 0;}}
    .block-container {{padding-top:2rem;padding-bottom:3rem;max-width:1440px;}}
    h1,h2,h3 {{font-family:"Arial Narrow","Aptos Display",sans-serif;letter-spacing:.035em;text-transform:uppercase;}}
    [data-testid="stMetric"] {{background:rgba(18,22,29,.94);border-left:3px solid var(--team-primary);padding:.7rem .8rem;}}
    [data-testid="stSidebar"] {{background:#0E1117;}}
    .finish-line {{height:9px;margin:.4rem 0 1.4rem;background-color:var(--team-primary);background-image:conic-gradient(from 90deg at 1px 1px,#fff 90deg,transparent 0);background-size:18px 18px;}}
    .team-panel {{background:linear-gradient(120deg,rgba(255,255,255,.06),rgba(0,0,0,.18));border-left:4px solid var(--team-primary);padding:1rem 1.2rem;margin:.5rem 0 1rem;}}
    .team-panel h2 {{white-space:nowrap;font-size:clamp(1.25rem,2vw,2rem);}}
    .telemetry-label {{color:#aeb8c4;text-transform:uppercase;letter-spacing:.09em;font-size:.74rem;}}
    .portrait-card {{text-align:center;background:rgba(12,16,22,.85);padding:.75rem;border-bottom:2px solid var(--team-secondary);}}
    .stButton > button[kind="primary"] {{background:var(--team-primary);border-color:var(--team-primary);}}
    [data-baseweb="tab"] {{font-weight:700;letter-spacing:.05em;}}
    </style>"""


def show_portrait(driver, team, width=78):
    path = avatar_path(driver["id"])
    if path.exists():
        st.image(str(path), width=width)
    else:
        initials = "".join(part[0] for part in driver["name"].split()[:2])
        st.markdown(f"<div style='background:{team['primary']};height:{width}px;width:{width}px;border-radius:50%;display:grid;place-items:center;font-weight:800'>{initials}</div>", unsafe_allow_html=True)


def display_team_dossier(team):
    left, middle, right = st.columns([1.1, 1.4, 1.4])
    with left:
        st.markdown(f"<div class='team-panel'><div class='telemetry-label'>2025 constructor</div><h2 style='margin:.2rem 0'>{team['name']}</h2><div>Historical position: P{team['historical_rank']} · {team['historical_points']} points</div></div>", unsafe_allow_html=True)
        st.metric("Opening pace delta", f"+{team['base_delta']:.2f}s")
        st.metric("Modelled fixed cost", money(team["fixed_cost"]))
    with middle:
        driver_columns = st.columns(2)
        for column, driver in zip(driver_columns, team["drivers"]):
            with column:
                st.markdown("<div class='portrait-card'>", unsafe_allow_html=True)
                show_portrait(driver, team)
                st.markdown(f"**{driver['name']}**")
                st.caption(f"Driver rating {driver['skill']}")
                st.markdown("</div>", unsafe_allow_html=True)
    with right:
        costs = pd.DataFrame({"Category": list(team["model_cost_2024"]), "Modelled 2024 CAD": list(team["model_cost_2024"].values())})
        fig = px.bar(costs, x="Modelled 2024 CAD", y="Category", orientation="h", color_discrete_sequence=[team["primary"]], title="Modelled 2024 cost profile")
        fig.update_layout(height=290, margin=dict(l=0, r=0, t=45, b=0))
        show_chart(fig)
        st.caption("Modelled planning profile. FIA team cost-cap filings are confidential.")


def show_safety_message(reserve):
    crashes = reserve["crashes"]
    if reserve["status"] == "safe":
        st.success(f"Crash money: safe. You could pay for {crashes} big crashes without breaking the budget cap.")
    elif reserve["status"] == "tight":
        st.warning("Crash money: tight. You can only pay for 1 more big crash. Think twice before buying more upgrades.")
    else:
        st.error(f"Crash money: at risk. If a big crash happened now, you could not pay for a new survival cell (about {money(reserve['crash_cost'])}) without breaking the budget cap.")


def show_safety_reserve(reserve):
    one, two, three = st.columns(3)
    one.metric("Money free for crashes", money(reserve["free"]))
    two.metric("Big crashes you can afford", reserve["crashes"])
    three.metric("Cost of one big crash", money(reserve["crash_cost"]))
    show_safety_message(reserve)
    if reserve["owed"]:
        st.caption(f"Already takes off {money(reserve['owed'])} owed for repairs that have not been paid yet.")


def show_survival_cell_check(incident):
    """Plain-language result of the survival-cell check for a structural crash."""
    severity = incident["severity"]
    heading = f"Survival cell check · {season.SEVERITY_LABELS[severity]} · {incident['impact_g']:.0f}g impact"
    extra = money(season.SURVIVAL_CELL_EXTRA_COST[severity])
    if severity == "small":
        st.info(f"**{heading}**\n\nPassed. The carbon-fibre shell that protects the driver is not damaged, so this repair can wait if you need the money.")
    elif severity == "medium":
        st.warning(f"**{heading}**\n\nCracked. The shell that protects the driver is damaged and would not survive another crash. It must be repaired ({extra} included) before the car races again.")
    else:
        st.error(f"**{heading}**\n\nDestroyed. The shell that protects the driver cannot be fixed. A new one must be built ({extra} included) before the car races again.")


def render_setup(con):
    st.title("2025 F1 Season Budget Simulation")
    st.markdown("<div class='finish-line'></div>", unsafe_allow_html=True)
    st.subheader("Pre-season command desk")
    selected_id = st.selectbox("Select your constructor", list(TEAMS), format_func=lambda key: TEAMS[key]["name"])
    team = TEAMS[selected_id]
    display_team_dossier(team)
    st.markdown("#### Allocate pre-season capital")
    st.caption("Every allocation counts toward the CAD $215M simulation cap. Keep reserve for race-weekend R&D, damage and the future car.")
    defaults = {"Aero":12., "Powertrain":5., "Chassis / structures":6., "Personnel":4., "Operations":2., "Testing":3., "Other":1.}
    allocation = {}
    cols = st.columns(2)
    for index, category in enumerate(CATEGORIES):
        with cols[index % 2]:
            allocation[category] = st.number_input(f"{category} pre-season allocation (CAD $M)", 0.0, 80.0, defaults[category], .5, key=f"setup_{category}") * 1_000_000
    total = team["fixed_cost"] + sum(allocation.values())
    remaining = CAP - total
    a, b, c = st.columns(3)
    a.metric("Pre-season committed", money(total))
    b.metric("Reserve for the season", money(remaining), "Within cap" if remaining >= 0 else "Over cap", delta_color="normal" if remaining >= 0 else "inverse")
    switch_round = c.slider("Future-car switch round", 1, 24, 16, help="New current-R&D spending shifts to the following car at this round.")
    if remaining >= 0:
        show_safety_message(season.reserve_status(remaining))
    if st.button("Begin 2025 budget simulation", disabled=remaining < 0):
        try:
            season.create_career(con, selected_id, allocation, switch_round=switch_round, theme="team")
            rerun_app()
        except ValueError as error:
            st.error(str(error))


def render_incident_decisions(con):
    incidents = season.pending_incidents(con)
    if not incidents:
        return
    st.markdown("#### Repair decisions required")
    st.warning("An unexpected event needs a budget decision before the next Grand Prix.")
    for incident in incidents:
        severity = incident.get("severity")
        hit = f" · {season.SEVERITY_LABELS[severity]}" if severity else ""
        with st.expander(f"{incident['title']}{hit} — {money(incident['amount'])}", expanded=incident["state"] == "pending"):
            st.write(incident["reason"])
            st.caption(f"Responsible party: {incident['responsible']} · Source: {incident['source']}")
            if severity:
                show_survival_cell_check(incident)
            if incident["state"] == "deferred":
                st.info(f"Older specification active: +{incident['penalty']:.3f}s until repaired.")
            options = [
                "Fund from cap headroom",
                "Cancel / reduce latest current-car upgrade",
                "Use future-car reserve",
                "Run older specification",
                "Approve repair despite cap (game breach)",
            ]
            if season.must_repair(incident):
                options.remove("Run older specification")
                st.caption("“Run older specification” is switched off: a car with a damaged survival cell cannot race.")
            choice = st.radio(
                "Decision",
                options,
                key=f"incident_{incident['id']}",
            )
            if st.button("Confirm repair decision", key=f"repair_{incident['id']}"):
                action = {
                    "Fund from cap headroom": "fund",
                    "Cancel / reduce latest current-car upgrade": "cancel_upgrade",
                    "Use future-car reserve": "future_reserve",
                    "Run older specification": "defer",
                    "Approve repair despite cap (game breach)": "breach",
                }[choice]
                try:
                    season.resolve_incident(con, incident["id"], action)
                    rerun_app()
                except ValueError as error:
                    st.error(str(error))


def dataframe_results(results):
    frame = pd.DataFrame(results)
    if frame.empty:
        st.info("No classification is available yet.")
        return
    cols = [col for col in ["position", "driver", "team", "gap", "points", "fastest_lap"] if col in frame.columns]
    display = frame[cols].rename(columns={"position":"Pos.", "driver":"Driver", "team":"Team", "gap":"Gap (s)", "points":"Points", "fastest_lap":"Fastest lap"})
    if "Fastest lap" in display:
        display["Fastest lap"] = display["Fastest lap"].map(lambda value: "Yes" if value else "")
    show_table(display)


def render_weekend_classification(records, team, team_id, heading):
    if not records:
        return
    st.markdown(f"#### {heading}")
    for record in records:
        with st.expander(record["session_name"], expanded=record == records[0]):
            dataframe_results(record["results"])
            if record.get("stages"):
                st.markdown("**Knockout stage timing**")
                for stage in record["stages"]:
                    st.markdown(f"**{stage['name']}**")
                    dataframe_results(stage["results"])
            fastest = next((row for row in record["results"] if row.get("fastest_lap")), None)
            if fastest:
                st.caption(f"Fastest lap: {fastest['driver']} — displayed without a bonus point under the 2025 rules.")
            own = [row for row in record["results"] if row["team_id"] == team_id]
            columns = st.columns(2)
            for column, result in zip(columns, own):
                driver = next(item for item in team["drivers"] if item["id"] == result["driver_id"])
                with column:
                    show_portrait(driver, team, 52)
                    st.write(f"P{result['position']} · {result['points']} points")


def render_race_control(con, state):
    context = season.historical_context(con)
    track, team = context["round"], TEAMS[state["team_id"]]
    st.markdown(f"<div class='team-panel'><div class='telemetry-label'>Round {track['round']} of 24 · {'Sprint weekend' if track['sprint'] else 'Grand Prix weekend'}</div><h2 style='margin:.15rem 0'>{track['name']} — {track['venue']}</h2><div>{track['date']} · {track['weather']['condition']}</div></div>", unsafe_allow_html=True)
    perf, finance = season.current_performance(con, track["round"]), season.finance_summary(con)
    a, b, c, d = st.columns(4)
    a.metric("Cap remaining", money(finance["remaining"]))
    b.metric("Track R&D gain", f"-{perf['track_gain']:.3f}s")
    c.metric("Personnel / operations", f"-{perf['personnel'] + perf['operations']:.3f}s")
    d.metric("Active component penalty", f"+{perf['damage_penalty']:.3f}s")
    render_incident_decisions(con)
    st.markdown("#### Crash safety money")
    st.caption("Money kept free inside the budget cap so the team can always pay for a new survival cell after a big crash.")
    show_safety_reserve(season.safety_reserve(con))
    st.markdown("#### Pre-race development call")
    with st.form("race_investment"):
        first, second, third = st.columns(3)
        category = first.selectbox("Investment category", CATEGORIES)
        amount = second.number_input("Package size (CAD $M)", 0.0, 20.0, 2.0, .5)
        note = third.text_input("Package note", f"{track['name']} package")
        target = "future car" if track["round"] >= state["switch_round"] and category in season.CURRENT_CAR_CATEGORIES else "current car"
        st.caption(f"This package is directed to the **{target}** under the current switch point.")
        # Keyed by ledger size so the override box starts unticked again after every committed package.
        override = st.checkbox("Buy it even if it leaves no money for a big crash", key=f"override_safety_{len(season.ledger(con))}")
        if st.form_submit_button("Commit package") and amount > 0:
            try:
                future = season.commit_investment(con, category, amount * 1_000_000, note, override_safety=override)
                st.success(f"Package committed to the {'future car' if future else 'current car'}.")
                rerun_app()
            except season.SafetyReserveError as error:
                st.warning(f"Safety warning: {error} To buy it anyway, tick the box above and press Commit package again.")
            except ValueError as error:
                st.error(str(error))
    next_name = season.next_session(con)
    blocking_repair = any(incident["state"] == "pending" for incident in season.pending_incidents(con))
    if blocking_repair:
        st.caption("Choose a funding path for the pending repair before the next session. A damaged survival cell must be paid for before the car races; other repairs can be delayed with their pace penalty.")
    if next_name and st.button(f"Simulate {next_name}", disabled=blocking_repair):
        season.simulate_next_session(con)
        rerun_app()
    latest = season.session_results(con, track["round"])
    if latest:
        render_weekend_classification(latest, team, state["team_id"], "Current weekend classification")
    elif state["current_round"] > 1 and state["session_index"] == 0:
        previous_round = state["current_round"] - 1
        previous = season.session_results(con, previous_round)
        if previous:
            prior_track = CALENDAR[previous_round - 1]
            render_weekend_classification(previous, team, state["team_id"], f"Post-race report · Round {previous_round} {prior_track['name']}")


def render_telemetry(con, state):
    finance = season.finance_summary(con)
    outlook = season.development_outlook(con)
    left, right = st.columns([1, 1.3])
    with left:
        st.subheader("Constructors’ standings")
        standings = pd.DataFrame(season.standings(con)).drop(columns=["team_id"])
        show_table(standings)
    with right:
        ledger = pd.DataFrame(season.ledger(con))
        if not ledger.empty:
            actual = ledger.groupby("round_number", as_index=False)["amount"].sum().sort_values("round_number")
            actual["Cumulative spend"] = actual["amount"].cumsum()
            actual = actual.rename(columns={"round_number":"Round"})
            base = TEAMS[state["team_id"]]["fixed_cost"]
            trajectory = pd.DataFrame({"Round":list(range(25))})
            trajectory["Permitted cap trajectory"] = base + (CAP - base) * trajectory["Round"] / 24
            fig = go.Figure()
            fig.add_scatter(x=trajectory["Round"], y=trajectory["Permitted cap trajectory"], name="Permitted trajectory", mode="lines", line=dict(dash="dot", color="#AAB2BD"))
            fig.add_scatter(x=actual["Round"], y=actual["Cumulative spend"], name="Actual spend", mode="lines+markers", line=dict(color=TEAMS[state["team_id"]]["primary"], width=4))
            fig.update_layout(title="Cap utilisation burn-down", xaxis_title="Round", yaxis_title="CAD", margin=dict(l=0,r=0,t=45,b=0))
            show_chart(fig)
    st.markdown("#### Financial health")
    projected = finance["spend"] + max(0, 24 - state["current_round"]) * 1_000_000
    health = max(0, min(100, (CAP - projected) / CAP * 100 + 50))
    gauge = go.Figure(go.Indicator(mode="gauge+number", value=health, number={"suffix":"%"}, title={"text":"Abu Dhabi cap health"}, gauge={"axis":{"range":[0,100]}, "bar":{"color":TEAMS[state["team_id"]]["primary"]}, "steps":[{"range":[0,35],"color":"#501515"},{"range":[35,65],"color":"#514718"},{"range":[65,100],"color":"#173D2A"}]}))
    one, two = st.columns([1,2])
    with one: show_chart(gauge)
    with two:
        st.metric("Forecast cap balance", money(CAP - projected))
        st.metric("Crash tax", money(finance["crash_tax"]))
        st.metric("Big crashes you can afford", season.safety_reserve(con)["crashes"])
        st.metric("Future-car committed", money(finance["future_car"]))
        if finance["future_reserve_draw"]:
            st.metric("Future reserve used for repairs", money(finance["future_reserve_draw"]))
        st.caption("Forecast is a management indicator, not an FIA determination.")
    st.markdown("#### Current versus next-year development")
    current, next_car, switch = st.columns(3)
    with current:
        current.metric("Projected current-season finish", f"P{outlook['projected_position']}")
        current.metric("Current-car pace credit", f"-{outlook['current_credit']:.3f}s")
    with next_car:
        next_car.metric("2026 opening pace credit", f"-{outlook['future_credit']:.3f}s")
        next_car.metric("Future-car reserve draw", money(outlook["reserve_draw"]))
    with switch:
        switch.metric("Development switch point", f"Round {outlook['switch_round']}")
        switch.caption("Aero, Powertrain, Chassis / structures, and Testing packages move to the following car from this round.")


def render_history_weather(con, state):
    context = season.historical_context(con)
    track, strategy, events = context["round"], context["strategy"], context["events"]
    historical_result = context["historical_result"]
    st.subheader("Historical weekend reference")
    left, right = st.columns(2)
    with left:
        st.markdown("#### Local historical weather")
        weather = track["weather"]
        a, b, c = st.columns(3)
        a.metric("Temperature", f"{weather['temperature_c']}°C")
        b.metric("Rainfall", f"{weather['rain_mm']:.1f} mm")
        c.metric("Wind", f"{weather['wind_kph']} km/h")
        st.info(weather["condition"])
    with right:
        st.markdown("#### Actual 2025 selected-team result")
        st.metric("Archived team points", historical_result["points"])
        if historical_result["results"]:
            actual = pd.DataFrame(historical_result["results"]).drop(columns=["driver_id"])
            show_table(actual.rename(columns={"session":"Session", "driver":"Driver", "position":"Pos.", "points":"Points", "status":"Session time / official status"}))
        st.caption(f"Source: {historical_result['source']}")
        st.markdown("#### Local strategy reference")
        st.write(f"**Tyre sequence:** {strategy['compounds']}")
        st.write("**Pit-stop laps:** " + ", ".join(str(lap) for lap in strategy["pit_laps"]))
        st.caption(strategy["note"])
    st.markdown("#### Selected-team incident context")
    if events:
        for event in events:
            with st.expander(event["title"], expanded=True):
                st.write(event["reason"])
                st.write(f"**Responsible party:** {event['responsible']}")
                st.write(f"**Source:** {event['source']}")
                if event["amount"]:
                    st.caption("Repair values are local gameplay estimates; they are not published team invoices.")
                else:
                    st.caption("This archived result status has no automatically created repair cost.")
    else:
        st.success("No selected-team local incident prompt is scheduled for this weekend.")


def render_season_ledger(con, state):
    st.subheader("Simulation financial ledger")
    items = pd.DataFrame(season.ledger(con))
    if not items.empty:
        display = items.rename(columns={"round_number":"Round", "session_name":"Session", "category":"Category", "amount":"Amount (CAD)", "kind":"Entry type", "note":"Note", "future_car":"Future car", "created_at":"Recorded"})
        show_table(cad_table(display, money_columns=("Amount (CAD)",)))
        st.download_button("Download season ledger CSV", items.to_csv(index=False).encode(), "2025_season_budget_ledger.csv", "text/csv")
    with st.expander("Add manual crash or repair event"):
        with st.form("manual_career_incident"):
            first, second, third = st.columns(3)
            title = first.text_input("Event", "Manual component damage")
            amount = second.number_input("Estimated repair (CAD)", min_value=0.0, value=1_000_000.0, step=100_000.0)
            category = third.selectbox("Category", CATEGORIES, index=2)
            hit_options = {"Roll from track risk": None, "Small hit": "small", "Medium hit": "medium", "Big hit": "big"}
            hit = st.selectbox("Survival cell hit", list(hit_options), help="Only used for Chassis / structures events. Pick a size to demo a specific survival cell result.")
            if st.form_submit_button("Add pending repair") and amount > 0:
                season.add_manual_incident(con, title, amount, category, severity=hit_options[hit])
                rerun_app()


def render_audit(con):
    audit = season.audit(con)
    team = audit["team"]
    st.title("The FIA & Board Audit")
    st.markdown("<div class='finish-line'></div>", unsafe_allow_html=True)
    st.markdown(f"<div class='team-panel'><div class='telemetry-label'>2025 executive post-season debrief</div><h2 style='margin:.15rem 0'>{audit['verdict']}</h2><div>{team['name']} · simulation versus real 2025 reference</div></div>", unsafe_allow_html=True)
    a, b, c, d = st.columns(4)
    a.metric("Final season spend", money(audit["summary"]["spend"]))
    b.metric("Cap status", money(audit["summary"]["remaining"]))
    finish_label = f"P{audit['sanctioned_player']['Position']}" if audit["sanction"]["point_deduction"] else f"P{audit['player']['Position']}"
    c.metric("Simulated finish", finish_label, f"Real: P{team['historical_rank']}")
    d.metric("Points delta", f"{audit['points_delta']:+d}", f"Real: {team['historical_points']}")
    st.markdown("#### Financial audit")
    left, right = st.columns([1.15,1])
    with left:
        breakdown = pd.DataFrame({"Category":list(audit["summary"]["breakdown"]), "Spend (CAD)":list(audit["summary"]["breakdown"].values())})
        show_chart(px.bar(breakdown, x="Category", y="Spend (CAD)", color_discrete_sequence=[team["primary"]], title="Line-item cap allocation"))
        line_items = pd.DataFrame(season.ledger(con))
        if not line_items.empty:
            lines = line_items.groupby(["kind", "future_car"], as_index=False)["amount"].sum().rename(columns={"kind":"Line item", "future_car":"Future car", "amount":"Spend (CAD)"})
            lines["Future car"] = lines["Future car"].map(lambda value: "Yes" if value else "No")
            st.caption("Upgrade, repair, operations, and future-car line items")
            show_table(cad_table(lines, money_columns=("Spend (CAD)",)))
    with right:
        st.metric("Crash tax", money(audit["summary"]["crash_tax"]))
        st.metric("Planned current-car R&D", money(audit["summary"]["planned_rnd"]))
        st.metric("Cost per point", f"CAD ${audit['cost_per_point']:,.0f}")
        modelled_grid_midpoint = float(np.median([sum(details["model_cost_2024"].values()) / max(1, details["historical_points"]) for details in TEAMS.values()]))
        st.metric("Modelled grid cost / point", f"CAD ${modelled_grid_midpoint:,.0f}")
        st.metric("Audit status", audit["sanction"]["label"])
        if audit["breach"] > 0:
            st.error(f"{money(audit['breach'])} over simulation cap. Game sanction: {money(audit['sanction']['fine'])} fine, {audit['sanction']['wind_tunnel_cut']}% wind-tunnel/CFD reduction, {audit['sanction']['point_deduction']} point deduction.")
            if audit["sanction"]["point_deduction"]:
                st.caption(f"Sanction-adjusted constructor points: {audit['sanctioned_player']['Points']}.")
        else: st.success("Clean gameplay-cap audit. This is not an FIA determination.")
    st.markdown("#### Simulation versus real 2025")
    comparison = pd.DataFrame([
        {"Measure":"Constructor position", "Real 2025":f"P{team['historical_rank']}", "Simulation":f"P{audit['player']['Position']}"},
        {"Measure":"Constructor points", "Real 2025":team["historical_points"], "Simulation":audit["player"]["Points"]},
        {"Measure":"Development switch", "Real team proxy":f"Round {audit['real_switch_proxy']} (last material-upgrade proxy)", "Simulation":f"Round {audit['summary']['state']['switch_round']}"},
    ])
    show_table(comparison)
    st.caption("The real-team development switch is an inferred local proxy because teams do not publish a complete development-stop date.")
    st.markdown("#### Key decision moments")
    cards = st.columns(4)
    with cards[0]:
        if audit["largest_upgrade"]: st.info(f"**Turning point**\n\nRound {audit['largest_upgrade']['round_number']}: {audit['largest_upgrade']['note']} — {money(audit['largest_upgrade']['amount'])}.")
        else: st.info("**Turning point**\n\nNo in-season R&D package was committed.")
    with cards[1]:
        if audit["crisis"]: st.warning(f"**Crisis event**\n\nRound {audit['crisis']['round_number']}: {audit['crisis']['title']} — {money(audit['crisis']['amount'])}.")
        else: st.success("**Crisis event**\n\nNo repair event reached the ledger.")
    with cards[2]: st.success(f"**Efficiency highlight**\n\n{audit['best_category']} delivered the best diminishing-return value per CAD spent.")
    with cards[3]:
        if audit["cancelled_upgrade"]:
            st.warning(f"**Redirected development**\n\nRound {audit['cancelled_upgrade']['round_number']}: {money(abs(audit['cancelled_upgrade']['amount']))} moved from a planned package to a repair.")
        else:
            st.info("**Redirected development**\n\nNo planned current-car package was cancelled for a repair.")
    st.markdown("#### 2026 carrying value")
    one, two, three = st.columns(3)
    one.metric("Unspent-cap starter credits", money(max(0, audit['summary']['remaining'])))
    two.metric("Future-car commitments", money(audit['summary']['future_car']))
    three.metric("2026 baseline pace", f"-{audit['next_baseline']:.3f}s")
    if audit["sanction"]["wind_tunnel_cut"]:
        st.warning(f"2026 aerodynamic-development allowance: {100 - audit['sanction']['wind_tunnel_cut']}%. The game model removes {audit['next_year_aero_loss']:.3f}s from the next-year pace credit.")
    st.caption("Game rule: unused 2025 cap converts to equal-value 2026 starter R&D credit. Future-car commitments and ending development inform the displayed baseline.")


def render_simulation(con, state):
    if not state:
        render_setup(con)
        return
    if state["status"] == "complete":
        render_audit(con)
        if st.button("Reset simulation"):
            season.reset_career(con); rerun_app()
        return
    team = TEAMS[state["team_id"]]
    st.title(f"{team['name']} · 2025 F1 Season Budget Simulation")
    st.markdown("<div class='finish-line'></div>", unsafe_allow_html=True)
    tabs = st.tabs(["Race control", "Telemetry", "History & weather", "Season ledger"])
    with tabs[0]: render_race_control(con, state)
    with tabs[1]: render_telemetry(con, state)
    with tabs[2]: render_history_weather(con, state)
    with tabs[3]: render_season_ledger(con, state)


def render_budget_overview(con):
    cats, spend = load_budget(con)
    total = float(spend.amount.sum())
    periods = max(1, spend.race_weekend.nunique())
    projected = total / periods * 4
    st.subheader("Budget Tracker")
    a, b, c, d = st.columns(4)
    a.metric("Spent to date", money(total), f"{total / CAP:.1%} of cap")
    b.metric("Cap remaining", money(CAP - total))
    c.metric("Projected season spend", money(projected))
    d.metric("Run-rate headroom", money(CAP - projected), "At risk" if projected > CAP else "On plan", delta_color="inverse" if projected > CAP else "normal")
    by_cat = cats.merge(spend.groupby("category", as_index=False).amount.sum(), left_on="name", right_on="category", how="left").fillna({"amount":0})
    by_cat["used"] = by_cat.amount / by_cat.cap_allocation
    by_cat["projected"] = by_cat.amount / periods * 4
    left, right = st.columns([1.2,1])
    with left:
        show_chart(px.bar(by_cat, x="name", y="amount", color="used", color_continuous_scale="RdYlGn_r", labels={"name":"Category", "amount":"Spend (CAD)", "used":"Used"}, title="Spend by category"))
    with right:
        display = by_cat[["name","cap_allocation","amount","projected","used"]].rename(columns={"name":"Category", "cap_allocation":"Allocation (CAD)", "amount":"Spent (CAD)", "projected":"Projected (CAD)", "used":"Used"})
        show_table(cad_table(display, money_columns=("Allocation (CAD)", "Spent (CAD)", "Projected (CAD)"), percent_columns=("Used",)))
        risks = by_cat[by_cat.projected > by_cat.cap_allocation]
        if len(risks): st.warning("Run-rate alert: " + ", ".join(risks.name) + " are projected to exceed allocation.")
    history = spend.groupby("race_weekend", as_index=False).amount.sum()
    show_chart(px.line(history, x="race_weekend", y="amount", markers=True, title="Historical spend by quarter / race weekend", labels={"amount":"Spend (CAD)","race_weekend":"Period"}))


def render_budget_ledger(con):
    cats, spend = load_budget(con)
    st.subheader("Spend Ledger")
    with st.expander("Add a budget spend entry", expanded=True):
        with st.form("legacy_add"):
            one, two, three = st.columns(3)
            category = one.selectbox("Category", CATEGORIES, key="ledger_category")
            amount = two.number_input("Amount (CAD)", min_value=0.0, step=10_000.0, key="ledger_amount")
            period = three.text_input("Quarter / race weekend", "Q4")
            note = st.text_input("Note")
            if st.form_submit_button("Add spend") and amount > 0:
                con.execute("INSERT INTO spend_entries(category, amount, entry_date, race_weekend, note) VALUES (?,?,?,?,?)", (category, amount, date.today().isoformat(), period, note)); con.commit(); rerun_app()
    st.download_button("Download budget ledger CSV", spend.to_csv(index=False).encode(), "f1_budget_ledger.csv", "text/csv")
    upload = st.file_uploader("Import CSV (category, amount, entry_date, race_weekend, note)", type="csv")
    if upload and st.button("Import CSV"):
        incoming = pd.read_csv(upload)
        if not {"category","amount"}.issubset(incoming.columns): st.error("CSV needs category and amount columns.")
        else:
            for key, value in [("entry_date",date.today().isoformat()),("race_weekend","Imported"),("note","")]:
                if key not in incoming: incoming[key] = value
            incoming[["category","amount","entry_date","race_weekend","note"]].to_sql("spend_entries", con, if_exists="append", index=False); rerun_app()
    st.markdown("#### Past expenditures")
    periods = ["All periods"] + sorted(spend.race_weekend.dropna().unique().tolist())
    selected = st.selectbox("Filter past expenditure", periods)
    past = spend if selected == "All periods" else spend[spend.race_weekend == selected]
    st.metric("Past expenditure total", money(float(past.amount.sum())))
    past_display = past.rename(columns={"amount":"Amount (CAD)","entry_date":"Date","race_weekend":"Quarter / race weekend","category":"Category"})
    show_table(cad_table(past_display, money_columns=("Amount (CAD)",)))
    st.markdown("#### Category allocations and performance curves")
    changed = []
    for _, row in cats.iterrows():
        one, two = st.columns(2)
        allocation = one.number_input(f"{row['name']} allocation (CAD)", value=float(row["cap_allocation"]), step=100_000.0, key=f"legacy_alloc_{row['name']}")
        rate = two.number_input(f"{row['name']} lap gain rate", value=float(row["rate"]), step=.01, format="%.3f", key=f"legacy_rate_{row['name']}")
        changed.append((row["name"], allocation, rate))
    if st.button("Save allocation model"):
        con.executemany("UPDATE categories SET cap_allocation = ?, rate = ? WHERE name = ?", [(alloc, rate, name) for name, alloc, rate in changed]); con.commit(); st.success("Budget model saved.")


def render_scenario_lab(con):
    cats, spend = load_budget(con)
    total = float(spend.amount.sum())
    st.subheader("What-if Scenario Lab")
    one, two = st.columns(2)
    category = one.selectbox("Investment category", CATEGORIES, key="scenario_category")
    mode = two.radio("Budget treatment", ["Add to cap","Reallocate from other categories"])
    amount = st.slider("Quarter adjustment (CAD $M)", 0.0, 25.0, 5.0, .5) * 1_000_000
    source, source_loss = None, 0.0
    rate = float(cats.loc[cats.name == category, "rate"].iloc[0])
    if mode.startswith("Reallocate"):
        source = st.selectbox("Move budget from", [item for item in CATEGORIES if item != category])
        source_loss = budget_gain(float(cats.loc[cats.name == source, "rate"].iloc[0]), amount)
    gain = budget_gain(rate, amount) - source_loss
    total_after = total + amount if source is None else total
    name = st.text_input("Scenario name", f"{category} push")
    a, b, c = st.columns(3)
    a.metric("Projected lap-time gain", f"-{gain:.3f}s")
    b.metric("Remaining cap", money(CAP-total_after), signed_money((CAP-total_after)-(CAP-total)))
    c.metric("Scenario spend", money(total_after))
    line = pd.DataFrame({"Added spend (CAD $M)":np.linspace(0,25,51)})
    line["Lap-time gain (s)"] = [budget_gain(rate, item*1_000_000) for item in line["Added spend (CAD $M)"]]
    show_chart(px.line(line, x="Added spend (CAD $M)", y="Lap-time gain (s)", title=f"Diminishing returns: {category}"))
    if st.button("Save scenario"):
        con.execute("INSERT INTO scenarios(name, category, adjustment, mode, lap_delta, remaining_cap, created_at) VALUES (?,?,?,?,?,?,?)", (name,category,amount,mode,gain,CAP-total_after,date.today().isoformat())); con.commit(); st.success("Scenario saved.")
    saved = pd.read_sql_query("SELECT name, category, adjustment, mode, lap_delta, remaining_cap, created_at FROM scenarios ORDER BY id DESC LIMIT 3", con)
    if not saved.empty:
        st.markdown("#### Saved comparisons")
        columns = st.columns(len(saved))
        for column, (_, row) in zip(columns, saved.iterrows()):
            with column: st.metric(row["name"], f"-{row['lap_delta']:.3f}s", money(float(row["remaining_cap"])))
        saved_display = saved.rename(columns={"name":"Scenario","category":"Category","adjustment":"Adjustment (CAD)","mode":"Treatment","lap_delta":"Net gain (s)","remaining_cap":"Cap remaining (CAD)","created_at":"Saved"})
        show_table(cad_table(saved_display, money_columns=("Adjustment (CAD)", "Cap remaining (CAD)"), decimal_columns=("Net gain (s)",)))


def render_budget_workspace(con):
    st.title("Budget Workspace")
    st.markdown("<div class='finish-line'></div>", unsafe_allow_html=True)
    page = st.radio("Budget view", ["Budget Tracker","Spend Ledger","What-if Scenario Lab"])
    if page == "Budget Tracker": render_budget_overview(con)
    elif page == "Spend Ledger": render_budget_ledger(con)
    else: render_scenario_lab(con)


st.set_page_config(page_title="2025 F1 Season Budget Simulation", page_icon="🏁", layout="wide")
con = db()
state = season.active_state(con)
palette = TEAMS[state["team_id"]] if state else {"primary":"#E10600", "secondary":"#F5F5F5"}
mode = state["theme"] if state else "neutral"
st.markdown(livery_css(palette["primary"], palette["secondary"], mode), unsafe_allow_html=True)
st.sidebar.markdown("## 🏁 Race Operations")
workspace = st.sidebar.radio("Workspace", ["2025 Season Budget Simulation","Budget Workspace"])
if state:
    appearance = st.sidebar.selectbox("Appearance", ["Team Livery","Race Operations"], index=0 if state["theme"] == "team" else 1)
    desired = "team" if appearance == "Team Livery" else "neutral"
    if desired != state["theme"]:
        con.execute("UPDATE career_state SET theme = ? WHERE id = 1", (desired,)); con.commit(); rerun_app()
    st.sidebar.metric("Selected constructor", TEAMS[state["team_id"]]["name"])
    st.sidebar.metric("Simulation cap", money(CAP))
    if st.sidebar.button("Reset active simulation"):
        season.reset_career(con); rerun_app()
else:
    st.sidebar.metric("Simulation cap", money(CAP))
    st.sidebar.caption("Select a constructor to start the 2025 season.")

if workspace == "2025 Season Budget Simulation": render_simulation(con, state)
else: render_budget_workspace(con)
