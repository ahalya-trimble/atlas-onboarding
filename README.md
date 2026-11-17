# Atlas Onboarding

Onboarding for the ATLAS desktop app and eAtlas web app. One install provides:

| Tool | What it does | Runs in |
|---|---|---|
| **Atlas Explorer** (visual guide) | 26 lessons in five phases, each with a flow diagram, a step-by-step walkthrough, key points, a quiz and glossary terms. It also opens the real Atlas documents live. | Your browser, served from your own computer at `http://localhost:8765` |
| **ATLAS Tutor** (agent) | Answers questions from the current Atlas documents and read-only source code, recaps earlier questions ("Revisit my learnings") and offers an optional recall quiz (`/quiz`). | VS Code Copilot Chat, or a Cursor rule |

The Explorer teaches; the tutor answers.

## Contents

- [Quick start](#quick-start)
- [Atlas Explorer](#atlas-explorer)
- [ATLAS Tutor](#atlas-tutor)
- [How it fits together](#how-it-fits-together)
- [Repository structure](#repository-structure)
- [What setup installs](#what-setup-installs)
- [Privacy and security](#privacy-and-security)
- [Contributing and maintenance](#contributing-and-maintenance)
- [Validation](#validation)

## Quick start

You need Git, Python 3.10+, and VS Code with GitHub Copilot or Cursor.

1. Clone this repository **outside** your Atlas folder.
2. Double-click `setup.bat`, or pass your Atlas checkout (the folder that contains `Atlas.sln`):

   ```powershell
   .\setup.bat "C:\path\to\atlas_v2.0"
   ```

3. Open the visual guide with `Open Atlas Explorer.bat` (installed in `<atlas>\.atlas-onboarding\`).
4. Open the Atlas folder in VS Code, select **ATLAS Tutor** in Copilot Chat and send `Hi`.
   In Cursor, type `@atlas-onboarding Hi`.

See [GETTING-STARTED.md](./GETTING-STARTED.md) for detailed steps and troubleshooting.

## Atlas Explorer

Explore 26 lessons across five phases: Atlas Desktop, eAtlas Web, How Atlas Connects, Background Services and Source Code.
Lessons include role-based recommendations, walkthroughs, diagrams, screenshots, quizzes and a 23-term glossary.

The guide also provides videos, a guided tour, live Atlas document headings, offline search and exportable progress.
Open it with `Open Atlas Explorer.bat`; do not open `index.html` directly.

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
| `setup.bat`, `scripts/setup.ps1` | Install, update or remove the onboarding tools |
| `scripts/install.py` | Safely install managed files into Atlas |
| `scripts/onboarding.py` | Save and retrieve tutor summaries |
| `scripts/open-explorer.bat` | Update the clone and launch the guide |
| `scripts/sync_docs.py`, `sync/` | Detect any change in the Atlas docs (new, renamed or deleted files, sections added, renamed or removed, edited text) so an agent can review it and update, add or skip lessons |
| `lessons.json` | Lesson content |
| `explorer/` | Guide, server and assets |
| `tests/` | Automated tests |

All scripts use Python's standard library.

## What setup installs

Setup adds these untracked, Git-excluded paths to the Atlas checkout:

- `.github/agents/atlas-onboarding-local.agent.md` and `.github/skills/quiz/SKILL.md`
- `.cursor/rules/atlas-onboarding.mdc`
- `.atlas-onboarding/` with the guide, CLI, workflow, manifest and launcher
- `.atlas-onboarding/state/` for Explorer progress and document review
- `.onboarding/` for tutor summaries

The installer does not overwrite tracked or unmanaged files, and rolls back on errors.
Run `Open Atlas Explorer.bat` to update, or use `.\setup.bat "<atlas>" -Remove` to uninstall.
Saved learning data is not deleted. Add `-Shortcut` to create a desktop shortcut.

## Privacy and security

- The guide server listens only on `127.0.0.1`; it makes no network or AI calls.
- It opens only `docs/**`, `AGENTS.md` and `README.md` from Atlas. It refuses source code, configuration and key files,
  hides values that look like passwords or tokens, and stores no document text in the browser.
- Progress and summaries are unencrypted, stay on your computer and do not sync. Do not save credentials or personal
  details in tutor questions.
- The tutor sends the documents and code it reads to your Copilot or Cursor model.

## Contributing and maintenance

Edit `lessons.json` to change lesson content, then run the tests. They check lesson sources, quizzes, glossary terms and
screenshots. See [explorer/assets/screens/README.md](./explorer/assets/screens/README.md) for screenshot names.

The weekly sync pipeline checks lessons against Atlas documents and opens a reviewed pull request. It does not run on
learners' computers; learners get updates by reopening the guide or running `git pull`. See [MAINTAINING.md](./MAINTAINING.md).

## Validation

```powershell
python -m unittest discover -s tests -v
```

CI runs the same command on every pull request (`CI / unit-tests`). Tests use temporary Git repositories and
databases, never your records. They do not prove live Copilot or Cursor behaviour. Before a wider rollout,
check in the real IDE: agent and skill discovery, command approvals, the saving notice, summaries, Revisit my
learnings, quiz buttons and scoring, and denied-write behaviour.
