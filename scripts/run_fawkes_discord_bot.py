#!/usr/bin/env python3
"""Run the bounded Fawkes Discord DM Gateway transport."""

from pathlib import Path
import json
import os
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.chat_service import FawkesChatService
from src.runtime.discord_bot import (
    DiscordBotConfiguration, DiscordBotHttpClient,
    DiscordConversationBridge, DiscordGatewayRunner, DiscordMessageCursorStore,
)
from src.runtime.component_supervision import ComponentReceiptStore


STATE_ROOT = Path(os.getenv("FAWKES_RUNTIME_STATE_ROOT", Path.home() / ".local/state/fawkes"))


def write_status(state, detail=None):
    path = STATE_ROOT / "discord-bridge-status.json"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    value = {"component": "discord_bridge", "state": state, "detail": detail or {}}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def report_message_failure(exception):
    print(
        f"Discord message failed safely; listener remains READY: {exception}",
        flush=True,
    )


def main():
    configuration = DiscordBotConfiguration.from_environment()
    client = DiscordBotHttpClient(configuration)
    bridge = DiscordConversationBridge(
        configuration, chat_service=FawkesChatService(), http_client=client,
        cursor_store=DiscordMessageCursorStore(STATE_ROOT / "discord-dm-cursors.json"),
    )
    print("Fawkes Discord conversational transport is connecting.", flush=True)
    write_status("connecting")

    def lifecycle(state, detail):
        write_status(state.lower(), detail)
        if state == "READY":
            print("Fawkes Discord conversational transport is READY.", flush=True)
            ComponentReceiptStore(STATE_ROOT).recover_latest("discord_bridge")
        elif state == "RESUMED":
            print("Fawkes Discord conversational transport is RESUMED.", flush=True)
        elif state in {"RECONNECTING", "RECONNECT_REQUESTED", "INVALID_SESSION"}:
            print(f"Fawkes Discord conversational transport lifecycle={state}.", flush=True)

    try:
        DiscordGatewayRunner(
            configuration, bridge, http_client=client,
            on_message_failure=report_message_failure, on_lifecycle=lifecycle,
            max_reconnect_attempts=None,
        ).run()
    except Exception as exc:
        provider_code = getattr(exc, "provider_code", None)
        stage = getattr(exc, "stage", None) or "gateway"
        category = getattr(exc, "category", None) or "terminal_failure"
        write_status("failed", {"stage": stage, "category": category,
                                "provider_code": provider_code})
        ComponentReceiptStore(STATE_ROOT).failure(
            component="discord_bridge", stage=stage, category=category,
            exception=exc, provider_code=provider_code, service_state="failed",
            notify=True, secrets=(configuration.bot_token,),
        )
        raise


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
