import contextlib
import copy
import importlib.util
import io
import json
import sqlite3
import subprocess
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


database = load("onboarding")
installer = load("install")


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="atlas-onboarding-test-")
        self.addCleanup(self.temporary.cleanup)
        self.atlas = Path(self.temporary.name)
        (self.atlas / "Atlas.sln").write_text("test solution", encoding="ascii")
        subprocess.run(["git", "init", "-q", str(self.atlas)], check=True, capture_output=True)
        self.exclude = self.atlas / ".git" / "info" / "exclude"
        self.exclude.write_bytes(b"# Existing private excludes\n/local-only.txt\n")
        self.original_exclude = self.exclude.read_bytes()
        curriculum = json.loads((ROOT / "curriculum.json").read_text(encoding="utf-8-sig"))
        for lesson in curriculum["lessons"]:
            for source in lesson["sources"]:
                path = self.atlas / source["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Fixture documentation\n", encoding="ascii")
        self.curriculum_path = ROOT / "curriculum.json"

    def install(self):
        return installer.install(self.atlas, "install")

    def store(self):
        return database.Store(self.atlas, self.curriculum_path)

    def init_store(self):
        self.install()
        store = self.store()
        store.initialize()
        return store

    def attempt(self, store, topic=None, **changes):
        lesson = store.lessons[topic or next(iter(store.lessons))]
        revision = store.progress()["revision"]
        payload = {
            "id": f"attempt-{revision}",
            "expectedRevision": revision,
            "topicId": lesson["id"],
            "questionId": lesson["assessment"]["id"],
            "question": lesson["assessment"]["question"],
            "answer": "Original learner answer",
            "kind": "teach_back",
            "assistance": "none",
            "result": "demonstrated",
            "correctConcepts": lesson["assessment"]["requiredConcepts"].copy(),
            "missingConcepts": [],
            "misconceptions": [],
            "feedback": "All required concepts demonstrated.",
            "sourcePaths": [source["path"] for source in lesson["sources"]],
            "sourceRevision": None,
        }
        payload.update(changes)
        return payload

    def save_attempt(self, store, **changes):
        payload = self.attempt(store, **changes)
        store.write("record-attempt", payload)
        return payload


class InstallerTests(Fixture):
    def test_install_update_remove_preserves_progress_and_existing_files(self):
        old_agent = self.atlas / ".github" / "agents" / "atlas-tutor.agent.md"
        old_agent.parent.mkdir(parents=True)
        old_agent.write_text("Existing legacy tutor", encoding="ascii")
        self.assertTrue(self.install()["verified"])
        store = self.store()
        store.initialize()
        self.save_attempt(store)
        before = store.path.read_bytes()
        self.assertTrue(installer.install(self.atlas, "update")["verified"])
        self.assertEqual(before, store.path.read_bytes())
        self.assertTrue(installer.install(self.atlas, "remove")["verified"])
        self.assertEqual(before, store.path.read_bytes())
        self.assertEqual("Existing legacy tutor", old_agent.read_text())
        self.assertTrue(self.exclude.read_bytes().startswith(self.original_exclude))
        self.assertNotIn(b"# BEGIN atlas-onboarding", self.exclude.read_bytes())
        self.assertIn(b"/.onboarding/", self.exclude.read_bytes())
        for relative in installer.FILES:
            self.assertFalse((self.atlas / relative).exists())
        ignored = subprocess.run(
            ["git", "-C", str(self.atlas), "check-ignore", "-q",
             ".onboarding/onboarding.db"], capture_output=True)
        self.assertEqual(0, ignored.returncode)

    def test_existing_unowned_file_is_not_overwritten(self):
        path = self.atlas / ".atlas-onboarding" / "tutor.md"
        path.parent.mkdir()
        path.write_text("mine")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.install()
        self.assertEqual("mine", path.read_text())
        self.assertEqual(self.original_exclude, self.exclude.read_bytes())

    def test_modified_managed_file_blocks_update_and_remove(self):
        self.install()
        path = self.atlas / ".atlas-onboarding" / "tutor.md"
        path.write_text("local edit")
        for action in ("update", "remove"):
            with self.assertRaisesRegex(ValueError, "changed or missing"):
                installer.install(self.atlas, action)
        self.assertEqual("local edit", path.read_text())

    def test_edit_after_ownership_check_is_not_overwritten(self):
        self.install()
        path = self.atlas / ".atlas-onboarding" / "onboarding.py"
        original_digest = installer.digest
        modified = False

        def edit_after_hash(content):
            nonlocal modified
            value = original_digest(content)
            if not modified:
                modified = True
                path.write_bytes(b"Concurrent user edit")
            return value

        with patch.object(installer, "digest", edit_after_hash):
            with self.assertRaisesRegex(ValueError, "changed during installation"):
                installer.install(self.atlas, "update")
        self.assertEqual(b"Concurrent user edit", path.read_bytes())

    def test_tracked_target_is_not_modified(self):
        path = self.atlas / ".atlas-onboarding" / "tutor.md"
        path.parent.mkdir()
        path.write_text("tracked")
        subprocess.run(["git", "-C", str(self.atlas), "add", "."], check=True, capture_output=True)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "tracked file"):
            self.install()
        self.assertEqual(self.original_exclude, self.exclude.read_bytes())

    def test_conflicting_shared_policy_blocks_install(self):
        path = self.atlas / ".github" / "copilot-instructions.md"
        path.parent.mkdir()
        path.write_text("The only permitted onboarding writes are `.onboarding/progress.json`.")
        with self.assertRaisesRegex(ValueError, "restricts onboarding to JSON"):
            self.install()
        self.assertFalse((self.atlas / ".atlas-onboarding").exists())
        self.assertEqual(self.original_exclude, self.exclude.read_bytes())

    def test_tampered_manifest_cannot_delete_arbitrary_file(self):
        self.install()
        path = self.atlas / installer.MANIFEST
        data = json.loads(path.read_text())
        data["files"]["Atlas.sln"] = installer.digest(b"test solution")
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "manifest"):
            installer.install(self.atlas, "remove")
        self.assertTrue((self.atlas / "Atlas.sln").is_file())

    def test_install_rolls_back_on_io_failure(self):
        original = Path.write_bytes
        fail_path = self.atlas / ".atlas-onboarding" / "tutor.md"

        def fail_once(path, content):
            if path == fail_path and content is not None:
                raise OSError("fixture disk failure")
            return original(path, content)

        with patch.object(Path, "write_bytes", fail_once):
            with self.assertRaisesRegex(OSError, "fixture disk failure"):
                self.install()
        self.assertEqual(self.original_exclude, self.exclude.read_bytes())
        self.assertFalse((self.atlas / installer.MANIFEST).exists())
        for relative in installer.FILES:
            self.assertFalse((self.atlas / relative).exists())
        self.assertFalse((self.exclude.parent / "atlas-onboarding.lock").exists())

    def test_duplicate_install_and_missing_removal_fail(self):
        with self.assertRaisesRegex(ValueError, "No managed"):
            installer.install(self.atlas, "remove")
        self.install()
        with self.assertRaisesRegex(ValueError, "Already installed"):
            self.install()

    def test_existing_installer_lock_is_preserved(self):
        lock = self.exclude.parent / "atlas-onboarding.lock"
        lock.write_text("another installer")
        with self.assertRaisesRegex(ValueError, "Another installer"):
            self.install()
        self.assertEqual("another installer", lock.read_text())
        self.assertFalse((self.atlas / installer.MANIFEST).exists())

    def test_modified_exclude_block_blocks_removal(self):
        self.install()
        modified = self.exclude.read_bytes().replace(b"# END atlas-onboarding", b"# Edited END")
        self.exclude.write_bytes(modified)
        with self.assertRaisesRegex(ValueError, "exclude block changed"):
            installer.install(self.atlas, "remove")
        self.assertEqual(modified, self.exclude.read_bytes())
        self.assertTrue((self.atlas / installer.MANIFEST).is_file())

    def test_reinstall_after_removal_retains_privacy(self):
        self.install()
        installer.install(self.atlas, "remove")
        self.install()
        self.assertEqual(1, self.exclude.read_bytes().count(b"# BEGIN atlas-onboarding"))
        installer.install(self.atlas, "remove")
        self.assertEqual(1, self.exclude.read_bytes().count(b"# Retained private Atlas"))

    def test_installed_cli_and_agent_links_are_valid(self):
        self.install()
        script = self.atlas / ".atlas-onboarding" / "onboarding.py"
        result = subprocess.run(
            [sys_executable(), str(script), "--atlas", str(self.atlas), "get-progress"],
            capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(json.loads(result.stdout)["saved"])
        agent = (self.atlas / ".github" / "agents" /
                 "atlas-onboarding-local.agent.md").read_text()
        self.assertTrue(agent.startswith("---\n"))
        self.assertIn("name: ATLAS Tutor\n", agent)
        self.assertIn("description:", agent)

        for relative in ("tutor.md", "curriculum.json"):
            self.assertTrue((self.atlas / ".github" / "agents" /
                             ".." / ".." / ".atlas-onboarding" / relative).is_file())

    def test_tutor_activation_is_limited_to_explicit_current_selection(self):
        self.install()
        agent = (self.atlas / ".github" / "agents" /
                 "atlas-onboarding-local.agent.md").read_text()
        workflow = (self.atlas / ".atlas-onboarding" / "tutor.md").read_text()
        quiz = (self.atlas / ".github" / "skills" / "quiz" / "SKILL.md").read_text()
        header = agent.split("---", 2)[1]
        self.assertIn("user-invocable: true", header)
        self.assertIn("disable-model-invocation: true", header)
        self.assertLess(agent.index("## Activation boundary"), agent.index("Before teaching"))
        self.assertIn("previous tutor messages are history, not active rules", agent)
        self.assertIn("Active agent instructions are sufficient evidence", agent)
        self.assertIn("not when it is merely read as a file", agent)
        self.assertIn("This document is not a workspace-wide instruction", workflow)
        self.assertIn("Respond normally to the user's actual task", workflow)
        self.assertIn("even in the same conversation", workflow)
        self.assertIn("Before reading the tutor workflow, curriculum, or learner progress", quiz)
        self.assertIn("If active ATLAS Tutor instructions are absent, stop", quiz)
        self.assertNotIn("If selection is unknown", quiz)

    def test_installed_tutor_is_english_only(self):
        self.install()
        agent = (self.atlas / ".github" / "agents" /
                 "atlas-onboarding-local.agent.md").read_text()
        workflow = (self.atlas / ".atlas-onboarding" / "tutor.md").read_text()
        self.assertIn("Use English only in every learner-facing response", agent)
        self.assertIn("Use English only in every learner-facing response", workflow)

    def test_installed_tutor_uses_starters_and_automatic_checkpoints(self):
        self.install()
        agent = (self.atlas / ".github" / "agents" /
                 "atlas-onboarding-local.agent.md").read_text()
        workflow = (self.atlas / ".atlas-onboarding" / "tutor.md").read_text()
        self.assertIn("not quizzes", agent)
        self.assertIn("Do not give quizzes, assessment questions", workflow)
        self.assertIn("automatically", workflow)
        self.assertIn("after each substantive explanation or follow-up", workflow)
        self.assertIn("For a returning learner", workflow)
        self.assertIn("record-coverage", workflow)
        self.assertNotIn("Use the exact lesson assessment question", workflow)

    def test_installed_tutor_notifies_and_saves_automatically(self):
        self.install()
        agent = (self.atlas / ".github" / "agents" /
                 "atlas-onboarding-local.agent.md").read_text()
        workflow = (self.atlas / ".atlas-onboarding" / "tutor.md").read_text()
        for content in (agent, workflow):
            self.assertIn("saved automatically on this computer", content)
            self.assertIn("No name or email is required", content)
            self.assertNotIn("Would you like me to track your progress", content)
        self.assertIn("Do not ask a tracking question", workflow)
        self.assertIn("Keep detailed learning summaries", workflow)
        self.assertIn("Do not save an entire chat transcript", workflow)
        self.assertIn("learner explicitly asks not to save", workflow)
        self.assertIn("denied, saving fails", workflow)
        self.assertIn("then the first-use saving notice below, then run `init`", workflow)

    def test_installed_tutor_guides_beginner_and_follow_up_questions(self):
        self.install()
        agent = (self.atlas / ".github" / "agents" /
                 "atlas-onboarding-local.agent.md").read_text()
        workflow = (self.atlas / ".atlas-onboarding" / "tutor.md").read_text()
        for content in (agent, workflow):
            self.assertIn("Start here", content)
            self.assertIn("You can ask next", content)
            self.assertIn("S1", content)
            self.assertIn("Q1", content)
        self.assertIn("first three topics' exact `starterQuestion` values", workflow)
        self.assertIn("After every explanation or substantive follow-up", workflow)
        self.assertIn("two or three short, specific questions", workflow)
        self.assertIn("never topic coverage", workflow)
        self.assertIn("keeps the current topic unfinished until Done or Next", workflow)
        self.assertIn("If the selection is ambiguous or its list is unavailable", workflow)

    def test_installed_tutor_hides_legacy_review_schedules(self):
        self.install()
        agent = (self.atlas / ".github" / "agents" /
                 "atlas-onboarding-local.agent.md").read_text()
        workflow = (self.atlas / ".atlas-onboarding" / "tutor.md").read_text()
        self.assertIn('Do not show legacy review schedules, due dates, or "No reviews due"', agent)
        self.assertIn("Do not display review schedules, due dates, review counts", workflow)
        self.assertIn("whether this list is empty or populated", workflow)
        self.assertIn("read progress without writing a checkpoint", workflow)
        self.assertIn("If all topics are covered, say so", workflow)
        self.assertIn("Preserve historical review data unchanged", workflow)

    def test_installed_tutor_explains_syllabus_and_usage_on_first_visit(self):
        self.install()
        agent = (self.atlas / ".github" / "agents" /
                 "atlas-onboarding-local.agent.md").read_text()
        workflow = (self.atlas / ".atlas-onboarding" / "tutor.md").read_text()
        for content in (agent, workflow):
            self.assertIn("What you will learn", content)
            self.assertIn("How to use this tutor", content)
            self.assertIn("installed curriculum", content)
        self.assertIn("including an initialized but unused database", workflow)
        self.assertIn("only once in the current conversation", workflow)
        self.assertIn("under 200 words", workflow)
        self.assertIn("Show all curriculum modules in order", workflow)
        self.assertIn("Show syllabus", workflow)
        self.assertIn("navigation requests, not topic coverage", workflow)
        self.assertIn("Returning learners get their saved recap instead", workflow)

    def test_installed_tutor_starts_with_complete_plain_text_syllabus_diagram(self):
        self.install()
        agent = (self.atlas / ".github" / "agents" /
                 "atlas-onboarding-local.agent.md").read_text()
        workflow = (self.atlas / ".atlas-onboarding" / "tutor.md").read_text()
        for content in (agent, workflow):
            self.assertIn("Welcome to ATLAS Tutor! Let's explore Atlas step by step.", content)
            self.assertIn("exactly one short welcome line", content)
            self.assertIn("Immediately follow it", content)
        self.assertIn("Do not repeat this first-time greeting on every turn", workflow)
        self.assertIn("before the saving notice, product introduction, usage guide", workflow)
        diagram = workflow.split("```text\n", 1)[1].split("```", 1)[0]
        curriculum = self.store().curriculum
        self.assertIn(
            f"({len(curriculum['lessons'])} topics, {len(curriculum['modules'])} modules)",
            diagram)
        branches = [line for line in diagram.splitlines()
                    if line.startswith(("+-- ", "`-- "))]
        self.assertEqual(len(curriculum["modules"]), len(branches))
        for index, branch in enumerate(branches, 1):
            self.assertTrue(branch[4:].startswith(f"{index}. "))
        self.assertTrue(all(len(line) <= 72 for line in diagram.splitlines()))
        self.assertIn("Mermaid-only output", workflow)
        self.assertIn("show the syllabus diagram again", workflow)

    def test_installed_tutor_explains_revisits_without_duplicate_saves(self):
        self.install()
        agent = (self.atlas / ".github" / "agents" /
                 "atlas-onboarding-local.agent.md").read_text()
        workflow = (self.atlas / ".atlas-onboarding" / "tutor.md").read_text()
        self.assertIn('On "revisit", explain what was previously covered', agent)
        self.assertIn("Revisit is read-only", agent)
        self.assertIn("recap all previously covered topics in curriculum order", workflow)
        self.assertIn("three to five key takeaways and one short practical example", workflow)
        self.assertIn("A storage-status message is not a learning recap", workflow)
        self.assertIn("This exception overrides normal automatic checkpoint saving", workflow)
        self.assertIn("Only an explicit request to save revisit notes", workflow)
        self.assertIn("returns to the original eligible unfinished topic", workflow)
        self.assertIn("If neither source exists", workflow)

    def test_installed_tutor_keeps_learning_in_final_visible_response(self):
        self.install()
        agent = (self.atlas / ".github" / "agents" /
                 "atlas-onboarding-local.agent.md").read_text()
        workflow = (self.atlas / ".atlas-onboarding" / "tutor.md").read_text()
        for content in (agent, workflow):
            self.assertIn("complete learner-facing answer in the final response", content)
        self.assertIn("repeat the complete welcome in the final response", workflow)
        self.assertIn("final first-time reply must contain, in order", workflow)
        self.assertIn("actual S1-S3 starter questions", workflow)
        self.assertIn("do not call `save-session` merely to checkpoint the welcome", workflow)
        self.assertIn("Initializing storage does not make the learner a returning learner", workflow)
        self.assertIn("retain the learning content and explicitly report UNSAVED", workflow)
        self.assertIn("without internal revision numbers", workflow)
        self.assertIn("optional quiz still presents its clickable questions", workflow)

    def install_legacy_package(self):
        files = {name: source for name, source in installer.FILES.items()
                 if name in installer.LEGACY_FILES}
        with patch.object(installer, "FILES", files), \
                patch.object(installer, "EXCLUDES", installer.LEGACY_EXCLUDES):
            self.install()

    def test_installed_quiz_is_user_triggered_with_clickable_choices_only(self):
        self.install()
        skill_path = self.atlas / ".github" / "skills" / "quiz" / "SKILL.md"
        skill = skill_path.read_text()
        agent_path = self.atlas / ".github" / "agents" / "atlas-onboarding-local.agent.md"
        agent = agent_path.read_text()
        workflow = (self.atlas / ".atlas-onboarding" / "tutor.md").read_text()
        self.assertTrue(skill.startswith("---\nname: quiz\n"))
        self.assertIn("user-invocable: true", skill)
        self.assertIn("disable-model-invocation: true", skill)
        self.assertIn("vscode/askQuestions", agent.split("---", 2)[1])
        self.assertIn("ask_user", agent.split("---", 2)[1])
        self.assertIn("multiSelect: false", skill)
        self.assertIn("allowFreeformInput: false", skill)
        self.assertIn("exactly five distinct questions", skill)
        self.assertIn("exactly one unambiguous correct answer", skill)
        self.assertIn("Warm-up score: X/5", skill)
        self.assertIn("do not start", agent)
        self.assertIn("Only when the learner invokes `/quiz`", agent)
        self.assertIn("Ordinary learning stays quiz-free", workflow)
        self.assertTrue((agent_path.parent / ".." / "skills" / "quiz" / "SKILL.md").is_file())
        for relative in ("tutor.md", "curriculum.json"):
            self.assertTrue((skill_path.parent / ".." / ".." / ".." /
                             ".atlas-onboarding" / relative).is_file())

    def test_quiz_instructions_preserve_progress_and_handle_interruption(self):
        skill = installer.FILES[".github/skills/quiz/SKILL.md"].read_text()
        self.assertIn("Read learner progress only", skill)
        self.assertIn("Never call `init`, `record-coverage`, `record-attempt`, or `save-session`", skill)
        self.assertIn("Do not save questions, answers, scores", skill)
        self.assertIn("original continuation topic", skill)
        self.assertIn("Exclude freshness-uncertain topics", skill)
        self.assertIn("Do not test future lessons, previews, unfinished topics", skill)
        self.assertIn("If no covered learning can be verified", skill)
        self.assertIn("fewer than five distinct, supported questions", skill)
        self.assertIn("Do not substitute Markdown links, typed A/B/C/D choices", skill)
        self.assertIn("do not infer an answer", skill.lower())
        self.assertIn("skips, cancels, asks to stop", skill)
        self.assertIn("clearly labelled incomplete", skill)
        self.assertIn("must select ATLAS Tutor first", skill)

    def test_quiz_varies_correct_option_positions_and_preserves_answer_mapping(self):
        skill = installer.FILES[".github/skills/quiz/SKILL.md"].read_text()
        self.assertIn("use each of the four positions at least once", skill)
        self.assertIn("exactly one position used twice and no adjacent repeats", skill)
        self.assertIn("Vary the order between quizzes", skill)
        self.assertIn("correct answer keyed to its exact option text", skill)
        self.assertIn("verify the answer mapping after reordering", skill)
        self.assertIn("Do not reveal the position plan", skill)
        self.assertIn("Keep that order and answer fixed once displayed", skill)
        self.assertIn("do not treat that as a submitted answer", skill)

    def test_quiz_supports_runtime_question_forms_without_picker_visibility(self):
        skill = installer.FILES[".github/skills/quiz/SKILL.md"].read_text()
        self.assertIn("Do not require visibility of the agent picker", skill)
        self.assertIn("using tool discovery first if tools are deferred", skill)
        self.assertIn("Prefer `ask_user` when actually exposed", skill)
        self.assertIn("`vscode_askQuestions`", skill)
        self.assertIn("`requestedSchema.properties.answer`", skill)
        self.assertIn("four `enum` option labels", skill)
        self.assertIn("Omit a default", skill)
        self.assertIn("Do not pass the VS Code `questions` array", skill)
        self.assertIn("Grade only an exact match", skill)
        self.assertIn("Handle decline/cancel as interruption", skill)
        self.assertIn("If no supported tool is exposed", skill)
        self.assertIn("without restarting the quiz", skill)

    def test_legacy_update_adds_quiz_without_changing_learning_data(self):
        self.install_legacy_package()
        store = self.store()
        store.initialize()
        self.save_attempt(store)
        before = store.path.read_bytes()
        self.assertTrue(installer.install(self.atlas, "update")["verified"])
        skill = self.atlas / ".github" / "skills" / "quiz" / "SKILL.md"
        self.assertEqual(installer.FILES[".github/skills/quiz/SKILL.md"].read_bytes(),
                         skill.read_bytes())
        manifest = json.loads((self.atlas / installer.MANIFEST).read_text())
        self.assertEqual(set(installer.FILES), set(manifest["files"]))
        self.assertEqual(1, self.exclude.read_bytes().count(installer.EXCLUDES.encode()))
        ignored = subprocess.run(
            ["git", "-C", str(self.atlas), "check-ignore", "-q",
             ".github/skills/quiz/SKILL.md"], capture_output=True)
        self.assertEqual(0, ignored.returncode)
        self.assertEqual(before, store.path.read_bytes())
        installer.install(self.atlas, "remove")
        self.assertFalse(skill.exists())
        self.assertEqual(before, store.path.read_bytes())

    def test_legacy_update_does_not_overwrite_unowned_quiz(self):
        self.install_legacy_package()
        skill = self.atlas / ".github" / "skills" / "quiz" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("Existing unrelated quiz")
        manifest = (self.atlas / installer.MANIFEST).read_bytes()
        exclude = self.exclude.read_bytes()
        with self.assertRaisesRegex(ValueError, "overwrite existing file"):
            installer.install(self.atlas, "update")
        self.assertEqual(manifest, (self.atlas / installer.MANIFEST).read_bytes())
        self.assertEqual(exclude, self.exclude.read_bytes())
        installer.install(self.atlas, "remove")
        self.assertEqual("Existing unrelated quiz", skill.read_text())

    def test_legacy_update_refuses_tracked_quiz_even_if_missing(self):
        self.install_legacy_package()
        skill = self.atlas / ".github" / "skills" / "quiz" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("Tracked quiz")
        subprocess.run(["git", "-C", str(self.atlas), "add",
                        ".github/skills/quiz/SKILL.md"], check=True, capture_output=True)
        skill.unlink()
        with self.assertRaisesRegex(ValueError, "tracked file"):
            installer.install(self.atlas, "update")
        self.assertFalse(skill.exists())
        self.assertEqual(1, self.exclude.read_bytes().count(installer.LEGACY_EXCLUDES.encode()))

    def test_failed_legacy_upgrade_rolls_back_added_quiz(self):
        self.install_legacy_package()
        manifest = (self.atlas / installer.MANIFEST).read_bytes()
        exclude = self.exclude.read_bytes()
        original = Path.write_bytes
        failed = False

        def fail_exclude_once(path, content):
            nonlocal failed
            if path == self.exclude and not failed:
                failed = True
                raise OSError("fixture upgrade failure")
            return original(path, content)

        with patch.object(Path, "write_bytes", fail_exclude_once):
            with self.assertRaisesRegex(OSError, "fixture upgrade failure"):
                installer.install(self.atlas, "update")
        self.assertEqual(manifest, (self.atlas / installer.MANIFEST).read_bytes())
        self.assertEqual(exclude, self.exclude.read_bytes())
        self.assertFalse((self.atlas / ".github" / "skills" / "quiz" / "SKILL.md").exists())
        self.assertFalse((self.exclude.parent / "atlas-onboarding.lock").exists())


def sys_executable():
    import sys
    return sys.executable


class CoverageTests(Fixture):
    def coverage(self, store, topic=None, **changes):
        topic = topic or next(iter(store.lessons))
        payload = {
            "id": f"coverage-{store.progress()['revision']}",
            "expectedRevision": store.progress()["revision"],
            "topicId": topic,
            "confirmation": "Done",
            "summary": "Explained the topic from inspected repository sources.",
            "sourcePaths": [source["path"] for source in store.lessons[topic]["sources"]],
            "sourceRevision": None,
        }
        payload.update(changes)
        return payload

    def test_coverage_resumes_without_assessment_or_review(self):
        store = self.init_store()
        payload = self.coverage(store, confirmation=" next ")
        store.write("record-coverage", payload)
        progress = self.store().progress()
        self.assertEqual(1, progress["revision"])
        self.assertEqual("atlas-startup-navigation", progress["nextTopic"])
        self.assertEqual("completed", progress["topics"][0]["status"])
        self.assertEqual("covered", progress["topics"][0]["understanding"])
        self.assertEqual([payload], progress["attempts"])
        self.assertEqual([], progress["dueReviews"])
        with contextlib.closing(store.connect()) as connection:
            row = connection.execute("SELECT kind, result, timestamp FROM attempts").fetchone()
            self.assertEqual(("coverage", "covered"), (row["kind"], row["result"]))
            self.assertIsNotNone(row["timestamp"])
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0])

    def test_confirmation_and_payload_validation_do_not_advance(self):
        store = self.init_store()
        for changes in ({"confirmation": "Hi"}, {"confirmation": ""},
                        {"confirmation": None}, {"topicId": "unknown"},
                        {"summary": ""}, {"question": "An unwanted quiz"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                store.write("record-coverage", self.coverage(store, **changes))
        self.assertEqual(0, store.progress()["revision"])
        self.assertEqual([], store.progress()["topics"])

    def test_coverage_checks_sources_and_prerequisites(self):
        store = self.init_store()
        for sources in ([], "docs/projects/example.md", [None],
                        ["..\\outside.md"], ["docs/projects/missing.md"],
                        ["docs/projects/01-atlas-application.md"] * 2):
            with self.subTest(sources=sources), self.assertRaises(ValueError):
                store.write("record-coverage", self.coverage(store, sourcePaths=sources))
        with self.assertRaisesRegex(ValueError, "Prerequisites"):
            store.write("record-coverage", self.coverage(store, "atlas-startup-navigation"))
        self.assertEqual([], store.progress()["attempts"])

    def test_coverage_retries_and_stale_writes(self):
        store = self.init_store()
        payload = self.coverage(store)
        store.write("record-coverage", payload)
        self.assertTrue(store.write("record-coverage", payload)["replayed"])
        with self.assertRaisesRegex(ValueError, "different content"):
            store.write("record-coverage", dict(payload, summary="Different summary"))
        with self.assertRaisesRegex(ValueError, "Stale revision"):
            store.write("record-coverage", dict(payload, id="stale-coverage"))
        self.assertEqual(1, store.progress()["revision"])
        self.assertEqual(1, len(store.progress()["attempts"]))

    def test_all_topics_can_be_covered_without_quizzes(self):
        store = self.init_store()
        for index, topic in enumerate(store.lessons):
            self.assertEqual(topic, store.progress()["nextTopic"])
            store.write("record-coverage", self.coverage(store, topic))
            self.assertEqual(index + 1, store.progress()["revision"])
        progress = store.progress()
        self.assertEqual(25, len(progress["topics"]))
        self.assertTrue(all(topic["understanding"] == "covered" for topic in progress["topics"]))
        self.assertIsNone(progress["nextTopic"])
        self.assertEqual([], progress["dueReviews"])

    def test_existing_assessments_and_checkpoints_are_preserved(self):
        store = self.init_store()
        historical = self.save_attempt(store)
        store.write("record-coverage", self.coverage(store))
        self.assertEqual(historical, store.progress()["attempts"][0])
        self.assertEqual([], store.progress()["dueReviews"])
        session = {"id": "automatic-checkpoint", "expectedRevision": 2,
                   "currentTopicId": "atlas-startup-navigation",
                   "summary": "Explained startup; learner has not said Done or Next.",
                   "nextStep": "Continue explaining desktop navigation.", "openQuestions": []}
        store.write("save-session", session)
        progress = self.store().progress()
        self.assertTrue(progress["consent"])
        self.assertEqual(session, progress["lastSession"])
        self.assertEqual(1, len(progress["topics"]))
        self.assertEqual("atlas-startup-navigation", progress["nextTopic"])

    def test_curriculum_change_requires_renewed_coverage(self):
        store = self.init_store()
        for topic in list(store.lessons)[:2]:
            store.write("record-coverage", self.coverage(store, topic))
        changed = copy.deepcopy(store.curriculum)
        changed["lessons"][0]["objectives"].append("Updated product purpose")
        path = self.atlas / "changed-curriculum.json"
        path.write_text(json.dumps(changed))
        newer = database.Store(self.atlas, path)
        self.assertEqual("atlas-overview", newer.progress()["nextTopic"])
        with self.assertRaisesRegex(ValueError, "Prerequisites"):
            newer.write("record-coverage", self.coverage(newer, "atlas-startup-navigation"))
        newer.write("record-coverage", self.coverage(newer, "atlas-overview"))
        self.assertEqual(3, len(newer.progress()["attempts"]))
        self.assertEqual("atlas-access-and-licensing", newer.progress()["nextTopic"])

    def test_coverage_rolls_back_atomically(self):
        store = self.init_store()
        with contextlib.closing(store.connect()) as connection, connection:
            connection.execute(
                "CREATE TRIGGER reject_topic BEFORE INSERT ON topics "
                "BEGIN SELECT RAISE(ABORT, 'fixture topic failure'); END")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "fixture topic failure"):
            store.write("record-coverage", self.coverage(store))
        progress = store.progress()
        self.assertEqual(0, progress["revision"])
        self.assertEqual([], progress["attempts"])
        self.assertEqual([], progress["topics"])

    def test_installed_cli_records_coverage_and_checkpoint(self):
        store = self.init_store()
        command = [sys_executable(), str(self.atlas / ".atlas-onboarding" / "onboarding.py"),
                   "--atlas", str(self.atlas)]
        payload = self.coverage(store, summary="Explained Atlas: $(not a command)\n'@\n\"quoted\"")
        for action, data in (
                ("record-coverage", payload),
                ("save-session", {"id": "checkpoint", "expectedRevision": 1,
                                  "currentTopicId": "atlas-startup-navigation",
                                  "summary": "Atlas overview covered.",
                                  "nextStep": "Explain startup.", "openQuestions": []})):
            result = subprocess.run(command + [action], input=json.dumps(data),
                                    capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(json.loads(result.stdout)["saved"])
        resumed = subprocess.run(command + ["next-topic"], capture_output=True, text=True)
        self.assertEqual(0, resumed.returncode, resumed.stderr)
        progress = json.loads(resumed.stdout)
        self.assertEqual(payload, progress["attempts"][0])
        self.assertEqual("Explain startup.", progress["lastSession"]["nextStep"])
        self.assertEqual("atlas-startup-navigation", progress["nextTopic"])
        self.assertEqual([], progress["dueReviews"])


class StoreTests(Fixture):
    def test_read_before_initialization_creates_nothing(self):
        result = self.store().progress()
        self.assertFalse(result["consent"])
        self.assertFalse((self.atlas / ".onboarding").exists())
        self.assertIn("Show the automatic-saving notice", result["message"])
        self.assertFalse((self.atlas / ".onboarding").exists())

    def test_init_requires_git_ignored_data(self):
        with self.assertRaisesRegex(ValueError, "Git-ignored"):
            self.store().initialize()
        self.assertFalse((self.atlas / ".onboarding").exists())

    def test_installed_cli_initializes_without_tracking_choice(self):
        self.install()
        command = [sys_executable(), str(self.atlas / ".atlas-onboarding" / "onboarding.py"),
                   "--atlas", str(self.atlas)]
        inspected = subprocess.run(command + ["get-progress"], capture_output=True, text=True)
        self.assertEqual(0, inspected.returncode, inspected.stderr)
        self.assertFalse(json.loads(inspected.stdout)["saved"])
        self.assertFalse(self.store().path.exists())
        initialized = subprocess.run(command + ["init"], capture_output=True, text=True)
        self.assertEqual(0, initialized.returncode, initialized.stderr)
        progress = json.loads(initialized.stdout)
        self.assertTrue(progress["saved"])
        self.assertEqual(0, progress["revision"])
        self.assertEqual([], progress["topics"])
        self.assertIsNone(progress["lastSession"])
        before = self.store().path.read_bytes()
        repeated = subprocess.run(command + ["init"], capture_output=True, text=True)
        self.assertEqual(1, repeated.returncode)
        self.assertIn("already exists", json.loads(repeated.stderr)["error"])
        self.assertEqual(before, self.store().path.read_bytes())

    def test_tracked_learner_data_blocks_writes(self):
        store = self.init_store()
        subprocess.run(["git", "-C", str(self.atlas), "add", "-f",
                        ".onboarding/onboarding.db"], check=True, capture_output=True)
        with self.assertRaisesRegex(ValueError, "Git-ignored and untracked"):
            self.save_attempt(store)
        self.assertEqual(0, store.progress()["revision"])

    def test_first_demonstration_and_resume(self):
        store = self.init_store()
        payload = self.save_attempt(store)
        progress = self.store().progress()
        self.assertEqual(1, progress["revision"])
        self.assertEqual("atlas-startup-navigation", progress["nextTopic"])
        self.assertEqual("completed", progress["topics"][0]["status"])
        self.assertEqual(payload, progress["attempts"][0])
        with contextlib.closing(store.connect()) as connection:
            review = connection.execute("SELECT * FROM reviews").fetchone()
            self.assertEqual(0, review["stage"])
            self.assertEqual((date.today() + timedelta(days=1)).isoformat(), review["due_date"])
            self.assertIsNotNone(connection.execute("SELECT timestamp FROM attempts").fetchone()[0])

    def test_cannot_bypass_prerequisites_or_modules(self):
        store = self.init_store()
        for topic in ("atlas-startup-navigation", "eatlas-overview"):
            if topic not in store.lessons:
                topic = next(item["id"] for item in store.lessons.values()
                             if item["moduleId"] == "eatlas-essentials")
            with self.assertRaisesRegex(ValueError, "Prerequisites"):
                store.write("record-attempt", self.attempt(store, topic))
        self.assertEqual([], store.progress()["attempts"])
        self.assertEqual(0, store.progress()["revision"])

    def test_all_25_lessons_complete_in_curriculum_order(self):
        store = self.init_store()
        self.assertEqual(25, len(store.lessons))
        for index, lesson in enumerate(store.lessons.values()):
            progress = store.progress()
            self.assertEqual(lesson["id"], progress["nextTopic"])
            store.write("record-attempt", self.attempt(store, lesson["id"]))
            self.assertEqual(index + 1, store.progress()["revision"])
        self.assertIsNone(store.progress()["nextTopic"])
        self.assertEqual(25, len(store.progress()["attempts"]))

    def test_failed_attempt_does_not_complete_topic(self):
        store = self.init_store()
        lesson = next(iter(store.lessons.values()))
        required = lesson["assessment"]["requiredConcepts"]
        self.save_attempt(store, result="needs_support", correctConcepts=required[:1],
                          missingConcepts=required[1:])
        progress = store.progress()
        self.assertEqual("in_progress", progress["topics"][0]["status"])
        self.assertEqual("atlas-overview", progress["nextTopic"])
        with contextlib.closing(store.connect()) as connection:
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0])

    def test_invalid_rubric_and_shown_solution_cannot_demonstrate(self):
        store = self.init_store()
        cases = ({"missingConcepts": ["invented concept"]},
                 {"assistance": "solution_shown"},
                 {"misconceptions": ["Material contradiction"]},
                 {"question": "An easier question"},
                 {"correctConcepts": []},
                 {"sourcePaths": ["..\\outside.md"]},
                 {"sourcePaths": ["docs/projects/missing.md"]})
        for changes in cases:
            with self.assertRaises(ValueError):
                store.write("record-attempt", self.attempt(store, **changes))
        self.assertEqual(0, store.progress()["revision"])
        self.assertEqual([], store.progress()["attempts"])

    def test_unknown_topic_and_unexpected_fields_fail(self):
        store = self.init_store()
        payload = self.attempt(store)
        payload["topicId"] = "invented"
        with self.assertRaisesRegex(ValueError, "Unknown topic"):
            store.write("record-attempt", payload)
        payload = self.attempt(store)
        payload["score"] = 100
        with self.assertRaisesRegex(ValueError, "exactly"):
            store.write("record-attempt", payload)

    def test_stale_writes_and_idempotent_retries(self):
        store = self.init_store()
        payload = self.attempt(store)
        result = store.write("record-attempt", payload)
        self.assertEqual(1, result["revision"])
        retry = store.write("record-attempt", payload)
        self.assertTrue(retry["replayed"])
        self.assertEqual(1, store.progress()["revision"])
        conflict = dict(payload, answer="different")
        with self.assertRaisesRegex(ValueError, "different content"):
            store.write("record-attempt", conflict)
        stale = dict(payload, id="other")
        with self.assertRaisesRegex(ValueError, "Stale revision"):
            store.write("record-attempt", stale)

    def test_review_stages_and_failed_review(self):
        store = self.init_store()
        self.save_attempt(store)
        for stage, days in ((1, 3), (2, 7), (2, 7)):
            self.save_attempt(store, kind="review")
            with contextlib.closing(store.connect()) as connection:
                review = connection.execute("SELECT * FROM reviews").fetchone()
                self.assertEqual(stage, review["stage"])
                self.assertEqual((date.today() + timedelta(days=days)).isoformat(), review["due_date"])
        required = next(iter(store.lessons.values()))["assessment"]["requiredConcepts"]
        self.save_attempt(store, kind="review", result="needs_support",
                          correctConcepts=[], missingConcepts=required)
        with contextlib.closing(store.connect()) as connection:
            self.assertEqual(0, connection.execute("SELECT stage FROM reviews").fetchone()[0])
        self.assertEqual("needs_revisit", store.progress()["topics"][0]["status"])

    def test_review_without_first_demonstration_fails(self):
        store = self.init_store()
        with self.assertRaisesRegex(ValueError, "earlier demonstrated"):
            self.save_attempt(store, kind="review")
        self.assertEqual(0, store.progress()["revision"])

    def test_due_review_reads_do_not_reschedule(self):
        store = self.init_store()
        self.save_attempt(store)
        due = (date.today() - timedelta(days=1)).isoformat()
        with contextlib.closing(store.connect()) as connection, connection:
            connection.execute("UPDATE reviews SET due_date = ?", (due,))
        first = store.progress()
        second = store.progress()
        self.assertEqual(first, second)
        self.assertEqual(due, first["dueReviews"][0]["due_date"])

    def test_curriculum_change_preserves_evidence_and_blocks_dependents(self):
        store = self.init_store()
        for topic in list(store.lessons)[:3]:
            store.write("record-attempt", self.attempt(store, topic))
        changed = copy.deepcopy(store.curriculum)
        changed["lessons"][0]["objectives"].append("New required understanding")
        path = self.atlas / "changed-curriculum.json"
        path.write_text(json.dumps(changed))
        newer = database.Store(self.atlas, path)
        progress = newer.progress()
        self.assertEqual(["atlas-overview"], progress["freshnessUncertain"])
        self.assertEqual(3, len(progress["attempts"]))
        self.assertEqual("atlas-overview", progress["nextTopic"])
        self.assertFalse(newer.eligible(
            {item["id"]: item for item in progress["topics"]},
            newer.lessons["technician-workflow"]))

    def test_sessions_preserve_questions_and_read_back(self):
        store = self.init_store()
        payload = {"id": "session-1", "expectedRevision": 0,
                   "currentTopicId": "atlas-overview", "summary": "Learned purpose",
                   "nextStep": "Teach back",
                   "openQuestions": [{"id": "q1", "topicId": None,
                                      "question": "How does offline sync work?", "status": "open"}]}
        result = store.write("save-session", payload)
        self.assertEqual(1, result["revision"])
        self.assertEqual(payload, store.progress()["lastSession"])
        self.assertTrue(store.write("save-session", payload)["replayed"])

    def test_unsupported_schema_and_corrupt_database_fail_without_reset(self):
        store = self.init_store()
        with contextlib.closing(sqlite3.connect(store.path)) as connection, connection:
            connection.execute("PRAGMA user_version=999")
        before = store.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "Unsupported database"):
            store.progress()
        self.assertEqual(before, store.path.read_bytes())
        store.path.write_bytes(b"not sqlite")
        with self.assertRaises(sqlite3.DatabaseError):
            store.progress()
        self.assertEqual(b"not sqlite", store.path.read_bytes())

    def test_database_lock_is_explicit_and_never_partially_saves(self):
        store = self.init_store()
        with contextlib.closing(store.connect()) as writer:
            writer.execute("BEGIN IMMEDIATE")
            with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                self.save_attempt(store)
            writer.rollback()
        self.assertEqual(0, store.progress()["revision"])
        self.assertEqual([], store.progress()["attempts"])

    def test_attempt_topic_review_and_revision_roll_back_together(self):
        store = self.init_store()
        with contextlib.closing(store.connect()) as connection, connection:
            connection.execute(
                "CREATE TRIGGER reject_review BEFORE INSERT ON reviews "
                "BEGIN SELECT RAISE(ABORT, 'fixture review failure'); END")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "fixture review failure"):
            self.save_attempt(store)
        progress = store.progress()
        self.assertEqual(0, progress["revision"])
        self.assertEqual([], progress["attempts"])
        self.assertEqual([], progress["topics"])

    def test_existing_database_cannot_be_reinitialized(self):
        store = self.init_store()
        before = store.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            store.initialize()
        self.assertEqual(before, store.path.read_bytes())

    def test_cli_errors_are_json_and_nonzero(self):
        store = self.init_store()
        with patch("sys.argv", ["onboarding.py", "--atlas", str(self.atlas), "record-attempt"]), \
                patch("sys.stdin", io.StringIO("{broken")), \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            # Source CLI resolves its curriculum beside the source script. Use installed CLI below.
            with patch.object(database, "Store", return_value=store):
                self.assertEqual(1, database.main())
        self.assertFalse(json.loads(stderr.getvalue())["saved"])

    def test_installed_cli_saves_stdin_and_resumes(self):
        self.install()
        command = [sys_executable(), str(self.atlas / ".atlas-onboarding" / "onboarding.py"),
                   "--atlas", str(self.atlas)]
        initialized = subprocess.run(command + ["init", "--consent"],
                                     capture_output=True, text=True)
        self.assertEqual(0, initialized.returncode, initialized.stderr)
        payload = self.attempt(self.store(), answer="Learner's answer: $(not a command)\n'@\n\"quoted\"")
        saved = subprocess.run(command + ["record-attempt"], input=json.dumps(payload),
                               capture_output=True, text=True)
        self.assertEqual(0, saved.returncode, saved.stderr)
        self.assertTrue(json.loads(saved.stdout)["saved"])
        resumed = subprocess.run(command + ["next-topic"], capture_output=True, text=True)
        self.assertEqual(0, resumed.returncode, resumed.stderr)
        progress = json.loads(resumed.stdout)
        self.assertEqual(payload["answer"], progress["attempts"][0]["answer"])
        self.assertEqual("atlas-startup-navigation", progress["nextTopic"])


if __name__ == "__main__":
    unittest.main()
