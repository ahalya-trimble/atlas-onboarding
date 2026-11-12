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

    def save_summary(self, store, **changes):
        revision = store.progress()["revision"]
        payload = {"id": f"session-{revision}", "expectedRevision": revision,
                   "currentTopicId": "atlas-overview", "summary": "Discussed who uses Atlas",
                   "nextStep": "Ask how assignment works", "openQuestions": []}
        payload.update(changes)
        store.write("save-session", payload)
        return payload


class InstallerTests(Fixture):
    def test_install_update_remove_preserves_progress_and_existing_files(self):
        old_agent = self.atlas / ".github" / "agents" / "atlas-tutor.agent.md"
        old_agent.parent.mkdir(parents=True)
        old_agent.write_text("Existing legacy tutor", encoding="ascii")
        self.assertTrue(self.install()["verified"])
        store = self.store()
        store.initialize()
        self.save_summary(store)
        before = store.path.read_bytes()
        self.assertTrue(installer.install(self.atlas, "update")["verified"])
        self.assertEqual(before, store.path.read_bytes())
        self.assertTrue(installer.install(self.atlas, "remove")["verified"])
        self.assertEqual(before, store.path.read_bytes())
        self.assertEqual("Existing legacy tutor", old_agent.read_text())
        self.assertTrue(self.exclude.read_bytes().startswith(self.original_exclude))
        self.assertNotIn(b"# BEGIN atlas-onboarding", self.exclude.read_bytes())
        self.assertIn(b"/.onboarding/", self.exclude.read_bytes())
        self.assertIn(b"/.atlas-onboarding/state/", self.exclude.read_bytes())
        ignored_state = subprocess.run(
            ["git", "-C", str(self.atlas), "check-ignore", "-q",
             ".atlas-onboarding/state/explorer-progress.json"], capture_output=True)
        self.assertEqual(0, ignored_state.returncode)
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
        self.assertLess(agent.index("## Activation boundary"), agent.index("Before answering"))
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

    def texts(self):
        self.install()
        agent = (self.atlas / ".github" / "agents" /
                 "atlas-onboarding-local.agent.md").read_text()
        workflow = (self.atlas / ".atlas-onboarding" / "tutor.md").read_text()
        quiz = (self.atlas / ".github" / "skills" / "quiz" / "SKILL.md").read_text()
        return agent, workflow, quiz

    def test_tutor_is_question_and_answer_not_a_second_course(self):
        agent, workflow, _ = self.texts()
        for content in (agent, workflow):
            self.assertNotIn("Let's explore Atlas step by step", content)
            self.assertNotIn("What you will learn", content)
            self.assertIn("Do not show a syllabus", content)
        self.assertIn("# Welcome to ATLAS Tutor", workflow)
        self.assertIn("## What Atlas Explorer does", workflow)
        self.assertIn("They do not record coverage", workflow)
        self.assertIn("single final welcome", agent)
        self.assertIn("no Done/Next coverage", workflow)
        self.assertIn("**You can ask next**", workflow)
        self.assertIn("Q1-Q3", agent)
        self.assertIn("mark assumptions", agent)
        self.assertIn("visual guide", agent)

    def test_tutor_saves_summaries_only_and_never_coverage_or_assessments(self):
        agent, workflow, _ = self.texts()
        self.assertIn("Do not call `record-coverage` or `record-attempt`", workflow)
        self.assertIn("call `save-session` once", workflow)
        self.assertIn("Never save a transcript, names", workflow)
        self.assertIn("Do not ask a tracking question", workflow)
        self.assertIn("UNSAVED", workflow)
        self.assertIn("Never delete or reset existing records", workflow)
        self.assertIn("Do not save a greeting, a menu, a Revisit, or a quiz", workflow)
        self.assertIn("saved automatically on this computer", workflow)
        self.assertIn("not encrypted", workflow)
        self.assertIn("Do not teach the curriculum in order", agent)
        self.assertIn("Put the complete learner-facing answer in the final response", agent)
        self.assertIn("Put the complete answer in the final response", workflow)

    def test_revisit_my_learnings_recaps_saved_summaries_read_only(self):
        agent, workflow, _ = self.texts()
        self.assertIn("Revisit my learnings", agent)
        self.assertIn("Revisit my learnings", workflow)
        self.assertIn("`sessions` list", workflow)
        self.assertIn("This is read-only. Do not call `init` or `save-session`", workflow)
        self.assertIn("Never invent history", workflow)
        self.assertIn("Revisit is read-only", agent)

    def test_quiz_is_limited_to_discussed_topics_clickable_and_unsaved(self):
        agent, workflow, quiz = self.texts()
        self.assertIn("/quiz", agent)
        self.assertIn("only about topics the learner previously discussed", agent)
        self.assertIn("Use only the `sessions` list", quiz)
        self.assertIn("Do not ask about topics the learner has not discussed", quiz)
        self.assertIn("Never call `init` or `save-session` for a quiz", quiz)
        self.assertIn("never call `record-coverage` or `record-attempt`", quiz.replace(
            "and never call", "and never call"))
        self.assertIn("scores stay in this chat and are not saved", quiz)
        self.assertIn("Do not substitute Markdown links, typed A/B/C/D choices", quiz)
        self.assertIn("allowFreeformInput: false", quiz)
        self.assertIn("Never set `recommended` on any option", quiz)
        self.assertIn("exactly five distinct questions", quiz)
        self.assertIn("use each of the four positions at least once", quiz)
        self.assertIn("ask_user", quiz)
        self.assertIn("vscode/askQuestions", quiz)
        self.assertIn("Do not require visibility of the agent picker", quiz)
        self.assertNotIn("teach-back", quiz.replace("Do not ask a teach-back question.", ""))
        self.assertIn("The Atlas Explorer already has a quiz for every lesson", quiz)

    def test_agent_may_read_explorer_progress_file_read_only(self):
        agent, workflow, _ = self.texts()
        for content in (agent, workflow):
            self.assertIn(".atlas-onboarding/state/explorer-progress.json", content)
            self.assertIn("read only", content)
            self.assertIn("Ignore", content)
        self.assertIn("never as evidence of understanding", " ".join(agent.split()))

    def install_legacy_package(self):
        files = {name: source for name, source in installer.FILES.items()
                 if name in installer.LEGACY_FILES}
        with patch.object(installer, "FILES", files),                 patch.object(installer, "EXCLUDES", installer.LEGACY_EXCLUDES):
            self.install()

    def test_legacy_update_adds_quiz_without_changing_learning_data(self):
        self.install_legacy_package()
        store = self.store()
        store.initialize()
        self.save_summary(store)
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


class StoreTests(Fixture):
    def command(self):
        self.install()
        return [sys_executable(), str(self.atlas / ".atlas-onboarding" / "onboarding.py"),
                "--atlas", str(self.atlas)]

    def test_read_before_initialization_creates_nothing(self):
        result = self.store().progress()
        self.assertFalse(result["consent"])
        self.assertEqual([], result["sessions"])
        self.assertFalse((self.atlas / ".onboarding").exists())
        self.assertIn("Show the automatic-saving notice", result["message"])

    def test_init_requires_git_ignored_data(self):
        with self.assertRaisesRegex(ValueError, "Git-ignored"):
            self.store().initialize()
        self.assertFalse((self.atlas / ".onboarding").exists())

    def test_installed_cli_initializes_without_tracking_choice(self):
        command = self.command()
        inspected = subprocess.run(command + ["get-progress"], capture_output=True, text=True)
        self.assertEqual(0, inspected.returncode, inspected.stderr)
        self.assertFalse(json.loads(inspected.stdout)["saved"])
        self.assertFalse(self.store().path.exists())
        initialized = subprocess.run(command + ["init"], capture_output=True, text=True)
        self.assertEqual(0, initialized.returncode, initialized.stderr)
        progress = json.loads(initialized.stdout)
        self.assertTrue(progress["saved"])
        self.assertEqual(0, progress["revision"])
        self.assertEqual([], progress["sessions"])
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
            self.save_summary(store)
        self.assertEqual(0, store.progress()["revision"])

    def test_unknown_topic_and_unexpected_fields_fail(self):
        store = self.init_store()
        with self.assertRaisesRegex(ValueError, "Unknown currentTopicId"):
            self.save_summary(store, currentTopicId="invented")
        with self.assertRaisesRegex(ValueError, "exactly"):
            self.save_summary(store, score=100)
        with self.assertRaisesRegex(ValueError, "Unknown write action"):
            store.write("record-coverage", {})
        self.assertEqual(0, store.progress()["revision"])

    def test_stale_writes_and_idempotent_retries(self):
        store = self.init_store()
        payload = self.save_summary(store)
        retry = store.write("save-session", payload)
        self.assertTrue(retry["replayed"])
        self.assertEqual(1, store.progress()["revision"])
        with self.assertRaisesRegex(ValueError, "different content"):
            store.write("save-session", dict(payload, summary="different"))
        with self.assertRaisesRegex(ValueError, "Stale revision"):
            store.write("save-session", dict(payload, id="other"))

    def test_sessions_preserve_questions_and_read_back(self):
        store = self.init_store()
        payload = {"id": "session-1", "expectedRevision": 0,
                   "currentTopicId": "atlas-overview", "summary": "Learned purpose",
                   "nextStep": "Ask a follow-up",
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
                self.save_summary(store)
            writer.rollback()
        self.assertEqual(0, store.progress()["revision"])
        self.assertEqual([], store.progress()["sessions"])

    def test_session_and_revision_roll_back_together(self):
        store = self.init_store()
        with contextlib.closing(store.connect()) as connection, connection:
            connection.execute(
                "CREATE TRIGGER reject_revision BEFORE UPDATE ON learner "
                "BEGIN SELECT RAISE(ABORT, 'fixture revision failure'); END")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "fixture revision failure"):
            self.save_summary(store)
        progress = store.progress()
        self.assertEqual(0, progress["revision"])
        self.assertEqual([], progress["sessions"])

    def test_database_from_an_older_version_still_works(self):
        store = self.init_store()
        with contextlib.closing(sqlite3.connect(store.path)) as connection, connection:
            connection.executescript(
                "CREATE TABLE topics (id TEXT PRIMARY KEY, status TEXT);"
                "CREATE TABLE attempts (id TEXT PRIMARY KEY, payload TEXT);")
        self.save_summary(store)
        self.assertEqual(1, store.progress()["revision"])

    def test_existing_database_cannot_be_reinitialized(self):
        store = self.init_store()
        before = store.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "already exists"):
            store.initialize()
        self.assertEqual(before, store.path.read_bytes())

    def test_cli_errors_are_json_and_nonzero(self):
        command = self.command()
        failed = subprocess.run(command + ["save-session"], input="{broken",
                                capture_output=True, text=True)
        self.assertEqual(1, failed.returncode)
        self.assertFalse(json.loads(failed.stderr)["saved"])

    def test_installed_cli_saves_stdin_and_resumes(self):
        command = self.command()
        initialized = subprocess.run(command + ["init", "--consent"],
                                     capture_output=True, text=True)
        self.assertEqual(0, initialized.returncode, initialized.stderr)
        payload = {"id": "s1", "expectedRevision": 0, "currentTopicId": "atlas-overview",
                   "summary": "Learner's note: $(not a command)\n'@\n\"quoted\"",
                   "nextStep": "Ask more", "openQuestions": []}
        saved = subprocess.run(command + ["save-session"], input=json.dumps(payload),
                               capture_output=True, text=True)
        self.assertEqual(0, saved.returncode, saved.stderr)
        self.assertTrue(json.loads(saved.stdout)["saved"])
        resumed = subprocess.run(command + ["get-progress"], capture_output=True, text=True)
        self.assertEqual(0, resumed.returncode, resumed.stderr)
        progress = json.loads(resumed.stdout)
        self.assertEqual(payload["summary"], progress["sessions"][0]["summary"])
        self.assertEqual(1, progress["revision"])

    def test_progress_lists_saved_sessions_for_revisit(self):
        store = self.init_store()
        self.assertEqual([], store.progress()["sessions"])
        for index in (1, 2):
            self.save_summary(store, id=f"s{index}", summary=f"Discussed question {index}")
        sessions = store.progress()["sessions"]
        self.assertEqual(["s1", "s2"], [item["id"] for item in sessions])
        self.assertEqual("s2", store.progress()["lastSession"]["id"])


if __name__ == "__main__":
    unittest.main()
