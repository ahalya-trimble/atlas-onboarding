#!/usr/bin/env python3
"""Find which lessons are out of date because the Atlas documents changed.

Step 1 of keeping atlas-onboarding current. It does no AI and writes no lesson text.

  python scripts/sync_docs.py --atlas <atlas-checkout> check     compare the docs with the recorded baseline
  python scripts/sync_docs.py --atlas <atlas-checkout> accept    record the docs as "lessons match these"
  python scripts/sync_docs.py --atlas <atlas-checkout> accept --lesson ID [ID ...]   only for those lessons
  python scripts/sync_docs.py --atlas <atlas-checkout> accept --drifted              only the lessons check flags

How it works
  * lessons.json says which Atlas doc sections each lesson was written from.
  * sync/baseline.json stores a short fingerprint (hash) of every doc and of every section, taken the
    last time someone confirmed the lessons match the docs. It stores no document text.
  * check re-reads the docs, compares fingerprints and writes sync/drift-report.md
    (headings and lesson ids only, never document text).

Exit codes: 0 = lessons match the docs, 2 = something changed (CI and schedulers can act on this),
1 = error (for example the Atlas folder was not found).
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LESSONS = ROOT / "lessons.json"
BASELINE = ROOT / "sync" / "baseline.json"
REPORT = ROOT / "sync" / "drift-report.md"
SCAN_DIRS = ("docs/projects", "docs/Functionality")     # where new, uncovered docs are looked for
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
INTRO = "(intro)"


def fingerprint(text):
    clean = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).strip()
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()[:16]


def norm(name):
    return re.sub(r"\s+", " ", re.sub(r"[`*_]", "", name)).strip().lower()


def split_sections(text):
    """Return {heading: body}. Text before the first heading is '(intro)'. Duplicate headings get '#2', '#3'."""
    sections, current, lines, fenced = {}, INTRO, [], False

    def close():
        key, n = current, 2
        while key in sections:
            key, n = f"{current} #{n}", n + 1
        sections[key] = "\n".join(lines)

    for line in text.replace("\r\n", "\n").split("\n"):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        match = None if fenced else HEADING.match(line)
        if match:
            close()
            current, lines = match.group(2).strip(), []
        else:
            lines.append(line)
    close()
    return sections


def read_doc(atlas, rel):
    path = atlas / rel
    if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(atlas):
        return None
    sections = split_sections(path.read_text(encoding="utf-8-sig", errors="replace"))
    return {"hash": fingerprint("\n".join(f"{k}\n{v}" for k, v in sections.items())),
            "sections": {k: fingerprint(v) for k, v in sections.items()}}


def lesson_sources(lessons_data):
    """{lesson id: [(doc path, [cited section names])]}"""
    return {lesson["id"]: [(s["path"], s.get("sections", [])) for s in lesson["sources"]]
            for lesson in lessons_data["lessons"]}


def find_section(doc_sections, wanted):
    wanted = norm(wanted)
    for name in doc_sections:
        if norm(name) == wanted:
            return name
    return None


def git_branch(atlas):
    done = subprocess.run(["git", "-C", str(atlas), "rev-parse", "--abbrev-ref", "HEAD"],
                          capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else "unknown"


def checkout_problem(atlas):
    """Why this Atlas folder is not a trustworthy baseline source, or None.

    A baseline must describe what is on the remote branch, not a developer's unmerged work. Only applies to
    git checkouts; CI clones always pass.
    """
    def run(*args):
        return subprocess.run(["git", "-C", str(atlas), *args], capture_output=True, text=True)

    if run("rev-parse", "--git-dir").returncode != 0:
        return None
    if run("status", "--porcelain", "--", "docs").stdout.strip():
        return "the Atlas docs folder has uncommitted changes"
    ahead_behind = run("rev-list", "--left-right", "--count", "HEAD...@{u}")
    if ahead_behind.returncode == 0 and ahead_behind.stdout.split() != ["0", "0"]:
        return "the Atlas checkout is not at the same commit as its remote branch (pull or push first)"
    return None


def git_head(atlas):
    done = subprocess.run(["git", "-C", str(atlas), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else "unknown"


def load_baseline():
    if not BASELINE.is_file():
        return None
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def compare(atlas, lessons_data, baseline):
    """Return findings: per lesson reasons, plus doc-level notes. Pure data, no printing."""
    sources = lesson_sources(lessons_data)
    cited = {path for items in sources.values() for path, _ in items}
    now = {path: read_doc(atlas, path) for path in cited}
    lessons, notes = {}, []
    for lesson_id, items in sources.items():
        reasons = []
        for path, wanted_sections in items:
            doc, old = now[path], baseline["docs"].get(path)
            if doc is None:
                reasons.append(f"`{path}` is missing or unreadable in Atlas")
            elif old is None:
                reasons.append(f"`{path}` was not in the baseline (new source for this lesson)")
            elif wanted_sections:
                for wanted in wanted_sections:
                    name = find_section(doc["sections"], wanted)
                    old_name = find_section(old["sections"], wanted)
                    if name is None:
                        reasons.append(f"`{path}`: section '{wanted}' no longer exists (renamed or removed)")
                    elif old_name is None:
                        reasons.append(f"`{path}`: section '{wanted}' is new since the baseline")
                    elif doc["sections"][name] != old["sections"][old_name]:
                        reasons.append(f"`{path}`: section '{wanted}' changed")
            elif doc["hash"] != old["hash"]:
                reasons.append(f"`{path}` changed (the lesson cites the whole document)")
        if reasons:
            lessons[lesson_id] = reasons
    for path, doc in now.items():
        old = baseline["docs"].get(path)
        if doc and old and doc["hash"] != old["hash"]:
            used = {w for items in sources.values() for p, ws in items if p == path for w in ws}
            if used:
                other = [n for n in doc["sections"] if n in old["sections"]
                         and doc["sections"][n] != old["sections"][n]
                         and not any(norm(n) == norm(u) for u in used)]
                added = [n for n in doc["sections"] if n not in old["sections"]
                         and not any(norm(n) == norm(u) for u in used)]
                if other or added:
                    notes.append(f"`{path}`: sections no lesson cites also changed: "
                                 + ", ".join(sorted(set(other + added))))
    uncovered = []
    for folder in SCAN_DIRS:
        base = atlas / folder
        if base.is_dir():
            for file in sorted(base.rglob("*.md")):
                rel = file.relative_to(atlas).as_posix()
                if rel not in cited and not file.is_symlink():
                    uncovered.append(rel)
    return lessons, notes, uncovered


def write_report(atlas, lessons, notes, uncovered, baseline):
    lines = ["# Atlas documents vs. lessons", "",
             f"Checked: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ",
             f"Atlas branch: {git_branch(atlas)}  ",
             f"Atlas commit: {git_head(atlas)}  ",
             f"Baseline: {baseline.get('atlasBranch', '?')} @ {baseline.get('atlasCommit', 'unknown')} ({baseline.get('recorded', 'unknown')})", ""]
    if lessons:
        lines += ["## Lessons to review", ""]
        for lesson_id, reasons in lessons.items():
            lines += [f"### {lesson_id}"] + [f"- {r}" for r in reasons] + [""]
    else:
        lines += ["All lessons match the documents they cite.", ""]
    if notes:
        lines += ["## Changed, but not cited by any lesson section", ""] + [f"- {n}" for n in notes] + [""]
    if uncovered:
        lines += ["## Documents no lesson cites yet (possible new lesson or source)", ""] \
            + [f"- `{p}`" for p in uncovered] + [""]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def cmd_check(atlas, lessons_data):
    baseline = load_baseline()
    if baseline is None:
        print("No baseline yet. If the lessons are currently correct, record one with:\n"
              f"  python scripts/sync_docs.py --atlas \"{atlas}\" accept")
        return 1
    lessons, notes, uncovered = compare(atlas, lessons_data, baseline)
    write_report(atlas, lessons, notes, uncovered, baseline)
    if not (lessons or notes or uncovered):
        print("In sync: every lesson matches the documents it cites.")
        return 0
    print(f"{len(lessons)} lesson(s) to review", ("(" + ", ".join(lessons) + ")") if lessons else "")
    for lesson_id, reasons in lessons.items():
        print(f"  {lesson_id}")
        for reason in reasons:
            print(f"    - {reason.replace('`', '')}")
    for note in notes:
        print("  note:", note.replace("`", ""))
    for path in uncovered:
        print("  uncovered document:", path)
    print(f"Report: {REPORT.relative_to(ROOT)}")
    return 2 if lessons else 0


def cmd_accept(atlas, lessons_data, only, drifted=False, allow_local=False):
    problem = None if allow_local else checkout_problem(atlas)
    if problem:
        print(f"Refusing to record a baseline: {problem}. "
              "The baseline must match the remote Atlas branch. Let the pipeline create it, "
              "or pass --allow-local if you know what you are doing.", file=sys.stderr)
        return 1
    if drifted:       # only the lessons currently flagged by check (used by automation after the lessons were rewritten)
        baseline = load_baseline()
        if baseline is None:
            print("No baseline yet; run accept once without --drifted.", file=sys.stderr)
            return 1
        only = list(compare(atlas, lessons_data, baseline)[0])
        if not only:
            print("No drifted lessons; baseline unchanged.")
            return 0
    sources = lesson_sources(lessons_data)
    unknown = [i for i in (only or []) if i not in sources]
    if unknown:
        print("Unknown lesson id(s): " + ", ".join(unknown), file=sys.stderr)
        return 1
    baseline = load_baseline() or {"version": 1, "docs": {}}
    wanted = {path for i, items in sources.items() if not only or i in only for path, _ in items}
    for path in sorted(wanted):
        doc = read_doc(atlas, path)
        if doc is None:
            print(f"Cannot read {path} in the Atlas folder; baseline not changed for it.", file=sys.stderr)
            return 1
        baseline["docs"][path] = doc
    baseline["atlasCommit"] = git_head(atlas)
    baseline["atlasBranch"] = git_branch(atlas)
    baseline["recorded"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(baseline, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"Baseline recorded for {len(wanted)} document(s) at Atlas {baseline['atlasBranch']} @ {baseline['atlasCommit']}.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--atlas", required=True, type=Path, help="Atlas checkout (full, or just its docs folder)")
    parser.add_argument("--pull", action="store_true",
                        help="run 'git pull --ff-only' in the Atlas checkout first (never changes your files otherwise)")
    parser.add_argument("command", nargs="?", default="check", choices=("check", "accept"))
    parser.add_argument("--allow-local", action="store_true",
                        help="with accept: record the baseline even if the Atlas checkout differs from its remote branch")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--lesson", nargs="+", help="with accept: only these lesson ids")
    group.add_argument("--drifted", action="store_true", help="with accept: only the lessons that check currently flags")
    args = parser.parse_args()
    atlas = args.atlas.resolve()
    # A full checkout has Atlas.sln; a sparse CI checkout only needs the docs folder.
    if not ((atlas / "Atlas.sln").is_file() or (atlas / "docs" / "projects").is_dir()):
        print("Not an Atlas checkout (no Atlas.sln or docs/projects): " + str(atlas), file=sys.stderr)
        return 1
    if args.pull:
        done = subprocess.run(["git", "-C", str(atlas), "pull", "--ff-only"], capture_output=True, text=True)
        if done.returncode:
            print("git pull --ff-only failed (local changes or diverged branch?):\n" + done.stderr, file=sys.stderr)
            return 1
    lessons_data = json.loads(LESSONS.read_text(encoding="utf-8-sig"))
    if args.command == "accept":
        return cmd_accept(atlas, lessons_data, args.lesson, args.drifted, args.allow_local)
    return cmd_check(atlas, lessons_data)


if __name__ == "__main__":
    sys.exit(main())
