# Local data-source notes

The simulation does not call a web API at runtime. It bundles compact reference data
in `career_data.py` so a season can be completed offline and reproduced from its saved
seed.

## Verified season structure

- The 24-round calendar and six Sprint venues were checked against Formula 1’s
  [2025 calendar announcement](https://www.formula1.com/en/latest/article/fia-and-formula-1-announces-calendar-for-2025.48ii9hOMGxuOJnjLgpA5qS).
- Round naming, dates, and winner context can be cross-checked against the official
  [2025 race-results index](https://www.formula1.com/en/results/2025/races).
- `data/historical_2025.json` bundles actual 2025 qualifying, Grand Prix, and Sprint
  result status and team points from the public [Jolpica Ergast archive](https://api.jolpi.ca/ergast/f1/2025/results.json).
- The app displays fastest lap without a point because the point was removed for 2025;
  see Formula 1’s [2025 rule-change note](https://www.formula1.com/en/latest/article/from-fastest-lap-to-increased-rookie-running-7-rule-changes-you-need-to-know.pgdSMDnDyv1aJUgtcKPp6).

## Weather, strategy, and incident material

- Weather cards use locally bundled track-day reference values. They are compact
  gameplay inputs, not a session-by-session official weather archive. Open-Meteo’s
  [Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)
  is the intended source for a future detailed refresh.
- The selected-team tyre and pit-stop cards are curated local reference prompts. The
  selected team’s actual qualifying, Grand Prix, and Sprint positions, points,
  retirement, and official session status are bundled separately in
  `data/historical_2025.json`. Team strategy intent, damage invoices, and every
  driver-contact cause are not comprehensively public, so the interface explicitly
  labels modeled repair cost and “Not officially assigned” responsibility when there
  is no verified public basis.
- Constructor targets and team cost profiles are simulation reference data. They are
  not FIA filings, which are confidential.

## Gameplay boundary

Financial return curves, repair costs, probabilities, forecast metrics, audit verdicts,
and sanctions are transparent game mechanics. The survival cell impact values (g),
the 20g and 45g hit thresholds, the survival-cell repair and replacement costs, and the
CAD $4.0M big-crash reserve are also gameplay estimates. They are not FIA homologation
test values or team invoices. Nothing in the app represents an FIA
cost-cap finding, a published team account, or an official assignment of blame.
