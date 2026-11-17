# Instructions for AI agents working in this repository

This file is read by Cursor, GitHub Copilot, Claude Code and similar tools. It applies only when you
are asked to keep the lessons up to date. For any other task, follow the normal repository conventions.

## Repository facts

- `lessons.json` is the single content file. The Explorer, the tutor and `scripts/sync_docs.py` all read it.
  Do not add or rename fields: a new lesson uses exactly the fields an existing lesson has.
- Atlas documents are confidential and read-only. Never copy long passages into lessons, never modify
  anything in the Atlas checkout, and never print secrets, tokens or connection strings.
- Do not commit, push, merge or open a pull request yourself unless the instruction says so.
  The automation or the maintainer does that after review.

## Task: sync lessons with changed Atlas documents

The Atlas checkout path is given in the instruction (for example `./atlas`). The drift report is
`sync/drift-report.md`; if it is missing or old, create it with
`python scripts/sync_docs.py --atlas "<atlas>" check` (exit 0 = nothing changed, 2 = something changed and
needs review, 1 = error: report it and stop).

**Any** documentation change is drift, whether or not a lesson cites it: a file created, renamed or deleted
(anywhere under `docs/`, or `AGENTS.md`), a section added, renamed or removed, or text changed in any section.
Whitespace-only differences are never reported. The report lists them in these groups:

- **New / Renamed / Deleted Files**
- **Added / Renamed / Removed Sections**
- **Modified Sections**, split into *Cited by a lesson* and *Not cited by any lesson*
- **Lessons to review**: lessons whose cited documents or sections changed, with the reason

### 1. Inspect every item

For each item in the report, open the file or section named in it under the Atlas checkout and read what
changed. The report names paths and headings only; the facts are in the documents. Do not guess from the
heading alone.

### 2. Triage each item (exactly one outcome per item)

**A. Relevant to an existing lesson.** The change affects something an existing lesson teaches (the lesson
cites that section, or the topic clearly belongs to it).
- Edit only the statements the change affects: `points`, `viz`, `quiz`, `hook`, `goals`, `prompts`.
  Keep the lesson's style, length and structure, and keep the quiz answerable from the lesson text (update
  the quiz if its answer changed).
- Keep the lesson's `sources` correct, because they decide what is tracked next time:
  - a section was **added** that the lesson now teaches: add its name to that source's `sections`;
  - a section was **renamed**: replace the old name with the new one;
  - a section was **removed**: drop it from `sections`. If the content moved elsewhere, cite the new place;
  - a document was **renamed or moved**: change the `path` to the new path (keep the same `sections`);
  - a document was **deleted** and its content now lives in another document: point the source there.
    If the content is gone and the lesson has other sources, remove this source and fix the lesson text.
    If it was the lesson's only source and nothing replaces it, stop and report it: do not leave a lesson
    citing a missing document, because the baseline cannot move past it.
- A lesson that cites a whole document (empty `sections`) needs no section edits, only a fact check.

**B. New onboarding-worthy topic or new document.** A new document, or a major new capability, that a new
joiner needs to understand Atlas's architecture, workflows, services or code, and that no existing lesson
covers. Create a **complete** new lesson in `lessons.json` (see "New lesson checklist").
Prefer extending an existing lesson (outcome A) when the topic is a small addition to one.

**C. Not relevant to onboarding.** For example a `Document status` or review-date edit, a typo or formatting
fix, a link or table-of-contents change, renumbering, or other housekeeping. Do **not** add anything to
`lessons.json` for these. Record the item and the reason in your summary (see step 4). The baseline still
moves past it once the tests pass, so it is not reported again.

When unsure between B and C, choose C and say what would change your mind; a maintainer decides in review.

### 3. New lesson checklist

The tests in `tests/test_lessons.py` enforce these rules; run them after editing.

- `id`: lowercase letters, digits and hyphens only (at most 64), and unique. Insert the lesson after the
  last existing lesson of its phase.
- `phase`: one of `desktop`, `eatlas`, `connect`, `services`, `code` (see `phases` in `lessons.json`).
- `title`, `tag`, `hook`, `icon`: short text; the hook is one or two sentences a newcomer understands.
- `goals`: a list of what the learner can do afterwards.
- `sources`: a list of `{"path": "...", "sections": ["...", ...]}`. Paths start with `docs/`, `AGENTS.md` or
  `README.md`. List the exact section headings the lesson was written from, so later changes to them are
  tracked. Use an empty `sections` list only when the lesson really covers the whole document.
- `points`: key facts from the documents, each marked "assumption" where the documents are unclear.
- `terms`: every term must exist in the top-level `glossary`; add a one-sentence glossary entry for new ones.
- `viz`: copy the shape of an existing diagram (`steps`, `compare`, `cards`, `flowchart`, `tree`, `timeline`,
  `mock`, `arch` or `datasource`) from a similar lesson; do not invent new types.
- `quiz`: `{"q": ..., "o": [at least two options], "a": index of the correct option, "why": ...}`, answerable
  from the lesson text.
- `prompts`: starter questions the learner can ask the tutor.
- `shot` and `video`: leave them out unless the file or video key already exists. Never reference a missing file.

### 4. Finish

1. If you can run commands, run `python -m unittest discover -s tests -v` and fix failures you caused. (In the
   pipeline you can run only this command; it runs the tests again afterwards and fails the run if they break.)
2. Write `sync/review-summary.md` (or print the same text if you cannot write files): one line **per item in
   the report**, so nothing is silently dropped.
   - `path` / section: **updated lesson `<id>`** (what changed), or **new lesson `<id>`**, or
     **skipped**: and the reason (for example "only the Document status line changed").
   The pipeline appends this file to the pull request description. It must contain paths, headings and
   lesson ids only, never document text.
3. If you can run commands and the Atlas documents are in a folder such as `./atlas`, finish with
   `python scripts/sync_docs.py --atlas atlas accept --drifted`. It records the new baseline for **every** reviewed
   item (cited or not, including the ones you skipped, new files and deleted files) inside your branch, so it
   takes effect only when a person reviews and merges the pull request. It refuses while a lesson still cites a
   missing document. Never record a baseline from a local Atlas folder that has uncommitted changes.
