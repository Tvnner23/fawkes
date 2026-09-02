#!/usr/bin/env python3
"""Establish a one-time high-water mark without replaying old Discord history."""

from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.discord_bot import DiscordBotConfiguration, DiscordBotHttpClient, DiscordMessageCursorStore


def main():
    configuration = DiscordBotConfiguration.from_environment()
    client = DiscordBotHttpClient(configuration)
    state_root = Path(os.getenv("FAWKES_RUNTIME_STATE_ROOT", Path.home() / ".local/state/fawkes"))
    store = DiscordMessageCursorStore(state_root / "discord-dm-cursors.json")
    for recipient in (configuration.tanner, configuration.emily):
        if recipient is None or not recipient.opted_in or store.get(recipient.identity) is not None:
            continue
        history = client.messages_after(recipient, None, limit=1)
        if history:
            store.advance(recipient.identity, max(history, key=lambda item: int(item["id"]))["id"])
        print(f"Discord cursor initialized for recipient_identity={recipient.identity}; authority=false")


if __name__ == "__main__":
    main()
