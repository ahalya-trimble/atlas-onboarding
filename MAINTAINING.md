# Maintaining the lessons

For maintainers. Learners never run any of this; they get new lessons automatically (see "How learners get updates").

## The principle: GitHub is the source of truth, not anyone's laptop

- The lessons live in `lessons.json` on the **default branch of this repository on GitHub** (today `develop`).
- They are checked against the Atlas documents on a **remote Atlas branch** (variable `ATLAS_BRANCH`, for example
  `main` or `release/2.x`), fetched fresh by the pipeline on every run.
- `sync_docs.py` refuses to record a baseline from a local Atlas folder that has uncommitted docs or differs from its
  remote branch (override: `--allow-local`).

## Two modes, with automatic fallback

`.github/workflows/weekly-lesson-sync.yml` runs **every Monday at 09:00 IST** (`30 3 * * 1`) and on demand.

```
fetch Atlas docs (shallow, read-only)  ->  sync_docs.py check  ->  stale lessons?
   no  -> done, nothing is created
   yes -> PRIMARY, Copilot CLI (if COPILOT_GITHUB_TOKEN exists)
            Copilot edits lessons.json  ->  guard (only lessons.json changed)  ->  tests  ->  baseline moves
            ->  pull request
          FALLBACK, Cursor (no token, or Copilot / guard / tests / pull request did not succeed)
            ->  one issue listing the stale lessons and changed docs, with the instruction to run /sync-lessons
```

- The Copilot step has `continue-on-error`, so an expired or removed licence never breaks the workflow: the same
  run falls back to the issue. When a pull request is opened later, an old fallback issue is closed automatically.
- **Cursor fallback:** open this repository in Cursor and run `/sync-lessons`
  (`.cursor/commands/sync-lessons.md`). It pulls Atlas, runs the check, edits only the stale lessons, runs the tests,
  records the baseline and prints a summary ready to commit. That command exists only in this repository;
  `setup.bat` never copies it to a learner.
- Both modes follow the same rules in [AGENTS.md](./AGENTS.md).
- Zero conflicts: one bot branch (`bot/lesson-sync`) that is updated in place, one open issue at a time, a
  concurrency lock, and nothing reaches the default branch without a reviewed pull request.

## How learners get updates (no action needed)

1. `setup.bat` writes the path of the atlas-onboarding clone it was run from into
   `<atlas>\.atlas-onboarding\.source-repo` (inside the folder Git already excludes).
2. Double-clicking `Open Atlas Explorer.bat` first runs `git pull --ff-only` in that clone (silent; offline or local
   edits just skip it). If the commit changed, it silently re-runs `setup.bat` for that Atlas folder, then starts the guide.
3. In Cursor, the rule `@atlas-onboarding` does the same check once per chat before its first answer.
Copilot (VS Code) users get updates through the same launcher.

## One-time setup

1. **Secrets** (Settings, Secrets and variables, Actions):
   - `ATLAS_REPO_URL`, Bitbucket Server form `https://bitbucket.trimble.tools/scm/sp/atlas_v2.0.git`
   - `BITBUCKET_READ_TOKEN`, a read-only HTTP access token (the old name `ATLAS_READ_TOKEN` also works)
   - `COPILOT_GITHUB_TOKEN`, optional: a fine-grained token created by a person who has Copilot, with the account
     permission "Copilot Requests". It must be user-owned; classic tokens do not work. When the licence goes away,
     delete it; the fallback takes over.
2. **Variable** `ATLAS_BRANCH`: the Atlas branch the lessons track. Leave empty for the Atlas default branch.
3. Settings, Actions, General: allow GitHub Actions to create pull requests. Create the issue label `content-drift`.
4. Protect the default branch: pull request required, one approval, the `CI / test` check required.
5. Merge these files to the default branch (workflows appear in the Actions tab only from there).
6. Run **Weekly lesson sync** manually with *init_baseline* ticked, then merge the pull request it opens
   (`sync/baseline.json`).

## Test it on GitHub (beginner steps)

1. **CI.** Open a pull request into the default branch; **CI / test** must go green.
2. **Baseline.** Actions, **Weekly lesson sync**, Run workflow, tick *init_baseline*. Every step green; merge the pull
   request. Red *Fetch Atlas documents*: 401/403 token, "repository not found" missing `/scm/`, timeout GitHub cannot
   reach Bitbucket (use a self-hosted runner).
3. **In sync.** Run it again, nothing ticked: "In sync", no issue, no pull request.
4. **Fake a change.** Merge a change to `sync/baseline.json` that alters one letter of one hash under `sections`. Run again.
5. **Primary mode.** With `COPILOT_GITHUB_TOKEN` set, a pull request "Update lessons for changed Atlas documents" appears.
   Check that only `lessons.json` and `sync/baseline.json` changed.
6. **Fallback mode.** Delete the `COPILOT_GITHUB_TOKEN` secret (or break it), run again: a green run and an issue
   "Lessons need review" with the `/sync-lessons` instructions. Run `/sync-lessons` in Cursor to see it fix the lessons.
7. **Clean up.** Close fake pull requests and issues, and restore `sync/baseline.json`.

## Credentials and confidentiality

- Never put credentials in the repository, in chat or in workflow files. Use GitHub secrets.
- The lessons derive from confidential documents: keep this repository private. Logs, issues and reports contain only
  lesson ids, document paths and section headings.
- The Copilot step sends Atlas document text to GitHub's Copilot models. Get security approval first.

## The scripts

- `scripts/sync_docs.py check` compares the Atlas docs with `sync/baseline.json` (hashes only, no text).
  Exit 0 in sync, 2 lessons to review, 1 error. `accept [--lesson ID ... | --drifted]` records the docs as
  "the lessons match". The baseline notes the Atlas branch and commit it was taken from.
- `lessons.json` is the only content file. CI runs the tests that validate it.

## Not verified yet

The workflow has not run on GitHub, and the Copilot CLI flags follow GitHub's documentation without having been run here.
Do the first runs by hand and fix repository-specific details (clone URL form, runner, token scopes).
