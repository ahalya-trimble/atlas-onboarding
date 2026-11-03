# Atlas Onboarding

**ATLAS Tutor** is a VS Code GitHub Copilot agent for learning Atlas and eAtlas.
It guides learners through repository-based explanations, suggests follow-up
questions, and saves learning progress so they can continue in a later chat.

This repository contains the tutor agent, a 25-topic curriculum across nine
modules, an optional quiz skill, and Python scripts for installation and SQLite
progress tracking.

## What the tutor provides

- A syllabus covering Atlas desktop, eAtlas, connected products, and supporting services.
- Starter questions and explanations grounded in the Atlas checkout's documentation and source code.
- Follow-up questions for exploring each topic in more detail.
- Topic coverage recorded only after the learner says `Done` or `Next`.
- Saved learning summaries, unfinished topics, next steps, and open questions.
- Read-only revisits of previously covered material.
- An optional five-question `/quiz` warm-up using clickable answers.

The tutor reads product sources but does not modify or run product code.
Lessons are drafts requiring project-expert review; coverage records learning
activity, not certification or proof of mastery.

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
3. Send `Hi` or `Start ATLAS onboarding`.
4. Review the syllabus and choose a starter question.

The first response introduces the syllabus, explains saving, and offers three
starter questions labelled S1-S3. Choose a label or ask your own question; the
tutor explains the answer rather than asking you to answer it.

After an explanation, suggested follow-up questions appear as Q1-Q3. These
labels are chat suggestions, not quiz buttons, and do not mark a topic covered.

| Message | Behavior |
|---|---|
| `S1`, `Q1`, or your own question | Explain the selected topic or follow-up |
| `Done` | Mark the explained topic covered and offer the next starter |
| `Next` | Mark the explained topic covered and continue to the next explanation |
| `Continue` | Resume saved unfinished learning |
| `Show progress` | Show covered topics, unfinished learning, and the next eligible topic |
| `Revisit` or `Revisit <topic>` | Explain previously covered material without changing the continuation point |
| `Show syllabus` or `Help` | Show the learning outline or usage guide without advancing progress |
| `Stop onboarding` | Stop tutoring without inventing completion or silently saving |

Select ATLAS Tutor before returning with `Hi` or `Continue` in a new chat.
Selecting the agent alone does not start learning. Switching to another agent
ends the tutor workflow; ordinary greetings under the default Agent must not
activate onboarding.

## Optional quiz

While ATLAS Tutor is selected, enter `/quiz` after covering a topic.
The warm-up asks five questions from verified previously covered material,
using clickable multiple-choice answers. Each correct answer earns one mark,
with a final score of `X/5` and short explanations.

Quiz questions, answers, scores, and explanations stay in chat. They do not
change coverage, saved notes, or the original continuation point. Quizzes are
optional and never block learning.

The quiz requires a supported structured question tool exposed by the host
(`ask_user` or `vscode/askQuestions`, including its runtime alias).
If no supported tool or sufficient covered material is available, it does not
start. It never substitutes typed A/B/C/D answers for clickable questions.

## Progress tracking

The tutor displays a saving notice before initializing storage or making the
first learner-data write in a conversation:

> Your learning progress and summaries are saved automatically on this computer
> so you can continue later. No name or email is required. Please do not share
> sensitive information.

Progress is stored at `.onboarding/onboarding.db` inside the Atlas checkout.
Reading progress alone does not create a database.

Meaningful explanations and follow-ups save session summaries automatically.
A welcome or starter menu alone does not create a session checkpoint.
Coverage is recorded only after `Done` or `Next`. Revisits remain read-only
unless the learner explicitly asks to save notes; quizzes never write progress.

| Table | Stored information |
|---|---|
| `learner` | Single-learner initialization, creation time, and write revision |
| `topics` | Current topic status, latest event, and curriculum evidence signature |
| `attempts` | Coverage events and retained historical assessment records |
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
saving notices, automatic checkpoints, Done/Next coverage, returning-learner
recaps, read-only revisits, and denied-write behavior. Check quiz buttons,
scoring, cancellation, and unchanged progress during quizzes.
Automated tests do not prove live Copilot behavior.
