"""Real release-context startup with synthetic state; never a live-use claim."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.runtime.production_release import materialize_release, promote_release
from tests.test_alpha_release_preparation import (
    source_fixture, state_fixture, release_options, prepared, load_script)


class LibraryReleaseStartupTests(unittest.TestCase):
    def test_real_app_in_verified_release_context_preserves_confinement(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = source_fixture(base / "source", full=True)
            state = state_fixture(base / "state")
            production = base / "production"
            record = materialize_release(production_root=production,
                                         **release_options(source, state))
            prepared(record, production)
            promote_release(record["release_id"], production_root=production)
            _, release, environment = load_script("run_fawkes_release").launch_context(production)
            self.assertTrue((release / "library").is_symlink())
            self.assertEqual(environment["FAWKES_RUNTIME_STATE_ROOT"], str(state))
            # Keep the launcher's verified binding but remove inherited secrets
            # and unrelated runtime overrides. Fixture venv is synthetic; use
            # the test interpreter with actual isolated release source.
            state_binding = environment["FAWKES_RUNTIME_STATE_ROOT"]
            environment = {key: value for key, value in environment.items()
                           if not key.startswith(("FAWKES_", "OPENAI_"))}
            environment.update(FAWKES_RUNTIME_STATE_ROOT=state_binding,
                FAWKES_INSTANCE_ID="one", FAWKES_DEVELOPMENT_ROOT=str(base / "development"),
                FAWKES_APP_SESSION_ROOT=str(state / "database/app_sessions"),
                FAWKES_CONSOLE_UPDATE_ROOT=str(state / "database/console_updates"),
                FAWKES_MEMORY_WORKER_ENABLED="0", OPENAI_API_KEY="fixture")
            script = r'''
import json, pathlib, sys, threading, urllib.request
release, state = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(release))
def audit(event, args):
    if event == "socket.connect":
        address = args[1]
        if not isinstance(address, tuple) or address[0] not in {"127.0.0.1", "::1"}:
            raise AssertionError("external network forbidden in startup test")
sys.addaudithook(audit)
from src.library import store
from src.library.storage import confined_path
assert pathlib.Path(store.__file__).resolve().is_relative_to(release)
assert store.LIBRARY_ROOT == state / "library"
assert store.ORIGINALS_DIR == store.LIBRARY_ROOT / "originals"
assert store.SOURCES_DIR == store.LIBRARY_ROOT / "sources"
assert store.EXTRACTIONS_DIR == store.LIBRARY_ROOT / "extractions"
paths = store.instance_library_paths("one")
for key in ("originals", "sources", "extractions", "events"):
    assert paths[key] == state / "library/instances/one" / key
assert not store.list_sources(instance_id="one")
explicit = state / "explicit-library"
assert store.instance_library_paths("one", library_root=explicit)["root"] == explicit / "instances/one"
linked = release / "library/instances/one/sources"
try: confined_path(linked.parent, linked.name)
except ValueError: pass
else: raise AssertionError("release symlink must still fail raw confinement")
paths["sources"].mkdir(parents=True, exist_ok=True)
(paths["sources"] / "escape.json").symlink_to(state / "outside.json")
try: store.list_sources(instance_id="one")
except ValueError: pass
else: raise AssertionError("child symlink must still fail")
(paths["sources"] / "escape.json").unlink()
for reference in ("../escape", "/absolute", "sub/../escape"):
    try: confined_path(paths["sources"], reference)
    except ValueError: pass
    else: raise AssertionError("traversal must still fail")
from src.runtime.chat_service import FawkesChatService
from src.app.server import FawkesAppServer
service = FawkesChatService()
server = FawkesAppServer(("127.0.0.1", 0), chat_service=service,
                        app_token="synthetic-startup-token")
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=5) as response:
        assert response.status == 200 and response.read()
finally:
    server.shutdown(); server.server_close(); thread.join(timeout=2)
print(json.dumps({"real_local_http": 200, "instance": service.instance_id,
                  "provider_calls": 0, "synthetic_state": True}))
'''
            completed = subprocess.run([sys.executable, "-I", "-B", "-c", script,
                str(release), str(state)], cwd=base, env=environment,
                text=True, capture_output=True, timeout=45)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn('"real_local_http": 200', completed.stdout)
            self.assertIn('"instance": "one"', completed.stdout)

    def test_checkout_fallback_without_runtime_override(self):
        root = Path(__file__).resolve().parents[1]
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("FAWKES_", "OPENAI_"))}
        script = ("import sys,pathlib;sys.path.insert(0,sys.argv[1]);"
                  "from src.library import store;"
                  "assert store.LIBRARY_ROOT==pathlib.Path(sys.argv[1])/'library'")
        completed = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(root)],
            env=environment, text=True, capture_output=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
