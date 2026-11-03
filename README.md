# Atlas onboarding: optional local package

Private, local-only onboarding for an existing Atlas checkout. No MCP, cloud
deployment, database server, or third-party Python packages are required.

The package contains 25 draft lessons in nine modules, a Copilot tutor, validated
SQLite coverage tracking, and a reversible installer. Teaching uses starter
questions and explanations, without required quizzes or assessments. An optional
`/quiz` skill provides a five-question warm-up with fun marks. Project-expert review is
required before official use. The curriculum was copied from the current local
Atlas onboarding draft; it is not a verified match for every Atlas revision.

## Requirements

- Windows, Git, Python 3.10+, and VS Code with company-approved Copilot access.
- A local Atlas Git checkout containing root `Atlas.sln`.
- Permission for the tutor to run the local Python CLI. If execution is denied,
  teaching can continue without persistence.
- Company-approved private hosting and access controls before publishing this
  repository. No remote repository is created by these scripts.

## Install

Clone this package beside Atlas, not inside it. From PowerShell:

```powershell
python C:\atlas-onboarding\scripts\install.py install --atlas <project_directory>
```

The installer adds only:

- `.github/agents/atlas-onboarding-local.agent.md`: **ATLAS Tutor**.
- `.github/skills/quiz/SKILL.md`: user-triggered **/quiz** warm-up.
- `.atlas-onboarding/`: workflow, curriculum, CLI, package version, and ownership manifest.
- A managed block in Git's local `info/exclude`, including all `.onboarding/` data.

It does not change shared `.gitignore`, existing agents, or product files. It
refuses tracked targets, existing unowned files, modified managed files,
conflicting shared onboarding policies, linked paths, and concurrent installers.
File contents are read back before installation reports success. Recoverable
filesystem errors roll back files already changed; power loss is not transactional.

The installer does not change shared policy. A maintainer must explicitly allow
this optional SQLite workflow if existing instructions prohibit its local writes.
Merely adding a new agent cannot override higher-priority instructions.

After a successful installation, reload VS Code if needed, select **ATLAS Tutor**,
and say `Hi` or `Start ATLAS onboarding`. Selecting the agent alone does not
trigger a response. Returning learners can say `Hi` or `Continue` for a saved
recap and choices to continue, revisit a topic, or view progress.

Tutor behavior is limited to the explicitly selected **ATLAS Tutor** agent.
The default **Agent** should answer normally, including after switching away
from tutoring in the same chat. A greeting or attached curriculum does not
activate onboarding. Automatic invocation of the tutor by other agents is disabled.
The quiz checks the selected agent before reading the guide or learner data.
These are instruction boundaries, not filesystem access controls: other agents
can still inspect tutor files for an explicit coding or maintenance task.
If default Agent still starts onboarding after updating and starting a fresh
chat, check shared workspace/user instructions or other installed onboarding
agents for conflicting greeting rules; the installer does not change those files.

Say `Revisit` to get an explanation of what you have covered so far, followed
by key takeaways and an example for the most recently covered topic. Name a
topic to revisit it specifically. The tutor uses saved notes and current
sources, not just a "checkpoint verified" message. Revisit and its follow-up
questions do not save duplicate checkpoints or change your learning position.
Say `Continue` to return to the original unfinished topic. Revisit notes are
saved only if you explicitly request it, without changing that continuation point.

Choose a starter question to get an explanation, not a quiz. Say `Done` to mark
the explained topic covered and see the next starter, or `Next` to mark it
covered and continue to the next explanation. Covered does not mean assessed
or certified.

On their first visit, learners see "Welcome to ATLAS Tutor! Let's explore Atlas
step by step." followed immediately by **What you will learn** with an ASCII
syllabus tree showing all nine modules in learning order and their main topics.
The diagram works in plain chat without Mermaid rendering and appears before
the saving notice, product introduction, usage guide, and starter questions.
It is followed by **How to use this tutor**, which explains starter
questions, follow-up suggestions, Done/Next, saving progress, and returning
later. Say `Show syllabus` or `Help` to see these again without changing progress.
Returning learners see their saved recap rather than the full welcome.

`Show progress` lists covered topics, unfinished learning, and what comes next.
Legacy review schedules and "No reviews due" messages are not shown. Revisit
and `/quiz` remain optional and available without due dates; historical data
is preserved.

The complete welcome, diagram, and starter questions belong in the final visible
reply, not only inside VS Code's collapsed steps. Saving must not replace the
learning content with a status message. A welcome or starter menu alone does
not create a learning-session checkpoint; actual topic teaching does.

New learners then see a **Start here** list with three curriculum starter questions
(S1-S3), with the first recommended. Reply with a label or copy a question;
you do not need to know its answer. After each explanation or follow-up, the
tutor shows **You can ask next** with two or three specific question ideas
(Q1-Q3). Select one for more detail, or ask your own question. These are chat
suggestions, not quizzes or clickable UI buttons, and selecting one does not
mark a topic covered.

## Optional warm-up: /quiz

Select **ATLAS Tutor** and enter `/quiz` after covering a topic. It asks five
questions, one at a time, using clickable multiple-choice options. Questions
come only from verified previously covered material, not future topics.
Each correct answer earns one mark; the final score is shown as `X/5`.
Correct answers are spread across all four option positions, with one position
used twice and no adjacent repeats. The answer stays tied to its option text
when choices are reordered; the position plan is not shown to the learner.
Feedback explains each answer. This is just for fun, not an assessment of
employee performance or a requirement for continuing onboarding.

Scores, answers, and quiz explanations stay in chat and are not written to the
progress database. Coverage, existing notes, and your original continuation
point remain unchanged. You can stop anytime; an interrupted quiz shows only
the score out of answered questions, labelled incomplete.

The agent lists `ask_user` (the structured question form used by SDK hosts) and
VS Code's `vscode/askQuestions`. The quiz discovers the actual runtime tool and
uses its own input schema; listing names does not install or guarantee tools.
A missing VS Code tool does not prevent using an exposed `ask_user` form.
Host-supplied active ATLAS Tutor instructions establish activation; the model
does not need to see the agent picker. Merely reading the agent file does not
activate it. If neither question tool is exposed, the quiz explains the
limitation and does not start. Denied or failed calls are reported explicitly. It never
falls back to typed A/B/C/D or Markdown links pretending to be buttons.
If there is not enough verified covered material for five distinct questions,
the tutor suggests learning more first. Skill discovery and the question UI
must be checked in your VS Code session; static tests cannot prove them.
Skills are workspace-discoverable; invoking `/quiz` under another agent asks
you to select ATLAS Tutor first, without starting the quiz.

## Local learner data

The tutor shows a first-use notice instead of asking Track/Skip:

**"Your learning progress and summaries are saved automatically on this computer
so you can continue later. No name or email is required. Please do not share
sensitive information."**

Starting learning creates `.onboarding/onboarding.db` after the notice.
The tutor automatically saves detailed learning summaries, current topic,
next step, and requested open questions after explanations and follow-ups;
read-only revisits are excluded unless you ask to save notes, and optional
quizzes never write learner data. It does not save
an entire chat transcript. Existing records remain intact.
It records coverage only when you say `Done` or `Next`. You do not
need to request a save before switching agents. Denied or failed writes are
reported as UNSAVED, not remembered progress.

Reads alone create no file. Workspace policy and tool approvals still apply.
If saving is blocked or you explicitly ask not to save, learning continues in
chat without further writes or deletion of existing records. The same chat
can use its conversation context; reliable cross-chat recall of unsaved work
is unavailable. Learners do not need to open or edit the database.

The database contains:

| Table | Purpose |
|---|---|
| `learner` | Single-learner initialization marker, creation date, and optimistic revision; legacy `consent` field retained for compatibility, not evidence of an explicit agreement |
| `topics` | Topic status, coverage or historical assessment result, last event, and curriculum evidence signature |
| `attempts` | Coverage summaries, Done/Next confirmation, source paths/revision, and timestamp; historical assessments are retained |
| `sessions` | Append-only session summaries, current topic, next step, and open questions |
| `reviews` | Historical review schedules, retained for compatibility; no new quizzes are scheduled |

Curriculum JSON remains the only source of lesson definitions. The database
stores learner state, not a second editable curriculum. There is no numeric score,
AI grading, or employee evaluation. Coverage records learner-confirmed progress,
not proof of understanding. Assessment definitions and the old `record-attempt`
command remain only for compatibility with previous installations.

Coverage writes validate Done/Next confirmation, actual source paths, earlier
modules, and explicit prerequisites. Coverage events and progress commit together
without generating assessment answers or review schedules. Each write checks
the expected revision and reads back the
committed payload. An identical ID/payload retry is idempotent; a conflicting
retry or stale writer fails explicitly.

Local data is unencrypted and not synchronized or backed up automatically.
Git exclusion prevents ordinary accidental staging, not deliberate force-adding
or filesystem access. Do not store credentials, customer details, employee names,
or other sensitive information. Use one learner per checkout.

## CLI

The installed workflow in [tutor.md](./tutor.md) documents exact write payloads.
Commands return JSON; errors go to stderr with exit code 1.

```powershell
python C:\atlas_v2.0\.atlas-onboarding\onboarding.py --atlas C:\atlas_v2.0 get-progress
python C:\atlas_v2.0\.atlas-onboarding\onboarding.py --atlas C:\atlas_v2.0 next-topic
# After showing the saving notice, only when storage is missing:
python C:\atlas_v2.0\.atlas-onboarding\onboarding.py --atlas C:\atlas_v2.0 init
```

`record-coverage` and `save-session` accept JSON on stdin. The tutor uses these
commands; learners do not need to type payloads. Safe command quoting and explicit
execution permission remain necessary without MCP. No background process runs.
The old `init --consent` spelling is still accepted for compatibility but is
not required. Database schema and existing saved history are unchanged.

## Update and remove

Update the package checkout, then:

```powershell
python C:\atlas-onboarding\scripts\install.py update --atlas C:\atlas_v2.0
python C:\atlas-onboarding\scripts\install.py remove --atlas C:\atlas_v2.0
```

Updates verify ownership hashes before replacing managed files. They also
support installations made before the quiz skill was added.
The new skill is installed only if its path is untracked and unused; existing
unowned skills are never overwritten. Removal handles both installation layouts
and leaves learner data untouched. Curriculum
changes invalidate affected completion eligibility without erasing attempts.
Prerequisite invalidation propagates to dependent lesson eligibility. Product
source changes still require tutor inspection; curriculum signatures cannot
prove source freshness or deployed behavior.

Removal deletes only unchanged, manifest-owned files and the managed Git exclude
block. Learner data is never read, changed, or deleted by the installer. To keep
retained learner data private after removal, the installer retains a separate
local `.onboarding/` exclusion. Empty directories may remain.

If a managed file was edited, update/removal fails before changes. Preserve and
reconcile that file explicitly; there is no force-overwrite option. Unsupported
database versions also fail without resetting data.

## Validation

```powershell
Set-Location C:\atlas-onboarding
python -m unittest discover -s tests -v
```

Tests use isolated temporary Git repositories and SQLite databases, not actual
learner data. Before wider rollout, verify live agent discovery, safe CLI
execution, the saving notice, automatic initialization and checkpoints, denied
writes and explicit requests not to save, Done/Next
coverage, returning-learner recaps, and revisiting topics in
each supported IDE. For `/quiz`, check slash discovery, clickable options,
five-question scoring, cancellation, no-covered-topic behavior, and refusal
when the question tool is unavailable. Confirm the progress database is unchanged.
Static checks do not prove live Copilot behavior.
