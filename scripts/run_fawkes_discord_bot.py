#!/usr/bin/env python3
"""Run the bounded Fawkes Discord DM Gateway transport."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.chat_service import FawkesChatService
from src.runtime.discord_bot import (
    DiscordBotConfiguration, DiscordBotHttpClient,
    DiscordConversationBridge, DiscordGatewayRunner,
)


def report_message_failure(exception):
    print(
        f"Discord message failed safely; listener remains READY: {exception}",
        flush=True,
    )


def main():
    configuration = DiscordBotConfiguration.from_environment()
    client = DiscordBotHttpClient(configuration)
    bridge = DiscordConversationBridge(
        configuration, chat_service=FawkesChatService(), http_client=client
    )
    print("Fawkes Discord conversational transport is connecting.", flush=True)
    DiscordGatewayRunner(
        configuration,
        bridge,
        http_client=client,
        on_ready=lambda: print(
            "Fawkes Discord conversational transport is READY.", flush=True
        ),
        on_message_failure=report_message_failure,
    ).run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
