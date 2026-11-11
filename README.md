# Atlas Onboarding

## 🧭 Atlas Explorer (visual onboarding app)

A visual, personalized study app for new teammates. **One-step install:** double-click `setup.bat`
(see [GETTING-STARTED.md](./GETTING-STARTED.md)). It installs the ATLAS Tutor agent and the guide into your
Atlas checkout. You can also open [explorer/index.html](./explorer/index.html) directly.

- 5 "islands": Atlas desktop -> eAtlas -> how they connect -> supporting services -> **source code** (unlocks last).
- Animated diagrams, clickable architecture map, mock Atlas window, cache-vs-server simulator.
- Mini-quizzes, XP/levels, glossary, copy-paste starter prompts for the Copilot tutor, and a **Save-state summary** export.
- Content is drawn from the Atlas repo docs; each lesson lists its source doc.
- Drop real screenshots into `explorer/assets/screens/` (names in that folder's README) and they appear in the lessons.

Lesson text lives in [explorer/js/data.js](./explorer/js/data.js); edit it to refine content.

**ATLAS Tutor** is a VS Code GitHub Copilot agent for learning Atlas and eAtlas.
It guides learners through repository-based explanations, suggests follow-up
questions, and saves learning progress so they can continue in a later chat.

This repository contains the tutor agent, a 30-topic curriculum (the topic list that
the agent and the visual guide share), an optional recall-quiz skill, the Atlas Explorer
visual guide, and Python scripts for installation and SQLite storage of saved summaries.

## What the tutor provides

The visual guide (Atlas Explorer) teaches the lessons and runs a quiz for each one. The
tutor does the live part: it answers questions from the current Atlas documents and
read-only source code.

- Source-grounded answers that cite document sections and code symbols, and mark assumptions.
- Follow-up questions (Q1-Q3) after each answer.
- Short saved summaries of what you asked, kept on your computer.
- **Revisit my learnings**: a read-only recap of your saved summaries, grouped by topic.
- An optional five-question `/quiz` that only asks about topics you discussed, using clickable answers.
- It can read your role and completed lessons from the visual guide's progress file, to skip basics.

The tutor reads product sources but does not modify or run product code.
Lessons are drafts requiring project-expert review; saved summaries record what was
discussed, not certification or proof of mastery.

## Curriculum

| Module | Focus |
|---|---|
| 1 | Product orientation |
| 2 | Atlas desktop essentials |
| 3 | Complete desktop repair journey |
| 4 | Remaining desktop capabilities and recovery |
| 5 | eAtlas essentials and desktop differences |
| 6 | eAtlas management, content, and administration |
| 7 | How desktop and eAtlas connect |
| 8 | Supporting services and background pipelines |
| 9 | End-to-end evidence-based investigation |

[curriculum.json](./curriculum.json) defines the lessons, starter questions,
objectives, prerequisites, and source references. Earlier modules and explicit
prerequisites determine which topic is eligible next. Source references must
be checked against the Atlas revision being used.

## Repository structure

| Path | Purpose |
|---|---|
| [atlas-onboarding-local.agent.md](./atlas-onboarding-local.agent.md) | ATLAS Tutor agent definition and activation boundaries |
| [tutor.md](./tutor.md) | Teaching workflow, saving rules, and CLI payloads |
| [curriculum.json](./curriculum.json) | Curriculum and repository source references |
| [skills/quiz/SKILL.md](./skills/quiz/SKILL.md) | Optional warm-up quiz workflow |
| [scripts/install.py](./scripts/install.py) | Install, update, and remove managed tutor files |
| [scripts/onboarding.py](./scripts/onboarding.py) | Validate and persist learner progress in SQLite |
| [tests/test_onboarding.py](./tests/test_onboarding.py) | Installer, curriculum, and progress-tracking tests |
| [VERSION](./VERSION) | Package version recorded during installation |

## Requirements

- Windows with Git and Python 3.10+.
- VS Code with company-approved GitHub Copilot access.
- An Atlas Git checkout with `Atlas.sln` at the repository root.
- Permission for the agent to read the checkout and execute the local Python CLI.

The Python scripts use only the standard library, including `sqlite3`.
If command execution is denied, tutoring can continue without saved progress.
Visual Studio and Cursor integrations are not included.

## Install

From a parent directory outside the Atlas checkout, clone this repository and
enter its folder:

```powershell
git clone https://github.com/ahalya-trimble/atlas-onboarding.git
Set-Location .\atlas-onboarding
```

Run the installer, replacing the example Atlas path with your checkout:

```powershell
python .\scripts\install.py install --atlas '<ATLAS_CHECKOUT_PATH>'
```

Replace `<ATLAS_CHECKOUT_PATH>` with the absolute path to your Atlas checkout.

The installer adds these files to the Atlas checkout:

| Installed path | Purpose |
|---|---|
| `.github/agents/atlas-onboarding-local.agent.md` | Selectable ATLAS Tutor agent |
| `.github/skills/quiz/SKILL.md` | Optional `/quiz` skill |
| `.atlas-onboarding/` | Python CLI, curriculum, workflow, version, and ownership manifest |

It also adds a managed block to Git's local `info/exclude` to exclude installed
files and learner data from ordinary commits. It does not modify the shared
`.gitignore`, existing agents, or product files.

The installer refuses tracked targets, existing unowned files, modified managed
files, linked paths, and concurrent installations. It verifies written content
and rolls back applied file changes on recoverable filesystem errors.
Installation is not transactional across power loss.

Existing workspace instructions still apply. If shared policy prohibits SQLite
onboarding writes, a maintainer must permit the workflow before installation.

## Start learning

1. Open the Atlas checkout in VS Code and reload the window if needed.
2. Select **ATLAS Tutor** in Copilot Chat.
3. Send `Hi` or ask a question.

The first response is a one-line welcome, the saving notice, and three sample questions.
Ask anything about Atlas or eAtlas. After each answer, suggested follow-ups appear as
Q1-Q3; they are chat suggestions, not quiz buttons.

| Message | Behavior |
|---|---|
| Your own question, or `Q1`-`Q3` | Answer from the current documents and code, then suggest follow-ups |
| `Revisit my learnings` | Recap the saved summaries by topic (read-only), then continue with Q&A |
| `Revisit <topic>` | Re-explain one earlier topic from the current sources (read-only) |
| `/quiz` | Five clickable questions about topics you discussed (not saved) |
| `Stop` | Stop tutoring without silently saving |

Select ATLAS Tutor before returning with `Hi` in a new chat. Selecting the agent alone does
not start a session. Switching to another agent ends the tutor workflow; ordinary
greetings under the default Agent must not activate it.

## Optional quiz

While ATLAS Tutor is selected, enter `/quiz`. It asks five clickable multiple-choice
questions about topics you previously discussed with the tutor (from the saved summaries).
Each correct answer earns one mark, with a final score of `X/5` and short explanations.
The Atlas Explorer already has a quiz for every lesson; this one only helps you remember
what you asked.

Quiz questions, answers and scores stay in chat and are never saved. The quiz requires a
supported structured question tool exposed by the host (`ask_user` or `vscode/askQuestions`,
including its runtime alias). If no supported tool or no discussed topic is available, it does
not start. It never substitutes typed A/B/C/D answers for clickable questions.

## Progress tracking

The tutor displays a saving notice before initializing storage or making the
first learner-data write in a conversation:

> Your learning progress and summaries are saved automatically on this computer
> so you can continue later. No name or email is required. Please do not share
> sensitive information.

Progress is stored at `.onboarding/onboarding.db` inside the Atlas checkout.
Reading progress alone does not create a database.

Each substantive answer saves a short session summary automatically. A welcome or sample
questions alone does not create one. Revisits remain read-only unless the learner
explicitly asks to save notes; quizzes never write progress.

| Table | Stored information |
|---|---|
| `learner` | Single-learner initialization, creation time, and write revision |
| `topics` | Current topic status, latest event, and curriculum evidence signature |
| `attempts` | Historical coverage and assessment records (no longer written by the tutor) |
| `sessions` | Append-only summaries, current topic, next step, and open questions |
| `reviews` | Historical review schedules retained for compatibility |

Writes validate prerequisites and source evidence, check the expected revision,
commit related progress changes together, and verify the saved payload.
Curriculum changes can invalidate completion eligibility without erasing history.
Curriculum signatures do not establish whether product sources are unchanged;
the tutor must inspect those sources again.

Use one learner per Atlas checkout. Data is unencrypted and does not synchronize
or back up automatically. Do not include credentials, employee identifiers,
customer information, or other sensitive content. Git exclusions prevent ordinary
accidental staging, not deliberate force-adding or filesystem access.

If saving fails, is denied, or is explicitly declined, the tutor reports
**UNSAVED** and continues chat-only without deleting existing records or claiming
cross-chat recall of unsaved work.

## Update or remove

From this repository's root, after updating the package checkout, update the
installed tutor using the same Atlas checkout path:

```powershell
python .\scripts\install.py update --atlas '<ATLAS_CHECKOUT_PATH>'
```

Remove the installed tutor:

```powershell
python .\scripts\install.py remove --atlas '<ATLAS_CHECKOUT_PATH>'
```

Update and removal verify manifest ownership hashes before changing managed
files. Edited or missing managed files require explicit reconciliation; there
is no force-overwrite option. Updates also support installations made before
the quiz skill was added.

Removal deletes unchanged managed files and their managed exclude block.
The installer never reads, changes, or deletes learner data. A separate local
`.onboarding/` exclusion remains to protect retained progress. Empty directories
may remain after removal.

## CLI reference

The tutor normally runs the CLI; learners do not need to prepare write payloads.
For troubleshooting, inspect progress without changing it:

```powershell
python 'C:\path\to\Atlas\.atlas-onboarding\onboarding.py' --atlas 'C:\path\to\Atlas' get-progress
python 'C:\path\to\Atlas\.atlas-onboarding\onboarding.py' --atlas 'C:\path\to\Atlas' next-topic
```

`init` creates storage after the saving notice, only when storage is missing.
`record-coverage` and `save-session` accept JSON through stdin.
`record-attempt` remains for historical compatibility, not ordinary teaching or
the optional quiz. Commands return JSON; errors use stderr and exit code 1.
See [tutor.md](./tutor.md#cli-use) for exact payloads and safe quoting.

## Validation

Run the test suite from this repository:

```powershell
python -m unittest discover -s tests -v
```

Tests use temporary Git repositories and SQLite databases, not learner records.
Before rollout, verify live VS Code agent and skill discovery, command approvals,
saving notices, automatic summaries, returning-learner welcome, Revisit my learnings,
and denied-write behavior. Check quiz buttons, scoring, cancellation, and that nothing
is saved during quizzes.
Automated tests do not prove live Copilot behavior.
