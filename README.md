# Atlas Onboarding

Onboarding for new teammates on the ATLAS desktop app and the eAtlas web app. One command installs two
parts that work together:

| Part | Purpose | Runs in |
|---|---|---|
| **Atlas Explorer** (visual guide) | 26 lessons in five phases, each with a flow diagram, a step-by-step walkthrough, key points, a quiz and glossary terms. It also opens the real Atlas documents live. | Your browser, served from your own computer at `http://localhost:8765` |
| **ATLAS Tutor** (agent) | Answers questions from the current Atlas documents and read-only source code, recaps earlier questions ("Revisit my learnings") and offers an optional recall quiz (`/quiz`). | VS Code Copilot Chat, or a Cursor rule |

The Explorer teaches and tests; the tutor answers. Nothing is taught twice.

## Contents

- [Quick start](#quick-start)
- [Atlas Explorer](#atlas-explorer)
- [ATLAS Tutor](#atlas-tutor)
- [How it fits together](#how-it-fits-together)
- [Repository structure](#repository-structure)
  - [Which parts need Python?](#which-parts-need-python)
- [What setup installs](#what-setup-installs)
- [Privacy and security](#privacy-and-security)
- [Contributing and maintenance](#contributing-and-maintenance)
- [CLI reference](#cli-reference)
- [Validation](#validation)

## Quick start

**Prerequisites:** Git, Python 3.10 or newer, and (for the tutor) VS Code with GitHub Copilot, or Cursor.

1. Clone this repository **outside** your Atlas folder.
2. Double-click `setup.bat`, or pass your Atlas checkout (the folder that contains `Atlas.sln`):

   ```powershell
   .\setup.bat "C:\path\to\atlas_v2.0"
   ```

3. Open the visual guide with `Open Atlas Explorer.bat` (installed in `<atlas>\.atlas-onboarding\`).
4. Open the Atlas folder in VS Code, select **ATLAS Tutor** in Copilot Chat and send `Hi`.
   In Cursor, type `@atlas-onboarding Hi`.

Step-by-step instructions and troubleshooting: [GETTING-STARTED.md](./GETTING-STARTED.md).

## Atlas Explorer

- **Personalised path.** On first launch you enter a first name, role (service technician, service manager,
  developer, QA / tester, or support / operations) and experience level. Lessons suggested for your role are
  marked, and none are hidden.
- **Five phases.** Atlas Desktop, eAtlas Web, How Atlas Connects, Background Services, and Source Code.
- **Per lesson.** Flow diagram with **Play walkthrough**, highlighted key points, screenshots, a quiz and
  **Ask next** prompts that carry your profile line into the tutor.
- **Glossary** of 23 terms, a first-use **guided tour**, a light/dark theme and an in-app **Setup guide**.
- **Live documents.** Each lesson lists the Atlas documents it came from, shows their current headings and
  warns when one changed after you last reviewed it.
- **Ask the tutor** (bottom right). Offline search of the guide and the Atlas documents, with file paths and
  line numbers. For answers from live code, use the ATLAS Tutor agent.
- **Save-state summary.** Export your progress as Markdown and paste it into a tutor chat to resume later.

## ATLAS Tutor

- Answers from the current documents and code, cites the section or symbol, and marks assumptions.
- Suggests follow-up questions (Q1 to Q3) after each answer.
- **Revisit my learnings** gives a read-only recap of your saved summaries, grouped by topic.
- `/quiz` asks five clickable questions about topics you discussed. Marks stay in chat and are never saved.
- Never modifies or runs product code. Answers are drafts for project-expert review, not certification.

| Message | Behaviour |
|---|---|
| A question, or `Q1` to `Q3` | Answer, then suggest follow-ups |
| `Revisit my learnings` | Recap saved summaries, then continue with Q&A |
| `Revisit <topic>` | Re-explain one earlier topic from the current sources |
| `/quiz` | Recall quiz on topics you discussed |
| `Stop` | Stop without silently saving |

Select ATLAS Tutor before sending `Hi` in a new chat. Selecting the agent alone does nothing, and switching
to another agent ends the tutor workflow.

## How it fits together

- **One lesson file.** `lessons.json` holds every lesson once: text, diagrams, quiz, and the Atlas documents
  and sections it came from. The Explorer, the tutor and the update checker all read this file, so they
  cannot drift apart. There is no build step.
- **Shared progress.** The Explorer saves your profile and progress in one local file. The tutor can read it
  (read only) to skip lessons you finished. The tutor keeps its own short summaries in its own database.
  Neither writes to the other.
- **Automatic updates.** Opening `Open Atlas Explorer.bat` pulls this repository and re-runs setup when
  lessons changed. Maintainers keep lessons current through a pipeline and reviewed pull requests
  (see [MAINTAINING.md](./MAINTAINING.md)).

## Repository structure

| Path | Purpose |
|---|---|
| `setup.bat`, `scripts/setup.ps1` | One-step install, update and removal |
| `scripts/install.py` | Safe installer for the agent files (manifest, rollback, Git exclude) |
| `scripts/onboarding.py` | Saves the tutor's session summaries in a local SQLite file |
| `scripts/open-explorer.bat` | Launcher installed as `Open Atlas Explorer.bat`; pulls new lessons first |
| `scripts/sync_docs.py`, `sync/` | Detects lessons made stale by changed Atlas documents |
| `AGENTS.md`, `.github/`, `.cursor/commands/` | Weekly sync pipeline and maintainer agents (see MAINTAINING.md) |
| `atlas-onboarding-local.agent.md`, `tutor.md`, `skills/quiz/SKILL.md` | The tutor agent, its workflow and the quiz |
| `cursor/atlas-onboarding.mdc` | The Cursor rule |
| `lessons.json` | The single lesson file. Edit this to change content |
| `explorer/` | The visual guide: `index.html`, `js/`, `css/`, `assets/` and `server.py` |
| `tests/` | Installer, summary store, tutor text, lesson file, Explorer server and sync tests |

### Which parts need Python?

| Script | Needed for | If missing |
|---|---|---|
| `setup.ps1` | The one-step install (PowerShell ships with Windows) | Install by hand |
| `install.py` | Copying the agent files into Atlas safely | Copy the files yourself; you lose the safety checks |
| `onboarding.py` | Saving the tutor's summaries and Revisit my learnings | The tutor still answers, but nothing is saved |
| `explorer/server.py` | Serving the guide, opening documents, live updates, saved progress | The guide cannot load; start it with `Open Atlas Explorer.bat` |

All scripts use only the Python standard library.

## What setup installs

Installed files are untracked and listed in Git's local `info/exclude`. Shared `.gitignore`, existing agents
and product files are never changed.

| Installed in the Atlas checkout | Purpose |
|---|---|
| `.github/agents/atlas-onboarding-local.agent.md` | The selectable ATLAS Tutor agent |
| `.github/skills/quiz/SKILL.md` | The `/quiz` skill |
| `.cursor/rules/atlas-onboarding.mdc` | The Cursor rule |
| `.atlas-onboarding/` | CLI, lesson file, workflow, manifest, the Explorer copy and its launcher |
| `.atlas-onboarding/state/` | Your Explorer progress and document-review baseline (created when used) |
| `.onboarding/` | The tutor's saved summaries (created on first save) |

`install.py` refuses tracked targets, unowned files, edited managed files, linked paths and concurrent
installs, verifies what it writes, and rolls back on filesystem errors.

**Update:** run `Open Atlas Explorer.bat` (it pulls and re-runs setup when something changed), or run
`git pull` and `setup.bat` again. Cursor performs the same check in `@atlas-onboarding`.
**Remove:** `.\setup.bat "<atlas>" -Remove`. Saved learning data is never deleted.
**Shortcut:** add `-Shortcut` to create a desktop shortcut to the guide.

## Privacy and security

- The Explorer's server listens only on `127.0.0.1`, rejects other hosts and other websites, and makes no
  network or AI calls.
- It can open only `docs/**` (Markdown or text), `AGENTS.md` and `README.md` from your Atlas folder. Source
  code, configuration and key files are refused. Values that look like passwords or tokens are hidden. No
  document text is stored in the browser.
- Saved summaries and progress are unencrypted, stay on your computer, are excluded from normal Git commits
  and do not sync. Do not put credentials or employee or customer details in questions meant to be saved.
  Git excludes stop accidental staging, not deliberate force-adding.
- If saving is denied or declined, the tutor says **UNSAVED** and continues in chat only.
- The tutor agent sends what it reads to your Copilot or Cursor model, as any IDE agent does.

## Contributing and maintenance

- **Content.** Edit `lessons.json`, then run the tests. They check that every lesson has sources, a quiz,
  glossary terms and an existing screenshot. Screenshots live in `explorer/assets/screens/` (see that
  folder's [README](./explorer/assets/screens/README.md)).
- **Staying current.** A weekly pipeline compares the lessons with the Atlas documents and opens a reviewed
  pull request. It never runs on a learner's computer. Learners just `git pull` or reopen the guide.
  Details: [MAINTAINING.md](./MAINTAINING.md).

## CLI reference

The tutor runs this itself. For troubleshooting:

```powershell
python 'C:\path\to\Atlas\.atlas-onboarding\onboarding.py' --atlas 'C:\path\to\Atlas' get-progress
```

`init` creates storage once, after the saving notice. `save-session` takes one JSON object on stdin (see
[tutor.md](./tutor.md#cli-use)). Commands print JSON; errors go to stderr with exit code 1.

## Validation

```powershell
python -m unittest discover -s tests -v
```

CI runs the same command on every pull request (`CI / unit-tests`). Tests use temporary Git repositories and
databases, never your records. They do not prove live Copilot or Cursor behaviour. Before a wider rollout,
check in the real IDE: agent and skill discovery, command approvals, the saving notice, summaries, Revisit my
learnings, quiz buttons and scoring, and denied-write behaviour.
