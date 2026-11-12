import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_server():
    spec = importlib.util.spec_from_file_location("explorer_server", ROOT / "explorer" / "server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


server = load_server()


class ExplorerServerTests(unittest.TestCase):
    def test_redacts_quoted_keys_values_and_headings(self):
        text = "\n".join([
            '# API key: "hunter2"',
            'password = "secret-value"',
            '"client_secret": "abc"',
            "AccountKey=abcd1234",
            "the secret of Atlas stays visible",
        ])
        hidden = server.redact(text)
        for secret in ("hunter2", "secret-value", "abc", "abcd1234"):
            self.assertNotIn(secret, hidden)
        self.assertIn("[redacted]", hidden)
        self.assertIn("the secret of Atlas stays visible", hidden)
        self.assertIn('"client_secret": "[redacted]"', hidden)

    def test_progress_save_uses_a_private_temp_file_and_rejects_stale_writes(self):
        folder = Path(tempfile.mkdtemp(prefix="explorer-state-"))
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        with mock.patch.object(server, "STATE", folder):
            server.save_progress(server.clean_progress({"xp": 1, "updatedAt": 10}))
            self.assertEqual([], list(folder.glob("explorer-progress-*.tmp")))
            saved = json.loads((folder / "explorer-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(10, saved["updatedAt"])
            with self.assertRaisesRegex(ValueError, "stale progress"):
                server.save_progress(server.clean_progress({"xp": 2, "updatedAt": 9}))
            self.assertEqual(1, json.loads((folder / "explorer-progress.json").read_text(encoding="utf-8"))["xp"])
            self.assertEqual([], list(folder.glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
