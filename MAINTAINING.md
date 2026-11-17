# Maintaining lessons

Maintainers only. Learners get updates automatically; the sync process never runs on their computers.

## Source and schedule

- `lessons.json` on GitHub's default branch is the source of truth. Stage work on `develop` and merge by pull request.
- The workflow fetches Atlas docs from `ATLAS_BRANCH` on every run. Leave it empty to use Atlas's default branch.
- `scripts/sync_docs.py check` compares document and section hashes with `sync/baseline.json`. The baseline covers every
  `docs/**/*.md` file and `AGENTS.md`, whether or not a lesson cites it. The report contains lesson ids, document paths
  and section headings, not document text. Exit codes: `0` nothing changed, `2` something changed, `1` error.
- **Any** change is drift (exit `2`), cited or not: a file created, renamed or deleted; a section added, renamed or
  removed; or text edited in any section. Whitespace and line-ending differences are ignored. A file moved to a new
  name is reported as renamed, not as one deletion plus one new file (also when it was edited at the same time, if
  most headings match), and a section renamed without a text change is reported as renamed.
- `drift-report.md` groups the findings: New / Renamed / Deleted Files; Added / Renamed / Removed Sections; Modified
  Sections (cited by a lesson, or not cited by any); and Lessons to review.
- `accept` records the baseline for **all** documents. `accept --drifted` records everything `check` flags (including
  uncited changes, new files, deleted files and items an agent judged irrelevant). `accept --lesson <ids>` records only
  the documents those lessons cite. `accept` refuses local Atlas docs with uncommitted changes or a commit that differs
  from the remote branch (`--allow-local` overrides this), and `--drifted` also refuses while a lesson still cites a
  document that no longer exists.

## Weekly sync

`.github/workflows/weekly-lesson-sync.yml` runs Mondays at 09:00 IST and on demand.

1. Fetch Atlas docs and check for drift. If nothing changed, stop.
2. With `COPILOT_GITHUB_TOKEN`, Copilot inspects every changed file and section in `atlas/` and triages each one (see
   [Editorial triage](#editorial-triage)). The workflow checks that only `lessons.json` changed (no change at all is
   fine), runs the tests, records the baseline for everything reviewed and opens a pull request. The pull request
   description is the drift report plus the agent's review summary (`sync/review-summary.md`).
3. After drift is detected, if the token is missing or the automatic update fails to produce a pull request, the workflow
   opens or updates one issue with the drift report and `/sync-lessons` instructions for Cursor. Fetch and drift-check
   errors fail the run without a fallback issue; inspect the Actions logs for those failures.
4. The Cursor command in `.cursor/commands/sync-lessons.md` follows the same triage, tests the result and records the
   baseline with `accept --drifted`. It exists only in this repository; setup does not copy it to learners.

## Editorial triage

Every item in the drift report gets exactly one outcome, and the agent lists all of them in its summary:

| Outcome | When | What the agent does |
|---|---|---|
| Relevant to an existing lesson | The change affects what a lesson teaches | Updates `points`, `viz`, `quiz`, `hook` or `goals`, and keeps `sources` current: adds new section names, updates renamed sections and moved file paths |
| New onboarding-worthy topic | A new document or major capability that helps a new joiner understand the architecture, workflows, services or code | Creates a complete lesson in the right phase (`desktop`, `eatlas`, `connect`, `services`, `code`) that passes `tests/test_lessons.py` |
| Not relevant | `Document status` edits, typos, formatting, housekeeping | Changes nothing in `lessons.json` and records the reason; the baseline still moves past it |

Reviewers: a pull request that changes only `sync/baseline.json` is normal when every item was skipped. Check the
review summary for the reasons, and look closely at any new lesson (facts must come from the documents).

## One-time baseline upgrade

Baselines recorded before this version track only the documents lessons cite. They keep working (cited documents are
still checked) but cannot see new, renamed or deleted documents, and the report says "Old baseline". Run **Weekly
lesson sync** once with `init_baseline` checked and merge its pull request to switch to full tracking; the first run
afterwards compares every document.

Both paths follow [AGENTS.md](./AGENTS.md). One bot branch, one open fallback issue and a concurrency lock prevent
overlapping runs. Changes reach the default branch only through a reviewed pull request.

## Learner updates

`setup.bat` records this clone's path in `<atlas>\.atlas-onboarding\.source-repo`. The Explorer launcher runs
`git pull --ff-only` and reruns setup when the clone changes. Offline or locally edited clones skip the update.
Cursor's `@atlas-onboarding` rule checks once per chat; Copilot users update through the launcher.

## One-time setup

1. Add GitHub Actions secrets:
   - `ATLAS_REPO_URL`: Bitbucket clone URL, such as `https://bitbucket.trimble.tools/scm/sp/atlas_v2.0.git`.
   - `BITBUCKET_READ_TOKEN`: read-only token. The legacy name `ATLAS_READ_TOKEN` also works.
   - `COPILOT_GITHUB_TOKEN` (optional): user-owned fine-grained token with the "Copilot Requests" permission.
     Classic tokens do not work. Remove it when its owner loses Copilot access; Cursor fallback will take over.
2. Set `ATLAS_BRANCH` to the Atlas branch to track, or leave it empty for the default branch.
3. Allow GitHub Actions to create pull requests. Create the `content-drift` issue label.
4. Protect the default branch: require a pull request, one approval and the `CI / unit-tests` check.
5. Merge the workflow and related files to the default branch.
6. Run **Weekly lesson sync** with `init_baseline` checked, then merge its baseline pull request.

## Verify the workflow

Run CI on a pull request and require **CI / unit-tests** to pass. Then run **Weekly lesson sync** with `init_baseline`
checked and merge its pull request. Run again without inputs; expect "In sync", no issue and no pull request.

To test drift handling, change one hash under `sections` in `sync/baseline.json` (a section no lesson cites works too),
or delete one document entry from `docs`, and run the workflow. With the token, expect a pull request (with only
`sync/baseline.json` changed if the agent skipped the item); without it, expect a "Lessons need review" issue. Close
test issues and pull requests, then restore the baseline.

## Security and limits

- Keep credentials in GitHub secrets and this repository private.
- Issues, reports and logs contain lesson ids, document paths and section headings only.
- Copilot receives Atlas document text. Get security approval before enabling it.
- GitHub-hosted runners may not reach internal Bitbucket. Use a self-hosted runner if needed.
