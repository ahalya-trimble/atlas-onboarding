#!/usr/bin/env python3
"""Find what changed in the Atlas documents since the lessons were last confirmed, so an agent can review it.

Step 1 of keeping atlas-onboarding current. It does no AI and writes no lesson text.

  python scripts/sync_docs.py --atlas <atlas-checkout> check     compare the docs with the recorded baseline
  python scripts/sync_docs.py --atlas <atlas-checkout> accept    record ALL docs as "lessons match these"
  python scripts/sync_docs.py --atlas <atlas-checkout> accept --drifted              record everything check flags
  python scripts/sync_docs.py --atlas <atlas-checkout> accept --lesson ID [ID ...]   only the docs those lessons cite

How it works
  * sync/baseline.json stores a short fingerprint (hash) of every Atlas document (docs/**/*.md and AGENTS.md)
    and of every section in it, taken the last time someone confirmed the lessons match the docs.
    It stores no document text.
  * check re-reads the docs, compares fingerprints and writes sync/drift-report.md
    (paths, headings and lesson ids only, never document text).
  * ANY difference counts as drift, whether or not a lesson cites it:
      - a file created, renamed or deleted;
      - a section added, renamed or removed (in any file);
      - text changed anywhere in a file (a cited or an uncited section).
    Whitespace and line-ending differences are ignored.
  * An agent then reviews each item and decides: update a lesson, create a lesson, or skip it with a reason.
    Skipping still moves the baseline forward (accept --drifted), so the same item is not reported again.

Exit codes: 0 = nothing changed, 2 = something changed (CI and schedulers can act on this),
1 = error (for example the Atlas folder was not found, or there is no baseline yet).
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
DOCS_DIR = "docs"                  # every *.md below it is tracked
ROOT_DOCS = ("AGENTS.md",)         # tracked Markdown files in the Atlas root
SCOPE = "docs"                     # baseline "scope" value written by this version (older baselines have none)
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
INTRO = "(intro)"
RENAME_SIMILARITY = 0.6            # shared headings (Jaccard) needed to call a missing + a new file "the same file, moved"


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


def shown(path):
    """A path for messages: relative to this repository when it is inside it, otherwise the full path
    (another folder or another drive, where a relative path does not exist)."""
    try:
        return str(Path(path).resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def read_doc(atlas, rel):
    # Compare fully resolved paths on both sides. A path given in Windows short form (RUNNER~1) or on another
    # drive than this repository would otherwise never match its resolved counterpart.
    atlas = Path(atlas).resolve()
    path = atlas / rel
    if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(atlas):
        return None
    sections = split_sections(path.read_text(encoding="utf-8-sig", errors="replace"))
    return {"hash": fingerprint("\n".join(f"{k}\n{v}" for k, v in sections.items())),
            "sections": {k: fingerprint(v) for k, v in sections.items()}}


def scan_doc_files(atlas):
    """Return fingerprints for readable Markdown and text files under docs/."""
    root = Path(atlas).resolve() / "docs"
    files = {}
    if not root.is_dir():
        return files
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in (".md", ".txt"):
            continue
        rel = path.relative_to(root.parent).as_posix()
        doc = read_doc(atlas, rel)
        if doc is None:
            raise ValueError(f"Cannot inventory Atlas doc: {rel}")
        files[rel] = fingerprint(path.read_text(encoding="utf-8-sig", errors="replace"))
    return files


def compare_doc_files(atlas, baseline):
    """Return created, modified, and deleted docs; None means an older baseline lacks inventory."""
    if "files" not in baseline:
        return None
    previous = baseline["files"]
    if not isinstance(previous, dict):
        raise ValueError("Atlas docs file inventory is malformed")
    if any(not isinstance(path, str) or not path.startswith("docs/")
           or ".." in path.replace("\\", "/").split("/") or not isinstance(digest, str)
           for path, digest in previous.items()):
        raise ValueError("Atlas docs file inventory contains an invalid entry")
    current = scan_doc_files(atlas)
    changes = []
    for path in sorted(set(previous) | set(current)):
        if path not in previous:
            status = "created"
        elif path not in current:
            status = "deleted"
        elif previous[path] != current[path]:
            status = "modified"
        else:
            continue
        changes.append({"path": path, "status": status})
    return changes


def lesson_sources(lessons_data):
    """{lesson id: [(doc path, [cited section names])]}"""
    return {lesson["id"]: [(s["path"], s.get("sections", [])) for s in lesson["sources"]]
            for lesson in lessons_data["lessons"]}


def cited_paths(sources):
    return {path for items in sources.values() for path, _ in items}


def citers(sources, path, section=None):
    """Lesson ids that cite this document (section=None) or this section of it. A lesson that lists no sections
    cites the whole document, so it covers every section."""
    found = set()
    for lesson_id, items in sources.items():
        for doc_path, wanted in items:
            if doc_path == path and (section is None or not wanted or any(norm(section) == norm(w) for w in wanted)):
                found.add(lesson_id)
    return sorted(found)


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


def tracked_paths(atlas):
    """Every Markdown document we watch: docs/**/*.md and the root documents."""
    atlas = Path(atlas).resolve()
    found = set()
    docs = atlas / DOCS_DIR
    if docs.is_dir():
        for file in docs.rglob("*"):
            if file.suffix.lower() == ".md" and file.is_file() and not file.is_symlink():
                found.add(file.relative_to(atlas).as_posix())
    found.update(name for name in ROOT_DOCS if (atlas / name).is_file())
    return found


def snapshot(atlas, sources, everything=True):
    """{path: doc or None}. Every tracked document plus every cited one (None = cited but missing/unreadable).
    With everything=False only the cited ones, which is how a baseline from before full tracking is compared."""
    paths = cited_paths(sources) | (tracked_paths(atlas) if everything else set())
    return {path: read_doc(atlas, path) for path in sorted(paths)}


def diff_sections(old, new):
    """Compare {heading: fingerprint} maps. Returns (added, removed, renamed [(old, new)], modified)."""
    added = [n for n in new if n not in old]
    removed = [n for n in old if n not in new]
    modified = [n for n in new if n in old and new[n] != old[n]]
    renamed, empty = [], fingerprint("")
    for name in list(removed):
        if old[name] == empty:
            continue                      # empty sections look identical; cannot tell which one was renamed
        twins = [a for a in added if new[a] == old[name]]
        if len(twins) == 1 and sum(1 for r in removed if old[r] == old[name]) == 1:
            renamed.append((name, twins[0]))
            removed.remove(name)
            added.remove(twins[0])
    return added, removed, renamed, modified


def pair_files(gone, new, before, now):
    """Match deleted files with new ones that are the same file moved: identical content first, then mostly the
    same headings (the file was also edited). Returns (pairs [(old, new, edited)], still_gone, still_new)."""
    pairs, gone, new = [], list(gone), list(new)
    for old in list(gone):
        for path in new:
            if now[path]["hash"] == before[old]["hash"]:
                pairs.append((old, path, False))
                gone.remove(old)
                new.remove(path)
                break
    scored = []
    for old in gone:
        old_heads = {norm(h) for h in before[old]["sections"] if h != INTRO}
        for path in new:
            new_heads = {norm(h) for h in now[path]["sections"] if h != INTRO}
            if len(old_heads) >= 2 and len(new_heads) >= 2:
                score = len(old_heads & new_heads) / len(old_heads | new_heads)
                if score >= RENAME_SIMILARITY:
                    scored.append((score, old, path))
    for _, old, path in sorted(scored, reverse=True):
        if old in gone and path in new:
            pairs.append((old, path, True))
            gone.remove(old)
            new.remove(path)
    return pairs, gone, new


def empty_changes(legacy=False):
    return {"legacy": legacy, "new": [], "deleted": [], "renamed": [], "added": [], "removed": [],
            "renamed_sections": [], "modified": []}


def has_changes(changes):
    return any(changes[k] for k in ("new", "deleted", "renamed", "added", "removed", "renamed_sections", "modified"))


def compare(atlas, lessons_data, baseline):
    """Return (lessons, changes). Pure data, no printing.

    lessons: {lesson id: [reasons]} for lessons whose cited documents or sections changed.
    changes: everything that differs from the baseline, cited or not (see empty_changes for the keys).
    """
    atlas = Path(atlas).resolve()
    sources = lesson_sources(lessons_data)
    cited = cited_paths(sources)
    legacy = baseline.get("scope") != SCOPE
    now_all = snapshot(atlas, sources, everything=not legacy)
    now = {p: d for p, d in now_all.items() if d is not None}
    before = {p: d for p, d in baseline["docs"].items() if not legacy or p in cited}
    changes = empty_changes(legacy)

    gone, new = sorted(set(before) - set(now)), sorted(set(now) - set(before))
    pairs, gone, new = pair_files(gone, new, before, now)
    moved = {old: path for old, path, _ in pairs}
    changes["new"] = new
    changes["deleted"] = [{"path": p, "lessons": citers(sources, p)} for p in gone]
    changes["renamed"] = [{"old": o, "new": n, "edited": e, "lessons": citers(sources, o)} for o, n, e in pairs]

    def add_section_changes(path, old_doc, new_doc, lesson_path):
        added, removed, renamed, modified = diff_sections(old_doc["sections"], new_doc["sections"])
        changes["added"] += [{"path": path, "section": s, "lessons": citers(sources, lesson_path, s)} for s in added]
        changes["removed"] += [{"path": path, "section": s, "lessons": citers(sources, lesson_path, s)} for s in removed]
        changes["renamed_sections"] += [{"path": path, "old": o, "new": n,
                                         "lessons": sorted(set(citers(sources, lesson_path, o)) | set(citers(sources, lesson_path, n)))}
                                        for o, n in renamed]
        changes["modified"] += [{"path": path, "section": s, "lessons": citers(sources, lesson_path, s)} for s in modified]

    for path in sorted(set(before) & set(now)):
        if now[path]["hash"] != before[path]["hash"]:
            add_section_changes(path, before[path], now[path], path)
    for old, path, _ in pairs:
        if now[path]["hash"] != before[old]["hash"]:
            add_section_changes(path, before[old], now[path], old)

    lessons = {}
    for lesson_id, items in sources.items():
        reasons = []
        for path, wanted_sections in items:
            target = moved.get(path, path)
            doc, old = now.get(target), before.get(path)
            if path in moved:
                reasons.append(f"`{path}` was renamed or moved to `{target}` (update this lesson's source path)")
            if doc is None:
                reasons.append(f"`{path}` is missing or unreadable in Atlas")
            elif old is None:
                reasons.append(f"`{path}` was not in the baseline (new source for this lesson)")
            elif wanted_sections:
                for wanted in wanted_sections:
                    name = find_section(doc["sections"], wanted)
                    old_name = find_section(old["sections"], wanted)
                    if name is None:
                        reasons.append(f"`{target}`: section '{wanted}' no longer exists (renamed or removed)")
                    elif old_name is None:
                        reasons.append(f"`{target}`: section '{wanted}' is new since the baseline")
                    elif doc["sections"][name] != old["sections"][old_name]:
                        reasons.append(f"`{target}`: section '{wanted}' changed")
            elif doc["hash"] != old["hash"]:
                reasons.append(f"`{target}` changed (the lesson cites the whole document)")
        if reasons:
            lessons[lesson_id] = reasons
    return lessons, changes


def lesson_list(ids):
    return ", ".join(f"`{i}`" for i in ids) if ids else "none"


def write_report(atlas, lessons, changes, baseline):
    lines = ["# Atlas documents vs. lessons", "",
             f"Checked: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ",
             f"Atlas branch: {git_branch(atlas)}  ",
             f"Atlas commit: {git_head(atlas)}  ",
             f"Baseline: {baseline.get('atlasBranch', '?')} @ {baseline.get('atlasCommit', 'unknown')} ({baseline.get('recorded', 'unknown')})", ""]
    if changes["legacy"]:
        lines += ["> **Old baseline.** It tracks only the documents lessons cite, so new, renamed and deleted files and "
                  "uncited sections cannot be detected yet. Re-record it once (run the workflow with `init_baseline`, "
                  "or `accept`) to watch every document.", ""]
    if not (lessons or has_changes(changes)):
        lines += ["Nothing changed: every document matches the baseline.", ""]
    else:
        counts = [("new files", len(changes["new"])), ("renamed files", len(changes["renamed"])),
                  ("deleted files", len(changes["deleted"])), ("added sections", len(changes["added"])),
                  ("renamed sections", len(changes["renamed_sections"])), ("removed sections", len(changes["removed"])),
                  ("modified sections", len(changes["modified"])), ("lessons to review", len(lessons))]
        lines += ["**Summary:** " + ", ".join(f"{n} {label}" for label, n in counts if n), "",
                  "For each item below, inspect the document in `atlas/`, then decide: update an existing lesson, "
                  "create a new lesson, or skip it and say why. See `AGENTS.md`.", ""]

    if changes["new"] or changes["renamed"] or changes["deleted"]:
        lines += ["## New / Renamed / Deleted Files", ""]
        if changes["new"]:
            lines += ["### New files", ""] + [f"- `{p}`" for p in changes["new"]] + [""]
        if changes["renamed"]:
            lines += ["### Renamed or moved files", ""]
            for r in changes["renamed"]:
                lines.append(f"- `{r['old']}` -> `{r['new']}`" + (" (content also changed)" if r["edited"] else "")
                             + f" | cited by: {lesson_list(r['lessons'])}")
            lines.append("")
        if changes["deleted"]:
            lines += ["### Deleted files", ""]
            lines += [f"- `{d['path']}` | cited by: {lesson_list(d['lessons'])}" for d in changes["deleted"]] + [""]

    if changes["added"] or changes["renamed_sections"] or changes["removed"]:
        lines += ["## Added / Renamed / Removed Sections", ""]
        if changes["added"]:
            lines += ["### Added sections", ""]
            lines += [f"- `{e['path']}`: '{e['section']}'" + (f" | whole-document lessons: {lesson_list(e['lessons'])}" if e["lessons"] else "")
                      for e in changes["added"]] + [""]
        if changes["renamed_sections"]:
            lines += ["### Renamed sections", ""]
            lines += [f"- `{e['path']}`: '{e['old']}' -> '{e['new']}' | cited by: {lesson_list(e['lessons'])}"
                      for e in changes["renamed_sections"]] + [""]
        if changes["removed"]:
            lines += ["### Removed sections", ""]
            lines += [f"- `{e['path']}`: '{e['section']}' | cited by: {lesson_list(e['lessons'])}"
                      for e in changes["removed"]] + [""]

    if changes["modified"]:
        cited_changes = [e for e in changes["modified"] if e["lessons"]]
        uncited_changes = [e for e in changes["modified"] if not e["lessons"]]
        lines += ["## Modified Sections", ""]
        if cited_changes:
            lines += ["### Cited by a lesson", ""]
            lines += [f"- `{e['path']}`: '{e['section']}' | lessons: {lesson_list(e['lessons'])}" for e in cited_changes] + [""]
        if uncited_changes:
            lines += ["### Not cited by any lesson", ""]
            lines += [f"- `{e['path']}`: '{e['section']}'" for e in uncited_changes] + [""]

    if lessons:
        lines += ["## Lessons to review", ""]
        for lesson_id, reasons in lessons.items():
            lines += [f"### {lesson_id}"] + [f"- {r}" for r in reasons] + [""]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def cmd_check(atlas, lessons_data):
    atlas = Path(atlas).resolve()
    baseline = load_baseline()
    if baseline is None:
        print("No baseline yet. If the lessons are currently correct, record one with:\n"
              f"  python scripts/sync_docs.py --atlas \"{atlas}\" accept")
        return 1
    lessons, changes = compare(atlas, lessons_data, baseline)
    write_report(atlas, lessons, changes, baseline)
    if changes["legacy"]:
        print("NOTE: this baseline only tracks documents that lessons cite. Re-record it once with 'accept' "
              "(or the workflow's init_baseline) so new, renamed and deleted documents are detected too.")
    if not (lessons or has_changes(changes)):
        print("In sync: no document differs from the baseline.")
        return 0
    print("Documentation changed since the baseline:")
    for key, label in (("new", "new file"), ("deleted", "deleted file")):
        for item in changes[key]:
            print(f"  {label}:", item if isinstance(item, str) else item["path"])
    for item in changes["renamed"]:
        print(f"  renamed file: {item['old']} -> {item['new']}")
    for key, label in (("added", "added section"), ("removed", "removed section"), ("modified", "modified section")):
        for item in changes[key]:
            cited = " (cited by " + ", ".join(item["lessons"]) + ")" if item["lessons"] else " (uncited)"
            print(f"  {label}: {item['path']}: {item['section']}{cited}")
    for item in changes["renamed_sections"]:
        print(f"  renamed section: {item['path']}: {item['old']} -> {item['new']}")
    if lessons:
        print(f"{len(lessons)} lesson(s) to review ({', '.join(lessons)})")
        for lesson_id, reasons in lessons.items():
            print(f"  {lesson_id}")
            for reason in reasons:
                print(f"    - {reason.replace('`', '')}")
    print(f"Report: {shown(REPORT)}")
    return 2


def touched_paths(changes):
    """Every document path that the changes mention (old and new names, deleted files, changed sections)."""
    paths = set(changes["new"])
    paths |= {d["path"] for d in changes["deleted"]}
    for item in changes["renamed"]:
        paths |= {item["old"], item["new"]}
    for key in ("added", "removed", "modified", "renamed_sections"):
        paths |= {item["path"] for item in changes[key]}
    return paths


def cmd_accept(atlas, lessons_data, only, drifted=False, allow_local=False, files_only=False):
    atlas = Path(atlas).resolve()
    if files_only and (only is not None or drifted):
        print("--files-only cannot be combined with --lesson or --drifted.", file=sys.stderr)
        return 1
    problem = None if allow_local else checkout_problem(atlas)
    if problem:
        print(f"Refusing to record a baseline: {problem}. "
              "The baseline must match the remote Atlas branch. Let the pipeline create it, "
              "or pass --allow-local if you know what you are doing.", file=sys.stderr)
        return 1
    sources = lesson_sources(lessons_data)
    unknown = [i for i in (only or []) if i not in sources]
    if unknown:
        print("Unknown lesson id(s): " + ", ".join(unknown), file=sys.stderr)
        return 1
    baseline = load_baseline()
    selected = None                          # lessons whose cited documents must be readable
    if drifted:
        # Everything check flags counts as reviewed: lessons, uncited sections, new, renamed and deleted files.
        if baseline is None:
            print("No baseline yet; run accept once without --drifted.", file=sys.stderr)
            return 1
        lessons, changes = compare(atlas, lessons_data, baseline)
        if not (lessons or has_changes(changes)):
            print("Nothing changed; baseline unchanged.")
            return 0
        selected = list(lessons)
        wanted = touched_paths(changes) | {p for i in selected for p, _ in sources[i]}
    elif only:
        selected = list(only)
        wanted = {p for i in selected for p, _ in sources[i]}
    else:
        wanted = None                        # everything: a fresh full snapshot
    now = snapshot(atlas, sources)
    for lesson_id in (selected if selected is not None else sources):
        for path, _ in sources[lesson_id]:
            if now.get(path) is None:
                print(f"Cannot read {path} (cited by lesson '{lesson_id}') in the Atlas folder; baseline not changed. "
                      "Point the lesson at the document's new path, or remove the source.", file=sys.stderr)
                return 1
    baseline = baseline or {"docs": {}}
    if wanted is None:
        baseline["docs"] = {p: d for p, d in now.items() if d is not None}
        baseline["scope"], baseline["version"] = SCOPE, 2
    else:
        for path in sorted(wanted):
            if now.get(path) is None:
                baseline["docs"].pop(path, None)     # deleted or renamed away
            else:
                baseline["docs"][path] = now[path]
    baseline.setdefault("version", 1)
    baseline["atlasCommit"] = git_head(atlas)
    baseline["atlasBranch"] = git_branch(atlas)
    baseline["recorded"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(baseline, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    count = len(baseline["docs"]) if wanted is None else len(wanted)
    print(f"Baseline recorded for {count} document(s) at Atlas {baseline['atlasBranch']} @ {baseline['atlasCommit']}.")
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
    group.add_argument("--lesson", nargs="+", help="with accept: only the documents these lesson ids cite")
    group.add_argument("--drifted", action="store_true",
                       help="with accept: every change that check currently flags (cited or not, including skipped ones)")
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
        return cmd_accept(atlas, lessons_data, args.lesson, args.drifted, args.allow_local, args.files_only)
    return cmd_check(atlas, lessons_data)


if __name__ == "__main__":
    sys.exit(main())
