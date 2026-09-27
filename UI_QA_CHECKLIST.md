# Prototype Repair Planner — Manual UI QA Checklist

This checklist is deliberately separate from automated tests. It records what
was exercised in a real Streamlit browser session and what still needs to be
checked before a live hackathon demo. Do not mark an item as passed merely
because the Python unit tests pass.

## Current verification status

- Automated engine/persistence verification: the current recorded run passed
  **56** tests with `python -B -m unittest discover -s tests -q`; compilation
  also passed for the app, engines, and all three test modules.
- Browser verification: the core workflow passed on **2026-09-27** on Windows,
  Python 3.11, and Streamlit 1.12. The app ran against a disposable SQLite copy
  selected with `F1_BUDGET_DB_PATH`; the repository's `f1_budget.db` was not
  used for the test actions.
- The passed browser flow was: `HOLD` with the zero-spare demo preset →
  `REVIEW ELIGIBLE` after the review-candidate inputs and human-record boxes →
  record → open the decision receipt and confirm its JSON-download control →
  one local funding action. A
  before/after database comparison confirmed `career_sessions`,
  `career_standings`, and `career_incidents` were unchanged. After the
  callback fix, the exercised flow had no browser-console errors.
- This is evidence for the core path, not a claim that every item below or
  every browser/version combination has been tested. Re-run relevant checks
  after a UI, Streamlit, catalog, or persistence change.
- Current-build browser smoke verification on the same disposable-database
  setup used a fresh local tab. It opened directly into **Safety Control Room**,
  rendered the historical launcher and planner, exercised the new two-case
  shared-resource `RESOURCE HOLD` and `RESOURCE FEASIBLE` presets, and reported
  no browser-console errors. No test action used the repository/user database.
- The latest first-time-user smoke check confirmed the **Start here** guide,
  plain-language example buttons, the simplified `HOLD` explanation, and the
  optional two-issue section render together without a browser-console error.
- The tracked `f1_budget.db` is user state. Always use a copied demo database
  or a disposable checkout for this checklist; do not overwrite or reset the
  user's existing simulation.

### Disposable database setup

1. Copy `f1_budget.db` to a safe temporary/demo location.
2. In the PowerShell session that will start Streamlit, point the app at that
   copy, for example:

   ```powershell
   $env:F1_BUDGET_DB_PATH = "C:\safe-demo-copy\f1_budget_demo.db"
   py -3.11 -m streamlit run app.py
   ```

3. Open the local URL Streamlit prints. Remove the environment variable or
   open a new terminal when you want to return to the normal bundled-database
   default.

## Completed core browser record

The following exact checks were completed in the recorded disposable-database
pass. They are separated from the broader regression list so a checked box has
a precise meaning.

- [x] Start Streamlit with `F1_BUDGET_DB_PATH` set to a copied database and
      open **2025 Season Budget Replay → Safety planning**.
- [x] Open a fresh app session and confirm an existing replay starts at
      **Safety Control Room** without needing to find the buried replay tab.
- [x] Confirm the page calls the planner editable, non-verified prototype
      assumptions and says it is not a vehicle-release or FIA decision.
- [x] Use **Show a spare-parts problem**. Confirm the selected plan is `HOLD` and the
      structured condition panel identifies the spare shortfall.
- [x] Use **Show a reviewable example**, complete the displayed human-record
      boxes, and confirm `REVIEW ELIGIBLE` appears without any safe-to-race or
      release language.
- [x] Record the eligible candidate, open **Decision receipt /
      reproducibility audit**, and confirm its local JSON-download control,
      frozen assumptions/profile fingerprint, current-catalog check, and
      `Receipt ledger-link check: OK` are visible.
- [x] Commit funding once. Confirm the record becomes `REVIEW REQUESTED` and
      is described as a local funding and review-handoff record, not a sent
      review, approval, or release.
- [x] Confirm the funding action created one local prototype repair-ledger
      entry linked to the decision; in this exact case no reserve transfer was
      required.
- [x] Compare historical tables before and after the funding action. Confirm
      `career_sessions`, `career_standings`, and `career_incidents` are
      unchanged.
- [x] Confirm the exercised planner path does not trigger the Streamlit nested
      columns exception or a browser-console error after the callback fix.
- [x] Expand a repair-required historical source card, inspect its preserved
      context boundary, and launch it. Confirm the planner selects the bounded
      `historical-context:<sha>` snapshot rather than a raw incident ID and
      does not auto-fill costs, time, spares, or checklist completion.
- [x] Use **Try a shared-resource conflict** in the two-case stress test;
      confirm the shared-resource result is `RESOURCE HOLD` and no record or
      funding action is created.
- [x] Use **Try a workable shared-resource example**; confirm the result changes to
      `RESOURCE FEASIBLE` while retaining the accounting-only, non-approval
      wording and creating no record or funding action.

## Preflight for each new demo build

- [ ] Begin a replay with enough cap headroom and a CAD $5M crash reserve.
- [ ] Open **2025 Season Budget Replay → Safety planning** and confirm the
      current catalog fingerprint/version is visible.
- [ ] Confirm the page still labels the planner as fictional/editable prototype
      assumptions and says it is not a vehicle-release or FIA decision.
- [ ] Copy the demo database and assumptions file before presenting so the
      original user state can be restored if needed.

## Core Track 3 workflow

- [ ] Select **Prototype demo case** and a response profile/option appropriate
      to the planned demo.
- [ ] Change the selected option's editable modelled cost, work hours, or spare
      requirement. Verify the comparison/selected-plan values update, then
      restore the intended demo values before recording.
- [x] Set assumed spare count to `0` with **Show a spare-parts problem**; verify the
      selected state is `HOLD` and names the spare shortfall.
- [ ] Set hours to `0`; verify `HOLD` names the work-window shortfall.
- [x] Restore enough modelled resources through **Show a reviewable example**,
      complete the listed human-record checkboxes, and verify `REVIEW ELIGIBLE`
      appears without saying the car is released or safe to race.
- [x] Save an eligible candidate and inspect its receipt, frozen assumption
      basis, and local-only disclaimer.
- [ ] Click save again unchanged; verify the app reports an existing matching
      record rather than making a duplicate.
- [x] Commit modelled funding once. Verify the record becomes `REVIEW
      REQUESTED` and a local repair-ledger entry appears.
- [ ] Attempt a second funding action or refresh/reopen the record; verify it
      cannot charge the same decision twice.

## Tangerine resource trade-off

- [x] Confirm the local reserve/cap waterfall preview renders for the selected
      option and labels the values as modelled local finance, not FIA
      accounting.
- [ ] Set the reserve floor high enough to require a transfer and click
      **Use calculated transfer needed for this option**.
- [ ] Verify the selected source capacity is shown and the plan is `HOLD` when
      the transfer exceeds that capacity.
- [ ] Choose an available local funding source, record/commit an eligible plan,
      and verify the local cap, reserve, and source capacity metrics update.
- [ ] Open **Season ledger** and verify the entries say they are local modelled
      prototype records, not real team spending or FIA accounting.

### Optional two-issue shared-resource check

- [x] Confirm the two-case section is visibly labelled fictional, editable,
      read-only, and accounting-only.
- [x] Run the shared-resource conflict and workable shared-resource presets. Confirm
      the first exposes shared resource gaps and the second gives only a
      `RESOURCE FEASIBLE` accounting result—not an approval, repair command,
      or safe-to-race conclusion.
- [ ] Change one case's editable cost, hours, or spares and confirm the shared
      totals/gaps update. Restore the intended demo inputs afterward.
- [ ] Download the JSON result and confirm it contains only the entered
      fictional case/envelope data, no historical incident ID and no ledger
      mutation.

## Provenance, reproducibility, and state isolation

- [ ] Select a historical context and give it a distinctive local title.
- [ ] Switch to another case context. Verify the prior case's spares, hours,
      reserve floor, transfer, source, and checklist selections do not carry
      into the new context.
- [x] In the saved eligible demo record, verify the receipt shows the
      app-preserved source-context label, catalog fingerprint/version, frozen
      selected-profile fingerprint, and local-ledger link section. Treat these
      as reproducibility information, not external source verification.
- [ ] Save two distinct cases. In **Saved prototype records**, verify each row
      shows its local title and app-preserved source context without describing
      it as immutable external evidence.
- [ ] If a record has a saved source URL, verify its displayed saved source link
      opens the expected historical reference.
- [ ] Record an eligible plan in a disposable copy, then change its catalog
      copy. Verify the live funding check holds the old record and asks for a
      fresh plan rather than silently applying the new catalog.

## Regression and failure paths

- [x] Visit every replay tab: Race control, Telemetry, History & weather,
      Season ledger, and Safety planning. Confirm no nested-column exception is
      raised under the supported Streamlit version.
- [x] In the exercised Safety planning flow, confirm no nested-column exception
      or browser-console error remains after the callback fix.
- [ ] Add a local manual repair entry. Confirm Race control labels it as local,
      not historical evidence.
- [ ] For a historical source-limited critical record, confirm the replay
      wording says it only permits replay continuity and does not establish
      prototype readiness or release.
- [ ] Temporarily point a disposable copy at a malformed
      `data/safety_planning_assumptions.json`; confirm Safety planning shows a
      contained planner-unavailable message while the historical-evidence area
      remains visible. Restore the valid file immediately afterward.
- [x] Capture/compare historical sessions, standings, and incidents before and
      after funding a prototype plan. Confirm they are identical afterward.

Record the date, environment, and any failed item in the project’s round
history before the presentation. A failed browser check is a known limitation,
not a reason to remove the integrity disclosure.
