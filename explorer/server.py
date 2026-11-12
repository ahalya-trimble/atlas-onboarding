#!/usr/bin/env python3
"""Atlas Explorer local server.

Serves the visual guide and a small READ-ONLY API over the Atlas docs so the guide can
open the source documents it cites, search them, and warn when they change.

Security model (everything stays on this computer):
  * Listens on 127.0.0.1 only and rejects any request whose Host header is not local
    (blocks DNS-rebinding from web pages).
  * API calls need the header X-Requested-With: atlas-explorer, so other websites cannot
    call it from the browser (no CORS headers are ever sent).
  * Only these files can be read: docs/**/*.md|txt, AGENTS.md, README.md. Anything else,
    including source code, config, .env and key files, is refused. Symlinks that leave
    the repository are refused. Secret-looking values are redacted in what is returned.
  * No outbound network access and no AI model is called. Only two small files are written, both in
    .atlas-onboarding/state/: sources.lock.json (document hashes) and explorer-progress.json
    (your progress).
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
ALLOWED_DIRS = {"docs"}
ALLOWED_FILES = {"AGENTS.md", "README.md"}
ALLOWED_EXT = {".md", ".txt"}
MAX_BYTES = 1_000_000
DENY_NAME = re.compile(r"(\.env|appsettings|\.pfx|\.pem|\.key|\.p12|id_rsa|\.snk|\.publishsettings)", re.I)
SECRET_KEY = re.compile(
    r"(?i)(?:^|(?<=[^A-Za-z0-9_]))[\"']?(?:password|pwd|secret|api[ _-]?key|accountkey|"
    r"sharedaccesskey|client[_-]?secret|token)[\"']?(?=\s*[=:])")
STATIC_EXT = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
              ".js": "text/javascript; charset=utf-8", ".json": "application/json",
              ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".svg": "image/svg+xml", ".ico": "image/x-icon", ".mp4": "video/mp4"}
STOP = set("the a an is are of to in on and or for how what why when where does do can it this that "
           "with from my be as at by about".split())
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "media-src 'self'; frame-src https://drive.google.com; connect-src 'self'; object-src 'none'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")

ATLAS = None          # repository root (Path)
STATE = None          # .atlas-onboarding/state
PORT = 8765


def _secret_value_end(text, start):
    if start >= len(text):
        return None
    quote = text[start]
    if quote in "\"'":
        index = start + 1
        while index < len(text):
            if text[index] == "\\" and index + 1 < len(text):
                index += 2
                continue
            if text[index] == quote:
                return index + 1
            if text[index] in "\r\n":
                return None
            index += 1
        return None
    index = start
    while index < len(text) and text[index] not in " \t\r\n;\"'`,)":
        index += 1
    return index if index - start >= 3 else None


def redact(text):
    parts = []
    cursor = 0
    for match in SECRET_KEY.finditer(text):
        index = match.end()
        while index < len(text) and text[index] in " \t":
            index += 1
        if index >= len(text) or text[index] not in "=:":
            continue
        index += 1
        while index < len(text) and text[index] in " \t":
            index += 1
        end = _secret_value_end(text, index)
        if end is None or index < cursor:
            continue
        parts.append(text[cursor:index])
        parts.append((text[index] + "[redacted]" + text[index]) if text[index] in "\"'" else "[redacted]")
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def sha(data):
    return hashlib.sha256(data).hexdigest()[:16]


def resolve_doc(rel):
    """Return (absolute Path, posix relative path) for an allowed doc, else None."""
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if not rel or "\x00" in rel or ".." in rel.split("/"):
        return None
    root = ATLAS.resolve()
    try:
        real = (root / rel).resolve(strict=True)
        relp = real.relative_to(root).as_posix()
    except (OSError, ValueError):
        return None
    if not real.is_file():
        return None
    if relp.split("/")[0] not in ALLOWED_DIRS and relp not in ALLOWED_FILES:
        return None
    if real.suffix.lower() not in ALLOWED_EXT or DENY_NAME.search(real.name):
        return None
    if real.stat().st_size > MAX_BYTES:
        return None
    return real, relp


def all_docs():
    out = []
    root = ATLAS.resolve()
    cands = [root / f for f in ALLOWED_FILES]
    for d in ALLOWED_DIRS:
        base = root / d
        if base.is_dir():
            cands += [p for p in base.rglob("*") if p.suffix.lower() in ALLOWED_EXT]
    for p in cands:
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            continue
        if p.is_file() and resolve_doc(rel):
            out.append(rel)
    return sorted(set(out))


def read_doc(rel):
    r = resolve_doc(rel)
    if not r:
        return None
    raw = r[0].read_bytes()
    return r[1], raw, raw.decode("utf-8-sig", errors="replace")


def outline(text):
    heads, first, in_code = [], "", False
    for i, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"^(#{1,4})\s+(.*\S)", line)
        if m:
            heads.append({"level": len(m.group(1)), "text": m.group(2).strip("# ").strip(), "line": i})
        elif not first and line.strip() and not line.startswith(("|", "-", "*", ">", "!", "[")) and heads:
            first = line.strip()
    return heads, first


def plain(t):
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    return re.sub(r"[*`_]{1,3}", "", t)


def lock_path():
    return STATE / "sources.lock.json"


def load_lock():
    try:
        return json.loads(lock_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_lock(data):
    STATE.mkdir(parents=True, exist_ok=True)
    lock_path().write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


ID_RE = re.compile(r"^[a-z0-9-]{1,64}$")
ROLES = {"technician", "manager", "developer", "qa", "support"}


def clean_progress(d):
    """Accept only the expected shape and sizes; anything else is dropped."""
    if not isinstance(d, dict):
        raise ValueError("progress must be an object")
    out = {"done": {}, "quiz": {}, "xp": 0, "unlock": False, "skipProfile": False, "profile": None}
    for key, val in (d.get("done") or {}).items():
        if ID_RE.match(str(key)) and val:
            out["done"][key] = 1
    for key, val in (d.get("quiz") or {}).items():
        if ID_RE.match(str(key)):
            out["quiz"][key] = bool(val)
    xp = d.get("xp")
    out["xp"] = max(0, min(int(xp), 100000)) if isinstance(xp, (int, float)) else 0
    out["unlock"], out["skipProfile"] = bool(d.get("unlock")), bool(d.get("skipProfile"))
    try:
        stamp = int(d.get("updatedAt") or 0)
    except (TypeError, ValueError):
        stamp = 0
    out["updatedAt"] = stamp if 0 <= stamp <= 4_102_444_800_000 else 0
    prof = d.get("profile")
    if isinstance(prof, dict) and prof.get("role") in ROLES:
        out["profile"] = {"name": str(prof.get("name", ""))[:40], "role": prof["role"],
                          "exp": str(prof.get("exp", ""))[:40], "goal": str(prof.get("goal", ""))[:200]}
    return out


def progress_path():
    return STATE / "explorer-progress.json"


def load_progress():
    try:
        return clean_progress(json.loads(progress_path().read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


_progress_guard = threading.Lock()


class _StateLock:
    """One lock file per checkout, shared by every thread and process that writes it."""

    def __init__(self, folder):
        self.folder = folder
        self.handle = None

    def __enter__(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.folder / ".progress.lock", "a+b")
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *_exc):
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()


def same_checkout(value):
    if not isinstance(value, str) or not value.strip() or ATLAS is None:
        return False
    try:
        return Path(value).resolve() == ATLAS.resolve()
    except OSError:
        return False


def save_progress(data):
    with _progress_guard, _StateLock(STATE):
        target = progress_path()
        if target.is_symlink():
            raise ValueError("refusing to write through a link")
        current = load_progress()
        if current and int(current.get("updatedAt") or 0) > int(data.get("updatedAt") or 0):
            raise ValueError("stale progress")
        fd, name = tempfile.mkstemp(prefix="explorer-progress-", suffix=".tmp", dir=STATE)
        tmp = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(data, indent=1) + "\n")
            os.replace(tmp, target)
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise


def tokens(s):
    return [w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2 and w not in STOP]


def search(q):
    qt = tokens(q)
    if not qt:
        return []
    results = []
    for rel in all_docs():
        doc = read_doc(rel)
        if not doc:
            continue
        lines = doc[2].splitlines()
        hits = []
        for i, line in enumerate(lines, 1):
            low = line.lower()
            sc = sum(1 for w in qt if w in low)
            if sc:
                hits.append((sc, i, line.strip()))
        if not hits:
            continue
        hits.sort(key=lambda h: (-h[0], h[1]))
        title = redact(next((h["text"] for h in outline(doc[2])[0] if h["level"] == 1), rel))
        total = sum(h[0] for h in hits[:3]) + (3 if any(w in rel.lower() for w in qt) else 0)
        results.append({"score": total, "path": rel, "title": title,
                        "hits": [{"line": h[1], "text": redact(h[2])[:240]} for h in hits[:2]]})
    results.sort(key=lambda r: -r["score"])
    return results[:6]


class Handler(BaseHTTPRequestHandler):
    server_version = "AtlasExplorer"
    sys_version = ""

    def log_message(self, *a):  # do not log URLs/queries
        pass

    def _send(self, code, body=b"", ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode("utf-8"))

    def _host_ok(self):
        return (self.headers.get("Host") or "").lower() in (f"localhost:{PORT}", f"127.0.0.1:{PORT}")

    def _api_ok(self):
        return self.headers.get("X-Requested-With") == "atlas-explorer"

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        u = urlparse(self.path)
        if u.path.startswith("/api/"):
            if not self._api_ok():
                return self._json({"error": "forbidden"}, 403)
            return self.api_get(u.path, parse_qs(u.query))
        self.static(u.path)

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        if not self._host_ok() or not self._api_ok():
            return self._json({"error": "forbidden"}, 403)
        u = urlparse(self.path)
        if u.path not in ("/api/accept", "/api/progress"):
            return self._json({"error": "not found"}, 404)
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 65536)
            body = json.loads(self.rfile.read(n) or b"{}")
            if u.path == "/api/progress":
                if not same_checkout(body.get("checkout")):
                    return self._json({"error": "wrong checkout"}, 409)
                try:
                    save_progress(clean_progress(body))
                except ValueError as exc:
                    if str(exc) == "stale progress":
                        return self._json({"error": "stale", "atlas": str(ATLAS.resolve()),
                                            "explorer": load_progress()}, 409)
                    raise
                return self._json({"ok": True, "atlas": str(ATLAS.resolve())})
            paths = body.get("paths", [])
            if not isinstance(paths, list):
                raise ValueError
        except (ValueError, TypeError, OSError):
            return self._json({"error": "bad request"}, 400)
        lock = load_lock() or {"hashes": {}}
        for p in paths:
            d = read_doc(str(p))
            if d:
                lock["hashes"][d[0]] = sha(d[1])
        save_lock(lock)
        self._json({"ok": True})

    def api_get(self, path, q):
        arg = lambda k: (q.get(k) or [""])[0]
        if path == "/api/health":
            root = ATLAS.resolve()
            return self._json({"ok": True, "docs": len(all_docs()), "atlasFolder": root.name, "atlas": str(root)})
        if path == "/api/doc":
            d = read_doc(arg("path"))
            if not d:
                return self._json({"error": "not available"}, 404)
            rel, raw, text = d
            return self._json({"path": rel, "sha": sha(raw), "text": redact(text),
                               "abs": str((ATLAS.resolve() / rel)).replace("\\", "/")})
        if path == "/api/outline":
            out = {}
            lock = load_lock()
            if lock is None:  # first run: current docs become the baseline
                lock = {"hashes": {}}
                for rel in all_docs():
                    d = read_doc(rel)
                    if d:
                        lock["hashes"][rel] = sha(d[1])
                save_lock(lock)
            for p in [x for x in arg("paths").split("|") if x][:40]:
                d = read_doc(p)
                if not d:
                    out[p] = {"status": "missing"}
                    continue
                heads, first = outline(d[2])
                base = lock["hashes"].get(d[0])
                shown = [{**h, "text": redact(h["text"])} for h in heads if h["level"] in (2, 3)][:8]
                out[p] = {"status": "ok" if base in (None, sha(d[1])) else "changed", "sha": sha(d[1]),
                          "title": redact(next((h["text"] for h in heads if h["level"] == 1), d[0])),
                          "headings": shown,
                          "summary": plain(redact(first))[:300]}
            return self._json(out)
        if path == "/api/progress":
            return self._json({"atlas": str(ATLAS.resolve()), "explorer": load_progress()})
        if path == "/api/search":
            return self._json({"results": search(arg("q")[:200])})
        self._json({"error": "not found"}, 404)

    def static(self, path):
        rel = unquote(path).lstrip("/") or "index.html"
        if "\x00" in rel or ".." in rel.replace("\\", "/").split("/"):
            return self._send(404, b"not found", "text/plain")
        try:
            real = (HERE / rel).resolve(strict=True)
            real.relative_to(HERE)
        except (OSError, ValueError):
            return self._send(404, b"not found", "text/plain")
        ctype = STATIC_EXT.get(real.suffix.lower())
        if not real.is_file() or not ctype:
            return self._send(404, b"not found", "text/plain")
        if real.suffix.lower() == ".mp4":
            return self._send_media(real, ctype)
        self._send(200, real.read_bytes(), ctype)

    def _send_media(self, real, ctype):
        size = real.stat().st_size
        start, end = 0, size - 1
        status = 200
        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            spec = range_header[6:].split(",", 1)[0].strip()
            left, _, right = spec.partition("-")
            try:
                start = int(left) if left else 0
                end = int(right) if right else size - 1
            except ValueError:
                start, end = 0, size - 1
            if start >= size or start < 0 or end < start:
                return self._send(416, b"range not satisfiable", "text/plain",
                                   {"Content-Range": f"bytes */{size}"})
            end = min(end, size - 1)
            status = 206
        length = end - start + 1
        extra = {"Accept-Ranges": "bytes"}
        if status == 206:
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        for key, value in extra.items():
            self.send_header(key, value)
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with real.open("rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining:
                    chunk = handle.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (ConnectionError, OSError):
            return


class ExclusiveServer(ThreadingHTTPServer):
    # On Windows, SO_REUSEADDR lets a second server bind the same port, so an old
    # server could keep answering with stale files. Refuse to share the port.
    allow_reuse_address = False
    daemon_threads = True


def main():
    global ATLAS, STATE, PORT
    ap = argparse.ArgumentParser()
    ap.add_argument("--atlas", help="Atlas repository root (default: two folders above this file)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true", help="open the default browser")
    a = ap.parse_args()
    PORT = a.port
    ATLAS = Path(a.atlas).resolve() if a.atlas else HERE.parents[1]
    STATE = ATLAS / ".atlas-onboarding" / "state"
    if not (ATLAS / "Atlas.sln").is_file():
        print(f"Atlas.sln not found in {ATLAS}. Pass --atlas <repo root>.", file=sys.stderr)
        sys.exit(2)
    try:
        srv = ExclusiveServer(("127.0.0.1", PORT), Handler)
    except OSError:
        # Already running for this checkout? Then just open the browser.
        import urllib.request
        health = None
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{PORT}/api/health",
                headers={"X-Requested-With": "atlas-explorer"})
            health = json.load(urllib.request.urlopen(req, timeout=2))
        except Exception:
            health = None
        named = (health or {}).get("atlas") if health and health.get("ok") else None
        running = Path(named).resolve() if named else None
        if running == ATLAS.resolve():
            print(f"Atlas Explorer is already running at http://localhost:{PORT}/")
            if a.open:
                import webbrowser
                webbrowser.open(f"http://localhost:{PORT}/")
            sys.exit(0)
        if health and health.get("ok"):
            where = running or "a checkout that did not identify itself"
            print(f"Port {PORT} is already used by Atlas Explorer for {where}. "
                  f"Close that window or run: python server.py --port 8766 --open", file=sys.stderr)
        else:
            print(f"Port {PORT} is used by another program. Close it or run: python server.py --port 8766 --open", file=sys.stderr)
        sys.exit(3)
    print(f"Atlas Explorer: http://localhost:{PORT}/   (read-only docs, local only; Ctrl+C to stop)")
    if a.open:
        import webbrowser
        webbrowser.open(f"http://localhost:{PORT}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
