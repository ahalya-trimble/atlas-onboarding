"""Install, update, or remove the optional tutor in a local Atlas checkout."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path(".atlas-onboarding") / "manifest.json"
FILES = {
    ".atlas-onboarding/onboarding.py": ROOT / "scripts" / "onboarding.py",
    ".atlas-onboarding/curriculum.json": ROOT / "curriculum.json",
    ".atlas-onboarding/tutor.md": ROOT / "tutor.md",
    ".atlas-onboarding/VERSION": ROOT / "VERSION",
    ".github/agents/atlas-onboarding-local.agent.md": ROOT / "atlas-onboarding-local.agent.md",
    ".github/skills/quiz/SKILL.md": ROOT / "skills" / "quiz" / "SKILL.md",
}
LEGACY_FILES = frozenset(FILES) - {".github/skills/quiz/SKILL.md"}
LEGACY_EXCLUDES = ("\n# BEGIN atlas-onboarding local add-on\n"
            "/.atlas-onboarding/\n"
            "/.github/agents/atlas-onboarding-local.agent.md\n"
            "/.onboarding/\n"
            "# END atlas-onboarding local add-on\n")
EXCLUDES = LEGACY_EXCLUDES.replace(
    "/.onboarding/\n", "/.github/skills/quiz/SKILL.md\n/.onboarding/\n")


def digest(content):
    return hashlib.sha256(content).hexdigest()


def git(atlas, *args):
    result = subprocess.run(["git", "-C", str(atlas), *args], capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Git command failed")
    return result.stdout.strip()


def safe_path(atlas, relative):
    path = atlas / relative
    parents = path.relative_to(atlas).parts
    linked = any(atlas.joinpath(*parents[:index]).is_symlink()
                 for index in range(1, len(parents) + 1))
    if linked or not path.resolve().is_relative_to(atlas):
        raise ValueError(f"Refusing linked or outside-checkout path: {relative}")
    return path


def conflict_check(atlas):
    # Existing shared instructions outrank the optional agent's SQLite workflow.
    candidates = [atlas / "AGENTS.md", atlas / ".github" / "copilot-instructions.md"]
    for candidate in candidates:
        if candidate.is_file():
            content = candidate.read_text(encoding="utf-8-sig").lower()
            if "only permitted onboarding writes" in content and ".onboarding/progress.json" in content:
                raise ValueError(
                    f"{candidate} restricts onboarding to JSON writes. Ask its maintainer to "
                    "explicitly permit this optional SQLite workflow first. No shared instructions were changed.")


def apply_install(atlas, action):
    manifest_path = safe_path(atlas, MANIFEST)
    installed = manifest_path.exists()
    if action == "install" and installed:
        raise ValueError("Already installed; use update")
    if action in ("update", "remove") and not installed:
        raise ValueError("No managed installation found")
    if action != "remove":
        conflict_check(atlas)
    manifest = None
    manifest_bytes = None
    if installed:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        if (not isinstance(manifest, dict) or manifest.get("schemaVersion") != 1
                or not isinstance(manifest.get("files"), dict)
                or set(manifest["files"]) not in (set(FILES), LEGACY_FILES)):
            raise ValueError("Unknown or malformed installation manifest; refusing changes")
    snapshots = {manifest_path: manifest_bytes}
    targets = manifest["files"] if action == "remove" else FILES
    for relative in targets:
        path = safe_path(atlas, relative)
        content = None
        if installed and relative in manifest["files"]:
            content = path.read_bytes() if path.is_file() else None
            if content is None or digest(content) != manifest["files"][relative]:
                raise ValueError(f"Installed file changed or missing; preserve and reconcile it: {path}")
        elif path.exists():
            raise ValueError(f"Refusing to overwrite existing file: {path}")
        snapshots[path] = content
        if git(atlas, "ls-files", "--", relative):
            raise ValueError(f"Refusing to modify a tracked file: {relative}")
    if git(atlas, "ls-files", "--", str(MANIFEST).replace("\\", "/")):
        raise ValueError("Refusing to modify a tracked manifest")

    exclude = Path(git(atlas, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"))
    if exclude.is_symlink():
        raise ValueError("Refusing to edit a linked Git exclude file")
    snapshots[exclude] = exclude.read_bytes() if exclude.exists() else None
    old_exclude = snapshots[exclude] or b""
    block = (LEGACY_EXCLUDES if installed and set(manifest["files"]) == LEGACY_FILES
             else EXCLUDES).encode()
    if installed and old_exclude.count(block) != 1:
        raise ValueError("Managed Git exclude block changed; reconcile before update/removal")
    if not installed and b"# BEGIN atlas-onboarding local add-on" in old_exclude:
        raise ValueError("Unmanaged onboarding exclude block already exists")
    updates = {}
    if action == "remove":
        updates.update({safe_path(atlas, name): None for name in targets})
        updates[manifest_path] = None
        retained = old_exclude.replace(block, b"", 1)
        retained_paths = [line for line in (b"/.onboarding/", b"/.atlas-onboarding/state/")
                          if line not in retained.splitlines()]
        if retained_paths:
            retained += b"\n# Retained private Atlas onboarding data\n" + b"".join(
                path + b"\n" for path in retained_paths)
        updates[exclude] = retained
    else:
        contents = {name: source.read_bytes() for name, source in FILES.items()}
        version = (ROOT / "VERSION").read_text(encoding="ascii").strip()
        updates.update({safe_path(atlas, name): content for name, content in contents.items()})
        new_manifest = {"schemaVersion": 1, "version": version,
                        "files": {name: digest(content) for name, content in contents.items()}}
        updates[manifest_path] = (json.dumps(new_manifest, indent=2) + "\n").encode()
        updates[exclude] = (old_exclude.replace(block, EXCLUDES.encode(), 1)
                           if installed else old_exclude + EXCLUDES.encode())
    for path in updates:
        if path.exists() and not path.is_file():
            raise ValueError(f"Expected a regular file: {path}")
    original = snapshots
    for path, before in original.items():
        actual = path.read_bytes() if path.exists() else None
        if actual != before:
            raise ValueError(f"File changed during installation: {path}")
    applied = []
    try:
        for path, content in updates.items():
            applied.append(path)
            if content is None:
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        for path, expected in updates.items():
            actual = path.read_bytes() if path.exists() else None
            if actual != expected:
                raise OSError(f"Read-back verification failed: {path}")
    except OSError:
        for path in reversed(applied):
            before = original[path]
            if before is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_bytes(before)
        raise
    return {"action": action, "atlas": str(atlas), "verified": True,
            "progressPreserved": True,
            "message": "Learner data was not read, changed, or removed."}


def install(atlas, action):
    atlas = Path(atlas).resolve()
    if not (atlas / "Atlas.sln").is_file():
        raise ValueError("Target must contain Atlas.sln")
    if Path(git(atlas, "rev-parse", "--show-toplevel")).resolve() != atlas:
        raise ValueError("Target must be the Git repository root")
    exclude = Path(git(atlas, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"))
    lock = exclude.parent / "atlas-onboarding.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise ValueError(f"Another installer may be active; inspect lock before retrying: {lock}") from error
    os.close(descriptor)
    try:
        return apply_install(atlas, action)
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "update", "remove"))
    parser.add_argument("--atlas", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.atlas, args.action), indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(json.dumps({"error": str(error), "verified": False}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
