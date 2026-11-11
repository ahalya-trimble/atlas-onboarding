"""Local, validated SQLite persistence for the optional Atlas tutor."""

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE learner (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    consent INTEGER NOT NULL CHECK (consent = 1),
    revision INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE topics (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    understanding TEXT NOT NULL,
    last_attempt_id TEXT NOT NULL REFERENCES attempts(id),
    curriculum_hash TEXT NOT NULL
);
CREATE TABLE attempts (
    id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    result TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE reviews (
    topic_id TEXT PRIMARY KEY REFERENCES topics(id),
    stage INTEGER NOT NULL,
    due_date TEXT NOT NULL,
    last_attempt_id TEXT NOT NULL REFERENCES attempts(id)
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
        self.curriculum = json.loads(Path(curriculum).read_text(encoding="utf-8-sig"))
        self.lessons = {lesson["id"]: lesson for lesson in self.curriculum["lessons"]}
        self.modules = [module["id"] for module in self.curriculum["modules"]]
        if len(self.lessons) != len(self.curriculum["lessons"]):
            raise ValueError("Duplicate curriculum lesson IDs")
        for lesson in self.lessons.values():
            if lesson["moduleId"] not in self.modules:
                raise ValueError("Unknown curriculum module")
            if any(key not in self.lessons for key in lesson["prerequisites"]):
                raise ValueError("Unknown curriculum prerequisite")

    def signature(self, topic):
        lesson = self.lessons[topic]
        evidence = {key: lesson[key] for key in
                    ("assessment", "prerequisites", "moduleId", "sources", "objectives")}
        return hashlib.sha256(canonical(evidence).encode()).hexdigest()

    def connect(self):
        connection = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=5)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
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

    def state(self, connection):
        learner = connection.execute("SELECT revision, consent FROM learner WHERE id = 1").fetchone()
        if learner is None or learner["consent"] != 1:
            raise ValueError("Missing or invalid learner record")
        topics = {row["id"]: dict(row) for row in connection.execute("SELECT * FROM topics")}
        unknown = set(topics) - set(self.lessons)
        if unknown:
            raise ValueError(f"Saved lessons no longer exist: {', '.join(sorted(unknown))}")
        return learner["revision"], topics

    def requirements(self, lesson):
        earlier = self.modules[:self.modules.index(lesson["moduleId"])]
        return set(lesson["prerequisites"]) | {
            item["id"] for item in self.lessons.values() if item["moduleId"] in earlier}

    def valid_topics(self, topics):
        valid = set()
        for _ in self.lessons:
            previous = len(valid)
            for topic, saved in topics.items():
                if (saved["status"] == "completed"
                        and saved["curriculum_hash"] == self.signature(topic)
                        and self.requirements(self.lessons[topic]) <= valid):
                    valid.add(topic)
            if len(valid) == previous:
                break
        return valid

    def eligible(self, topics, lesson):
        return self.requirements(lesson) <= self.valid_topics(topics)

    def progress(self):
        if not self.path.exists():
            return {"saved": False, "consent": False, "revision": None,
                    "topics": [], "attempts": [], "dueReviews": [],
                    "freshnessUncertain": [], "nextTopic": next(iter(self.lessons)),
                    "lastSession": None, "sessions": [],
                    "message": "Progress storage is not initialized. Show the automatic-saving notice, then run init."}
        with closing(self.connect()) as connection:
            # Keep all reads on one snapshot while another tutor may save.
            connection.execute("BEGIN")
            revision, topics = self.state(connection)
            valid = self.valid_topics(topics)
            reviews = [dict(row) for row in connection.execute(
                "SELECT * FROM reviews WHERE due_date <= ? ORDER BY due_date, topic_id",
                (date.today().isoformat(),))]
            next_lesson = next((lesson for lesson in self.lessons.values()
                                if lesson["id"] not in valid
                                and self.eligible(topics, lesson)), None)
            session = connection.execute(
                "SELECT payload FROM sessions ORDER BY rowid DESC LIMIT 1").fetchone()
            attempts = [json.loads(row[0]) for row in
                        connection.execute("SELECT payload FROM attempts ORDER BY rowid")]
            return {
                "saved": True, "consent": True, "revision": revision,
                "topics": list(topics.values()), "attempts": attempts,
                "dueReviews": reviews,
                "freshnessUncertain": [key for key, value in topics.items()
                                       if value["curriculum_hash"] != self.signature(key)],
                "nextTopic": next_lesson["id"] if next_lesson else None,
                "lastSession": json.loads(session[0]) if session else None,
                "sessions": [json.loads(row[0]) for row in connection.execute(
                    "SELECT payload FROM sessions ORDER BY rowid")],
            }

    def write(self, action, payload):
        if action not in ("record-attempt", "record-coverage", "save-session"):
            raise ValueError(f"Unknown write action: {action}")
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object")
        identifier = text(payload.get("id"), "id")
        revision = payload.get("expectedRevision")
        if type(revision) is not int or revision < 0:
            raise ValueError("expectedRevision must be a non-negative integer")
        self.check_privacy()
        table = "sessions" if action == "save-session" else "attempts"
        with closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            current, topics = self.state(connection)
            existing = connection.execute(
                f"SELECT payload FROM {table} WHERE id = ?", (identifier,)).fetchone()
            if existing:
                if existing[0] != canonical(payload):
                    raise ValueError("ID already exists with different content")
                return {"saved": True, "replayed": True, "revision": current, "id": identifier}
            if current != revision:
                raise ValueError(f"Stale revision: expected {revision}, actual {current}; reread progress")
            if action == "record-attempt":
                self.record_attempt(connection, topics, payload)
            elif action == "record-coverage":
                self.record_coverage(connection, topics, payload)
            else:
                self.save_session(connection, payload)
            connection.execute("UPDATE learner SET revision = revision + 1 WHERE id = 1")
        # A separate read confirms the committed record before reporting success.
        with closing(self.connect()) as connection:
            saved = connection.execute(
                f"SELECT payload FROM {table} WHERE id = ?", (identifier,)).fetchone()
            if saved is None or saved[0] != canonical(payload):
                raise ValueError("Read-back verification failed")
        return {"saved": True, "replayed": False, "revision": current + 1, "id": identifier}

    def record_coverage(self, connection, topics, payload):
        exact_fields(payload, ("id", "expectedRevision", "topicId", "confirmation",
                               "summary", "sourcePaths", "sourceRevision"))
        topic = text(payload["topicId"], "topicId")
        if topic not in self.lessons:
            raise ValueError("Unknown topicId")
        if text(payload["confirmation"], "confirmation").strip().casefold() not in ("done", "next"):
            raise ValueError("Coverage requires the learner's Done or Next confirmation")
        text(payload["summary"], "summary")
        if not self.eligible(topics, self.lessons[topic]):
            raise ValueError("Prerequisites or earlier modules are incomplete or need revalidation")
        self.validate_sources(payload)
        connection.execute("INSERT INTO attempts VALUES (?, ?, ?, ?, ?, ?)",
                           (payload["id"], topic, "coverage", "covered", now(), canonical(payload)))
        connection.execute(
            "INSERT INTO topics VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "status=excluded.status, understanding=excluded.understanding, "
            "last_attempt_id=excluded.last_attempt_id, curriculum_hash=excluded.curriculum_hash",
            (topic, "completed", "covered", payload["id"], self.signature(topic)))
        connection.execute("DELETE FROM reviews WHERE topic_id = ?", (topic,))

    def record_attempt(self, connection, topics, payload):
        exact_fields(payload, (
            "id", "expectedRevision", "topicId", "questionId", "question", "answer",
            "kind", "assistance", "result", "correctConcepts", "missingConcepts",
            "misconceptions", "feedback", "sourcePaths", "sourceRevision",
        ))
        topic = text(payload["topicId"], "topicId")
        if topic not in self.lessons:
            raise ValueError("Unknown topicId")
        lesson = self.lessons[topic]
        assessment = lesson["assessment"]
        if payload["questionId"] != assessment["id"] or payload["question"] != assessment["question"]:
            raise ValueError("Question must match the curriculum assessment")
        for key in ("answer", "feedback"):
            text(payload[key], key)
        if payload["kind"] not in ("teach_back", "review"):
            raise ValueError("kind must be teach_back or review")
        if payload["assistance"] not in ("none", "hint", "solution_shown"):
            raise ValueError("Invalid assistance")
        if payload["result"] not in ("demonstrated", "needs_support"):
            raise ValueError("Invalid result")
        for key in ("correctConcepts", "missingConcepts", "misconceptions"):
            values = payload[key]
            if not isinstance(values, list) or any(not isinstance(item, str) or not item.strip()
                                                   for item in values):
                raise ValueError(f"{key} must be a list of non-empty strings")
            if len(values) != len(set(values)):
                raise ValueError(f"{key} must not contain duplicates")
        correct, missing = set(payload["correctConcepts"]), set(payload["missingConcepts"])
        required = set(assessment["requiredConcepts"])
        if correct & missing or correct | missing != required:
            raise ValueError("correctConcepts and missingConcepts must partition requiredConcepts exactly")
        demonstrated = payload["result"] == "demonstrated"
        if demonstrated and (missing or payload["misconceptions"]
                             or payload["assistance"] == "solution_shown"):
            raise ValueError("Demonstration requires all concepts, no misconceptions, and no shown solution")
        if not self.eligible(topics, lesson):
            raise ValueError("Prerequisites or earlier modules are incomplete or need revalidation")
        previous_review = connection.execute(
            "SELECT stage FROM reviews WHERE topic_id = ?", (topic,)).fetchone()
        if payload["kind"] == "review" and previous_review is None:
            raise ValueError("A review requires an earlier demonstrated assessment")
        self.validate_sources(payload)
        timestamp = now()
        connection.execute("INSERT INTO attempts VALUES (?, ?, ?, ?, ?, ?)",
                           (payload["id"], topic, payload["kind"], payload["result"],
                            timestamp, canonical(payload)))
        status = "completed" if demonstrated else (
            "needs_revisit" if previous_review else "in_progress")
        connection.execute(
            "INSERT INTO topics VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "status=excluded.status, understanding=excluded.understanding, "
            "last_attempt_id=excluded.last_attempt_id, curriculum_hash=excluded.curriculum_hash",
            (topic, status, payload["result"], payload["id"], self.signature(topic)))
        if demonstrated or previous_review:
            stage = (min(previous_review["stage"] + 1, 2)
                     if demonstrated and payload["kind"] == "review" else 0)
            days = (1, 3, 7)[stage]
            due = (date.today() + timedelta(days=days)).isoformat()
            connection.execute(
                "INSERT INTO reviews VALUES (?, ?, ?, ?) ON CONFLICT(topic_id) DO UPDATE SET "
                "stage=excluded.stage, due_date=excluded.due_date, last_attempt_id=excluded.last_attempt_id",
                (topic, stage, due, payload["id"]))

    def validate_sources(self, payload):
        revision = payload["sourceRevision"]
        if revision is not None:
            text(revision, "sourceRevision")
        sources = payload["sourcePaths"]
        if (not isinstance(sources, list)
                or any(not isinstance(item, str) or not item.strip() for item in sources)):
            raise ValueError("sourcePaths must be a list of non-empty strings")
        if len(sources) != len(set(sources)):
            raise ValueError("sourcePaths must not contain duplicates")
        if not sources:
            raise ValueError("At least one inspected source path is required")
        allowed_roots = self.curriculum["sourcePolicy"]["allowedRoots"]
        for source in sources:
            normalized = source.replace("\\", "/")
            parts = normalized.split("/")
            if (Path(source).is_absolute() or ":" in source or ".." in parts
                    or not any(normalized.startswith(root) for root in allowed_roots)):
                raise ValueError(f"Source outside allowed roots: {source}")
            resolved = (self.atlas / source).resolve()
            if not resolved.is_relative_to(self.atlas) or not resolved.is_file():
                raise ValueError(f"Missing or outside-checkout source: {source}")
            if resolved.suffix.lower() not in (".md", ".cs", ".xaml", ".ts", ".tsx",
                                               ".js", ".jsx", ".json", ".csproj"):
                raise ValueError(f"Unsupported evidence file: {source}")
            if resolved.suffix.lower() == ".json" and resolved.name.lower() != "package.json":
                raise ValueError("JSON configuration is not an allowed evidence source")

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
    parser.add_argument("command", choices=("init", "get-progress", "next-topic",
                                            "record-attempt", "record-coverage", "save-session"))
    # Accept the previous initialization flag without requiring it.
    parser.add_argument("--consent", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        store = Store(args.atlas)
        if args.command == "init":
            result = store.initialize()
        elif args.command in ("get-progress", "next-topic"):
            result = store.progress()
        else:
            result = store.write(args.command, json.load(sys.stdin))
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as error:
        print(json.dumps({"error": str(error), "saved": False}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
