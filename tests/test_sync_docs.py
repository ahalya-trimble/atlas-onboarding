import ctypes
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sync_docs", ROOT / "scripts" / "sync_docs.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

DOC = """Intro text

# Purpose
Atlas repairs instruments.

# Who uses it
Technicians.

```
# not a heading
```

# Other
Unrelated.
"""
CURRICULUM = {"lessons": [
    {"id": "one", "sources": [{"path": "docs/projects/a.md", "sections": ["Purpose", "Who uses it"]}]},
    {"id": "two", "sources": [{"path": "docs/projects/a.md", "sections": []}]},
]}


class SyncTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.atlas = Path(tmp.name) / "atlas"
        (self.atlas / "docs" / "projects").mkdir(parents=True)
        (self.atlas / "Atlas.sln").write_text("", encoding="utf-8")
        self.doc = self.atlas / "docs" / "projects" / "a.md"
        self.doc.write_text(DOC, encoding="utf-8")
        self.baseline_file, self.report_file = Path(tmp.name) / "baseline.json", Path(tmp.name) / "report.md"
        saved = (sync.BASELINE, sync.REPORT, sync.ROOT)
        self.addCleanup(lambda: setattr(sync, "BASELINE", saved[0]) or setattr(sync, "REPORT", saved[1])
                        or setattr(sync, "ROOT", saved[2]))
        sync.BASELINE, sync.REPORT = self.baseline_file, self.report_file
        sync.ROOT = Path(tmp.name)          # report path is printed relative to ROOT
        self.accept()

    def run_quiet(self, function, *args):
        with redirect_stdout(StringIO()):
            return function(*args)

    def accept(self, only=None):
        return self.run_quiet(sync.cmd_accept, self.atlas, CURRICULUM, only)

    def check(self):
        return self.run_quiet(sync.cmd_check, self.atlas, CURRICULUM)

    def drift(self):
        return sync.compare(self.atlas, CURRICULUM, json.loads(self.baseline_file.read_text(encoding="utf-8")))

    def test_unchanged_docs_are_in_sync(self):
        self.assertEqual(0, self.check())
        self.assertEqual({}, self.drift()[0])

    def test_headings_inside_code_fences_are_ignored(self):
        self.assertNotIn("not a heading", sync.split_sections(DOC))

    def test_whitespace_and_line_endings_do_not_count_as_changes(self):
        self.doc.write_bytes(DOC.replace("\n", "\r\n").replace("Technicians.", "Technicians.   ").encode())
        self.assertEqual(0, self.check())

    def test_changed_cited_section_flags_only_the_lesson_that_cites_it(self):
        self.doc.write_text(DOC.replace("Technicians.", "Technicians and managers."), encoding="utf-8")
        lessons = self.drift()[0]
        self.assertEqual({"one", "two"}, set(lessons))      # 'two' cites the whole document
        self.assertIn("section 'Who uses it' changed", lessons["one"][0])
        self.assertEqual(2, self.check())

    def test_change_in_uncited_section_is_a_note_not_a_lesson_change(self):
        self.doc.write_text(DOC.replace("Unrelated.", "Different."), encoding="utf-8")
        lessons, notes, _ = self.drift()
        self.assertNotIn("one", lessons)
        self.assertTrue(any("Other" in n for n in notes))
        self.assertIn("two", lessons)       # 'two' cites the whole document, so any change counts

    def test_renamed_section_is_reported(self):
        self.doc.write_text(DOC.replace("# Purpose", "# Goal"), encoding="utf-8")
        self.assertIn("no longer exists", self.drift()[0]["one"][0])

    def test_missing_document_is_reported(self):
        self.doc.unlink()
        self.assertIn("missing", self.drift()[0]["one"][0])

    def test_new_uncovered_document_is_listed(self):
        (self.atlas / "docs" / "projects" / "b.md").write_text("# New\nText", encoding="utf-8")
        self.assertEqual(["docs/projects/b.md"], self.drift()[2])

    def test_report_contains_names_never_document_text(self):
        self.doc.write_text(DOC.replace("Technicians.", "SECRET-VALUE-123"), encoding="utf-8")
        self.check()
        report = self.report_file.read_text(encoding="utf-8")
        self.assertIn("Who uses it", report)
        self.assertNotIn("SECRET-VALUE-123", report)
        self.assertNotIn("SECRET-VALUE-123", self.baseline_file.read_text(encoding="utf-8"))

    def test_accept_for_one_lesson_leaves_others_untouched(self):
        other = self.atlas / "docs" / "projects" / "c.md"
        other.write_text("# X\n1", encoding="utf-8")
        curriculum = {"lessons": CURRICULUM["lessons"] + [
            {"id": "three", "sources": [{"path": "docs/projects/c.md", "sections": ["X"]}]}]}
        self.run_quiet(sync.cmd_accept, self.atlas, curriculum, None)
        other.write_text("# X\n2", encoding="utf-8")
        self.doc.write_text(DOC.replace("Technicians.", "Changed."), encoding="utf-8")
        self.run_quiet(sync.cmd_accept, self.atlas, curriculum, ["one"])
        baseline = json.loads(self.baseline_file.read_text(encoding="utf-8"))
        lessons = sync.compare(self.atlas, curriculum, baseline)[0]
        self.assertNotIn("one", lessons)
        self.assertIn("three", lessons)

    def test_accept_drifted_moves_only_flagged_lessons(self):
        self.doc.write_text(DOC.replace("Technicians.", "Changed."), encoding="utf-8")
        self.assertEqual(2, self.check())
        self.assertEqual(0, self.run_quiet(sync.cmd_accept, self.atlas, CURRICULUM, None, True))
        self.assertEqual(0, self.check())
        self.assertEqual(0, self.run_quiet(sync.cmd_accept, self.atlas, CURRICULUM, None, True))   # nothing left to accept

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.atlas), *args], check=True, capture_output=True)

    def test_baseline_refuses_uncommitted_docs_in_a_git_checkout(self):
        self.git("init", "-q")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "add", ".")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "docs")
        self.assertEqual(0, self.accept())                       # clean checkout is accepted
        self.doc.write_text(DOC.replace("Technicians.", "Local edit."), encoding="utf-8")
        self.assertEqual(1, self.accept())                       # a local, uncommitted edit is not
        self.assertEqual(0, self.run_quiet(sync.cmd_accept, self.atlas, CURRICULUM, None, False, True))
        baseline = json.loads(self.baseline_file.read_text(encoding="utf-8"))
        self.assertIn("atlasBranch", baseline)

    @unittest.skipUnless(os.name == "nt", "8.3 short names exist only on Windows")
    def test_atlas_path_in_windows_short_form_is_accepted(self):
        # GitHub runners hand out temp paths like C:\Users\RUNNER~1\...; the resolved path is the long one.
        long_name = self.atlas.parent / "a_directory_with_a_long_name"
        self.atlas.rename(long_name)
        buffer = ctypes.create_unicode_buffer(260)
        if not ctypes.windll.kernel32.GetShortPathNameW(str(long_name), buffer, 260) or buffer.value == str(long_name):
            self.skipTest("this volume does not create short names")
        short = Path(buffer.value)
        self.assertNotEqual(str(short.resolve()), str(short))
        self.assertEqual(0, self.run_quiet(sync.cmd_check, short, CURRICULUM))
        self.assertEqual(0, self.run_quiet(sync.cmd_accept, short, CURRICULUM, None))

    def test_report_path_outside_the_repository_does_not_crash(self):
        elsewhere = Path(tempfile.gettempdir()) / "somewhere" / "report.md"
        self.assertEqual(str(elsewhere), sync.shown(elsewhere))

    def test_check_without_baseline_asks_for_accept(self):
        self.baseline_file.unlink()
        self.assertEqual(1, self.check())

    def test_unknown_lesson_id_is_rejected(self):
        self.assertEqual(1, self.accept(["nope"]))

    def test_real_lesson_file_has_sources_for_every_lesson(self):
        lesson_file = json.loads((ROOT / "lessons.json").read_text(encoding="utf-8-sig"))
        sources = sync.lesson_sources(lesson_file)
        self.assertEqual(len(lesson_file["lessons"]), len(sources))
        self.assertTrue(all(items for items in sources.values()))


if __name__ == "__main__":
    unittest.main()
