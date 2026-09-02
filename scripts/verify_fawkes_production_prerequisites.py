#!/usr/bin/env python3
from pathlib import Path

required = [
    Path("/home/tvnner/.local/lib/fawkes-production/current/release.json"),
    Path("/home/tvnner/.local/lib/fawkes-production/venv/bin/python"),
    Path("/home/tvnner/.config/fawkes/app.env"),
    Path("/home/tvnner/.config/fawkes/discord-bot.env"),
    Path("/home/tvnner/.config/fawkes/notification.env"),
    Path("/home/tvnner/fawkes/database"),
]
for path in required:
    if not path.exists():
        raise SystemExit(f"required production prerequisite unavailable: {path}")
for path in required[2:5]:
    if path.stat().st_mode & 0o077:
        raise SystemExit(f"protected credential permissions are too broad: {path}")
print("Fawkes production release, credentials, and shared state are available.")
