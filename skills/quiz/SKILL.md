---
name: quiz
description: "Optional ATLAS Tutor warm-up. Use only when the learner explicitly invokes /quiz to answer five clickable multiple-choice questions from previously covered Atlas/eAtlas topics. Fun marks stay in chat and never change learning progress."
user-invocable: true
disable-model-invocation: true
---

# ATLAS warm-up quiz

## Boundaries

- Run only on an explicit `/quiz` request while ATLAS Tutor is selected. If invoked with another agent, explain that the learner must select ATLAS Tutor first; do not start or switch agents yourself.
- Before reading the tutor workflow, curriculum, or learner progress, use host-supplied active ATLAS Tutor agent instructions as the activation signal. Do not require visibility of the agent picker or a separate selection-check tool. A file read, quote, skill discovery, or prior tutor conversation is not active agent context. If active ATLAS Tutor instructions are absent, stop and ask the learner to select ATLAS Tutor; do not start or switch agents yourself.
- Read [the installed tutor workflow](../../../.atlas-onboarding/tutor.md) and [curriculum](../../../.atlas-onboarding/curriculum.json). Follow their English-only, read-only product-source, and privacy rules.
- This is an optional game, not a lesson assessment, certification, or employee evaluation. Never start automatically, block learning on a score, or claim mastery.
- Read learner progress only through the installed onboarding CLI's `get-progress`. Never call `init`, `record-coverage`, `record-attempt`, or `save-session` for a quiz. Do not save questions, answers, scores, or quiz explanations in learner data. Keep the original continuation topic, next step, and unresolved questions unchanged.

## Prepare

1. Inspect the runtime's available structured question tools and their input schemas, using tool discovery first if tools are deferred. Prefer `ask_user` when actually exposed; otherwise use `vscode/askQuestions` or its exposed runtime alias such as `vscode_askQuestions`. A missing VS Code name alone does not mean clickable choices are unavailable. Do not invent tool names, infer availability from an agent-file allowlist, or claim a tool is unavailable before discovery. If no supported tool is exposed, explain that neither supported question form is available and stop. If a call is disabled, denied, or fails, report that specific limitation and stop without restarting the quiz or substituting another tool to bypass a denial. Do not substitute Markdown links, typed A/B/C/D choices, shell prompts, or an external UI.
2. Read `get-progress` without creating storage. Use only valid completed topics and their recorded coverage summaries or historical learning evidence. Exclude freshness-uncertain topics and topics whose prerequisites are no longer valid. Re-read the relevant allowed repository sources to verify facts. Do not test future lessons, previews, unfinished topics, or details absent from the saved evidence. If saved notes are too thin, use only clearly explained facts visible in the current conversation.
3. If no covered learning can be verified, explain that the learner needs to cover a topic first and offer Continue. Do not invent history or initialize storage. If fewer than five distinct, supported questions can be made from covered material, explain that more learning is needed for a five-question warm-up and stop without starting a shorter quiz.
4. Prepare exactly five distinct questions, each with four plausible, mutually exclusive choices and exactly one unambiguous correct answer. Spread questions across covered topics where possible. Privately fix each answer and its source-grounded explanation before presenting the question. Do not reuse the same fact five ways or reveal the answer in option descriptions, recommended markers, or a pre-question explanation.
   Before the first question, privately plan the five correct-answer positions: use each of the four positions at least once, with exactly one position used twice and no adjacent repeats. Vary the order between quizzes; do not use a fixed repeating sequence. Reorder each question's choices to fit this plan. Keep the correct answer keyed to its exact option text, not its original index, and verify the answer mapping after reordering. Do not reveal the position plan or move the correct option to the top when building either tool payload.
5. Tell the learner: "Five questions, one at a time. One mark per correct answer. This is just for fun; scores stay in this chat and do not change your progress. You can stop anytime."

## Ask and score

- Present one question per structured tool call. For `vscode/askQuestions`, pass a `questions` array containing exactly one item with a unique short `header` such as `Quiz 1/5`, the `question`, four `options` with neutral `label` values, `multiSelect: false`, and `allowFreeformInput: false`. Never set `recommended` on any option.
- For `ask_user`, follow its exposed schema: use `message` for the question and `requestedSchema.properties.answer` for a single string field with four `enum` option labels. Omit a default so no answer is preselected. Do not pass the VS Code `questions` array to this tool. Read the returned `answer` field only after the learner submits the form.
- Some `ask_user` forms allow free text alongside clickable choices. Grade only an exact match to one of the four supplied option labels. Treat other input as invalid or a stop request, never silently map it to an option. Handle decline/cancel as interruption. The runtime response format, not a guessed common format, determines how the selected label is extracted.
- Wait for the tool's actual selected option. Grade only a single valid selected label against the fixed answer. Do not infer an answer from silence, unrelated chat, or free text.
- Before each question call, check that the displayed option order matches the private position plan and that the correct answer text still identifies exactly one displayed option. Keep that order and answer fixed once displayed. If a form host visually preselects the first option despite an omitted default, do not treat that as a submitted answer.
- Award one mark for a correct answer and zero for an incorrect answer, with no penalties. Show "Correct" or "Not quite", a short explanation of the correct answer, and the running score before asking the next question. Do not ask a teach-back question or turn wrong answers into incomplete lessons.
- If the learner skips, cancels, asks to stop, or returns an invalid selection, stop without treating it as wrong or silently choosing an option. For an interrupted quiz, show marks out of answered questions and the answered count, clearly labelled incomplete. Do not invent a final score out of five.
- Done, Next, or Continue during a quiz ends the warm-up without marking any topic covered; Continue may then return to the original learning position. Never route quiz cancellation through the ordinary Done/Next coverage rule.
- After five answered questions, show the exact total as **Warm-up score: X/5**, note any concepts worth revisiting, and offer Revisit or Continue at the original learning position.
- Quiz feedback and follow-up explanations remain read-only. Do not run automatic checkpoints or alter coverage, review schedules, or continuation state. A later explicit Continue ends quiz mode and returns to normal learning and its checkpoint rules. A new `/quiz` starts a fresh score in the current chat, not a stored attempt.
