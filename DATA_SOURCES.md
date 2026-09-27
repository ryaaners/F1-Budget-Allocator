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

### Safety-planning evidence boundary and prototype assumptions

The historical-evidence area uses only the fields above, the recorded repair
state, and the local crash-contingency ledger. A project critical-repair flag is
a local replay workflow rule, not an FIA or engineering finding. The bundled
public record does **not** contain verified spare inventory, component
condition, repair duration, staffing, inspection/sign-off, release approval, or
validated risk inputs.

The separate Prototype Repair Planner intentionally does not fill those gaps
with claimed facts. Its cost, duration, spare count, reserve floor, checklist,
and response-option values are all local editable educational assumptions. The
catalog defaults/checklist are in
[`data/safety_planning_assumptions.json`](data/safety_planning_assumptions.json),
and selected-option cost/work/spare values can be overridden in the UI and
snapshotted with a local decision.
They are not sourced team data, repair instructions, engineering validation, or
official FIA requirements. Historical events can be selected only as a text
context snapshot; their incident rows and source records are never modified by
the planner. A saved planning record preserves an **app-preserved
source-context snapshot** of the selected context label and available
round/title/source-link fields. That snapshot is useful local context, not an
immutable external source, proof that the linked source is correct, or a live
dependency on the replay incident ID.

The **Historical incident → prototype case** launcher only accepts a
repair-required historical row. It creates an identifier-free bounded v1
snapshot of the available app-held fields rather than passing through the
database incident ID or importing a repair plan. The snapshot has a local
SHA-256 and must use its matching `historical-context:<sha>` reference before a
decision can be recorded or funded. The app validates that schema/origin/hash
relationship again at funding time. That is a local provenance boundary, not
evidence that the public source, estimate, inventory, or repair is true.

At record time, the app also stores a canonical SHA-256 fingerprint of the
editable assumptions catalog, its stated catalog and rules-engine versions, and
a frozen copy of the selected profile and option. These fields make a local
decision reproducible even if the editable catalog later changes; they do not
verify the assumptions or the historical source. Before optional local funding,
the app checks the current catalog against the recorded fingerprint. A changed,
unavailable, or legacy-unfingerprinted catalog holds the old plan until it is
recorded again under a valid current basis rather than silently reinterpreting
it.

Each saved decision exposes an app-generated **Decision receipt /
reproducibility audit** and JSON download. The receipt includes the preserved
context, recorded and funding-time checks, catalog/profile fingerprints, and
locally linked ledger IDs. It is a local audit artifact only: it is not a
message sent to a reviewer, external verification, repair completion record,
or vehicle approval.

The receipt recomputes a decision-basis fingerprint from frozen persisted
fields and verifies funding-time resource values and linked local-ledger rows
against that basis. If the local basis is missing, inconsistent, stale, or has
any correlated prototype funding row despite cleared mutable pointers, new
funding is held. This provides local reproducibility/tamper evidence and a
duplicate-charge backstop; it is not cryptographic storage integrity or an
external audit.

The optional **Two-case shared-resource stress test** has no historical-data
claim. Its case costs, spares, work hours, shared reserve, transfer, source
capacity, and cap headroom are all explicit editable prototype inputs. It
returns only an accounting-envelope `RESOURCE_FEASIBLE` or `RESOURCE_HOLD`
result, creates no persisted decision or ledger entry, and does not determine
safety, authorise work, or release a vehicle.

The prototype may produce `HOLD`, `REVIEW_ELIGIBLE`, or `REVIEW_REQUESTED`.
These describe only whether its entered assumptions, transparent resource
checks, and local audit/handoff action are complete. `REVIEW_REQUESTED` means
the app recorded a local funding and review-handoff package; it does not mean
that a person was contacted or approved anything. The states do not calculate a
readiness score, recommend a real repair, predict a failure, authorise a
vehicle release, or establish that a car is safe to race.

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
how much local repair expenditure it can cover; unused reserve remains unspent
cap headroom. A user may also explicitly commit a Prototype Repair
Planner scenario: that creates a clearly labelled local modelled repair charge
and, where selected, a matching local planned-spend reprioritisation and reserve
top-up. Those records are finance-model entries only, not real transfers,
invoices, FIA Relevant Costs, or evidence of a completed repair. The local
source-capacity calculation excludes future-car-labelled commitments, and the local audit
shows the negative reprioritisation separately so it reconciles with the
positive modelled repair charge. Financial
entries may exceed the gameplay cap. Any fine,
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
