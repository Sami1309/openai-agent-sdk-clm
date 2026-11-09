"""Local read-only dashboard over ``runs/``: ``python -m dashboard [--port 8765]``."""

from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
RUNS = ROOT.parent / "runs"
SAFE_NAME = re.compile(r"^[\w.\-]+$")


def list_runs() -> list[dict]:
    runs = []
    if RUNS.is_dir():
        for path in sorted(RUNS.glob("*/summary.json"), reverse=True):
            try:
                runs.append(json.loads(path.read_text()))
            except (OSError, json.JSONDecodeError):
                continue  # A benchmark may be mid-write.
    return runs


def trace_path(run: str, file: str, runs: Path = RUNS) -> Path | None:
    """Resolve a requested trace, or return None if it is not a file directly in a run."""
    if not (SAFE_NAME.match(run) and SAFE_NAME.match(file)):
        return None
    path = (runs / run / file).resolve()
    return path if path.parent.parent == runs.resolve() and path.is_file() else None


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/":
            self._send(200, (ROOT / "static" / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/runs":
            self._send(200, json.dumps(list_runs()).encode(), "application/json")
        elif url.path == "/api/trace":
            query = parse_qs(url.query)
            path = trace_path(query.get("run", [""])[0], query.get("file", [""])[0])
            if path is not None:
                self._send(200, path.read_bytes(), "application/json")
            else:
                self._send(404, b"{}", "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def log_message(self, *args: object) -> None:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the CLM dashboard on localhost.")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Dashboard: http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
