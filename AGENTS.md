# Instructions for AI agents working in this repository

This file is read by Cursor, GitHub Copilot, Claude Code and similar tools. It applies only when you
are asked to keep the lessons up to date. For any other task, follow the normal repository conventions.

## Repository facts

- `lessons.json` is the single content file. The Explorer, the tutor and `scripts/sync_docs.py` all read it.
  Keep its structure; do not add or rename fields.
- Atlas documents are confidential and read-only. Never copy long passages into lessons, never modify
  anything in the Atlas checkout, and never print secrets, tokens or connection strings.
- Do not commit, push, merge or open a pull request yourself unless the instruction says so.
  The automation or the maintainer does that after review.

## Task: sync lessons with changed Atlas documents

The Atlas checkout path is given in the instruction (for example `./atlas`). The drift report is
`sync/drift-report.md`; if it is missing or old, create it with
`python scripts/sync_docs.py --atlas "<atlas>" check` (exit 0 = nothing to do, 2 = lessons to review,
1 = error: report it and stop).

1. For each lesson listed in the report, read the listed sections in the Atlas documents, then the
   lesson in `lessons.json` (goals, `sources` and their `sections`, hook, points, diagram steps, quiz,
   prompts).
2. Edit only the statements those sections affect. Facts come only from the Atlas documents; where a
   section is unclear, keep or add the word "assumption". Keep each lesson's style, length and structure,
   and keep the quiz answerable from the lesson text (update it if its answer changed).
   - A section "no longer exists": find where the content moved and update that lesson's `sections`; if
     it was removed, report it instead of deleting teaching content.
   - Documents no lesson cites: list them and say which phase they belong in. Do not create lessons.
3. If you can run commands, run `python -m unittest discover -s tests` and fix failures you caused. (In the pipeline you cannot; it runs the tests itself afterwards and fails the run if they break.)
4. Finish with a short summary per lesson: what changed and which document section it came from.
5. If you can run commands and the Atlas documents are in a folder such as `./atlas`, finish with
   `python scripts/sync_docs.py --atlas atlas accept --lesson <ids you updated>` when lessons changed.
   If only docs files changed and no lessons need edits, use `python scripts/sync_docs.py --atlas atlas accept --files-only`.
   It records the new baseline inside your branch, so it takes effect only when a person reviews and merges the pull request.
   Never record a baseline from a local Atlas folder that has uncommitted changes.
