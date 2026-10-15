# Stage: qa

1. `python3 "$S/qa.py" <p>` - writes `qa/report.md`, exits 1 on any FAIL.
2. Fix each FAIL at its stage (with `redo` where needed), then re-run. SKIP lines say what could not
   be checked; WARN lines are for the creator to see, not to hide.
3. Your own read-through of `narration/narration.md` against the voice profile and the brief:
   does the first 15 seconds confirm the title, open a question, and prove the payoff exists?
   Is anything stated more strongly than `factcheck/claims.md` allows? Add your findings under
   a `## Reviewer notes` heading at the end of `qa/report.md`. Re-running `qa.py` replaces the
   table and keeps that section.
4. Mark `qa` done only when the last run is PASS (`state.py` enforces this).
