#!/usr/bin/env python3
"""Native, no-overwrite setup of one component's protected environment file."""
import argparse
import getpass
import os
from pathlib import Path
import stat
import uuid
import warnings

FIELDS = {
    "app": (("FAWKES_APP_TOKEN", "Fawkes app token: "), ("OPENAI_API_KEY", "OpenAI API key: ")),
    "discord": (("FAWKES_DISCORD_BOT_TOKEN", "Discord bot token: "),
                ("FAWKES_DISCORD_TANNER_USER_ID", "Tanner Discord user ID: "),
                ("OPENAI_API_KEY", "OpenAI API key: ")),
    "notification": (("FAWKES_DISCORD_WEBHOOK_URL", "Failure-notification webhook URL: "),),
}
NAMES = {"app": "app.env", "discord": "discord-bot.env", "notification": "notification.env"}


def configure(component="app", *, config_root=Path("/home/tvnner/.config/fawkes"), prompt=getpass.getpass):
    fields = FIELDS[component]
    root = Path(config_root)
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".credentials-" + uuid.uuid4().hex
    try:
        metadata = os.fstat(fd)
        if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ValueError("configuration directory must be owned by this user and private")
        def bound():
            current = root.lstat()
            if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
                raise ValueError("configuration directory changed; inspect metadata before retrying")
        bound()
        name = NAMES[component]
        try:
            os.stat(name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("configuration already exists; it was not read or overwritten")
        values = []
        for key, label in fields:
            # getpass must not fall back to echoed stdin when no protected TTY
            # is available. Turn its warning into failure before fallback reads.
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                value = prompt(label)
            if not value or any(character in value for character in ("\n", "\r", "\x00")):
                raise ValueError("credential must be nonempty and contain no newlines or NUL")
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            values.append(key + '="' + escaped + '"\n')
        output = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        with os.fdopen(output, "w") as handle:
            handle.write("".join(values))
            handle.flush()
            os.fsync(handle.fileno())
        bound()
        # Hard-link publication is atomic and fails if another writer published
        # first, including a symlink. Existing unrelated configs are untouched.
        os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        os.fsync(fd)
        bound()
    finally:
        try:
            os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError:
            pass
        os.close(fd)
    return root / name


def main():
    parser = argparse.ArgumentParser(description="Native protected setup; never paste credentials into chat")
    parser.add_argument("--component", choices=tuple(FIELDS), default="app")
    args = parser.parse_args()
    configure(args.component)
    print(f"New {args.component} configuration published privately. Existing component files were preserved.")


if __name__ == "__main__":
    main()
