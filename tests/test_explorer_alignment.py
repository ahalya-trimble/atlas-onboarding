import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ExplorerAlignmentTests(unittest.TestCase):
    def test_generated_data_matches_curriculum(self):
        run = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_explorer.py"), "--check"],
                             capture_output=True, text=True)
        self.assertEqual(0, run.returncode, run.stderr)

    def test_every_curriculum_lesson_is_covered_once(self):
        curriculum = json.loads((ROOT / "curriculum.json").read_text(encoding="utf-8"))
        content = json.loads((ROOT / "content" / "lessons.json").read_text(encoding="utf-8"))
        covered = [t for item in content["lessons"] for t in [item["id"]] + item.get("covers", [])]
        self.assertEqual(sorted(item["id"] for item in curriculum["lessons"]), sorted(covered))


if __name__ == "__main__":
    unittest.main()
