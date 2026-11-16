# Atlas Onboarding

Onboarding for new teammates on the ATLAS desktop app and the eAtlas web app. It has two
parts that work together and are installed with one command:

| Part | What it is for | Runs in |
|---|---|---|
| **Atlas Explorer** (visual guide) | The lessons: flow diagrams, animations, videos, a quiz for every lesson, a glossary, and the real Atlas documents opened live. | Your browser, served from your own computer |
| **ATLAS Tutor** (agent) | The live part: answers questions from the current Atlas documents and read-only source code, recaps what you asked before ("Revisit my learnings"), and runs an optional recall quiz. | VS Code Copilot Chat, or a Cursor rule |

The Explorer teaches and tests; the tutor answers. Nothing is taught twice.

## Quick start

1. Install Git, Python 3.10+ and (for the agent) VS Code with Copilot, or Cursor.
2. Clone this repository and double-click `setup.bat`. Or run it with your Atlas folder:

   ```powershell
   .\setup.bat "C:\path\to\atlas_v2.0"
   ```

3. Open the visual guide with `Open Atlas Explorer.bat` (inside `<atlas>\.atlas-onboarding\`).
4. Open the Atlas folder in VS Code, pick **ATLAS Tutor** in Copilot Chat and send `Hi`.
   In Cursor, type `@atlas-onboarding Hi`.

Step-by-step instructions with troubleshooting: [GETTING-STARTED.md](./GETTING-STARTED.md).

## How it fits together

- **One lesson file.** `lessons.json` holds every lesson once: its text, diagrams, quiz, and the Atlas
  documents and sections it came from. The Explorer, the tutor and the update checker all read this
  same file, so they cannot drift apart. There is no build step.
- **Live documents.** Every lesson links to the real Atlas documents it came from, shows their
  current headings, and warns when a document changed after you last reviewed it.
- **Shared progress.** The Explorer saves your role and progress in one local file. The tutor can
  read that file (read only) to skip lessons you finished. The tutor keeps its own short
  summaries of your questions in its own database. Neither writes to the other.

## What the tutor does

- Answers from the current documents and code, cites the section or symbol, and marks assumptions.
- Suggests follow-up questions (Q1-Q3) after each answer.
- **Revisit my learnings:** read-only recap of your saved summaries, grouped by topic.
- `/quiz`: five clickable questions about topics you discussed. Marks stay in chat and are never saved.
- Never modifies or runs product code. Answers are drafts for project-expert review, not certification.

| Message | Behavior |
|---|---|
| A question, or `Q1`-`Q3` | Answer, then suggest follow-ups |
| `Revisit my learnings` | Recap saved summaries, then continue with Q&A |
| `Revisit <topic>` | Re-explain one earlier topic from the current sources |
| `/quiz` | Recall quiz on topics you discussed |
| `Stop` | Stop without silently saving |

Select ATLAS Tutor before sending `Hi` in a new chat. Selecting the agent alone does nothing, and
switching to another agent ends the tutor workflow.

## Repository structure

| Path | Purpose |
|---|---|
| `setup.bat`, `scripts/setup.ps1` | One-step install, update and removal |
| `scripts/install.py` | Safe installer for the agent files (manifest, rollback, Git exclude) |
| `scripts/onboarding.py` | Saves the tutor's session summaries in a local SQLite file |
| `scripts/sync_docs.py`, `sync/`, `AGENTS.md`, `.github/`, `.cursor/commands/` | Weekly pipeline that finds lessons made stale by changed Atlas docs; Copilot updates them, with a Cursor `/sync-lessons` fallback (see MAINTAINING.md) |
| `scripts/open-explorer.bat` | The launcher installed as `Open Atlas Explorer.bat`; it pulls new lessons before starting |
| `atlas-onboarding-local.agent.md`, `tutor.md`, `skills/quiz/SKILL.md` | The agent, its workflow and the quiz |
| `cursor/atlas-onboarding.mdc` | The Cursor rule |
| `lessons.json` | The single lesson file (edit this to change content) |
| `explorer/` | The visual guide: `index.html`, `js/`, `css/`, `assets/`, and `server.py` |
| `tests/` | Installer, summary store, tutor text, lesson file and update-checker tests |

### Which parts need Python?

| Script | Needed for | If missing |
|---|---|---|
| `setup.ps1` | The one-step install (needs PowerShell, included in Windows) | Install by hand |
| `install.py` | Copying the agent files into Atlas safely | Copy the files yourself; you lose the safety checks |
| `onboarding.py` | Saving the tutor's summaries (and Revisit my learnings) | Tutor still answers, but nothing is saved |
| `explorer/server.py` | Serving the guide, opening real documents, live updates and saved progress | The guide cannot load; start it with `Open Atlas Explorer.bat` |

All scripts use only the Python standard library.

## What setup installs

All installed files are untracked and listed in Git's local `info/exclude`. Shared `.gitignore`,
existing agents and product files are never changed.

| Installed in the Atlas checkout | Purpose |
|---|---|
| `.github/agents/atlas-onboarding-local.agent.md` | The selectable ATLAS Tutor agent |
| `.github/skills/quiz/SKILL.md` | The `/quiz` skill |
| `.cursor/rules/atlas-onboarding.mdc` | The Cursor rule |
| `.atlas-onboarding/` | CLI, lesson file, workflow, manifest, the Explorer copy and its launcher |
| `.atlas-onboarding/state/` | Your Explorer progress and document-review baseline (created when used) |
| `.onboarding/` | The tutor's saved summaries (created on first save) |

`install.py` refuses tracked targets, unowned files, edited managed files, linked paths and
concurrent installs, verifies what it writes, and rolls back on filesystem errors.

Update: new lessons arrive by themselves whenever you open `Open Atlas Explorer.bat` (it pulls this repository and re-runs setup when something changed; Cursor does the same check in `@atlas-onboarding`). You can also re-run `setup.bat` (it also stops any old Explorer server). Remove:
`.\setup.bat "<atlas>" -Remove`. Your saved learning data is never deleted. Add `-Shortcut` to create a
desktop shortcut for the guide.

## Privacy and security

- The Explorer's server listens only on `127.0.0.1`, rejects other hosts and other websites, and
  makes no network calls and no AI calls.
- It can open only `docs/**` (Markdown or text), `AGENTS.md` and `README.md` from your Atlas folder.
  Source code, configuration and key files are refused. Values that look like passwords or tokens are
  hidden. No document text is stored in the browser.
- Saved summaries and progress are unencrypted, stay on your computer, are excluded from normal Git
  commits, and do not sync. Do not put credentials, employee or customer details in questions meant
  to be saved. Git excludes stop accidental staging, not deliberate force-adding.
- If saving is denied or declined, the tutor says **UNSAVED** and carries on in chat only.
- The tutor agent sends what it reads to your Copilot or Cursor model, as any IDE agent does.

## Maintaining the content

Edit `lessons.json` and run the tests (`python -m unittest discover -s tests`). The tests check that
every lesson has what the guide needs (sources, quiz, glossary terms, screenshots). There is nothing to
generate. Screenshots go in `explorer/assets/screens/` (names in that folder's README).

## Keeping lessons current

Handled by the maintainers through a pipeline and reviewed pull requests, never on a learner's computer. Learners just `git pull`. See [MAINTAINING.md](./MAINTAINING.md).

## CLI reference

The tutor runs this itself. For troubleshooting:

```powershell
python 'C:\path\to\Atlas\.atlas-onboarding\onboarding.py' --atlas 'C:\path\to\Atlas' get-progress
```

`init` creates storage once, after the saving notice. `save-session` takes one JSON object on stdin
(see [tutor.md](./tutor.md#cli-use)). Commands print JSON; errors go to stderr with exit code 1.

## Validation

```powershell
python -m unittest discover -s tests -v
```

Tests use temporary Git repositories and databases, never your records. Automated tests do not prove
live Copilot or Cursor behavior. Before a wider rollout, check in the real IDE: agent and skill
discovery, command approvals, the saving notice, summaries, Revisit my learnings, quiz buttons and
scoring, and denied-write behavior.
