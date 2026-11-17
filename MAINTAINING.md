# Maintaining lessons

Maintainers only. Learners get updates automatically; the sync process never runs on their computers.

## Source and schedule

- `lessons.json` on GitHub's default branch is the source of truth. Stage work on `develop` and merge by pull request.
- The workflow fetches Atlas docs from `ATLAS_BRANCH` on every run. Leave it empty to use Atlas's default branch.
- `scripts/sync_docs.py check` compares document and section hashes with `sync/baseline.json`. The report contains
  lesson ids, document paths and section headings, not document text. Exit codes: `0` in sync, `2` drift found, `1` error.
- `accept` records the baseline. It refuses local Atlas docs with uncommitted changes or a commit that differs from
  the remote branch; `--allow-local` overrides this check.

## Weekly sync

`.github/workflows/weekly-lesson-sync.yml` runs Mondays at 09:00 IST and on demand.

1. Fetch Atlas docs and check for drift. If lessons are current, stop.
2. With `COPILOT_GITHUB_TOKEN`, Copilot edits only stale lessons in `lessons.json`. The workflow checks the diff, runs
   tests, records the baseline and opens a pull request.
3. If the token is missing or any step fails, the workflow opens or updates one issue with the drift report and
   instructions to run `/sync-lessons` in Cursor.
4. The Cursor command in `.cursor/commands/sync-lessons.md` updates only stale lessons, tests them and records the
   baseline. It exists only in this repository; setup does not copy it to learners.

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

To test drift handling, change one hash under `sections` in `sync/baseline.json` and run the workflow. With the token,
expect a lessons pull request; without it, expect a "Lessons need review" issue. Close test issues and pull requests,
then restore the baseline.

## Security and limits

- Keep credentials in GitHub secrets and this repository private.
- Issues, reports and logs contain lesson ids, document paths and section headings only.
- Copilot receives Atlas document text. Get security approval before enabling it.
- GitHub-hosted runners may not reach internal Bitbucket. Use a self-hosted runner if needed.
