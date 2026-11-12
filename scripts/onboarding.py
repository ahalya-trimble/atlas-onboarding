"""Local, validated SQLite store for the ATLAS Tutor's saved session summaries.

Commands: init, get-progress, save-session (JSON on stdin).
Only short summaries of what was discussed are stored, never a transcript.
"""

import argparse
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION = 1
# Older databases may contain extra tables from earlier versions; they are ignored.
SCHEMA = """
CREATE TABLE learner (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    consent INTEGER NOT NULL CHECK (consent = 1),
    revision INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def exact_fields(payload, fields):
    if not isinstance(payload, dict) or set(payload) != set(fields):
        raise ValueError(f"Expected exactly these fields: {', '.join(fields)}")


class Store:
    def __init__(self, atlas, curriculum=None):
        self.atlas = Path(atlas).resolve()
        if not (self.atlas / "Atlas.sln").is_file():
            raise ValueError("Target must be an Atlas checkout containing Atlas.sln")
        self.path = self.atlas / ".onboarding" / "onboarding.db"
        if (self.path.is_symlink() or self.path.parent.is_symlink()
                or not self.path.resolve().is_relative_to(self.atlas)):
            raise ValueError("Learner database must be a regular local path inside the Atlas checkout")
        curriculum = curriculum or Path(__file__).resolve().parent / "curriculum.json"
        data = json.loads(Path(curriculum).read_text(encoding="utf-8-sig"))
        # The curriculum is only the list of topic labels a saved summary may use.
        self.lessons = {lesson["id"]: lesson for lesson in data["lessons"]}
        if len(self.lessons) != len(data["lessons"]):
            raise ValueError("Duplicate curriculum lesson IDs")

    def connect(self):
        connection = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=5)
        try:
            connection.row_factory = sqlite3.Row
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        except sqlite3.Error:
            connection.close()
            raise
        if version != SCHEMA_VERSION:
            connection.close()
            raise ValueError("Unsupported database schema; preserve the file and reconcile explicitly")
        return connection

    def check_privacy(self):
        relative = ".onboarding/onboarding.db"
        ignored = subprocess.run(
            ["git", "-C", str(self.atlas), "check-ignore", "-q", "--", relative],
            capture_output=True, text=True)
        tracked = subprocess.run(
            ["git", "-C", str(self.atlas), "ls-files", "--", ".onboarding"],
            capture_output=True, text=True)
        if ignored.returncode != 0 or tracked.returncode != 0 or tracked.stdout.strip():
            raise ValueError(
                "Learner data must be Git-ignored and untracked; run the installer or reconcile Git first")

    def initialize(self):
        if self.path.exists():
            raise ValueError("Database already exists; use get-progress, not init")
        self.check_privacy()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents a second initializer from replacing a learner record.
        with self.path.open("xb"):
            pass
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript(SCHEMA)
            connection.execute("INSERT INTO learner VALUES (1, 1, 0, ?)", (now(),))
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        return self.progress()

    def revision(self, connection):
        learner = connection.execute("SELECT revision, consent FROM learner WHERE id = 1").fetchone()
        if learner is None or learner["consent"] != 1:
            raise ValueError("Missing or invalid learner record")
        return learner["revision"]

    def progress(self):
        if not self.path.exists():
            return {"saved": False, "consent": False, "revision": None, "lastSession": None,
                    "sessions": [],
                    "message": "Progress storage is not initialized. Show the automatic-saving notice, then run init."}
        with closing(self.connect()) as connection:
            # Keep all reads on one snapshot while another tutor may save.
            connection.execute("BEGIN")
            revision = self.revision(connection)
            sessions = [json.loads(row[0]) for row in
                        connection.execute("SELECT payload FROM sessions ORDER BY rowid")]
            return {"saved": True, "consent": True, "revision": revision,
                    "lastSession": sessions[-1] if sessions else None, "sessions": sessions}

    def write(self, action, payload):
        if action != "save-session":
            raise ValueError(f"Unknown write action: {action}")
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object")
        identifier = text(payload.get("id"), "id")
        revision = payload.get("expectedRevision")
        if type(revision) is not int or revision < 0:
            raise ValueError("expectedRevision must be a non-negative integer")
        self.check_privacy()
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self.revision(connection)
            existing = connection.execute(
                "SELECT payload FROM sessions WHERE id = ?", (identifier,)).fetchone()
            if existing:
                if existing[0] != canonical(payload):
                    raise ValueError("ID already exists with different content")
                return {"saved": True, "replayed": True, "revision": current, "id": identifier}
            if current != revision:
                raise ValueError(f"Stale revision: expected {revision}, actual {current}; reread progress")
            self.save_session(connection, payload)
            connection.execute("UPDATE learner SET revision = revision + 1 WHERE id = 1")
        # A separate read confirms the committed record before reporting success.
        with closing(self.connect()) as connection:
            saved = connection.execute(
                "SELECT payload FROM sessions WHERE id = ?", (identifier,)).fetchone()
            if saved is None or saved[0] != canonical(payload):
                raise ValueError("Read-back verification failed")
        return {"saved": True, "replayed": False, "revision": current + 1, "id": identifier}

    def save_session(self, connection, payload):
        exact_fields(payload, ("id", "expectedRevision", "currentTopicId",
                               "summary", "nextStep", "openQuestions"))
        if payload["currentTopicId"] not in self.lessons:
            raise ValueError("Unknown currentTopicId")
        for key in ("summary", "nextStep"):
            text(payload[key], key)
        questions = payload["openQuestions"]
        if not isinstance(questions, list):
            raise ValueError("openQuestions must be a list")
        seen = set()
        for question in questions:
            exact_fields(question, ("id", "topicId", "question", "status"))
            identifier = text(question["id"], "openQuestions.id")
            if identifier in seen:
                raise ValueError("Duplicate open question ID")
            seen.add(identifier)
            text(question["question"], "openQuestions.question")
            if question["topicId"] is not None and question["topicId"] not in self.lessons:
                raise ValueError("Unknown open question topic")
            if question["status"] not in ("open", "resolved"):
                raise ValueError("Invalid open question status")
        connection.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                           (payload["id"], now(), canonical(payload)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas", required=True, type=Path)
    parser.add_argument("command", choices=("init", "get-progress", "save-session"))
    # Accept the previous initialization flag without requiring it.
    parser.add_argument("--consent", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        store = Store(args.atlas)
        if args.command == "init":
            result = store.initialize()
        elif args.command == "get-progress":
            result = store.progress()
        else:
            result = store.write("save-session", json.load(sys.stdin))
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as error:
        print(json.dumps({"error": str(error), "saved": False}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
