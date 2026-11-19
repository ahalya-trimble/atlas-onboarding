import importlib.util
import json
import shutil
import tempfile
import threading
import time
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
    def test_local_doc_changes_lists_file_status_and_related_lessons(self):
        folder = Path(tempfile.mkdtemp(prefix="explorer-updates-"))
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        atlas = folder / "atlas"
        docs = atlas / "docs" / "projects"
        docs.mkdir(parents=True)
        (docs / "changed.md").write_text("New text", encoding="utf-8")
        (docs / "created.md").write_text("New file", encoding="utf-8")
        explorer = folder / "explorer"
        explorer.mkdir()
        (explorer / "atlas-baseline.json").write_text(json.dumps({
            "files": {
                "docs/projects/changed.md": server.doc_fingerprint("Old text"),
                "docs/projects/deleted.md": server.doc_fingerprint("Removed file"),
            },
            "changes": {
                "docs/projects/changed.md": "modified",
                "docs/projects/created.md": "created",
                "docs/projects/deleted.md": "deleted",
            },
        }), encoding="utf-8")
        (folder / "lessons.json").write_text(json.dumps({"lessons": [
            {"id": "example", "sources": [{"path": "docs/projects/changed.md"}]}
        ]}), encoding="utf-8")

        with mock.patch.object(server, "HERE", explorer), mock.patch.object(server, "ATLAS", atlas):
            changes = server.local_doc_changes()

        self.assertEqual([
            {"path": "docs/projects/changed.md", "status": "modified", "lessons": ["example"]},
            {"path": "docs/projects/created.md", "status": "created", "lessons": []},
            {"path": "docs/projects/deleted.md", "status": "deleted", "lessons": []},
        ], changes)

    def test_local_doc_inventory_includes_files_larger_than_the_read_limit(self):
        folder = Path(tempfile.mkdtemp(prefix="explorer-large-update-"))
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        atlas = folder / "atlas"
        docs = atlas / "docs" / "projects"
        docs.mkdir(parents=True)
        text = "large documentation " * 60_000
        path = docs / "large.md"
        path.write_text(text, encoding="utf-8")
        explorer = folder / "explorer"
        explorer.mkdir()
        (explorer / "atlas-baseline.json").write_text(json.dumps({
            "files": {"docs/projects/large.md": server.doc_fingerprint(text)},
            "changes": {},
        }), encoding="utf-8")
        (folder / "lessons.json").write_text(json.dumps({"lessons": []}), encoding="utf-8")

        with mock.patch.object(server, "HERE", explorer), mock.patch.object(server, "ATLAS", atlas):
            changes = server.local_doc_changes()

        self.assertEqual([], changes)

    def test_live_document_review_endpoints_are_removed(self):
        handler = server.Handler.__new__(server.Handler)
        handler._json = mock.Mock()

        handler.api_get("/api/outline", {})
        handler._json.assert_called_once_with({"error": "not found"}, 404)

        handler._json.reset_mock()
        handler._host_ok = lambda: True
        handler._api_ok = lambda: True
        handler.path = "/api/accept"
        handler.do_POST()
        handler._json.assert_called_once_with({"error": "not found"}, 404)

    def test_redacts_quoted_keys_values_and_headings(self):
        text = "\n".join([
            '# API key: "hunter2"',
            'password = "secret-value"',
            '"client_secret": "abc"',
            "AccountKey=abcd1234",
            'password = "ab\'cd"',
            'token = "ab\\"cd"',
            'api_key = "' + ("x" * 240) + '"',
            "the secret of Atlas stays visible",
        ])
        hidden = server.redact(text)
        for secret in ("hunter2", "secret-value", "abc", "abcd1234", "ab'cd", 'ab\\"cd', "x" * 240):
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

    def test_overlapping_saves_keep_the_newer_write(self):
        folder = Path(tempfile.mkdtemp(prefix="explorer-state-"))
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        entered, release = threading.Event(), threading.Event()
        original = server.load_progress
        calls = {"n": 0}

        def slow_load():
            value = original()
            calls["n"] += 1
            if calls["n"] == 1:
                entered.set()
                self.assertTrue(release.wait(3))
            return value

        finished = {"second": False}

        def second():
            server.save_progress(server.clean_progress({"xp": 2, "updatedAt": 20}))
            finished["second"] = True

        with mock.patch.object(server, "STATE", folder), mock.patch.object(server, "load_progress", slow_load):
            first = threading.Thread(target=lambda: server.save_progress(
                server.clean_progress({"xp": 1, "updatedAt": 10})))
            later = threading.Thread(target=second)
            first.start()
            self.assertTrue(entered.wait(2))
            later.start()
            time.sleep(0.2)
            self.assertFalse(finished["second"])
            release.set()
            first.join(3)
            later.join(3)
        saved = json.loads((folder / "explorer-progress.json").read_text(encoding="utf-8"))
        self.assertTrue(finished["second"])
        self.assertEqual(20, saved["updatedAt"])
        self.assertEqual(2, saved["xp"])

    def test_progress_write_requires_this_checkout(self):
        folder = Path(tempfile.mkdtemp(prefix="explorer-atlas-"))
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        with mock.patch.object(server, "ATLAS", folder):
            self.assertTrue(server.same_checkout(str(folder)))
            self.assertFalse(server.same_checkout(str(folder) + "-backup"))
            self.assertFalse(server.same_checkout("."))


if __name__ == "__main__":
    unittest.main()
