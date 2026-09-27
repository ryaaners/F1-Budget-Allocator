# 2025 F1 Season Budget Simulation

An offline Streamlit decision tool for managing a Formula 1 constructor through a
modelled 2025 season under a **CAD $215M gameplay cost cap**. It also retains the
analytical Budget Workspace for live budget tracking, ledgers, and what-if analysis.

## Start it locally

This project is compatible with the Python 3.9.7 installation shown in the earlier
terminal output. Install and launch it with the Python module command so it does not
depend on the user-level `streamlit` command being on your `PATH`:

```bash
python3 -m pip install --user -r requirements.txt
python3 -m streamlit run app.py
```

Open the local URL Streamlit prints, normally `http://localhost:XXXX`.

The app stores its local state in `f1_budget.db`. The sidebar **Reset active
simulation** control clears only the season simulation and returns to team setup.

## What the simulator does

### 2025 Season Budget Simulation

- Lets the player choose any 2025 constructor, view its two-driver dossier and choose
  pre-season spending across Aero, Powertrain, Chassis / structures, Personnel,
  Operations, Testing, and Other.
- Uses all 24 rounds of the 2025 calendar, including Sprint weekends in China, Miami,
  Belgium, the United States, São Paulo, and Qatar.
- Runs standard weekends as Qualifying then Grand Prix, and Sprint weekends as Sprint
  Qualifying, Sprint, Grand Prix Qualifying, then Grand Prix. Qualifying shows the
  Q1/Q2/Q3 and SQ1/SQ2/SQ3 knockout ladders for all 20 cars.
- Scores constructors using the 2025 Grand Prix and Sprint points tables. Fastest lap
  is shown in classifications but awards no point.
- Applies bounded effects from R&D, Personnel, Operations, Testing, weather,
  reliability, component condition, driver ratings, and a saved deterministic seed.
- Gives a pre-race development control for current-car or future-car packages. From
  the selected switch round, Aero, Powertrain, Chassis, and Testing packages move to
  the next car while still counting against the current CAD $215M gameplay cap.
- Tracks repairs, manual damage events, older-spec component penalties, future-car
  reserve decisions, constructor standings, burn-down, cap health, and a post-race
  classification for the round just completed.
- Shows a current-season constructor-position estimate beside the future-car opening
  pace credit and selected development switch point.
- Adds circuit-risk and weather-sensitive simulation variance beside the local
  historical-risk prompts. Variance incidents are labeled as gameplay events.
- Shows the selected team’s local weekend reference card: weather conditions, actual
  archived 2025 qualifying, Grand Prix, and Sprint result status and points, a
  tyre/pit-stop reference, and only that team’s incident prompts.
- Ends with an **FIA & Board Audit** covering the verdict, cap status, crash tax,
  planned R&D, cost per point, game sanctions, real-2025 comparison, decision moments,
  and 2026 carrying value.

### Survival cell safety

The survival cell is the carbon-fibre shell around the driver. Under a cost cap, every
dollar kept for it competes with lap time, so the simulator makes that trade-off visible.

- **Crash severity:** every Chassis / structures incident gets a simulated impact
  (in g), harder at risky or wet circuits. A **small hit** (under 20g) passes the
  survival cell check and can still be delayed with "Run older specification". A
  **medium hit** (20–45g) cracks the cell and adds a CAD $0.8M repair. A **big hit**
  (45g and up) destroys it and adds a CAD $2.5M replacement. Medium and big hits
  cannot be delayed, because a car with a damaged survival cell cannot race.
- **Crash safety money:** Race control shows how many big crashes (about CAD $4.0M
  each) the team could still pay for inside the cap, after unpaid repairs. Committing
  a package that would leave less than one big crash triggers a safety warning, and the
  player must tick an override box to buy it anyway. Pre-season setup shows the same
  status for the planned reserve.
- The manual crash form in the Season ledger can force a small, medium, or big hit for
  demos.

### Budget Workspace

- **Budget Tracker:** category spend, allocation use, CAD cost-cap balance, historical
  spend line, projected run rate, and allocation risk alerts.
- **Spend Ledger:** CAD-labelled manual entries, CSV import/export, past-expenditure
  filtering, and allocation/curve editing.
- **What-if Scenario Lab:** add or reallocate CAD spending, view diminishing-return
  lap-time change, inspect the curve, and save up to three comparable scenarios.

## Visual system

- Carbon-fibre CSS texture and checkered finish-line dividers.
- Team Livery and neutral Race Operations appearance modes.
- Team palettes applied to key metrics, charts, and panels.
- Local reusable driver SVG portrait badges with initials fallbacks.

The driver assets are original vector badges, not photos. Their status and replacement
instructions are recorded in [assets/drivers/ATTRIBUTIONS.md](assets/drivers/ATTRIBUTIONS.md).

## Data and modelling notes

- Financial amounts, cost tiers, crash-repair values, R&D return curves, mitigation
  rates, and FIA sanctions are **gameplay models**, not FIA or team financial filings.
- The calendar, Sprint rounds, constructor targets, scoring format, and actual
  round-level constructor qualifying/Grand Prix/Sprint results are held locally. The
  in-app weather, strategy, and damage material is intentionally a compact local
  reference layer so the app stays offline. It labels local estimates and “Not
  officially assigned” responsibility explicitly.
- The post-season sanction matrix is a transparent game rule: up to 5% over cap gives
  a CAD $5M fine and 10% aerodynamic-development reduction; over 5% gives a CAD $10M
  fine, 20% reduction, and 10 constructor-point deduction. It is not an FIA ruling.

See [DATA_SOURCES.md](DATA_SOURCES.md) for the local source notes and the boundary
between verified season structure and gameplay reference material.

## Compatibility

`requirements.txt` pins Streamlit 1.12.0 because Python 3.9.7 cannot install newer
Streamlit releases. The UI avoids newer-only `divider`, `dataframe` sizing/index, and
`rerun` APIs, so it runs on that version and on newer Streamlit versions.
