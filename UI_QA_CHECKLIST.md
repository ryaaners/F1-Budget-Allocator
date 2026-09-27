# Prototype Repair Planner — Manual UI QA Checklist

This checklist is deliberately separate from automated tests. It records what
must be exercised in a real Streamlit browser session before a live hackathon
demo. Do not mark an item as passed merely because the Python unit tests pass.

## Current verification status

- Automated engine/persistence verification: run with
  `python -m unittest discover -s tests -v`.
- Browser verification in this checkout: **pending** until Streamlit and the
  project requirements are installed in a Python environment with enough free
  disk space.
- The tracked `f1_budget.db` is user state. For this checklist, use a copied
  demo database or a disposable checkout; do not overwrite/reset the user's
  existing simulation.

## Preflight

- [ ] Start `streamlit run app.py` and open the local address it prints.
- [ ] Begin a replay with enough cap headroom and a CAD $5M crash reserve.
- [ ] Open **2025 Season Budget Replay → Safety planning**.
- [ ] Confirm the page labels the planner as fictional/editable prototype
      assumptions and says it is not a vehicle-release or FIA decision.

## Core Track 3 workflow

- [ ] Select **Prototype demo case** and the **Suspension / steering scenario**.
- [ ] Choose **Assumed inspection and spare replacement**.
- [ ] Change the selected option's editable modelled cost, work hours, or spare
      requirement. Verify the comparison/selected-plan values update, then
      restore the intended demo values before recording.
- [ ] Set assumed spare count to `0`; verify the selected state is `HOLD` and
      names the spare shortfall.
- [ ] Set hours to `0`; verify `HOLD` names the work-window shortfall.
- [ ] Restore enough spares/hours, complete the listed human-record checkboxes,
      and verify `REVIEW ELIGIBLE` appears without saying the car is released or
      safe to race.
- [ ] Save the eligible candidate. Click save again unchanged; verify the app
      reports an existing matching record rather than making a duplicate.
- [ ] Commit modelled funding once. Verify the record becomes
      `REVIEW REQUESTED`, a local repair-ledger entry appears, and a second
      click cannot charge it twice.

## Tangerine resource trade-off

- [ ] Set the reserve floor high enough to require a transfer and click
      **Use calculated transfer needed for this option**.
- [ ] Verify the selected source capacity is shown and the plan is `HOLD` when
      the transfer exceeds that capacity.
- [ ] Choose an available local funding source, record/commit an eligible plan,
      and verify the local cap, reserve, and source capacity metrics update.
- [ ] Open **Season ledger** and verify the entries say they are local modelled
      prototype records, not real team spending or FIA accounting.

## Provenance and state isolation

- [ ] Select a historical context and give it a distinctive local title.
- [ ] Switch to another case context. Verify the prior case's spares, hours,
      reserve floor, transfer, source, and checklist selections do not carry
      into the new context.
- [ ] Save the second case. In **Saved prototype records**, verify each row
      shows both its local title and an immutable source-context label.
- [ ] If a record has a saved source URL, verify its displayed saved source link
      opens the expected historical reference.

## Regression and failure paths

- [ ] Visit every replay tab: Race control, Telemetry, History & weather,
      Season ledger, and Safety planning. Confirm no nested-column exception is
      raised under Streamlit 1.12.
- [ ] Add a local manual repair entry. Confirm Race control labels it as local,
      not historical evidence.
- [ ] For a historical source-limited critical record, confirm the replay
      wording says it only permits replay continuity and does not establish
      prototype readiness or release.
- [ ] Temporarily point a disposable copy at a malformed
      `data/safety_planning_assumptions.json`; confirm Safety planning shows a
      contained planner-unavailable message while the historical-evidence area
      remains visible. Restore the valid file immediately afterward.
- [ ] Capture standings, session results, and incident count before funding a
      prototype plan. Confirm they are identical afterward.

Record the date, environment, and any failed item in the project’s round
history before the presentation. A failed browser check is a known limitation,
not a reason to remove the integrity disclosure.
