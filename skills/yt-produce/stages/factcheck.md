# Stage: factcheck

Goal: an independent check of every factual claim in `script/script.md` against
`research/sources.json`. The writer does not check its own work.

## Run it

Use the Agent tool with `subagent_type: "yt-fact-checker"` and this prompt (fill in the folder):

> Fact-check the project at <project folder>. Read script/script.md, research/sources.json and
> research/sources.md. Write factcheck/claims.json and factcheck/claims.md as your instructions
> describe. Report the counts by status and every claim that is not `supported`.

If the `yt-fact-checker` agent is not installed, use `subagent_type: "general-purpose"` and paste
the full body of `agents/yt-fact-checker.md` (from the skills repo) at the top of the prompt. It
must then write `"checked_by": "general-purpose:yt-fact-checker-instructions"`. Do not do the check
yourself in this context.

## After it reports

1. Run `python3 "$S/qa.py" <p> --gate factcheck`.
2. For each `unsupported` claim: cut it from the script, rewrite it to what the sources do support,
   or go back to `sources` for a real source. For `contested` / `partly_supported`: hedge in the
   script ("according to some accounts...", "one chronicler claims...") and say so in the note.
3. Any script change makes the fact-check stale (the gate compares file times). Re-run the agent on
   the revised script. Mark claims you cut as `removed` - do not delete them from the ledger.
4. When the gate passes, show the creator: counts by status, every hedged claim with its wording,
   and anything removed. Get the script approved, then mark the stage done.

Never edit a claim's status yourself to make the gate pass.
