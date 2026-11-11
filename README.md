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

- **One lesson list.** `curriculum.json` (lesson ids, order, source documents and sections,
  objectives, starter questions) is shared. The Explorer's `data.js` is generated from it, so the
  two cannot drift apart.
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
| `scripts/build_explorer.py` | Generates `explorer/js/data.js` from the two content files |
| `atlas-onboarding-local.agent.md`, `tutor.md`, `skills/quiz/SKILL.md` | The agent, its workflow and the quiz |
| `cursor/atlas-onboarding.mdc` | The Cursor rule |
| `curriculum.json` | Shared lesson list and source references |
| `content/lessons.json` | How the Explorer presents each lesson (text, diagrams, quiz, videos) |
| `explorer/` | The visual guide: `index.html`, `js/`, `css/`, `assets/`, and `server.py` |
| `tests/` | Installer, summary store, tutor text and alignment tests |

### Which parts need Python?

| Script | Needed for | If missing |
|---|---|---|
| `setup.ps1` | The one-step install (needs PowerShell, included in Windows) | Install by hand |
| `install.py` | Copying the agent files into Atlas safely | Copy the files yourself; you lose the safety checks |
| `onboarding.py` | Saving the tutor's summaries (and Revisit my learnings) | Tutor still answers, but nothing is saved |
| `explorer/server.py` | Opening real documents, live updates and saved progress in the guide | Guide still opens as a plain file with lessons and quizzes |
| `build_explorer.py` | Maintainers only, after editing content | Not needed by learners |

All scripts use only the Python standard library.

## What setup installs

All installed files are untracked and listed in Git's local `info/exclude`. Shared `.gitignore`,
existing agents and product files are never changed.

| Installed in the Atlas checkout | Purpose |
|---|---|
| `.github/agents/atlas-onboarding-local.agent.md` | The selectable ATLAS Tutor agent |
| `.github/skills/quiz/SKILL.md` | The `/quiz` skill |
| `.cursor/rules/atlas-onboarding.mdc` | The Cursor rule |
| `.atlas-onboarding/` | CLI, curriculum, workflow, manifest, the Explorer copy and its launcher |
| `.atlas-onboarding/state/` | Your Explorer progress and document-review baseline (created when used) |
| `.onboarding/` | The tutor's saved summaries (created on first save) |

`install.py` refuses tracked targets, unowned files, edited managed files, linked paths and
concurrent installs, verifies what it writes, and rolls back on filesystem errors.

Update: re-run `setup.bat` (it also stops any old Explorer server). Remove:
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

Edit `curriculum.json` (shared structure) or `content/lessons.json` (presentation), then run:

```powershell
python scripts\build_explorer.py
```

It stops with a clear message if a lesson exists on one side only. Never edit `explorer/js/data.js`
by hand; a test fails if it is out of date. Screenshots go in `explorer/assets/screens/` (names in
that folder's README).

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
