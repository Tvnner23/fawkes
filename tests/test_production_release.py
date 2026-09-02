import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.runtime.production_release import (DEVELOPMENT_RUNTIME_CLOSURE, materialize_release,
    promote_release, release_files, rollback_release, verify_release)


class ProductionReleaseTests(unittest.TestCase):
    def source(self, root, marker):
        root = Path(root)
        (root / "src/app/static").mkdir(parents=True)
        (root / "scripts").mkdir()
        (root / "config").mkdir()
        (root / "requirements.txt").write_text("\n")
        (root / "src/__init__.py").write_text("")
        (root / "src/example.py").write_text(f"VALUE = {marker!r}\n")
        (root / "src/app/static/index.html").write_text(marker)
        for name in __import__("src.runtime.production_release", fromlist=["SCRIPT_NAMES"]).SCRIPT_NAMES:
            (root / "scripts" / name).write_text("#!/bin/sh\n")
        for name in ("archive", "database", "memory", "library", "conversations", "instances", "backups", "logs"):
            (root / name).mkdir()
        return root

    def test_atomic_promotion_and_rollback_preserve_shared_state(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); source = self.source(base / "dev", "one"); production = base / "prod"
            first = materialize_release(source=source, production_root=production,
                                        validation_reference="tests-pass-one")
            promote_release(first["release_id"], production_root=production)
            (source / "database/state.json").write_text("continuity")
            (source / "src/example.py").write_text("VALUE = 'two'\n")
            second = materialize_release(source=source, production_root=production,
                                         validation_reference="tests-pass-two")
            promote_release(second["release_id"], production_root=production)
            self.assertEqual((production / "current/src/example.py").read_text(), "VALUE = 'two'\n")
            rollback_release(production_root=production)
            self.assertEqual((production / "current/src/example.py").read_text(), "VALUE = 'one'\n")
            self.assertEqual((production / "current/database/state.json").read_text(), "continuity")

    def test_release_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); source = self.source(base / "dev", "one"); production = base / "prod"
            record = materialize_release(source=source, production_root=production,
                                         validation_reference="tests-pass")
            target = production / "releases" / record["release_id"] / "src/example.py"
            target.chmod(0o644); target.write_text("tampered")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                verify_release(target.parents[1])

    def test_real_source_closure_contains_development_app_server_runtime(self):
        included = {relative for relative, _ in release_files()}
        self.assertLessEqual(DEVELOPMENT_RUNTIME_CLOSURE, included)

    def test_isolated_release_imports_do_not_resolve_from_development_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            production = Path(directory) / "production"
            record = materialize_release(production_root=production,
                validation_reference="isolated-production-import-test")
            release = production / "releases" / record["release_id"]
            modules = [
                "src.runtime.codex_app_server", "src.runtime.development_attention",
                "src.runtime.codex_development_campaign", "src.runtime.codex_development_handoff",
                "src.runtime.codex_write_builder_adapter", "src.runtime.wsl_codex_reviewer",
            ]
            script = ("import importlib,json,sys; root=sys.argv[1]; sys.path.insert(0,root); "
                "mods=[importlib.import_module(x) for x in json.loads(sys.argv[2])]; "
                "print(json.dumps([m.__file__ for m in mods]))")
            environment = {key: value for key, value in os.environ.items()
                           if key not in {"PYTHONPATH", "PYTHONHOME"}}
            completed = subprocess.run([sys.executable, "-I", "-B", "-c", script,
                str(release), json.dumps(modules)], cwd="/tmp", env=environment,
                text=True, capture_output=True, check=True)
            loaded = json.loads(completed.stdout)
            self.assertTrue(all(Path(path).resolve().is_relative_to(release.resolve())
                                for path in loaded), loaded)
