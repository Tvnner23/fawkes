#!/usr/bin/env python3
"""Metadata-only readiness for the requested component; never reads secrets."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_fawkes_release import launch_context, PRODUCTION_ROOT


def verify_prerequisites(*, production_root=PRODUCTION_ROOT,
                         config_root=Path("/home/tvnner/.config/fawkes"), component="app"):
    if component not in {"app", "discord", "notification"}:
        raise ValueError("unknown production component")
    launch_context(production_root)
    names = {"app": ("app.env",), "discord": ("discord-bot.env",),
             "notification": ("notification.env",)}[component]
    for name in names:
        path = Path(config_root) / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"required protected configuration unavailable: {path}")
        if path.stat().st_mode & 0o077:
            raise ValueError(f"protected credential permissions are too broad: {path}")
    return {"component": component, "metadata_ready": True,
            "credentials_validated": False, "provider_contacted": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--component", choices=("app", "discord", "notification"), default="app")
    args = parser.parse_args()
    verify_prerequisites(component=args.component)
    print(f"Fawkes {args.component} release, state binding, and protected configuration metadata are ready; credential validity is not tested.")


if __name__ == "__main__":
    main()
