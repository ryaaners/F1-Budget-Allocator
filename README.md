# 2025 F1 Season Budget Replay

An offline Streamlit application for replaying the recorded 2025 Formula 1
season while managing a constructor's budget operations under a **CAD $215M
gameplay cost cap**. It also keeps the separate analytical **Budget Workspace**
for tracking expenditure and running independent what-if analysis.

## Start it locally

The project is tested with **Python 3.11**. Launch Streamlit through Python so
it works even if the user-level `streamlit` command is not on your `PATH`:

```bash
cd /path/to/f1-budget-allocator
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

Open the local address Streamlit prints, usually `http://localhost:8501`.

On Windows PowerShell, the equivalent is:

```powershell
Set-Location 'C:\path\to\F1-Budget-Allocator'
py -3.11 -m pip install --user -r requirements.txt
py -3.11 -m streamlit run app.py
```

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

For a repairable event, record the low end of the local estimate, the high-end
current-spec estimate, a custom local amount, or a local ledger choice to reuse
older-spec parts where eligible. A project-critical repair record cannot use
the deferred-parts option. When public reporting does not support a cost band,
the app records a source limitation rather than claiming a repair, safety
outcome, or vehicle release.

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

### Safety planning: evidence plus a separate prototype planner

When a saved replay exists, the application opens the **Safety Control Room**
first so the safety-planning workflow is the natural demo entry point. It keeps
two things separate:

- **Historical evidence and data boundary** brings together only the read-only
  incident record, source links where available, project critical-repair flags,
  repair-record status, and the local crash-contingency ledger.
- **Prototype Repair Planner** is a deliberately separate local scenario tool.
  It lets a user compare editable assumed response options against assumed
  spares, work time, reserve floor, local cap headroom, a selected local
  R&D/operations funding source, and a user-confirmed human-record checklist.

The planner returns only `HOLD`, `REVIEW_ELIGIBLE`, or `REVIEW_REQUESTED`.
`REVIEW_ELIGIBLE` means the entered prototype values meet this app's transparent
rules; `REVIEW_REQUESTED` means one explicit local-ledger funding action was
recorded. Neither status is a vehicle release, repair instruction, safety
certification, FIA finding, risk prediction, or safe-to-race verdict.

Every cost, duration, spare count, reserve floor, checklist action, and gate is
an editable educational assumption. The selected option's cost/work/spares and
case resources can be changed in the planner; catalog defaults and checklist
structure live in
[`data/safety_planning_assumptions.json`](data/safety_planning_assumptions.json).
They are not public-team inventory, repair invoices, validated engineering
facts, or official FIA rules. The planner can store a historical incident as a
bounded source-context reference, but it never writes to the historical
incident record or uses the public record as hidden repair data.

The **Historical incident → prototype case** launcher accepts only a
repair-required historical record and turns it into an identifier-free,
app-preserved context snapshot. It exposes only the bundled context that is
actually available (for example round, title, public source link, damage-area
summary, and any pre-existing local estimate label). It does not prefill a
response option, cost, work duration, spare count, checklist, or sign-off.
The app verifies that snapshot's bounded schema, origin, SHA-256, and matching
`historical-context:<sha>` reference before a decision can be saved or funded.
This guards the local workflow against detached/forged context through the
app's own APIs; it is still not independent source verification.

Each saved prototype record keeps both a user-editable local title and an
app-preserved source-context snapshot (plus bundled round/title/source-link
details where present). It records a canonical SHA-256 fingerprint of the
editable assumptions catalog, its stated catalog/rules-engine version, and a
frozen selected-profile/option basis. These are local reproducibility checks,
not proof that a source or repair assumption is true. If the catalog or rules
engine changes, the current funding check holds the old record and requires a
fresh plan rather than silently reinterpreting it. Legacy records without this
basis are viewable but cannot receive new local funding.

For each `HOLD`, the planner exposes structured model gaps—such as assumed
spare, work-window, reserve, funding-source, cap, or checklist shortfalls—and
renders a reserve/cap trade-off preview. It also includes three fictional demo
input presets. The presets never import historical facts, complete a human
record, create a decision, or commit funding.

The **Two-case shared-resource stress test** adds a read-only Orange Flag
scenario: two fictional, editable response options are summed once against one
shared assumed spare pool, work window, reserve floor, planned transfer, source
capacity, and cap headroom. It makes a resource conflict visible even when a
single case appears contained. `RESOURCE_FEASIBLE` only means the entered
fictional accounting envelope contains those two entered demands; it creates no
case, funding record, review request, repair instruction, or release outcome.

Saved decisions have a read-only **Decision receipt / reproducibility audit**
panel and JSON download. It contains the app-preserved context, recorded and
funding-time checks, catalog/profile fingerprints, linked local-ledger IDs, and
the non-release disclaimer. This is an app-generated audit artifact; it is not
sent to a reviewer and does not constitute a vehicle approval.

The receipt also re-derives a local decision fingerprint from the persisted
frozen decision basis and checks that the saved funding snapshot and linked
ledger rows still reconcile to it. Funding refuses a stale, incomplete,
inconsistent, or already-correlated local record, including a record whose
mutable funding pointers were cleared. These checks are local tamper-evidence
and duplicate-charge safeguards—not tamper-proof storage or external audit.

When the user explicitly commits funding, the app records one modelled repair
charge and (where needed) a matching negative local planned-spend
reprioritisation from the selected source. That makes the reserve/cap/R&D or
operations trade-off visible in the local ledger. It does not move money in a
real team, change any 2025 classification, or clear the historical replay's
separate repair-record gate.

Funding uses the plan's original replay round. A plan recorded for an earlier
round is held until it is re-recorded for the current local replay round. The
ledger links the repair, reprioritisation, and reserve-top-up rows to the saved
decision, so a receipt can verify their local correlation.

Only local **current-season** planned commitments are available as an
explicit funding source; future-car-labelled commitments are excluded. The
final local audit shows a negative prototype-source reprioritisation beside the
positive modelled repair charge so its displayed financial lines reconcile to
the app's cap total.

Before a live demo, run the focused browser checks in
[`UI_QA_CHECKLIST.md`](UI_QA_CHECKLIST.md). The unit tests cover the pure rules
and SQLite boundaries; the checklist is intentionally honest about requiring a
real Streamlit session for widget-level verification.

For the Formula Tech Hacks presentation narrative, scope boundaries, Q&A, and
click-by-click demo script, use
[`HACKATHON_PRESENTATION.md`](HACKATHON_PRESENTATION.md).

For a disposable local test/demo database, set `F1_BUDGET_DB_PATH` before
running Streamlit. The normal default remains the bundled `f1_budget.db`.

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
