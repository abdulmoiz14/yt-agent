# Stage: handoff

Goal: everything the creator needs to upload, in one file, waiting for their decision.
This stage never uploads, schedules or publishes, and never opens YouTube Studio.

## `publish/upload-pack.md`

Start with this banner, verbatim:

> NOT UPLOADED. Nothing in this pack has been uploaded, scheduled or published. You do that
> yourself in YouTube Studio once you approve it.

Then, each in a fenced block they can copy:

1. Title (`package/chosen-title.txt`) and thumbnail text + brief.
2. Description (`seo/description.md`), with the chapters marked provisional until the post-recording
   chapters exist.
3. Tags (`seo/tags.txt`).
4. Sources for the description: the sources the video relies on, from `research/sources.md`.
5. Pinned-comment suggestion, if useful.

Then, outside the blocks:

- QA result and every WARN/SKIP from `qa/report.md`.
- Stages that were `unavailable` or `skipped`, and what that means for this video.
- Post-recording stages still to do (`state.py next <p> --post`).

## Then

`state.py set <p> handoff awaiting_approval`. Show the creator the pack and ask:
**ship it, or change it?**

- Change: go to the stage that owns it, redo, re-run `qa`, rebuild the pack.
- Explicit approval in their own words: `state.py set <p> handoff approved --user-statement "<verbatim>"`.
  Tell them the pack is final and that they upload it. You do not.
