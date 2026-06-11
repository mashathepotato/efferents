"""Local read-only HTTP server for the lab dashboard.

Stdlib http.server only — no web framework dependency. Serves the static
dashboard page plus JSON endpoints backed by `reader`. Read-only: there are no
POST/PUT routes and nothing here mutates lab state.
"""

from __future__ import annotations

import json
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from efferents.dashboard import reader

STATIC_DIR = Path(__file__).parent / "static"

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
}


class DashboardHandler(BaseHTTPRequestHandler):
    lab_root: Path

    def __init__(self, *args, lab_root: Path, **kwargs):
        self.lab_root = Path(lab_root)
        super().__init__(*args, **kwargs)

    def do_GET(self):  # noqa: N802 (stdlib naming)
        try:
            if self.path in ("/", "/index.html"):
                return self._send_file(STATIC_DIR / "dashboard.html")
            if self.path == "/api/state":
                return self._send_json(reader.read_state(self.lab_root))
            if self.path == "/api/runs":
                return self._send_json(reader.read_runs(self.lab_root))
            if self.path == "/api/papers":
                return self._send_json(reader.read_papers(self.lab_root))
            if self.path == "/api/activity":
                return self._send_json(reader.read_activity(self.lab_root))
            if self.path.startswith("/static/"):
                target = (STATIC_DIR / self.path[len("/static/"):]).resolve()
                if STATIC_DIR in target.parents and target.is_file():
                    return self._send_file(target)
            self.send_error(404)
        except Exception as exc:  # read-only server: report, don't crash
            self.send_error(500, str(exc))

    def _send_json(self, obj) -> None:
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type",
                         _CONTENT_TYPES.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:  # silence per-request stderr logging
        pass


def make_server(lab_root: Path, port: int = 8800) -> ThreadingHTTPServer:
    handler = partial(DashboardHandler, lab_root=Path(lab_root))
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve(lab_root: Path, port: int = 8800, open_browser: bool = True) -> None:
    httpd = make_server(lab_root, port)
    url = f"http://localhost:{httpd.server_address[1]}"
    print(f"efferents dashboard: {url}  (Ctrl-C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
