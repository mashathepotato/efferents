"""macOS notifications via osascript + iPhone push via ntfy.sh.

ntfy.sh is unauthenticated by default. The topic acts as a shared secret —
choose something unguessable and put it in NTFY_TOPIC env var. Subscribe to it
on the iPhone via the ntfy iOS app.
"""
from __future__ import annotations

import os
import subprocess
from typing import Any

import urllib.error
import urllib.request


def _ascript_str(s: str) -> str:
    """Quote a Python string for embedding in an AppleScript literal."""
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{s}"'


def notify_macos(title: str, message: str, *, sound: bool = False) -> None:
    """Fire a macOS Banner notification via osascript. Best-effort, never raises."""
    sound_part = ' sound name "Glass"' if sound else ""
    script = f"display notification {_ascript_str(message[:300])} with title {_ascript_str(title[:80])}{sound_part}"
    try:
        subprocess.run(["osascript", "-e", script], check=False, timeout=5, capture_output=True)
    except Exception:
        pass


def notify_ntfy(message: str, *, title: str | None = None, priority: int = 3) -> bool:
    """POST to ntfy.sh with topic from $NTFY_TOPIC. Returns True on 2xx."""
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return False
    url = f"https://ntfy.sh/{topic}"
    headers: dict[str, str] = {"Priority": str(priority)}
    if title:
        headers["Title"] = title
    req = urllib.request.Request(
        url, data=message.encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def notify_all(title: str, message: str, *, sound: bool = False, priority: int = 3) -> dict[str, Any]:
    """Fire macOS + ntfy.sh in parallel-effect (sequential calls; both best-effort)."""
    notify_macos(title, message, sound=sound)
    sent = notify_ntfy(message, title=title, priority=priority)
    return {"ntfy_sent": sent}
