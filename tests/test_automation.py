"""Checks the weekly sync workflow, the Cursor maintainer command and the learners' automatic updates."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = os.name == "nt"


def read(*parts):
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = read(".github", "workflows", "weekly-lesson-sync.yml")

    def test_runs_monday_0900_ist_and_on_demand(self):
        self.assertIn('cron: "30 3 * * 1"', self.text)       # 03:30 UTC = 09:00 IST
        self.assertIn("workflow_dispatch:", self.text)

    def test_fetches_atlas_from_bitbucket_with_a_read_token(self):
        self.assertIn("secrets.BITBUCKET_READ_TOKEN", self.text)
        self.assertIn("clone --depth 1", self.text)
        self.assertIn("scripts/sync_docs.py --atlas atlas check", self.text)

    def test_copilot_is_primary_and_can_never_break_the_workflow(self):
        self.assertIn("secrets.COPILOT_GITHUB_TOKEN != ''", self.text)
        self.assertIn("npm install -g @github/copilot", self.text)
        step = self.text.split("id: copilot")[1].split("- name:")[0]
        self.assertIn("continue-on-error: true", step)
        self.assertIn("python -m unittest discover -s tests -v", self.text)
        self.assertIn("peter-evans/create-pull-request", self.text)

    def test_cursor_issue_is_the_fallback_when_there_is_no_pull_request(self):
        self.assertIn("steps.pr.outputs.pull-request-number == ''", self.text)
        self.assertIn("/sync-lessons", self.text)

    def test_only_lessons_json_may_be_changed_by_the_agent(self):
        self.assertIn('"$changed" != "lessons.json"', self.text)

    def test_no_old_workflows_are_left_behind(self):
        names = {p.name for p in (ROOT / ".github" / "workflows").iterdir()}
        self.assertEqual({"ci.yml", "weekly-lesson-sync.yml"}, names)


class CursorCommandTests(unittest.TestCase):
    def test_command_has_the_required_steps_in_order(self):
        text = read(".cursor", "commands", "sync-lessons.md")
        order = ["pull --ff-only", "sync_docs.py --atlas", "AGENTS.md", "MAINTAINING.md", "lessons.json",
                 "python -m unittest discover -s tests -v", "accept --lesson", "Summarize"]
        positions = [text.index(item) for item in order]
        self.assertEqual(sorted(positions), positions)

    def test_command_is_never_installed_into_a_learner_checkout(self):
        for name in ("scripts/setup.ps1", "scripts/install.py"):
            self.assertNotIn("commands", read(*name.split("/")), name)
            self.assertNotIn("sync-lessons", read(*name.split("/")), name)


class LearnerAutoUpdateTests(unittest.TestCase):
    def test_setup_records_the_source_repo_and_installs_the_launcher_file(self):
        setup = read("scripts", "setup.ps1")
        self.assertIn(".source-repo", setup)
        self.assertIn("open-explorer.bat", setup)
        self.assertIn("ATLAS_ONBOARDING_SILENT", setup)
        self.assertIn("ATLAS_ONBOARDING_SILENT", read("setup.bat"))

    def test_source_repo_file_is_inside_the_git_excluded_folder(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import install
        self.assertIn("/.atlas-onboarding/\n", install.EXCLUDES)

    def test_cursor_rule_checks_for_updates_silently_first(self):
        rule = read("cursor", "atlas-onboarding.mdc")
        self.assertIn("atlas-onboarding-managed", rule)
        self.assertLess(rule.index(".source-repo"), rule.index("You answer questions about Atlas"))
        for phrase in ("pull --ff-only", "Ignore every error", "Never delay or change the answer"):
            self.assertIn(phrase, rule)

    @unittest.skipUnless(WINDOWS, "the launcher is a Windows batch file")
    def test_setup_script_parses(self):
        script = (f"$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile("
                  f"'{ROOT / 'scripts' / 'setup.ps1'}',[ref]$null,[ref]$e);exit $e.Count")
        done = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)


@unittest.skipUnless(WINDOWS, "the launcher is a Windows batch file")
class LauncherTests(unittest.TestCase):
    """Runs the real launcher against throw-away git repositories and a fake setup.bat."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.upstream, self.source = base / "upstream", base / "source"
        self.atlas = base / "atlas"
        self.home = self.atlas / ".atlas-onboarding"
        self.upstream.mkdir()
        self.git(self.upstream, "init", "-q")
        (self.upstream / "setup.bat").write_bytes(
            b'@echo off\r\necho %ATLAS_ONBOARDING_SILENT%;%~1>"%~dp0setup-called.txt"\r\nexit /b 0\r\n')
        self.commit(self.upstream, "first")
        subprocess.run(["git", "clone", "-q", str(self.upstream), str(self.source)], check=True, capture_output=True)
        (self.home / "explorer").mkdir(parents=True)
        shutil.copy(ROOT / "scripts" / "open-explorer.bat", self.home / "Open Atlas Explorer.bat")
        (self.home / "explorer" / "server.py").write_text(
            "from pathlib import Path\nimport sys\nPath(__file__).with_name('ran.txt').write_text(' '.join(sys.argv[1:]))\n",
            encoding="utf-8")
        (self.home / ".source-repo").write_text(str(self.source) + "\r\n", encoding="ascii")

    def git(self, repo, *args):
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                       check=True, capture_output=True)

    def commit(self, repo, name):
        (repo / f"{name}.txt").write_text(name, encoding="utf-8")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-qm", name)

    def launch(self):
        return subprocess.run([str(self.home / "Open Atlas Explorer.bat")], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=120)

    @property
    def setup_marker(self):
        return self.source / "setup-called.txt"

    def test_new_commits_trigger_a_silent_setup_then_the_guide_starts(self):
        self.commit(self.upstream, "second")
        self.launch()
        self.assertTrue((self.source / "second.txt").exists(), "the source repo was not pulled")
        self.assertTrue(self.setup_marker.exists(), "setup.bat was not re-run")
        flag, atlas_arg = self.setup_marker.read_text().strip().split(";", 1)
        self.assertEqual("1", flag)
        self.assertEqual(self.atlas.resolve(), Path(atlas_arg).resolve())
        self.assertTrue((self.home / "explorer" / "ran.txt").exists(), "the guide did not start after the update")

    def test_nothing_new_means_no_setup_and_the_guide_starts(self):
        self.launch()
        self.assertFalse(self.setup_marker.exists())
        self.assertTrue((self.home / "explorer" / "ran.txt").exists())

    def test_an_unreachable_or_missing_source_never_blocks_the_guide(self):
        (self.home / ".source-repo").write_text(str(self.source.parent / "gone") + "\r\n", encoding="ascii")
        self.launch()
        self.assertTrue((self.home / "explorer" / "ran.txt").exists())
        (self.home / ".source-repo").unlink()
        (self.home / "explorer" / "ran.txt").unlink()
        self.launch()
        self.assertTrue((self.home / "explorer" / "ran.txt").exists())

    def test_local_edits_in_the_source_repo_make_the_pull_fail_quietly(self):
        self.commit(self.upstream, "second")
        (self.source / "second.txt").write_text("local", encoding="utf-8")                   # blocks the fast-forward
        self.launch()
        self.assertFalse(self.setup_marker.exists())
        self.assertTrue((self.home / "explorer" / "ran.txt").exists())


if __name__ == "__main__":
    unittest.main()
