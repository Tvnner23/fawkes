#!/usr/bin/env python3
"""Explicitly send Fawkes's one-shot private Discord bootstrap to Tanner."""

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.runtime.discord_bot import (
    DiscordBotConfiguration,
    DiscordBotHttpClient,
    bootstrap_tanner_dm,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="bootstrap_fawkes_discord_dm.py",
        description="Send the one-shot Fawkes Discord DM bootstrap to configured Tanner."
    )
    parser.parse_args(argv)
    configuration = DiscordBotConfiguration.from_environment()
    result = bootstrap_tanner_dm(
        configuration,
        DiscordBotHttpClient(configuration),
    )
    print("Fawkes Discord Tanner DM bootstrap delivered.")
    print(f"recipient_identity={result['recipient_identity']}")
    print("creates_authority=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
