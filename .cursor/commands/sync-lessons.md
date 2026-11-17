# Sync lessons with the Atlas documents

Maintainer command. Run it from the **atlas-onboarding** repository in Cursor (type `/sync-lessons`). It is
the fallback for the weekly GitHub workflow: use it when the workflow opened an issue "Lessons need review", or
whenever you want to refresh the lessons by hand. It lives in `.cursor/commands/` of this repository only; setup
never copies it into a learner's Atlas checkout.

Ask for the path of the local Atlas checkout (the folder with `Atlas.sln`) if you do not know it. Call it `<atlas>`.

1. **Update Atlas.** Run `git -C "<atlas>" pull --ff-only`. If it fails (local changes, diverged branch), stop and
   tell the user; do not try to fix the Atlas checkout and never change files in it.
2. **Find stale lessons.** Run `python scripts/sync_docs.py --atlas "<atlas>" check`.
   - Exit 0 ("In sync"): say so and stop.
   - Exit 1: show the message and stop (a missing baseline means the first baseline has not been recorded yet).
   - Exit 2: continue. The report is `sync/drift-report.md` (lesson ids, changed documents and section names).
3. **Update the lessons.** Read `AGENTS.md` and `MAINTAINING.md`. For each lesson in the report, open the changed
   sections in `<atlas>/docs/` and edit only the affected lessons in `lessons.json`, following the rules in
   `AGENTS.md` (facts only from the documents, mark unclear points "assumption", do not add fields, do not create new
   lessons for uncited documents; list them instead).
4. **Validate.** Run `python -m unittest discover -s tests -v`. Fix every failure you caused and run it again until
   all tests pass.
5. **Record the baseline.** Run `python scripts/sync_docs.py --atlas "<atlas>" accept --lesson <ids you updated>`.
   It refuses if the Atlas folder has uncommitted docs or is not at its remote commit; if so, report that instead
   of forcing it.
6. **Summarize** in a short list: per lesson, what changed and which document section it came from, plus anything
   you did not touch (uncited documents, removed sections). Say that the changes are ready to commit and open as a
   pull request. Do not commit or push unless the user asks.
