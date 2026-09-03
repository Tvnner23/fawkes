from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FawkesServiceDefinitionTests(unittest.TestCase):
    def _isolated_src(self, checkout):
        shutil.copytree(ROOT / "src", checkout / "src")

    def test_legacy_state_owners_honor_external_runtime_root_without_leakage(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            checkout = temporary / "checkout"
            checkout.mkdir()
            self._isolated_src(checkout)
            state_root = temporary / "runtime-state"
            program = """
import json
from src import archive, archive_file, conversations, ingest, instances
from src.capabilities import phoenix_presence

store = phoenix_presence.PresenceProfileStore("test-phoenix")
print(json.dumps({
    "archive_raw": str(archive.RAW_DIR),
    "archive_file_meta": str(archive_file.META_DIR),
    "ingest_raw": str(ingest.RAW_DIR),
    "conversations": str(conversations.CONVERSATION_DIR),
    "instances": str(instances.INSTANCE_DIR),
    "presence": str(store.root),
    "presence_path": str(store.path),
}))
"""
            environment = {
                "FAWKES_RUNTIME_STATE_ROOT": str(state_root),
                "PYTHONPATH": str(checkout),
            }
            completed = subprocess.run(
                [sys.executable, "-c", program], cwd=checkout, env=environment,
                check=True, capture_output=True, text=True,
            )
            paths = json.loads(completed.stdout)
            self.assertEqual(Path(paths["archive_raw"]), state_root / "archive" / "raw")
            self.assertEqual(Path(paths["archive_file_meta"]), state_root / "archive" / "meta")
            self.assertEqual(Path(paths["ingest_raw"]), state_root / "archive" / "raw")
            self.assertEqual(Path(paths["conversations"]), state_root / "conversations")
            self.assertEqual(Path(paths["instances"]), state_root / "instances")
            self.assertEqual(Path(paths["presence"]), state_root / "database" / "presentation")
            self.assertEqual(
                Path(paths["presence_path"]),
                state_root / "database" / "presentation" / "test-phoenix" / "profile.json",
            )
            for relative in ("archive", "conversations", "instances", "database"):
                self.assertFalse((checkout / relative).exists())
            self.assertEqual(set(environment), {"FAWKES_RUNTIME_STATE_ROOT", "PYTHONPATH"})

    def test_legacy_state_owners_retain_repository_fallback_and_presence_injection(self):
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary) / "checkout"
            checkout.mkdir()
            self._isolated_src(checkout)
            program = """
import json
from src import archive, archive_file, conversations, ingest, instances
from src.capabilities import phoenix_presence

injected = phoenix_presence.PresenceProfileStore("test-phoenix", root="explicit-root")
print(json.dumps({
    "archive": str(archive.RAW_DIR),
    "archive_file": str(archive_file.META_DIR),
    "ingest": str(ingest.RAW_DIR),
    "conversations": str(conversations.CONVERSATION_DIR),
    "instances": str(instances.INSTANCE_DIR),
    "presence": str(phoenix_presence.PRESENCE_ROOT),
    "injected": str(injected.path),
}))
"""
            completed = subprocess.run(
                [sys.executable, "-c", program], cwd=checkout,
                env={"PYTHONPATH": str(checkout)}, check=True,
                capture_output=True, text=True,
            )
            paths = json.loads(completed.stdout)
            self.assertEqual(Path(paths["archive"]), checkout / "archive" / "raw")
            self.assertEqual(Path(paths["archive_file"]), checkout / "archive" / "meta")
            self.assertEqual(Path(paths["ingest"]), checkout / "archive" / "raw")
            self.assertEqual(Path(paths["conversations"]), checkout / "conversations")
            self.assertEqual(Path(paths["instances"]), checkout / "instances")
            self.assertEqual(Path(paths["presence"]), checkout / "database" / "presentation")
            self.assertEqual(Path(paths["injected"]), Path("explicit-root/test-phoenix/profile.json"))

    def test_services_are_credential_free_and_separate(self):
        app = (ROOT / "deploy/systemd/fawkes-app.service").read_text()
        discord = (ROOT / "deploy/systemd/fawkes-discord.service").read_text()
        notifier = (ROOT / "deploy/systemd/fawkes-failure-notifier.service").read_text()
        self.assertIn("EnvironmentFile=/home/tvnner/.config/fawkes/app.env", app)
        self.assertIn("EnvironmentFile=-/home/tvnner/.config/fawkes/notification.env", app)
        self.assertIn("EnvironmentFile=/home/tvnner/.config/fawkes/discord-bot.env", discord)
        self.assertIn("EnvironmentFile=/home/tvnner/.config/fawkes/notification.env", notifier)
        self.assertNotIn("WEBHOOK", discord)
        self.assertNotIn("BOT_TOKEN", notifier)
        self.assertIn("Restart=on-failure", app)
        self.assertIn("Restart=on-failure", discord)
        self.assertIn("WorkingDirectory=/home/tvnner/.local/lib/fawkes-production/current", app)
        self.assertIn("WorkingDirectory=/home/tvnner/.local/lib/fawkes-production/current", discord)
        self.assertNotIn("WorkingDirectory=/home/tvnner/fawkes", app)
        self.assertNotIn("WorkingDirectory=/home/tvnner/fawkes", discord)
        self.assertIn("FAWKES_DEVELOPMENT_ROOT=/home/tvnner/fawkes", app)
        self.assertIn("FAWKES_RUNTIME_STATE_ROOT=/home/tvnner/.local/state/fawkes", app)

    def test_target_contains_only_current_production_components(self):
        target = (ROOT / "deploy/systemd/fawkes.target").read_text()
        self.assertIn("fawkes-app.service fawkes-discord.service", target)
        self.assertNotIn("worker", target.lower())

    def test_production_readiness_precedes_runtime(self):
        ready = (ROOT / "deploy/systemd/fawkes-production-ready.service").read_text()
        app = (ROOT / "deploy/systemd/fawkes-app.service").read_text()
        discord = (ROOT / "deploy/systemd/fawkes-discord.service").read_text()
        self.assertIn("approved Fawkes release", ready)
        self.assertIn("Requires=fawkes-production-ready.service", app)
        self.assertIn("Requires=fawkes-production-ready.service fawkes-app.service", discord)

    def test_windows_task_is_limited_current_user_and_secret_free(self):
        source = (ROOT / "deploy/windows/Install-FawkesStartupTask.ps1").read_text()
        self.assertIn("Project Fawkes WSL Startup", source)
        self.assertIn("-d Ubuntu --exec /bin/true", source)
        self.assertIn("RunLevel Limited", source)
        self.assertNotIn("TOKEN", source.upper())
