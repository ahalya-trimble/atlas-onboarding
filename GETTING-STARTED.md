# Getting started: from zero to learning Atlas

You get two things from one install:

- **ATLAS Tutor**, an agent in VS Code Copilot Chat. Ask it anything; it reads the real Atlas source and docs.
- **Cursor users:** setup also adds a Cursor rule. Open the Atlas folder in Cursor, open chat and type `@atlas-onboarding Hi`.
- **Atlas Explorer**, a visual guide with flow diagrams, animations, videos, quizzes and an offline "Ask the tutor" box.

Nothing here costs money or needs a server. Everything added to your Atlas checkout is untracked and git-excluded, so your product files are never changed.

## Before you start

| You need | Check it (PowerShell) |
|---|---|
| Git | `git --version` |
| Python 3.10 or newer | `python --version` |
| VS Code with GitHub Copilot (company-approved) | open VS Code, Copilot Chat icon is present |
| Your Atlas checkout (folder containing `Atlas.sln`) | e.g. `C:\Users\<you>\Documents\atlas_v2.0` |

## Step 1. Get this repository

```powershell
git clone https://github.com/ahalya-trimble/atlas-onboarding.git
cd atlas-onboarding
```

Put it anywhere **outside** the Atlas folder.

## Step 2. One-step install

Double-click `setup.bat` (it asks for your Atlas path), or pass the path:

```powershell
.\setup.bat "C:\Users\<you>\Documents\atlas_v2.0"
```

It checks Python and Git, installs the ATLAS Tutor agent, copies the visual guide into `<atlas>\.atlas-onboarding\explorer\`, creates `Open Atlas Explorer.bat`, and opens the guide.

## Step 3. Use the agent (ask questions)

1. Open the **Atlas folder** in VS Code (File > Open Folder). Reload the window if you had it open (Ctrl+Shift+P, "Developer: Reload Window").
2. Open Copilot Chat and pick **ATLAS Tutor** in the agent list.
3. Send `Hi`, or ask a question about Atlas or eAtlas.
4. After each answer pick a follow-up (Q1 to Q3) or ask your own. Say `Revisit my learnings` any time to recap what you asked before. Type `/quiz` for a quick recall quiz on those topics. The lessons and their quizzes are in the visual guide.

## Step 4. Use the visual guide

Double-click `<atlas>\.atlas-onboarding\Open Atlas Explorer.bat`.

1. Enter your first name and role. This sets your recommended path.
2. Follow the lessons: watch the flowchart, press **Play walkthrough**, read the highlighted key points, answer the quiz.
3. Watch the two overview videos where the lessons ask for them (Atlas overview, eAtlas overview).
4. Click **Ask next** prompts to copy them (they carry your profile line), then paste into ATLAS Tutor for a source-level answer.
5. Use **Ask the tutor** (bottom right) for a quick offline answer from the guide itself.
6. Finish with **Save-state summary** and paste it into the tutor chat tomorrow to resume.

## Step 5. Add your own screenshots (optional)

Save PNGs in `explorer\assets\screens\` with the file names in that folder's README, then re-run `setup.bat`. Screenshots already in the installed copy are kept.

## Update or remove

```powershell
git pull
.\setup.bat "C:\Users\<you>\Documents\atlas_v2.0"            # update
.\setup.bat "C:\Users\<you>\Documents\atlas_v2.0" -Remove    # uninstall (progress is kept)
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not recognized | Install Python 3.10+ from python.org with "Add to PATH", reopen the terminal. |
| "Refusing to overwrite / tracked file" | Something already exists at that path. The installer never overwrites files it does not own. |
| Agent missing in Copilot | Reload the VS Code window and reopen the Atlas folder. |
| Video will not play | The recordings are on Google Drive and need your Trimble access. Use "Open in Google Drive". |
| Shared policy forbids SQLite onboarding writes | A maintainer must permit it first; see README "Install". |

## Opening the source documents (live)

Start the guide with `Open Atlas Explorer.bat` (not by opening index.html). It runs a small server that listens only on your own computer. Then:

- Every document named under "Source-grounded in" is a link that opens the real file from your Atlas folder.
- Each lesson shows a "Live from the Atlas docs" box with the current headings. If a document changed after you last reviewed it, the box says so and offers "Mark these documents as reviewed".
- "Ask the tutor" also searches the Atlas docs and shows file paths and line numbers.
- Only `docs/`, `AGENTS.md` and `README.md` can be opened. Source code, config and key files cannot. Values that look like passwords or tokens are hidden. Nothing from the documents is stored in the browser, only your progress.

## Keeping the agent and the guide in step (for maintainers)

The agent and the guide share one lesson list.

- `curriculum.json` defines what the ATLAS Tutor teaches and checks: lesson ids, order, source documents and sections, objectives, starter questions and assessment questions.
- `content/lessons.json` holds how the guide presents each lesson: pictures, key points, quiz, videos.
- `explorer/js/data.js` is generated from both. Never edit it by hand. After changing either file run:

```
python scripts/build_explorer.py
```

The script stops with a clear message if a lesson exists on one side only. The test suite also fails if `data.js` is out of date.

## Progress storage

When you start the guide with `Open Atlas Explorer.bat`, your progress and profile are saved in `.atlas-onboarding/state/explorer-progress.json` on your computer (git-ignored, never sent anywhere). The browser keeps a backup copy.

- The ATLAS Tutor agent can read that file (read only) to adapt to your role and skip lessons you finished. It never writes to it. The agent keeps its own short summaries of your questions in its own database.
