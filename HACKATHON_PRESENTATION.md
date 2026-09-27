# F1 Budget Allocator — Safety Reserve & Repair Readiness Planner

## Presentation status

This is the presentation and judging record for the Formula Tech Hacks
submission. Five independent Builder → Judge → Improve rounds were completed.
The **historical Round 5 score was 91 / 100**. Since that review, the planner
has received bounded historical-context handling, decision/ledger integrity
hardening, a two-case shared-resource check, and a passed current-build
Streamlit browser smoke test on a disposable database. Those post-Round-5
changes require a fresh independent score; they are not evidence for a
self-awarded 100. See [`UI_QA_CHECKLIST.md`](UI_QA_CHECKLIST.md) for the exact
browser path and the remaining manual checks.

### Submission focus

This submission claims exactly two categories:

- **Track 3 — Safety Fixing:** support a safer operational response by showing
  when a proposed repair response is under-resourced and must be held rather
  than locally funded.
- **Tangerine Track — Orange Flag:** make the financial trade-off visible when
  a team protects safety-readiness reserve while balancing its local season
  budget.

It does not claim any other hackathon track. In particular, it does not claim
real-time risk detection, safety-system stress testing, connected-device
capability, data-driven prediction, or AI capability.

## Elevator pitch — 30 seconds

Teams need to protect a finite racing budget while responding to damage. F1
Budget Allocator turns its locked 2025 replay into a Safety Reserve & Repair
Readiness Planner. A user can take an incident into a clearly labelled
prototype workflow, compare response choices against modelled cost, reserve,
parts, and time, and see an under-resourced plan blocked rather than quietly
accepted. It can also show when two fictional responses compete for one shared
resource envelope. It records a local review-handoff package and its local
budget impact; it does not send a request to a person. It never says a car is
safe to race.

## Problem → solution → demo

### The problem

A budget decision can conflict with repair readiness. A team needs a clear
record of what it can afford, what resources a proposed response consumes, and
when an option should stop for review rather than move forward on an
unsubstantiated assumption.

### The solution

The planner adds a separate prototype decision layer to the existing,
read-only 2025 replay. Its inputs are explicitly editable model assumptions;
they are not confidential team data, FIA figures, repair instructions, or a
vehicle-certification process. It is useful because it makes a resource
shortfall visible before a local budget commitment is recorded.

### Workflow diagram

```text
Incident or selected source reference
              ↓
Read-only historical evidence / source context
              ↓
Choose an editable prototype response profile and option
              ↓
Compare modelled cost, reserve, parts, time, transfer, and checklist actions
              ↓
       ┌──────┴───────────────────┐
       ↓                          ↓
  HOLD: structured gaps      REVIEW_ELIGIBLE:
  shown; local decision      modelled conditions are complete
  may be recorded
       ↓                          ↓
       └──────────→ Record an auditable local decision
                              ↓
                 Optional modelled local-ledger commitment
                              ↓
      REVIEW_REQUESTED: local funding/review-handoff record
                  (not sent review or vehicle release)
```

The optional **two-case shared-resource stress test** sits alongside this
single-case workflow. It aggregates two fictional entered options only once
against one editable pool of parts, work hours, reserve, transfer, funding
capacity, and cap headroom. Its result is either `RESOURCE HOLD` or
`RESOURCE FEASIBLE` for that modelled accounting envelope; it never creates a
decision, charge, review, or release.

The last state is deliberately **not** “approved,” “released,” or “safe to
race.” The system can block a modelled plan or record a local review-handoff
package; it does not contact a reviewer or replace engineering inspection,
regulatory approval, or race-team authority.

## What the app must demonstrate

For the presentation claims to be valid, the independent Judge should be able
to observe this end-to-end path:

1. Select a historical source reference or a clearly labelled prototype demo
   case without changing any historic result, standing, point total, incident,
   or source record.
2. Select a response profile and inspect its editable, non-verified
   assumptions for parts, cost, time, reserve floor, and required actions.
3. Compare at least two options, including their modelled resource use and
   blockers.
4. Demonstrate a **HOLD** result with an observable shortfall, such as zero
   available spares, no time remaining, insufficient transfer, or an incomplete
   checklist.
5. Demonstrate the two-case stress test: show that two independently plausible
   fictional options can become `RESOURCE HOLD` when the same shared envelope
   is too small, then show a contained envelope without claiming approval.
6. Demonstrate a separate **REVIEW_ELIGIBLE** result only after all modelled
   constraints and required checklist items are satisfied.
7. Record the outcome, then—only for an eligible option—show the optional
   modelled local-ledger commitment, its reserve/cap impact, and the Decision
   receipt. The resulting state is `REVIEW_REQUESTED`, meaning a local
   funding/review-handoff record exists; it is never a sent review, safety, or
   release verdict.
8. Return to the replay and verify that its historical points, classification,
   standings, and incident log have not changed.

## Live demo script

Use this as a click-by-click runbook. Match the bracketed labels to the final
UI if a label changes during implementation; do not improvise a claim that the
screen does not support.

### Before judges arrive

1. Start the local Streamlit app and open a saved demo replay with enough
   local reserve to show both a blocked and an eligible scenario.
2. Use a copied demo database by setting `F1_BUDGET_DB_PATH`; do not present
   against a user's live `f1_budget.db`. Keep a restorable copy of the catalog
   file as well.
3. Confirm the assumptions screen/file visibly says “editable,” “prototype,”
   and “not verified,” and that the current catalog fingerprint/version is
   visible. If it does not, stop and fix the label before presenting.
4. Prepare the **Show a spare-parts problem** and **Show a reviewable example** demo
   presets. Do not pre-record either as a real repair, FIA result, or safety
   approval.
5. Keep the historical standings screen available so it can be checked before
   and after the finance action.

### On-stage path

1. Open **Safety Control Room** and introduce it as a planning aid, not a car
   release system.
2. Open the **Prototype repair planner** section and select a source reference.
   State whether it is a read-only historical reference or a prototype demo
   case.
3. Open the selected response profile. Point to the editable model assumptions
   for cost, parts, time, reserve floor, and required checklist actions. Point
   to the catalog fingerprint and say it is a local reproducibility check, not
   source verification.
4. Select **Show a spare-parts problem** (or set **Spare parts available** to `0`). Show the
   comparison result and the structured conditions panel for the response
   option.
5. Show the **HOLD** state and read one concrete blocker aloud: for example,
   “This option consumes one spare, but the model currently has zero.” Record
   the held decision. This is the proof point: the app declines an
   under-resourced plan.
6. Open **Optional: can the team handle two issues at once?**. Click **Try a
   shared-resource conflict**, identify one shared shortfall, then click **Try
   a workable shared-resource example**. State: “This is an entered accounting envelope
   only; neither result creates a plan, charge, or release.”
7. Select **Show a reviewable example**, complete the required human-record
   checklist, and show `REVIEW_ELIGIBLE`.
8. Record the local decision. Open its **Decision receipt / reproducibility
   audit** and point out the preserved source context, frozen selected-profile
   basis, current-catalog check, decision-basis local consistency check, and
   local-only disclaimer.
9. If the app offers a modelled funding action, commit it once and show the new
   local-ledger entry, reserve effect, and cap effect. Describe this as a
   **local prototype budget commitment**, not an invoice or official cap
   calculation.
10. Show the record’s `REVIEW_REQUESTED` status. Say explicitly: “A human
   engineering review would still be required; this app has not sent a review
   request and does not authorize a car to race.”
11. Return to Race Control or the standings view. Show that the historic 2025
   outcome did not move when the local finance decision was recorded.

### Demo fallback

If a browser, local database, or Streamlit session fails, use a pre-captured
screen recording only if it visibly includes the same assumption labels,
catalog/receipt evidence, blocker, ledger effect, and non-release language.
State that it is a recording of a local prototype run against a disposable
database. Never replace an unavailable calculation with a verbal claim.

## Integrity and scope boundaries

| Boundary | What we say | What we do not say |
| --- | --- | --- |
| Historical replay | 2025 replay records remain read-only while local planning decisions are recorded separately. | A finance choice changes a race, points, positions, incidents, or standings. |
| Assumptions | Parts, duration, cost, reserve floor, and checklist items are editable prototype assumptions. | They are team inventory, invoices, FIA values, or validated engineering data. |
| Reproducibility | A record preserves app-preserved source context plus catalog/profile fingerprints and a local receipt. | The context/fingerprint is immutable external evidence, independently verifies a source, or proves a repair assumption. |
| Safety outcome | The workflow can issue `HOLD`, `REVIEW_ELIGIBLE`, or `REVIEW_REQUESTED`. | The car is safe, certified, approved, released, or legally/regulatorily compliant. |
| Review handoff | `REVIEW_REQUESTED` records a local funding and review-handoff package. | A human has been contacted, has reviewed it, or has approved it. |
| Finance | The displayed commitment is a local ledger/reserve/cap model for the app. | It calculates a real FIA cost-cap position or likely FIA sanction. |
| Intelligence | The prototype applies transparent rule checks to entered/modelled values. | It uses AI, predicts risk, forecasts accidents, or detects a live safety issue. |
| Connectivity | The core demo works from local bundled data and a local database. | It is live telemetry, a connected safety system, or real-time operational control. |

The existing CAD $215M cap and audit outcomes are local gameplay rules. They
may be described as “FIA-inspired” only when the local/gameplay qualification
is stated in the same sentence or immediately beside it.

## Anticipated Q&A

| Judge question | Prepared answer |
| --- | --- |
| Why this submission focus? | We focused on the decision point we can genuinely demonstrate: a repair-readiness response is blocked when its modelled resources do not support it, and its local budget consequence is visible. That is the practical link between Track 3 and Orange Flag. |
| Why not Track 1/2 or the other sponsor categories? | Those would require capabilities such as real-time detection, stress simulation, defensible risk analysis, live data, connectivity, or AI that this prototype does not have. We chose a focused, honest two-category submission rather than stretch the claim. |
| Is this based on official FIA rules? | No. The CAD $215M cap and the app’s audit rules are local gameplay mechanics labelled FIA-inspired, not an FIA compliance calculation. FIA cost-cap assessment and sanctions are case-specific; this app does not determine either. |
| Are the repair costs, times, parts, and checks real? | No. In the repair planner they are clearly labelled editable, non-verified prototype assumptions. They exist to make the decision logic demonstrable, not to represent a real team’s repair process. |
| Does `REVIEW_ELIGIBLE` mean the car can race? | No. It only means the entered model values and checklist satisfy the prototype’s local rules. A human engineering and safety process would still be required. `REVIEW_REQUESTED` is a local handoff record, not a sent review or release. |
| Does the receipt verify the incident or repair plan? | No. It packages app-preserved context, frozen local assumptions, ledger links, and checks so the prototype decision can be inspected. It does not independently validate external data or engineering work. |
| What is actually AI here? | Nothing yet, by design. The current prototype uses transparent local checks, which makes its limits easy to inspect. We will not claim AI until there is a defensible model and suitable data. |
| Does spending change the historic season? | No. The replay’s historical results and standings stay fixed. The interactive impact is limited to the local finance ledger, reserve, and audit presentation. |
| How does this help resource allocation? | It exposes the trade-off: committing a modelled repair response consumes local reserve/cap headroom, while declining or holding it records the shortfall rather than concealing it. |
| What would make it production-ready? | Reviewed inventory and cost data, validated engineering workflows, role-based approvals, governance, and formal safety/regulatory review. Those are future requirements, not claims about this prototype. |

## Seven-slide outline

1. **Problem — safety readiness has a budget trade-off.** Show one plain
   sentence: “What happens when a necessary response has insufficient reserve,
   parts, or time?”
2. **Reframe — from budget replay to repair-readiness planning.** Name only
   Track 3 and Tangerine/Orange Flag.
3. **Workflow.** Use the incident → evidence → compare → resources → hold or
   review-eligible → local decision/receipt → optional funding diagram above.
4. **Live demo.** Keep this slide minimal; use it as a title card while the
   product shows a concrete `HOLD` decision.
5. **Resource trade-off.** Show the local reserve/cap waterfall and ledger
   impact of an eligible modelled response, alongside the statement that
   historical results do not change.
6. **Integrity is a feature.** Display the editable-assumptions label, the
   receipt/frozen-basis evidence, and the explicit “not safe-to-race / not FIA
   compliance” boundary.
7. **Roadmap and ask.** Ask for feedback on the decision workflow and for
   access to reviewed data/process owners before any real-world use.

## Recommended five-minute timing budget

Adapt the numbers if the event gives a different slot; do not shorten the
blocker demonstration to make room for more slides.

| Time | Segment | Purpose |
| --- | --- | --- |
| 0:00–0:20 | Slides 1–2 | State the problem and focused submission. |
| 0:20–0:45 | Slide 3 | Explain the decision workflow and boundary. |
| 0:45–3:30 | Slide 4 + live app | Demonstrate `HOLD`, then `REVIEW_ELIGIBLE` and `REVIEW_REQUESTED`. |
| 3:30–4:00 | Slide 5 | Show the local reserve/cap trade-off and unchanged replay. |
| 4:00–4:30 | Slide 6 | State the integrity limits before judges have to ask. |
| 4:30–5:00 | Slide 7 | Roadmap, ask, and handoff to Q&A. |

The live product occupies 55% of this version of the pitch. If only three
minutes are available, keep the `HOLD` demonstration and remove detail from
the slide narration, not from the proof of a blocked decision.

## Judge-round history

The Builder must not fill this table from its own opinion. Enter a score only
after a separate Judge has exercised the workflow or inspected the exact code
path and recorded evidence. Complete at least five rounds and no more than
eight, following the project’s Build → Judge → Improve loop.

| Round | Score / 100 | Critical/High weaknesses found | Fixed this round | Notes / evidence link |
| --- | --- | --- | --- | --- |
| 1 | 45 | No concrete repair-planning workflow; historical repair state could be mistaken for readiness; no presentation package. | Added a separate, labelled prototype planner, explicit non-release boundaries, and this presentation package. | Independent code/product review. |
| 2 | 80 | Record creation trusted caller-supplied financial fields. | The engine now recalculates every decision from the selected profile, option, and live local-ledger facts. | Independent implementation review. |
| 3 | 88 | A non-UTF-8 or malformed assumptions file could crash the planner. | Assumption loading/validation is contained; the historical-evidence view continues with a clear error. | Independent robustness review. |
| 4 | 83 | A lower user-selected modelled funding capacity was lost on save, changing displayed `HOLD` to saved eligibility. | Lower modelled capacity now persists and is bounded by live capacity; accounting, reserve, future-car, and duplicate-funding findings were also fixed. | Independent workflow and accounting review. |
| 5 | 91 | None at Critical or High severity. | Stop condition met at that time; only disclosed Medium limitations remained. | Historical independent review: 29 automated tests, static compile, and diff checks passed. |
| 6 | Pending independent re-review | Not yet assessed. | Post-Round-5 hardening added bounded historical-context snapshots, catalog/profile fingerprints, decision/ledger consistency checks, duplicate-charge backstops, a two-case resource check, structured gaps, demo presets, resource waterfalls, and current-build browser smoke coverage. | A separate Judge must score the exact current code; the Builder must not assign this score. |
| 7–8 | Not used yet | — | — | Reserve for a further build/judge pass only if Round 6 finds material weaknesses. |

### Round 5 historical independent scorecard — not the current final score

This preserves the evidence-backed Round 5 result. It predates the
post-Round-5 hardening and browser pass, so it must not be relabelled as a new
final score or rounded up to 100.

| Rubric category | Available | Judge-verified score | Evidence |
| --- | ---: | ---: | --- |
| Track 3 — Safety Fixing core functionality | 30 | 27 | The planner demonstrated `HOLD` → option comparison → `REVIEW_ELIGIBLE` → local review-handoff record, while blocking inadequate modelled parts, time, reserve, funding, cap, or checklist conditions. |
| Tangerine — Orange Flag resource-allocation depth | 15 | 14 | Local reserve, cap headroom, current-season source capacity, and negative reprioritisation entries create a visible resource trade-off. |
| Integrity / honest scope | 20 | 20 | Historical replay data is isolated; inputs are labelled fictional/editable; the app makes no release, certification, FIA-compliance, AI, or prediction claim. |
| Technical robustness | 15 | 13 | 29 automated tests cover validation, malformed catalog containment, idempotency, accounting, historical isolation, and SQLite write locking. Browser-level Streamlit QA remains pending. |
| Presentation readiness | 20 | 17 | Pitch, demo path, Q&A, scope boundaries, and slide outline are complete; live UI QA remains pending. |
| **Total** | **100** | **91** | Historical Round 5 independent Judge round. |

### Post-Round-5 verification — not a score

- A recorded current backend run passed **56** tests, with `py_compile` and
  `git diff --check` also passing.
- A manual Streamlit 1.12 browser pass on a copied database completed the core
  `HOLD` → `REVIEW ELIGIBLE` → record/receipt → one funding action path; the
  receipt visibly reported an `OK` ledger-link check.
- The same pass compared the historical `career_sessions`,
  `career_standings`, and `career_incidents` tables before and after funding
  and found no changes.
- The receipt shows app-preserved source context, catalog/profile fingerprints,
  funding-time information, a local decision-basis consistency check, and
  linked local-ledger rows. A catalog change, unavailable catalog, legacy
  un-fingerprinted record, stale replay round, inconsistent historical context,
  or already-correlated local funding row holds a saved plan rather than
  silently funding it under a different basis.
- The current browser smoke test opened directly at Safety Control Room, tested
  the bounded historical launcher, and exercised both the `RESOURCE HOLD` and
  `RESOURCE FEASIBLE` two-case resource presets with no fresh console error.
- These are implementation and QA facts. They are not a replacement for the
  pending independent Round 6 assessment or a claim of a 100/100 score.

### Remaining disclosed limitations

- The core browser path and current two-case smoke path passed, but the broader
  manual regression, malformed-catalog, duplicate-action, transfer, and
  downloadable-artifact checks in
  [`UI_QA_CHECKLIST.md`](UI_QA_CHECKLIST.md) remain build-by-build demo
  safeguards rather than completed coverage claims.
- The catalog/profile fingerprint and app-preserved source context strengthen
  local reproducibility only. They do not independently verify a public source,
  real inventory, repair duration, cost, risk, or engineering conclusion.
- A catalog/rules change intentionally holds an existing record until it is
  re-recorded. That prevents silent reinterpretation, but a production system
  would still need controlled catalog governance and formal change approval.
- Every repair input and checklist confirmation remains a self-entered,
  editable prototype assumption. That is intentional and clearly disclosed;
  it prevents any real-world safety-authorisation claim.

### Verification record

The historical Round 5 independent review reported all of the following:

- 29 automated tests passed.
- `py_compile` passed for the application, engine, and tests.
- `git diff --check` passed.
- Funding preserves historical sessions, standings, and incident records;
  duplicate funding is prevented by SQLite write locking and idempotent ledger
  handling.

The post-Round-5 browser evidence is recorded separately in
[`UI_QA_CHECKLIST.md`](UI_QA_CHECKLIST.md). It used a disposable
`F1_BUDGET_DB_PATH` copy, not the user's simulation database.

## Final honesty check

Before presenting the project as complete, the independent Judge and Builder
must both be able to answer these in writing:

- [x] The historical Round 5 rubric score has evidence for every category.
- [ ] A fresh independent score has been recorded for the post-Round-5 changes;
      until then, neither the Builder nor this document claims 100/100.
- [x] Remaining Medium limitations are listed above rather than hidden.
- [x] A browser-visible core workflow was exercised on a disposable database;
      the exact passed path and remaining manual checks are in
      [`UI_QA_CHECKLIST.md`](UI_QA_CHECKLIST.md).
- [x] Automated and controlled browser verification showed historical points,
      positions, standings, and incident records remain unchanged.
- [x] Every on-stage claim maps to code, a tested path, or a disclosed limit.
- [x] Prototype inputs are labelled editable, non-verified assumptions.
- [x] Copy avoids vehicle-release, FIA-authority, certification, prediction,
      detection, live-data, AI, and excluded-track claims.
- [ ] Before presenting, back up the demo database and assumptions file and
      follow the recovery steps in the UI QA checklist.

If any answer is “no” or “not yet verified,” say so plainly, repair the issue
when feasible, or remove the related claim from the presentation. An honest
gap is more credible than an unsupported promise.
