# Local data-source notes

The application runs offline. It does not query Formula 1, Jolpica, weather,
or image services while a replay is running. The local database only stores a
player's budget decisions and the sessions already revealed in their replay.

## Exact 2025 replay bundle

`data/historical_2025_replay.json` contains the 2025 record used by Race
Control:

- 24 championship rounds and 60 sessions;
- Qualifying and Grand Prix rows for every round;
- Sprint Qualifying and Sprint rows for the six scheduled Sprint weekends;
- entrants, driver/team assignments, classifications, points, status text,
  grid detail, gaps, available Q1/Q2/Q3 or SQ1/SQ2/SQ3 timing, fastest-lap
  information, and session notes;
- the changes to the racing roster during the season, including Lawson/Tsunoda
  and Doohan/Colapinto.

The official Formula 1 [2025 results index](https://www.formula1.com/en/results/2025/races)
is the human-readable result reference for classifications, timing, points, and
published notes. The bundled machine-readable session data uses the
[Jolpica F1 alpha results feed](https://api.jolpi.ca/f1/alpha/results/) as its
offline source support. The feed's session availability and endpoint structure
are documented by [Jolpica](https://github.com/jolpica/jolpica-f1/discussions/319).

The bundle intentionally preserves source limitations rather than estimating
missing timing. In particular, Miami Grand Prix Qualifying has its recorded
classification but no source-supplied session timing values, so the application
shows `Timing not supplied` for that session.

The 2025 points interpretation follows Formula 1's
[rule-change announcement](https://www.formula1.com/en/latest/article/from-fastest-lap-to-increased-rookie-running-7-rule-changes-you-need-to-know.pgdSMDnDyv1aJUgtcKPp6):
fastest lap receives no championship point.

## Incidents, penalties, and damage estimates

`data/incidents_2025.json` is a selected-team incident feed. It contains local
records for 2025 GP and Sprint non-finishes and relevant penalty events, with
the session, driver, factual description, responsibility where a source
establishes it, damaged-area summary, source URL, repair band, and project
critical-repair flag.

- The underlying result status is drawn from the historical replay bundle.
- Formula1.com reporting is linked when public reporting provides a factual
  incident description.
- If public records do not establish cause or responsibility, the record says
  so instead of inferring fault or intent.
- Public team repair invoices and cost-cap filings are not available. A non-zero
  repair band is therefore an **unofficial local estimate** only when damage is
  publicly described. It uses public component-cost context such as the
  [Destructors Championship](https://f1.top-app.eu/destructors-championship),
  never an FIA or team cost record.

An incident with no public physical-damage basis can remain a zero-cost reviewed
record. The app does not invent a repair amount merely to create a decision.

### Safety-planning evidence boundary

The first Safety planning view uses only the fields above, the recorded repair
state, and the local crash-contingency ledger. A project critical-repair flag
is a local replay workflow rule, not an FIA or engineering finding. The bundle
does not contain verified spare inventory, component condition, repair duration,
staffing, inspection/sign-off, release approval, or validated risk inputs. It
therefore does not calculate a readiness score, recommend a repair, predict a
failure, or authorise a car release.

User-added repair events from the Season ledger are displayed separately as
local planning entries. They are never presented as historical incident
evidence or source-backed records.

## Weather and strategy reference cards

`data/historical_weekend_context_2025.json` is the locally bundled race
operations context used by the selected-team weather and strategy cards. It
covers all 24 Grand Prix sessions plus the six 2025 Sprint sessions. It does
not make a request while the app is running.

### OpenF1 session records

The [OpenF1 historical data API](https://openf1.org/docs/) supplies the
recorded session-level inputs:

- weather samples for air and track temperature, humidity, wind, and the
  source's observed-rain field;
- per-driver tyre compound, stint number, lap start/end, and tyre age;
- per-driver pit-lane records, including lap and supplied lane/stationary
  durations when available.

OpenF1 is an independent public data service, not Formula 1 or FIA data. Its
rain field is a binary observation, not millimetres of rainfall. The app shows
only the selected team's source rows and never generates tyre choices, stops,
or weather values. An empty source-returned pit list means OpenF1 returned no
pit record; missing fields remain unavailable and are not inferred.

### Open-Meteo Grand Prix-window reanalysis

The [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)
adds hourly temperature, precipitation, wind, and WMO weather-code reanalysis
for each Grand Prix session window. Circuit coordinates originate from the
[Jolpica Ergast-compatible 2025 schedule](https://api.jolpi.ca/ergast/f1/2025.json?limit=100).

Open-Meteo precipitation is a weather-grid reanalysis estimate, not a circuit
rain-gauge reading. It is displayed alongside, never substituted for, the
OpenF1 observed-rain samples. Source fields that are absent are stored as null
instead of being fabricated.

These weather and race-operations cards are informational. Weather, actual
stints, pit data, repairs, personnel, testing, and operations do not change
the historical classifications, points, gaps, DNFs, penalties, or standings in
this replay.

## Financial and audit model boundary

The CAD $215M cap, fixed operating profiles, pre-season funding, crash
contingency allocation, repair choices, current-to-future funding labels,
board targets, financial health indicators, and sanction bands are local
gameplay rules.

The cap and fixed outcome matrix are not FIA compliance calculations. Under the
[2025 FIA Financial Regulations](https://www.fia.com/system/files/documents/2025_fia_formula_1_financial_regulations_-_issue_25_-_2025-07-31.pdf),
a Minor Overspend Breach is less than 5% above the FIA-defined Cost Cap in
Relevant Costs and a Material Overspend Breach is 5% or more. The application
does not calculate Relevant Costs, determine an FIA breach, or predict an FIA
sanction.

The crash contingency is a planning reserve, not immediate spend. It tracks
how much source-backed repair expenditure it can cover; unused reserve remains
unspent cap headroom. Financial entries may exceed the gameplay cap. Any fine,
aerodynamic-development reduction, or audit-only points deduction shown in the
post-season review is an application rule and does not alter the historic 2025
standings.

No financial investment creates a simulated lap-time improvement or changes a
race outcome. Development and operational entries have finance, readiness, or
safety labels in the ledger only.

Constructor cost profiles, repair ranges, allocation curves in the independent
Budget Workspace, and all audit verdicts are models. They are not FIA filings,
official team accounts, or official assignments of legal responsibility.

## Driver images and visual assets

`assets/drivers/photos/` contains local resized derivatives of licensed
Wikimedia Commons photographs for every driver who raced in 2025. Each file's
source page, author, and original licence are recorded in
[assets/drivers/ATTRIBUTIONS.md](assets/drivers/ATTRIBUTIONS.md). The original
team-coloured SVG initials badges remain only as a fallback when an image cannot
be rendered; they are project-created artwork and are documented in
[ATTRIBUTIONS.md](ATTRIBUTIONS.md).

`assets/team_palettes.json` contains accessible application palette values. It
is UI data, not an official Formula 1 or constructor brand guide.
