# Sync lessons with the Atlas documents

Maintainer command. Run it from the **atlas-onboarding** repository in Cursor (type `/sync-lessons`). It is
the fallback for the weekly GitHub workflow: use it when the workflow opened an issue "Lessons need review", or
whenever you want to refresh the lessons by hand. It lives in `.cursor/commands/` of this repository only; setup
never copies it into a learner's Atlas checkout.

Ask for the path of the local Atlas checkout (the folder with `Atlas.sln`) if you do not know it. Call it `<atlas>`.

1. **Update Atlas.** Run `git -C "<atlas>" pull --ff-only`. If it fails (local changes, diverged branch), stop and
   tell the user; do not try to fix the Atlas checkout and never change files in it.
2. **Find what changed.** Run `python scripts/sync_docs.py --atlas "<atlas>" check`. Any documentation change counts:
   a file created, renamed or deleted, a section added, renamed or removed, or text changed in any section, whether
   or not a lesson cites it.
   - Exit 0 ("In sync"): say so and stop.
   - Exit 1: show the message and stop (a missing baseline means the first baseline has not been recorded yet).
   - Exit 2: continue. The report is `sync/drift-report.md` (paths, section headings and lesson ids), grouped as
     New / Renamed / Deleted Files, Added / Renamed / Removed Sections, Modified Sections (cited or not) and
     Lessons to review.
3. **Review every item.** Read `AGENTS.md` and `MAINTAINING.md`. For each item in the report, open the changed file
   or section in `<atlas>/docs/` and triage it, following `AGENTS.md`:
   - **Relevant to an existing lesson:** edit that lesson in `lessons.json` (points, viz, quiz, hook, goals) and
     update its `sources`: add new section names, replace renamed sections and moved file paths.
   - **New onboarding-worthy topic or document:** create a complete new lesson in `lessons.json` under the right
     phase (`desktop`, `eatlas`, `connect`, `services` or `code`), using the checklist in `AGENTS.md`.
   - **Not relevant** (Document status edits, typos, housekeeping): change nothing and note why.
   Facts come only from the documents; mark unclear points "assumption"; do not add fields.
4. **Validate.** Run `python -m unittest discover -s tests -v`. Fix every failure you caused and run it again until
   all tests pass.
5. **Record the baseline.** Run `python scripts/sync_docs.py --atlas "<atlas>" accept --drifted`. It records every
   reviewed item, including the ones you skipped, new files and deleted files, so they are not reported again.
   It refuses if the Atlas folder has uncommitted docs or is not at its remote commit, or while a lesson still
   cites a missing document; if so, report that instead of forcing it.
6. **Summarize** in a short list with one line for every item in the report: which lesson you updated (and what
   changed), which new lesson you created, or why you skipped it. Say that the changes are ready to commit and open
   as a pull request. Do not commit or push unless the user asks.
