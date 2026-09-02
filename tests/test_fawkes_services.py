from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FawkesServiceDefinitionTests(unittest.TestCase):
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
