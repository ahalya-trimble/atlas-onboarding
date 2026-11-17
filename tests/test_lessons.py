"""Checks the single lesson file (lessons.json) that the Explorer, the tutor and sync_docs all read."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "lessons.json").read_text(encoding="utf-8"))
LESSONS = DATA["lessons"]
ID = re.compile(r"^[a-z0-9-]{1,64}$")


class LessonFileTests(unittest.TestCase):
    def test_top_level_shape(self):
        for key in ("schemaVersion", "sourcePolicy", "videos", "phases", "glossary", "lessons"):
            self.assertIn(key, DATA)
        self.assertEqual(2, DATA["schemaVersion"])

    def test_ids_and_aliases_are_valid_and_unique(self):
        names = [n for lesson in LESSONS for n in [lesson["id"], *lesson.get("aliases", [])]]
        self.assertEqual(len(names), len(set(names)), "a lesson id or alias is used twice")
        for name in names:
            self.assertRegex(name, ID)

    def test_every_lesson_has_the_fields_the_explorer_needs(self):
        phases = {p["id"] for p in DATA["phases"]}
        for lesson in LESSONS:
            where = lesson["id"]
            for key in ("title", "tag", "hook", "goals", "sources", "points", "terms", "quiz", "prompts"):
                self.assertTrue(lesson.get(key) is not None, f"{where}: missing {key}")
            self.assertIn(lesson["phase"], phases, where)
            self.assertTrue(lesson["sources"], f"{where}: needs at least one source document")
            self.assertTrue(lesson["prompts"], where)

    def test_sources_are_allowed_documents(self):
        for lesson in LESSONS:
            for source in lesson["sources"]:
                self.assertEqual({"path", "sections"}, set(source), lesson["id"])
                self.assertTrue(source["path"].startswith(("docs/", "AGENTS.md", "README.md")), source["path"])
                self.assertIsInstance(source["sections"], list)

    def test_quiz_has_one_correct_answer_inside_the_options(self):
        for lesson in LESSONS:
            quiz = lesson["quiz"]
            self.assertGreaterEqual(len(quiz["o"]), 2, lesson["id"])
            self.assertIn(quiz["a"], range(len(quiz["o"])), lesson["id"])
            self.assertTrue(quiz["q"] and quiz["why"], lesson["id"])

    def test_terms_exist_in_the_glossary(self):
        for lesson in LESSONS:
            for term in lesson["terms"]:
                self.assertIn(term, DATA["glossary"], f"{lesson['id']}: unknown term {term}")

    def test_videos_and_screenshots_exist_when_referenced(self):
        for lesson in LESSONS:
            if lesson.get("video"):
                self.assertIn(lesson["video"]["key"] if isinstance(lesson["video"], dict) else lesson["video"],
                              DATA["videos"], lesson["id"])
            if lesson.get("shot"):
                self.assertTrue((ROOT / "explorer" / "assets" / "screens" / f"{lesson['shot']}.png").is_file(),
                                f"{lesson['id']}: screenshot {lesson['shot']}.png is missing")


if __name__ == "__main__":
    unittest.main()
