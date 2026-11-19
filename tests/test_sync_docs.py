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
UNCITED = """Notes

# Release notes
First release.

# Housekeeping
Nothing yet.
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
        self.uncited = self.atlas / "docs" / "projects" / "u.md"          # no lesson cites this one
        self.uncited.write_text(UNCITED, encoding="utf-8")
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

    def baseline(self):
        return json.loads(self.baseline_file.read_text(encoding="utf-8"))

    def drift(self):
        """(lessons, changes) compared with the recorded baseline."""
        return sync.compare(self.atlas, CURRICULUM, self.baseline())

    def report(self):
        self.check()
        return self.report_file.read_text(encoding="utf-8")

    # ---- nothing changed ----

    def test_unchanged_docs_are_in_sync(self):
        self.assertEqual(0, self.check())
        lessons, changes = self.drift()
        self.assertEqual({}, lessons)
        self.assertFalse(sync.has_changes(changes))

    def test_baseline_tracks_every_document_not_only_cited_ones(self):
        baseline = self.baseline()
        self.assertEqual("docs", baseline["scope"])
        self.assertEqual({"docs/projects/a.md", "docs/projects/u.md"}, set(baseline["docs"]))

    def test_headings_inside_code_fences_are_ignored(self):
        self.assertNotIn("not a heading", sync.split_sections(DOC))

    def test_whitespace_and_line_endings_do_not_count_as_changes(self):
        self.doc.write_bytes(DOC.replace("\n", "\r\n").replace("Technicians.", "Technicians.   ").encode())
        self.uncited.write_bytes(UNCITED.replace("\n", "\r\n").replace("First release.", "First release.  ").encode())
        self.assertEqual(0, self.check())
        self.assertFalse(sync.has_changes(self.drift()[1]))

    def test_non_markdown_files_are_ignored(self):
        (self.atlas / "docs" / "projects" / "diagram.png").write_bytes(b"png")
        (self.atlas / "docs" / "projects" / "notes.txt").write_text("text", encoding="utf-8")
        self.assertEqual(0, self.check())

    # ---- text changes, cited and uncited ----

    def test_changed_cited_section_flags_only_the_lesson_that_cites_it(self):
        self.doc.write_text(DOC.replace("Technicians.", "Technicians and managers."), encoding="utf-8")
        lessons, changes = self.drift()
        self.assertEqual({"one", "two"}, set(lessons))      # 'two' cites the whole document
        self.assertIn("section 'Who uses it' changed", lessons["one"][0])
        self.assertEqual([("docs/projects/a.md", "Who uses it", ["one", "two"])],
                         [(e["path"], e["section"], e["lessons"]) for e in changes["modified"]])
        self.assertEqual(2, self.check())

    def test_change_in_uncited_section_of_a_cited_document_triggers_review(self):
        # lesson 'one' does not cite 'Other', but lesson 'two' cites the whole document
        self.doc.write_text(DOC.replace("Unrelated.", "Different."), encoding="utf-8")
        lessons, changes = self.drift()
        self.assertNotIn("one", lessons)
        self.assertIn("two", lessons)
        self.assertEqual([("Other", ["two"])], [(e["section"], e["lessons"]) for e in changes["modified"]])
        self.assertEqual(2, self.check())

    def test_text_changed_in_an_uncited_document_triggers_review(self):
        self.uncited.write_text(UNCITED.replace("First release.", "First and second release."), encoding="utf-8")
        lessons, changes = self.drift()
        self.assertEqual({}, lessons)                        # no lesson cites it ...
        self.assertEqual([("docs/projects/u.md", "Release notes", [])],
                         [(e["path"], e["section"], e["lessons"]) for e in changes["modified"]])
        self.assertEqual(2, self.check())                    # ... but it is still reviewed
        self.assertIn("### Not cited by any lesson", self.report())

    def test_text_added_outside_any_heading_triggers_review(self):
        self.uncited.write_text(UNCITED.replace("Notes", "Notes and a new intro line"), encoding="utf-8")
        self.assertEqual(2, self.check())
        self.assertEqual("(intro)", self.drift()[1]["modified"][0]["section"])

    # ---- sections added, renamed, removed ----

    def test_added_section_triggers_review_in_cited_and_uncited_documents(self):
        self.uncited.write_text(UNCITED + "\n# Known issues\nSomething.\n", encoding="utf-8")
        self.assertEqual(2, self.check())
        self.assertEqual([("docs/projects/u.md", "Known issues", [])],
                         [(e["path"], e["section"], e["lessons"]) for e in self.drift()[1]["added"]])
        self.doc.write_text(DOC + "\n# Brand new\nText.\n", encoding="utf-8")
        added = {(e["path"], e["section"]): e["lessons"] for e in self.drift()[1]["added"]}
        self.assertEqual(["two"], added[("docs/projects/a.md", "Brand new")])     # the whole-document lesson covers it
        self.assertIn("### Added sections", self.report())

    def test_removed_section_triggers_review(self):
        self.uncited.write_text(UNCITED.replace("# Housekeeping\nNothing yet.\n", ""), encoding="utf-8")
        self.assertEqual(2, self.check())
        self.assertEqual(["Housekeeping"], [e["section"] for e in self.drift()[1]["removed"]])
        self.assertIn("### Removed sections", self.report())

    def test_renamed_section_with_the_same_text_is_reported_as_a_rename(self):
        self.uncited.write_text(UNCITED.replace("# Release notes", "# Changelog"), encoding="utf-8")
        changes = self.drift()[1]
        self.assertEqual([("Release notes", "Changelog")], [(e["old"], e["new"]) for e in changes["renamed_sections"]])
        self.assertEqual([], changes["added"] + changes["removed"])
        self.assertEqual(2, self.check())
        self.assertIn("'Release notes' -> 'Changelog'", self.report())

    def test_renamed_cited_section_is_reported_for_its_lesson(self):
        self.doc.write_text(DOC.replace("# Purpose", "# Goal"), encoding="utf-8")
        lessons, changes = self.drift()
        self.assertIn("no longer exists", lessons["one"][0])
        self.assertEqual([("Purpose", "Goal")], [(e["old"], e["new"]) for e in changes["renamed_sections"]])
        self.assertEqual(["one", "two"], changes["renamed_sections"][0]["lessons"])

    # ---- files created, renamed, deleted ----

    def test_deleted_cited_document_is_reported(self):
        self.doc.unlink()
        lessons, changes = self.drift()
        self.assertIn("missing", lessons["one"][0])
        self.assertEqual([{"path": "docs/projects/a.md", "lessons": ["one", "two"]}], changes["deleted"])
        self.assertEqual(2, self.check())

    def test_deleted_uncited_document_triggers_review(self):
        self.uncited.unlink()
        lessons, changes = self.drift()
        self.assertEqual({}, lessons)
        self.assertEqual(["docs/projects/u.md"], [d["path"] for d in changes["deleted"]])
        self.assertEqual(2, self.check())
        self.assertIn("### Deleted files", self.report())

    def test_new_document_triggers_review_even_if_no_lesson_cites_it(self):
        (self.atlas / "docs" / "projects" / "b.md").write_text("# New\nText", encoding="utf-8")
        (self.atlas / "docs" / "elsewhere").mkdir()
        (self.atlas / "docs" / "elsewhere" / "c.md").write_text("# Deep\nText", encoding="utf-8")   # any folder under docs/
        self.assertEqual(["docs/elsewhere/c.md", "docs/projects/b.md"], self.drift()[1]["new"])
        self.assertEqual(2, self.check())
        self.assertIn("### New files", self.report())

    def test_agents_md_in_the_atlas_root_is_tracked(self):
        (self.atlas / "AGENTS.md").write_text("# Rules\nOne.\n", encoding="utf-8")
        self.assertEqual(["AGENTS.md"], self.drift()[1]["new"])
        self.accept()
        self.assertEqual(0, self.check())
        (self.atlas / "AGENTS.md").write_text("# Rules\nTwo.\n", encoding="utf-8")
        self.assertEqual(2, self.check())

    def test_renamed_document_is_not_reported_as_new_plus_deleted(self):
        self.doc.rename(self.atlas / "docs" / "projects" / "a-renamed.md")
        lessons, changes = self.drift()
        self.assertEqual([], changes["new"] + changes["deleted"])
        self.assertEqual([{"old": "docs/projects/a.md", "new": "docs/projects/a-renamed.md",
                           "edited": False, "lessons": ["one", "two"]}], changes["renamed"])
        self.assertIn("renamed or moved to `docs/projects/a-renamed.md`", lessons["one"][0])
        self.assertEqual(2, self.check())
        self.assertIn("### Renamed or moved files", self.report())

    def test_renamed_and_edited_document_is_still_recognized_and_diffed(self):
        moved = self.atlas / "docs" / "projects" / "a-moved.md"
        self.doc.unlink()
        moved.write_text(DOC.replace("Technicians.", "Everybody."), encoding="utf-8")
        changes = self.drift()[1]
        self.assertTrue(changes["renamed"][0]["edited"])
        self.assertEqual([("docs/projects/a-moved.md", "Who uses it")],
                         [(e["path"], e["section"]) for e in changes["modified"]])
        self.assertEqual([], changes["new"] + changes["deleted"])

    def test_unrelated_new_and_deleted_documents_are_not_mistaken_for_a_rename(self):
        self.uncited.unlink()
        (self.atlas / "docs" / "projects" / "z.md").write_text("# Totally\nDifferent\n# Headings\nHere\n", encoding="utf-8")
        changes = self.drift()[1]
        self.assertEqual(([], ["docs/projects/z.md"]), (changes["renamed"], changes["new"]))
        self.assertEqual(["docs/projects/u.md"], [d["path"] for d in changes["deleted"]])

    # ---- the report ----

    def test_report_is_categorized_with_paths_and_headings(self):
        self.doc.write_text(DOC.replace("Technicians.", "Technicians and managers."), encoding="utf-8")
        self.uncited.write_text(UNCITED.replace("First release.", "Changed."), encoding="utf-8")
        (self.atlas / "docs" / "projects" / "b.md").write_text("# New\nText", encoding="utf-8")
        report = self.report()
        for heading in ("## New / Renamed / Deleted Files", "### New files", "## Modified Sections",
                        "### Cited by a lesson", "### Not cited by any lesson", "## Lessons to review"):
            self.assertIn(heading, report)
        self.assertIn("`docs/projects/b.md`", report)
        self.assertIn("`docs/projects/a.md`: 'Who uses it' | lessons: `one`, `two`", report)
        self.assertIn("`docs/projects/u.md`: 'Release notes'", report)

    def test_doc_inventory_reports_created_modified_and_deleted_files(self):
        baseline = {"files": {
            "docs/projects/a.md": sync.fingerprint(DOC),
            "docs/projects/removed.md": "old-hash",
        }}
        self.doc.write_text(DOC.replace("Technicians.", "Technicians and managers."), encoding="utf-8")
        (self.atlas / "docs" / "projects" / "new.txt").write_text("New doc", encoding="utf-8")
        changes = sync.compare_doc_files(self.atlas, baseline)
        self.assertEqual([
            {"path": "docs/projects/a.md", "status": "modified"},
            {"path": "docs/projects/new.txt", "status": "created"},
            {"path": "docs/projects/removed.md", "status": "deleted"},
        ], changes)

    def test_docs_only_drift_is_reported_without_marking_lessons_stale(self):
        created = self.atlas / "docs" / "projects" / "new.md"
        created.write_text("# New doc\nNo lesson uses this yet.", encoding="utf-8")
        self.assertEqual(2, self.check())
        report = self.report_file.read_text(encoding="utf-8")
        self.assertIn("created: `docs/projects/new.md`", report)
        self.assertNotIn("## Lessons to review", report)

    def test_files_only_accept_updates_inventory_not_lesson_sections(self):
        before = json.loads(self.baseline_file.read_text(encoding="utf-8"))
        (self.atlas / "docs" / "projects" / "new.md").write_text("# New", encoding="utf-8")
        result = self.run_quiet(sync.cmd_accept, self.atlas, CURRICULUM, None, False, False, True)
        after = json.loads(self.baseline_file.read_text(encoding="utf-8"))
        self.assertEqual(0, result)
        self.assertEqual(before["docs"], after["docs"])
        self.assertIn("docs/projects/new.md", after["files"])
        self.assertEqual("created", after["changes"]["docs/projects/new.md"])

    def test_report_contains_names_never_document_text(self):
        self.doc.write_text(DOC.replace("Technicians.", "SECRET-VALUE-123"), encoding="utf-8")
        self.uncited.write_text(UNCITED.replace("First release.", "SECRET-VALUE-456"), encoding="utf-8")
        report = self.report()
        self.assertIn("Who uses it", report)
        for secret in ("SECRET-VALUE-123", "SECRET-VALUE-456"):
            self.assertNotIn(secret, report)
            self.assertNotIn(secret, self.baseline_file.read_text(encoding="utf-8"))

    # ---- baselines recorded before every document was tracked ----

    def test_old_baseline_without_scope_still_works_and_asks_for_a_re_record(self):
        legacy = self.baseline()
        del legacy["scope"]
        legacy["docs"] = {"docs/projects/a.md": legacy["docs"]["docs/projects/a.md"]}      # cited documents only
        self.baseline_file.write_text(json.dumps(legacy), encoding="utf-8")
        (self.atlas / "docs" / "projects" / "b.md").write_text("# New\nText", encoding="utf-8")
        self.uncited.write_text(UNCITED.replace("First release.", "Changed."), encoding="utf-8")
        self.assertEqual(0, self.check())                    # cannot tell what is new, so it does not guess
        self.assertIn("Old baseline", self.report_file.read_text(encoding="utf-8"))
        self.doc.write_text(DOC.replace("Technicians.", "Changed."), encoding="utf-8")
        self.assertEqual(2, self.check())                    # cited changes are still detected
        self.accept()                                        # a full accept upgrades it
        self.assertEqual("docs", self.baseline()["scope"])
        self.assertEqual(0, self.check())

    # ---- accept ----

    def test_accept_for_one_lesson_leaves_others_untouched(self):
        other = self.atlas / "docs" / "projects" / "c.md"
        other.write_text("# X\n1", encoding="utf-8")
        curriculum = {"lessons": CURRICULUM["lessons"] + [
            {"id": "three", "sources": [{"path": "docs/projects/c.md", "sections": ["X"]}]}]}
        self.run_quiet(sync.cmd_accept, self.atlas, curriculum, None)
        other.write_text("# X\n2", encoding="utf-8")
        self.doc.write_text(DOC.replace("Technicians.", "Changed."), encoding="utf-8")
        self.run_quiet(sync.cmd_accept, self.atlas, curriculum, ["one"])
        lessons = sync.compare(self.atlas, curriculum, self.baseline())[0]
        self.assertNotIn("one", lessons)
        self.assertIn("three", lessons)

    def test_accept_drifted_moves_only_flagged_lessons(self):
        self.doc.write_text(DOC.replace("Technicians.", "Changed."), encoding="utf-8")
        self.assertEqual(2, self.check())
        self.assertEqual(0, self.run_quiet(sync.cmd_accept, self.atlas, CURRICULUM, None, True))
        self.assertEqual(0, self.check())
        self.assertEqual(0, self.run_quiet(sync.cmd_accept, self.atlas, CURRICULUM, None, True))   # nothing left to accept

    def test_accept_drifted_also_records_skipped_changes_new_and_deleted_documents(self):
        # The agent decided none of these needs a lesson edit; the baseline must still move forward.
        self.uncited.write_text(UNCITED.replace("First release.", "Changed."), encoding="utf-8")
        (self.atlas / "docs" / "projects" / "b.md").write_text("# New\nText", encoding="utf-8")
        self.assertEqual(2, self.check())
        self.assertEqual(0, self.run_quiet(sync.cmd_accept, self.atlas, CURRICULUM, None, True))
        self.assertEqual(0, self.check())
        self.assertIn("docs/projects/b.md", self.baseline()["docs"])
        self.uncited.unlink()
        self.assertEqual(2, self.check())
        self.assertEqual(0, self.run_quiet(sync.cmd_accept, self.atlas, CURRICULUM, None, True))
        self.assertNotIn("docs/projects/u.md", self.baseline()["docs"])
        self.assertEqual(0, self.check())

    def test_accept_drifted_follows_a_rename_once_the_lessons_point_at_the_new_path(self):
        self.doc.rename(self.atlas / "docs" / "projects" / "a-renamed.md")
        self.assertEqual(1, self.run_quiet(sync.cmd_accept, self.atlas, CURRICULUM, None, True))   # lessons still cite the old path
        fixed = {"lessons": [{"id": i["id"], "sources": [{"path": "docs/projects/a-renamed.md",
                                                           "sections": i["sources"][0]["sections"]}]}
                             for i in CURRICULUM["lessons"]]}
        self.assertEqual(0, self.run_quiet(sync.cmd_accept, self.atlas, fixed, None, True))
        self.assertEqual({"docs/projects/a-renamed.md", "docs/projects/u.md"}, set(self.baseline()["docs"]))
        self.assertEqual(0, self.run_quiet(sync.cmd_check, self.atlas, fixed))

    def test_accept_drifted_refuses_while_a_lesson_still_cites_a_deleted_document(self):
        self.doc.unlink()
        before = self.baseline_file.read_text(encoding="utf-8")
        self.assertEqual(1, self.run_quiet(sync.cmd_accept, self.atlas, CURRICULUM, None, True))
        self.assertEqual(before, self.baseline_file.read_text(encoding="utf-8"))

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
        self.assertIn("atlasBranch", self.baseline())

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
