# 2025 F1 Season Budget Replay

An offline Streamlit application for replaying the recorded 2025 Formula 1
season while managing a constructor's budget operations under a **CAD $215M
gameplay cost cap**. It also keeps the separate analytical **Budget Workspace**
for tracking expenditure and running independent what-if analysis.

## Start it locally

The project supports the Python 3.9.7 installation used by this workspace.
Launch Streamlit through Python so it works even if the user-level `streamlit`
command is not on your `PATH`:

```bash
cd /path/to/f1-budget-allocator
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

Open the local address Streamlit prints, usually `http://localhost:8501`.

Streamlit Community Cloud uses the repository `runtime.txt` pin (`python-3.11`)
so it does not select Python 3.14 for the Streamlit 1.12 dependency stack.

Local state is stored in `f1_budget.db`. **Reset active simulation** removes
only the replay save and returns to team setup. Older active saves are migrated
locally when opened: their team, allocation, and ledger choices remain, while
completed on-track sessions and standings are rebuilt from the bundled replay.

## Exact 2025 historical replay

The Season Budget Replay is a recorded-season experience, rather than an
alternate-history race simulator.

- It contains all 24 rounds, with Sprint weekends in China, Miami, Belgium,
  the United States, São Paulo, and Qatar.
- One **Advance race weekend** action reveals the whole weekend on Race Control:
  Qualifying and Grand Prix for a standard round; Sprint Qualifying, Sprint,
  Grand Prix Qualifying, and Grand Prix for a Sprint round.
- Each session presents the locally bundled entrants, classification, recorded
  gap or status text, points, knockout timing where available, and session
  notes. The roster follows the drivers who actually raced at that round,
  including the Lawson/Tsunoda and Doohan/Colapinto changes.
- Constructors' points use the 2025 Grand Prix and Sprint scoring tables.
  Fastest lap is displayed but awards no point under the 2025 rules.
- Race positions, gaps, points, DNFs, penalties, and standings are locked to
  the historic replay. Budget allocations, repairs, weather cards, personnel,
  operations, testing, component condition, and any local decision **never
  change an on-track classification or the historic standings**.

One source limitation is shown transparently in the UI: the bundled Miami
Grand Prix Qualifying result preserves the recorded classification but has no
session timing values supplied by the source, so it displays `Timing not
supplied` rather than an invented time.

### Historical weather and race operations context

`data/historical_weekend_context_2025.json` supplies the factual context cards
shown for the selected team. It contains all 24 Grand Prix weekends and the
six Sprint sessions:

- **OpenF1** session samples for air and track temperature, humidity, wind, and
  observed rain; plus each driver's recorded tyre stints and pit-lane records.
- **Open-Meteo** hourly reanalysis for the Grand Prix session window at the
  circuit coordinates, including temperature, precipitation, wind, and weather
  code. It supplies the millimetre precipitation figure alongside OpenF1's
  observed-rain flag.
- Actual tyre compounds, stint lap ranges, tyre age, pit laps, and supplied
  lane/stationary timing when available. The interface displays this read-only
  historical record only for the constructor being replayed.

No weather value, stint, pit stop, or strategy is generated. A missing source
field stays unavailable rather than being estimated, and an empty OpenF1 pit
list is shown as no source-recorded stop. This context is informational and
does not change the historic replay.

## Budget operations and safety cover

### Pre-season planning

Choose one of the ten 2025 constructors, review its roster and modelled cost
profile, then allocate pre-season funding across:

- Aero
- Powertrain
- Chassis / structures
- Personnel
- Operations
- Testing
- Other

The setup screen also has an editable **Crash contingency allocation**. This
is a protected repair envelope inside the CAD $215M planning view. It is not
cap spend when earmarked: only a repair charged against it becomes actual cap
spend. The app shows the allocated reserve, repair spend, remaining cover, and
any repair amount that exceeds the reserve. Unused cover stays unspent at the
end of the replay.

### Race-weekend incidents and repairs

After a selected team's historical DNF, penalty, crash, or retirement, Race
Control shows a source-linked warning. Where public reporting describes damage,
the warning includes a damaged-area summary and a CAD low-to-high repair band.
Those bands are local gameplay estimates based on public component-cost
references; they are not team invoices, FIA figures, or official repair costs.

For a repairable event, choose the project's minimum repair record, a full
current-spec repair, a custom funded amount, or certified older-spec parts
where eligible. A project-critical repair record cannot be deferred to
older-spec parts. Incidents that do not have a public repair estimate can be
reviewed and retained in the ledger without inventing a cost.

The **Season ledger** records an explicit **Effects** description for every
entry. It distinguishes crash-cover allocation, repair-record status,
cap/headroom commitments, and the fact that development entries do not change
the historical replay.

### Cap handling and audit

The app permits allocations, packages, and repairs above CAD $215M. It gives
an inline breach preview before recording the entry and preserves all financial
choices in the final audit. The game-only audit consequences are:

| Gameplay cap position | Game audit consequence |
| --- | --- |
| At or below CAD $215M | Within gameplay cap |
| More than CAD $215M, up to and including 5% over | CAD $5M fine and 10% next-year aerodynamic-development reduction |
| More than 5% over | CAD $10M fine, 20% reduction, and a 10-point audit-only deduction |

The audit-only deduction is never used to rewrite the exact 2025 standings.
These rules are transparent local game mechanics, not an FIA ruling or a
prediction of a real sanction.

### FIA regulatory context

The CAD $215M cap and fixed outcome table above are illustrative gameplay
rules, not a calculation of FIA compliance. Under the
[2025 FIA Financial Regulations](https://www.fia.com/system/files/documents/2025_fia_formula_1_financial_regulations_-_issue_25_-_2025-07-31.pdf),
a Minor Overspend Breach is less than 5% above the FIA-defined Cost Cap in
Relevant Costs, while a Material Overspend Breach is 5% or more. Actual
accounting, investigations, and sanctions are case-specific. This prototype
does not calculate Relevant Costs, determine an FIA breach, or predict an FIA
sanction.

At Abu Dhabi, the **Board Audit & FIA-Inspired Review** reports the verdict, spend by category,
crash tax, planned investment, reserve use, cost per historic constructor
point, breach result, and the 2026 carry-forward value. It compares the saved
replay's constructor rank and points with the locally recorded 2025 outcome.

### Safety planning foundation

The **Safety planning** tab is an evidence view for the later planning phase.
It brings together only the historical incident record, source links where
available, project critical-repair flags, repair-record status, and the local
crash-contingency ledger. It does not calculate a readiness score, predict
risk, prescribe a repair, or issue a safe-to-race outcome. Verified spare
inventory, repair durations, inspection/sign-off, and release approval are not
included in the bundled public data and will remain unavailable until reviewed
data or clearly labelled prototype assumptions are added separately.

## What investments do

In the Season Budget Replay, investments affect only financial records,
repair-readiness/safety labelling, reserve use, and the final audit. They do
not create a lap-time delta, alter a strategy call, prevent a recorded crash,
or produce hypothetical future performance. The selected current-to-future
switch point records whether applicable funding is labelled for the following
car while still counting toward the current gameplay cap.

The **Budget Workspace** remains separate. Its Scenario Lab can still show a
diminishing-returns analytical curve for manually entered budget scenarios, but
it has no connection to replayed sessions, points, classifications, or the
Season Budget Replay ledger.

## Visual system and driver assets

- The homepage provides a team-coloured replay entry point, 2025 calendar
  preview, cap snapshot, carbon-fibre texture, and finish-line styling.
- Choose **Team Livery** for the selected team's palette or **Race Operations**
  for the neutral telemetry palette. The preference is saved with the active
  replay.
- Local driver photos appear throughout team setup, classifications, incidents,
  and review screens. The pack covers all 21 drivers who raced in 2025. If a
  photo cannot render, the app uses a team-coloured locally created initials
  badge.

The local photo derivatives are licensed Wikimedia Commons assets. Per-file
source page, author, and licence information is in
[assets/drivers/ATTRIBUTIONS.md](assets/drivers/ATTRIBUTIONS.md). The fallback
SVG badges and palette information are described in [ATTRIBUTIONS.md](ATTRIBUTIONS.md).

## Budget Workspace

- **Budget Tracker:** category allocation, actual spend, cap balance,
  historical spend, run-rate indicators, and allocation alerts.
- **Spend Ledger:** CAD-labelled manual entries, CSV import/export, filtering
  of past expenditure, and editable allocation/curve data.
- **What-if Scenario Lab:** independent add-or-reallocate scenarios, a
  diminishing-returns chart, and comparison of saved scenarios.

## Data and modelling boundaries

- The exact historical session bundle is local and the app makes no network
  request at runtime.
- Calendar structure, results, points, entrants, statuses, and session data
  are historic records. See [DATA_SOURCES.md](DATA_SOURCES.md) for their local
  files, sources, and known data limitation.
- Financial amounts, constructor cost profiles, repair ranges, reserve rules,
  project critical-repair flags, board targets, and sanctions are local gameplay models.
  They are not confidential FIA or team financial records.
- Local weather, tyre-stint, pit-stop, and incident context is source-backed
  historical reference for the selected team. OpenF1 observations and
  Open-Meteo reanalysis stay separate in the UI and do not affect recorded race
  results.

## Compatibility

`requirements.txt` pins Streamlit 1.12.0 because Python 3.9.7 cannot install
newer Streamlit releases. The UI intentionally avoids newer-only APIs such as
`st.divider`, DataFrame sizing/index options, and `st.rerun`, so it works with
Streamlit 1.12.0 and newer compatible releases.
