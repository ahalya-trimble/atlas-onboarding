# Getting started

One install gives you two things:

- **Atlas Explorer**, a visual guide with flow diagrams, walkthroughs, videos, quizzes and an offline "Ask the tutor" box.
- **ATLAS Tutor**, an agent in VS Code Copilot Chat (or `@atlas-onboarding` in Cursor) that answers questions from the real Atlas documents and source code.

Everything added to your Atlas checkout is untracked and Git-excluded, so product files are never changed.

## Contents

- [Before you start](#before-you-start)
- [Step 1. Get this repository](#step-1-get-this-repository)
- [Step 2. Install](#step-2-install)
- [Step 3. Use the visual guide](#step-3-use-the-visual-guide)
- [Step 4. Use the tutor](#step-4-use-the-tutor)
- [Optional: add screenshots](#optional-add-screenshots)
- [Update or remove](#update-or-remove)
- [Where your data is stored](#where-your-data-is-stored)
- [Troubleshooting](#troubleshooting)

## Before you start

| You need | How to check (PowerShell) |
|---|---|
| Git | `git --version` |
| Python 3.10 or newer | `python --version` |
| VS Code with GitHub Copilot (company-approved), or Cursor | The Copilot Chat icon is present |
| Your Atlas checkout (the folder containing `Atlas.sln`) | For example `C:\Users\<you>\Documents\atlas_v2.0` |

## Step 1. Get this repository

```powershell
git clone https://github.com/ahalya-trimble/atlas-onboarding.git
cd atlas-onboarding
```

Keep it **outside** the Atlas folder.

## Step 2. Install

Double-click `setup.bat` (it asks for your Atlas path), or pass the path:

```powershell
.\setup.bat "C:\Users\<you>\Documents\atlas_v2.0"
```

Setup checks Python and Git, installs the ATLAS Tutor agent, copies the guide to `<atlas>\.atlas-onboarding\explorer\`, creates `Open Atlas Explorer.bat` and opens the guide. Add `-Shortcut` to also create a desktop shortcut.

## Step 3. Use the visual guide

Double-click `<atlas>\.atlas-onboarding\Open Atlas Explorer.bat` and leave its window open. The guide runs at `http://localhost:8765`, only on your computer.

1. Enter your first name, role and experience. This sets your recommended path. Lessons with a blue bar are suggested for your role; all others stay available. Change it any time under **Edit my profile**.
2. Take the **guided tour** on first use (or later from the side menu).
3. In each lesson, watch the flow diagram, press **Play walkthrough**, read the key points and answer the quiz.
4. Watch the overview videos where a lesson asks for them (Atlas, eAtlas, architecture).
5. Click an **Ask next** prompt to copy it with your profile line, then paste it into ATLAS Tutor for a source-level answer.
6. Use **Ask the tutor** (bottom right) for a quick offline search of the guide and the Atlas documents.
7. Finish with **Save-state summary** and paste it into a tutor chat later to resume.

**Live documents.** Always start the guide with `Open Atlas Explorer.bat`, not by opening `index.html`. Each lesson links to the real Atlas documents it came from and shows a **Live from the Atlas docs** box with their current headings. If a document changed after you last reviewed it, the box says so and offers **Mark these documents as reviewed**. Only `docs/`, `AGENTS.md` and `README.md` can be opened; source code, configuration and key files cannot, and values that look like passwords or tokens are hidden.

## Step 4. Use the tutor

**VS Code**

1. Open the **Atlas folder** (File > Open Folder). If it was already open, reload the window (Ctrl+Shift+P, "Developer: Reload Window").
2. Open Copilot Chat and select **ATLAS Tutor** in the agent list.
3. Send `Hi`, or ask a question about Atlas or eAtlas.

**Cursor:** open the Atlas folder, open chat and type `@atlas-onboarding Hi`.

After each answer, pick a follow-up (Q1 to Q3) or ask your own. Say `Revisit my learnings` to recap earlier questions, or type `/quiz` for a short recall quiz on topics you discussed. Lessons and their quizzes live in the guide, not in the chat.

## Optional: add screenshots

Save a PNG in `explorer\assets\screens\` using the file names in that folder's README, then run `setup.bat` again. Screenshots already in the installed copy are kept.

## Update or remove

The guide updates itself: each time you open `Open Atlas Explorer.bat` it pulls this repository and re-runs setup if lessons changed. To update by hand, or to remove everything:

```powershell
git pull
.\setup.bat "C:\Users\<you>\Documents\atlas_v2.0"            # update
.\setup.bat "C:\Users\<you>\Documents\atlas_v2.0" -Remove    # uninstall (your progress is kept)
```

## Where your data is stored

| Data | Location | Notes |
|---|---|---|
| Explorer profile and progress | `.atlas-onboarding/state/explorer-progress.json` | Git-excluded and never sent anywhere. The browser keeps a backup copy. The tutor can read it but never writes to it. |
| Tutor summaries | `.onboarding/` in the Atlas folder | Created on first save. Unencrypted and not synced, so do not include credentials or personal details in questions. |

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` is not recognized | Install Python 3.10+ from python.org with "Add to PATH", then reopen the terminal. |
| "Refusing to overwrite" or "tracked file" | Something already exists at that path. The installer never overwrites files it does not own. Read the message for the path. |
| Agent missing in Copilot | Reload the VS Code window and reopen the Atlas folder. |
| Guide shows "lessons could not be loaded", or documents do not open | Start it with `Open Atlas Explorer.bat`, not by opening `index.html`. |
| "Port 8765 is already used" | The guide is already running (possibly for another Atlas folder). Close its window and start it again. |
| Diagrams look unstyled | Use the installed `explorer` folder with its `css` and `js` subfolders intact. Re-run `setup.bat` to restore it. |
| Video will not play | The recordings are on Google Drive and need your Trimble sign-in. Use "Open in Google Drive". |
| Tutor says **UNSAVED** | Saving was denied or unavailable (for example a workspace policy blocks writing the local SQLite file). The chat still works; ask a maintainer to permit the write if you want summaries kept. |

For maintainers: see [MAINTAINING.md](./MAINTAINING.md). For the full reference: [README.md](./README.md).
