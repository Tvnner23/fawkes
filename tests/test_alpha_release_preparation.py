"""Disposable release/state fixtures; no credentials, dependency installs or provider calls."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from src.runtime import production_release as releases
from src.runtime.disposable_verifier import candidate_manifest

ROOT = Path(__file__).resolve().parents[1]


def seal(value):
    import hashlib
    value = dict(value)
    value["record_sha256"] = hashlib.sha256(json.dumps(value, sort_keys=True,
        ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return value


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))


def state_fixture(root):
    root = Path(root)
    for name in releases.SHARED_STATE:
        (root / name).mkdir(parents=True, exist_ok=True)
    write_json(root / "instances/registry.json",
        {"schema_version": 1, "instances": [{"name": "Fawkes", "instance_id": "one"}]})
    return root


def source_fixture(root, marker="one", *, full=False):
    root = Path(root)
    root.mkdir(parents=True)
    if full:
        for name in ("src", "scripts", "deploy"):
            shutil.copytree(ROOT / name, root / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copyfile(ROOT / "requirements.txt", root / "requirements.txt")
    else:
        (root / "src/runtime").mkdir(parents=True)
        (root / "src/app/static").mkdir(parents=True)
        (root / "scripts").mkdir()
        (root / "src/__init__.py").write_text("")
        (root / "src/runtime/__init__.py").write_text("")
        (root / "src/example.py").write_text(f"VALUE = {marker!r}\n")
        (root / "src/app/static/index.html").write_text(marker)
        (root / "requirements.txt").write_text("\n")
        for name in ("production_release.py", "codex_app_server_01534_schemas.json"):
            shutil.copyfile(ROOT / "src/runtime" / name, root / "src/runtime" / name)
        for name in releases.SCRIPT_NAMES:
            shutil.copyfile(ROOT / "scripts" / name, root / "scripts" / name)
    (root / ".gitignore").write_text("\n".join(releases.SHARED_STATE) + "\n__pycache__/\n")
    return root


def release_options(source, state, *, task=None):
    """Make explicitly synthetic accepted evidence for a real disposable Git commit."""
    source = Path(source)
    task = Path(task or source.parent / (source.name + "-evidence"))
    def git(*args):
        return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(source), *args],
            check=True, capture_output=True, text=True).stdout.strip()
    if not (source / ".git").exists():
        git("init", "--quiet")
    git("add", "--all")
    git("-c", "user.name=Release Fixture", "-c", "user.email=fixture@localhost.invalid",
        "commit", "--allow-empty", "--quiet", "-m", "Synthetic release qualification")
    head = git("rev-parse", "HEAD")
    digest = "1" * 64
    context = "candidate-snapshot-" + "2" * 64
    conditions_hash = __import__("hashlib").sha256(b'["synthetic-condition"]').hexdigest()
    receipt = seal({"schema_version": 2, "status": "accepted", "fixture_only": True,
        "record_type": "codex_independent_review_acceptance_receipt", "creates_authority": False,
        "campaign_id": "synthetic-release-test", "package_id": "synthetic-builder-package",
        "review_report_id": "synthetic-review-report", "source_report_id": "synthetic-source-report",
        "review_package_id": "synthetic-review-package", "review_invocation_id": "synthetic-review-invocation",
        "reviewer_worker_id": "synthetic-reviewer", "reviewer_role": "wsl_read_only_code_health_review",
        "delivery_receipt_id": "synthetic-delivery", "verification_receipt_id": "synthetic-verification",
        "candidate_snapshot_id": context, "mutation_manifest_sha256": digest,
        "allowed_scope_sha256": digest, "exact_change_evidence_sha256": digest,
        "candidate_retention_receipt_sha256": digest, "review_package_sha256": digest,
        "review_report_sha256": digest, "acceptance_condition_ids_sha256": conditions_hash,
        "authoritative_preimages_sha256": digest, "replay_identity": digest, "verdict": "pass",
        "recipient": {"worker_id": "synthetic-reviewer", "role": "wsl_read_only_code_health_review"}})
    application = seal({"schema_version": 1, "application_count": 1,
        "record_type": "codex_post_review_authoritative_application_receipt",
        "status": "applied_verified_after_review", "campaign_id": "synthetic-release-test",
        "package_id": receipt["package_id"], "review_report_id": receipt["review_report_id"],
        "candidate_snapshot_id": context, "mutation_manifest_sha256": digest,
        "allowed_scope_sha256": digest, "exact_change_evidence_sha256": digest,
        "binding": {key: receipt[key] for key in ("candidate_snapshot_id",
            "candidate_retention_receipt_sha256", "review_invocation_id", "review_package_id",
            "review_package_sha256", "reviewer_worker_id")},
        "review_acceptance_receipt_sha256": receipt["record_sha256"]})
    git_receipt = seal({"status": "committed", "head": head,
        "record_type": "reviewed_git_commit_terminal_receipt_v01",
        "review_receipt_sha256": receipt["record_sha256"],
        "application_receipt_sha256": application["record_sha256"]})
    terminal = seal({"status": "succeeded", "campaign_id": "synthetic-release-test",
        "record_type": "codex_development_campaign", "acceptance_condition_ids": ["synthetic-condition"],
        "reviews": [{"review_acceptance_receipt": receipt,
                    "acceptance_condition_ids_satisfied": ["synthetic-condition"],
                    "violated_acceptance_condition_ids": [], "defects": []}],
        "application_evidence": application, "git_commit_evidence": git_receipt})
    closed = {"canonical_accepted": True, "closed": seal({"campaign_id": "synthetic-release-test",
        "reviews": [{"review_acceptance_receipt": receipt}]}),
        "review_result": {"review_acceptance_receipt": receipt}}
    integrated = seal({"status": "integrated", "integration_commit": head,
        "review_context_snapshot_id": context, "mutation_digest_sha256": digest,
        "acceptance_receipt_sha256": receipt["record_sha256"],
        "product_candidate_snapshot_id": candidate_manifest(source)["candidate_snapshot_id"],
        "application_receipt": application, "git_receipt": git_receipt})
    path = task / "delivery-v1/integration-v1/integration-result.json"
    write_json(path, integrated)
    write_json(path.with_name("git-observation.json"), terminal)
    write_json(task / "evidence/closed-review.json", closed)
    return dict(source=source, state_root=state, instance_id="one", accepted_integration=path,
                accepted_integration_record_sha256=integrated["record_sha256"],
                acceptance_receipt_sha256=receipt["record_sha256"], validation_reference="synthetic-only")


def fake_dependencies(commands, *, fail_at=None):
    def run(command, **kwargs):
        commands.append(command)
        if fail_at == len(commands):
            raise subprocess.CalledProcessError(1, command, stderr="synthetic dependency failure")
        if command[1:3] == ["-m", "venv"]:
            environment = Path(command[-1])
            (environment / "bin").mkdir()
            (environment / "bin/python").write_text("# synthetic, never executed\n")
            (environment / "bin/python").chmod(0o755)
            (environment / "pyvenv.cfg").write_text("synthetic environment\n")
            (environment / "dependency.py").write_text("# synthetic installed dependency\n")
        return subprocess.CompletedProcess(command, 0, "", "")
    return run


def prepared(record, production):
    commands = []
    releases.prepare_environment(record["release_id"], production_root=production,
                                 runner=fake_dependencies(commands))
    shutil.copyfile(production / "releases" / record["release_id"] / "scripts/run_fawkes_release.py",
                    production / "run_fawkes_release.py")
    return commands


def load_script(name):
    spec = importlib.util.spec_from_file_location("_test_" + name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AlphaReleasePreparationTests(unittest.TestCase):

    def test_real_release_cli_build_binds_selected_disposable_owner(self):
        import sys
        options = release_options(self.source, self.state)
        command = [sys.executable, "-B", str(ROOT / "scripts/manage_fawkes_release.py"),
                   "--production-root", str(self.production), "build"]
        for key, value in options.items():
            command.extend(("--" + key.replace("_", "-"), str(value)))
        result = subprocess.run(command, check=True, capture_output=True, text=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"})
        record = json.loads(result.stdout)
        self.assertEqual(record["state_owner"]["root"], str(self.state))
        self.assertEqual(record["source_root"], str(self.source))
        self.assertFalse((self.production / "current").exists())

    def test_actual_prepare_shell_reuses_one_root_and_never_promotes(self):
        fake_bin = self.root / "bin"; fake_bin.mkdir()
        log = self.root / "commands.jsonl"
        stub = fake_bin / "python3"
        stub.write_text("""#!/usr/bin/python3
import json, os, sys
if '-c' in sys.argv:
    print(json.load(sys.stdin)['release_id'])
else:
    with open(os.environ['FAWKES_TEST_LOG'], 'a') as handle:
        handle.write(json.dumps(sys.argv[1:]) + '\\n')
    if 'build' in sys.argv:
        print(json.dumps({'release_id': 'fawkes-release-' + 'a' * 64}))
    elif 'prepare-env' in sys.argv and os.environ.get('FAWKES_TEST_FAIL'):
        raise SystemExit(9)
""")
        stub.chmod(0o755)
        environment = {"PATH": str(fake_bin) + ":/usr/bin:/bin", "FAWKES_TEST_LOG": str(log)}
        command = ["/bin/bash", str(ROOT / "scripts/prepare_fawkes_production.sh"),
                   "--production-root", str(self.production), "--source", str(self.source)]
        result = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
        self.assertTrue(json.loads(result.stdout)["release_id"].startswith("fawkes-release-"))
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertEqual(call[call.index("--production-root") + 1], str(self.production))
            self.assertNotIn("promote", call)
        failed = subprocess.run(command, env={**environment, "FAWKES_TEST_FAIL": "1"},
                                capture_output=True, text=True)
        self.assertEqual(failed.returncode, 9)
        self.assertFalse((self.production / "current").exists())

    def test_actual_installer_app_default_does_not_enable_social_or_sudo_policy(self):
        fake_bin = self.root / "bin"; fake_bin.mkdir()
        log = self.root / "commands.log"
        for name in ("python3", "install", "systemctl", "visudo"):
            stub = fake_bin / name
            stub.write_text('#!/bin/bash\nprintf "%s " "${0##*/}" "$@" >> "$FAWKES_TEST_LOG"\nprintf "\\n" >> "$FAWKES_TEST_LOG"\n')
            stub.chmod(0o755)
        # Only replace the fixed deployment-root literal in the fixture. The
        # actual argument parser, selected commands and app/full-stack branches
        # execute unchanged with command stubs; no system paths are touched.
        fixture = self.root / "scripts/install_fawkes_systemd.sh"
        fixture.parent.mkdir()
        source = (ROOT / "scripts/install_fawkes_systemd.sh").read_text()
        literal = "production=/home/tvnner/.local/lib/fawkes-production"
        self.assertEqual(source.count(literal), 1)
        fixture.write_text(source.replace(literal, "production=" + str(self.production)))
        environment = {"PATH": str(fake_bin) + ":/usr/bin:/bin", "FAWKES_TEST_LOG": str(log)}
        command = ["/bin/bash", str(fixture), "fawkes-release-" + "a" * 64]
        subprocess.run(command, env=environment, check=True, capture_output=True, text=True)
        commands = log.read_text()
        self.assertIn("systemctl enable fawkes-app.service", commands)
        self.assertNotIn("fawkes.target", commands)
        self.assertNotIn("discord", commands)
        self.assertNotIn("failure-notifier", commands)
        self.assertNotIn("sudoers", commands)
        self.assertNotIn("visudo", commands)
        self.assertNotIn(" stop ", commands)
        self.assertNotIn(" restart ", commands)
        self.assertIn("WantedBy=multi-user.target", (ROOT / "deploy/systemd/fawkes-app.service").read_text())
        log.write_text("")
        subprocess.run([*command, "--full-stack"], env=environment, check=True,
                       capture_output=True, text=True)
        self.assertIn("systemctl enable fawkes.target fawkes-discord.service fawkes-failure-notifier.timer",
                      log.read_text())
        self.assertIn("/etc/sudoers.d/fawkes-runtime-control", log.read_text())

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = source_fixture(self.root / "source")
        self.state = state_fixture(self.root / "state")
        self.production = self.root / "production"

    def build(self):
        return releases.materialize_release(production_root=self.production,
            **release_options(self.source, self.state))

    def test_source_and_state_are_independent_and_schema_is_packaged(self):
        record = self.build()
        release = self.production / "releases" / record["release_id"]
        self.assertEqual((release / "memory").resolve(), self.state / "memory")
        self.assertFalse((self.source / "memory").exists())
        schema = "src/runtime/codex_app_server_01534_schemas.json"
        self.assertIn(schema, {entry["path"] for entry in record["files"]})
        from src.runtime.codex_app_server import REVIEWER_SCHEMA_MANIFEST_SHA256
        import hashlib
        self.assertEqual(hashlib.sha256((release / schema).read_bytes()).hexdigest(),
                         REVIEWER_SCHEMA_MANIFEST_SHA256)

    def test_clean_source_is_not_acceptance_and_dirty_source_is_rejected(self):
        options = release_options(self.source, self.state)
        options["acceptance_receipt_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "accepted integration"):
            releases.materialize_release(production_root=self.production, **options)
        options = release_options(self.source, self.state)
        (self.source / "src/example.py").write_text("dirty")
        with self.assertRaisesRegex(ValueError, "clean integrated"):
            releases.materialize_release(production_root=self.production, **options)
        self.assertFalse((self.production / "current").exists())

    def test_trusted_integration_pin_and_real_receipt_shape_are_required(self):
        options = release_options(self.source, self.state)
        options["accepted_integration_record_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "trusted handoff"):
            releases.materialize_release(production_root=self.production, **options)
        options = release_options(self.source, self.state)
        closed_path = options["accepted_integration"].parents[2] / "evidence/closed-review.json"
        closed = json.loads(closed_path.read_text())
        closed["review_result"]["review_acceptance_receipt"] = seal({"status": "accepted"})
        write_json(closed_path, closed)
        with self.assertRaisesRegex(ValueError, "canonical accepted receipt shape"):
            releases.materialize_release(production_root=self.production, **options)

    def test_ignored_credential_file_cannot_enter_accepted_release(self):
        ignore = self.source / '.gitignore'
        ignore.write_text(ignore.read_text() + '\n.env\n')
        options = release_options(self.source, self.state)
        before = candidate_manifest(self.source)
        private = self.source / 'config/.env'
        private.parent.mkdir(); private.write_text('SYNTHETIC_SECRET=not-real\n'); private.chmod(0o600)
        self.assertEqual(candidate_manifest(self.source), before)
        with self.assertRaisesRegex(ValueError, 'outside accepted source inventory'):
            releases.materialize_release(production_root=self.production, **options)
        self.assertFalse((self.production / 'releases').exists())
        self.assertEqual(private.stat().st_mode & 0o777, 0o600)

    def test_duplicate_owner_and_registry_drift_block_prepare_promote_and_launch(self):
        record = self.build(); prepared(record, self.production)
        releases.promote_release(record['release_id'], production_root=self.production)
        release = self.production / 'releases' / record['release_id']
        registry = self.state / 'instances/registry.json'
        original = json.loads(registry.read_text())
        launcher = load_script('run_fawkes_release')
        for changed in (
                {'schema_version':1,'instances':[{'name':'Other','instance_id':'one'}, *original['instances']]},
                {**original,'metadata_changed':True}):
            with self.subTest(changed=changed):
                write_json(registry, changed)
                with self.assertRaises(ValueError): releases.verify_release(release)
                with self.assertRaises(ValueError): releases.prepare_environment(record['release_id'], production_root=self.production)
                with patch.object(releases, '_atomic_link') as publish:
                    with self.assertRaises(ValueError): releases.promote_release(record['release_id'], production_root=self.production)
                    publish.assert_not_called()
                with self.assertRaises(ValueError): launcher.launch_context(self.production)
                write_json(registry, original)
        duplicate = {'schema_version':1,'instances':[{'name':'Other','instance_id':'one'}, *original['instances']]}
        write_json(registry, duplicate)
        with self.assertRaises(ValueError): self.build()

    def test_wrong_or_missing_existing_owner_fails_without_initializing_state(self):
        options = release_options(self.source, self.state)
        options["instance_id"] = "different"
        with self.assertRaisesRegex(ValueError, "existing Fawkes"):
            releases.materialize_release(production_root=self.production, **options)
        (self.state / "instances/registry.json").unlink()
        with self.assertRaises(FileNotFoundError):
            releases.materialize_release(production_root=self.production, **options)
        self.assertFalse((self.state / "instances/registry.json").exists())

    def test_unprepared_release_cannot_replace_current(self):
        first = self.build()
        prepared(first, self.production)
        releases.promote_release(first["release_id"], production_root=self.production)
        (self.source / "src/example.py").write_text("VALUE = 'second'\n")
        second = self.build()
        before = (self.production / "current").resolve()
        with self.assertRaises((OSError, ValueError)):
            releases.promote_release(second["release_id"], production_root=self.production)
        self.assertEqual((self.production / "current").resolve(), before)

    def test_dependency_failure_preserves_current_and_existing_venv(self):
        first = self.build()
        prepared(first, self.production)
        releases.promote_release(first["release_id"], production_root=self.production)
        legacy = self.production / "venv/bin/python"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("existing interpreter")
        (self.source / "src/example.py").write_text("VALUE = 'second'\n")
        second = self.build()
        commands = []
        with self.assertRaises(subprocess.CalledProcessError):
            releases.prepare_environment(second["release_id"], production_root=self.production,
                runner=fake_dependencies(commands, fail_at=2))
        self.assertEqual((self.production / "current").resolve().name, first["release_id"])
        self.assertEqual(legacy.read_text(), "existing interpreter")
        self.assertFalse((self.production / "environments" / second["release_id"] / "ready.json").exists())
        self.assertEqual(len(commands), 2)
        self.assertNotIn(str(self.production / "venv"), json.dumps(commands))

    def test_dependency_order_and_rollback_bind_release_specific_environments(self):
        first = self.build()
        commands = prepared(first, self.production)
        self.assertEqual(commands[0][1:3], ["-m", "venv"])
        self.assertEqual(commands[1][1:4], ["-m", "pip", "install"])
        self.assertEqual(commands[2][1:4], ["-m", "pip", "check"])
        self.assertIn("-I", commands[3])
        releases.promote_release(first["release_id"], production_root=self.production)
        (self.source / "src/example.py").write_text("VALUE = 'second'\n")
        second = self.build()
        prepared(second, self.production)
        releases.promote_release(second["release_id"], production_root=self.production)
        releases.rollback_release(production_root=self.production)
        launcher = load_script("run_fawkes_release")
        with patch.dict(os.environ, {'FAWKES_INSTANCE_ID': 'another-registered-owner'}):
            python, release, environment = launcher.launch_context(self.production)
        self.assertEqual(environment['FAWKES_INSTANCE_ID'], 'one')
        self.assertEqual(python, self.production / "environments" / first["release_id"] / "bin/python")
        self.assertEqual(environment["FAWKES_RUNTIME_STATE_ROOT"], str(self.state))
        self.assertEqual(environment["FAWKES_DEVELOPMENT_ROOT"], str(self.source))
        self.assertEqual(environment["FAWKES_APP_SESSION_ROOT"], str(self.state / "database/app_sessions"))
        self.assertEqual((release / "memory/development").resolve(),
                         self.state / "memory/development")

    def test_new_environment_interpreter_dependency_and_permission_drift_fail_closed(self):
        record = self.build()
        prepared(record, self.production)
        releases.promote_release(record['release_id'], production_root=self.production)
        release = self.production / 'releases' / record['release_id']
        environment = self.production / 'environments' / record['release_id']
        python = environment / 'bin/python'
        original = python.read_bytes()
        launcher = load_script('run_fawkes_release')
        before = (self.production / 'current').resolve()
        for mutation in ('interpreter', 'dependency', 'missing_dependency', 'executable'):
            with self.subTest(mutation=mutation):
                python.write_bytes(original); python.chmod(0o755)
                dependency = environment / 'dependency.py'
                dependency.write_text('# synthetic installed dependency\n')
                extra = environment / 'injected_dependency.py'
                if extra.exists(): extra.unlink()
                if mutation == 'interpreter': python.write_bytes(b'replacement')
                elif mutation == 'dependency': extra.write_text('changed dependency')
                elif mutation == 'missing_dependency': dependency.unlink()
                else: python.chmod(0o644)
                with self.assertRaises(ValueError): releases.verify_environment(release, production_root=self.production)
                with self.assertRaises(ValueError): releases.promote_release(record['release_id'], production_root=self.production)
                with self.assertRaises(ValueError): launcher.launch_context(self.production)
                self.assertEqual((self.production / 'current').resolve(), before)

    def test_repeated_promotion_preserves_distinct_rollback_target(self):
        first = self.build(); prepared(first, self.production)
        releases.promote_release(first['release_id'], production_root=self.production)
        (self.source / 'src/example.py').write_text("VALUE = 'retry'\n")
        second = self.build(); prepared(second, self.production)
        releases.promote_release(second['release_id'], production_root=self.production)
        previous = (self.production / 'previous').resolve()
        events = sorted((self.production / 'release-events').iterdir())
        releases.promote_release(second['release_id'], production_root=self.production)
        self.assertEqual((self.production / 'previous').resolve(), previous)
        self.assertEqual(sorted((self.production / 'release-events').iterdir()), events)
        releases.rollback_release(production_root=self.production)
        self.assertEqual((self.production / 'current').resolve().name, first['release_id'])

    def test_extra_shadow_package_rejected_before_import_or_pointer_write(self):
        record = self.build(); prepared(record, self.production)
        releases.promote_release(record['release_id'], production_root=self.production)
        release = self.production / 'releases' / record['release_id']
        shadow = release / 'src/app/server'
        shadow.mkdir()
        (shadow / '__init__.py').write_text('raise AssertionError("unlisted code executed")')
        (shadow / '__main__.py').write_text('raise AssertionError("unlisted code executed")')
        with self.assertRaisesRegex(ValueError, 'unlisted release'):
            releases.verify_release(release)
        with self.assertRaisesRegex(ValueError, 'unlisted release'):
            releases.promote_release(record['release_id'], production_root=self.production)
        launcher = load_script('run_fawkes_release')
        with patch.object(launcher.importlib.util, 'spec_from_file_location', side_effect=AssertionError('imported before inventory')):
            with self.assertRaisesRegex(ValueError, 'unlisted release'):
                launcher.launch_context(self.production)

    def test_failed_release_entrypoint_does_not_create_receipt_or_notification_store(self):
        import runpy
        with patch('src.runtime.production_release.materialize_release', side_effect=ValueError('rejected')):
            with patch('src.runtime.component_supervision.ComponentReceiptStore', side_effect=AssertionError('unowned store')):
                args = [str(ROOT / 'scripts/manage_fawkes_release.py'), '--production-root', str(self.production), 'build']
                for flag in ('source','state-root','instance-id','accepted-integration','acceptance-receipt-sha256',
                             'accepted-integration-record-sha256','validation-reference'):
                    args += ['--' + flag, 'synthetic-invalid']
                with patch('sys.argv', args), self.assertRaisesRegex(ValueError, 'rejected'):
                    runpy.run_path(str(ROOT / 'scripts/manage_fawkes_release.py'), run_name='__main__')
        self.assertFalse(self.production.exists())

    def test_new_release_missing_environment_never_uses_legacy_fallback(self):
        record = self.build()
        prepared(record, self.production)
        releases.promote_release(record["release_id"], production_root=self.production)
        legacy = self.production / "venv/bin/python"
        legacy.parent.mkdir(parents=True); legacy.write_text("legacy")
        (self.production / "environments" / record["release_id"] / "ready.json").unlink()
        with self.assertRaises(FileNotFoundError):
            load_script("run_fawkes_release").launch_context(self.production)

    def legacy_fixture(self):
        record = self.build()
        release = self.production / "releases" / record["release_id"]
        legacy = dict(record)
        legacy["schema_version"] = 1
        legacy.pop("accepted_source"); legacy.pop("state_owner"); legacy.pop("manifest_sha256")
        import hashlib
        legacy["manifest_sha256"] = hashlib.sha256(json.dumps(legacy, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        manifest = release / "release.json"; manifest.chmod(0o644); write_json(manifest, legacy)
        (self.production / "current").symlink_to(release)
        # A real isolated interpreter with bundled pip, never a placeholder.
        # No network or dependency installation is needed for empty requirements.
        import venv
        venv.EnvBuilder(with_pip=True).create(self.production / 'venv')
        return release, legacy

    def test_legacy_fallback_requires_actual_prior_binding(self):
        release, legacy = self.legacy_fixture()
        python = self.production / 'venv/bin/python'
        launcher = load_script("run_fawkes_release")
        with self.assertRaises(FileNotFoundError):
            launcher.launch_context(self.production)
        releases.bind_legacy_environments(state_root=self.state, instance_id="one",
                                         production_root=self.production)
        selected, _, environment = launcher.launch_context(self.production)
        self.assertEqual(selected, python)
        self.assertEqual(environment["FAWKES_RUNTIME_STATE_ROOT"], str(self.state))
        self.assertEqual(environment['FAWKES_INSTANCE_ID'], 'one')
        with self.assertRaisesRegex(ValueError, "already exists"):
            releases.bind_legacy_environments(state_root=self.state, instance_id="one",
                                             production_root=self.production)

    def test_legacy_binding_rejects_nonexecutable_placeholder_before_publication(self):
        release, legacy = self.legacy_fixture()
        python = self.production / 'venv/bin/python'
        python.unlink(); python.write_text('not an interpreter')
        with self.assertRaisesRegex(ValueError, 'interpreter'):
            releases.bind_legacy_environments(state_root=self.state, instance_id='one', production_root=self.production)
        self.assertFalse((self.production / 'legacy-environments.json').exists())

    def test_legacy_binding_checks_dependencies_and_rechecks_environment(self):
        release, legacy = self.legacy_fixture()
        launcher = load_script('run_fawkes_release')
        commands = []
        def fail_check(command, **kwargs):
            commands.append(command)
            raise subprocess.CalledProcessError(1, command)
        with self.assertRaises(subprocess.CalledProcessError):
            releases.bind_legacy_environments(state_root=self.state, instance_id='one',
                production_root=self.production, runner=fail_check)
        self.assertEqual(commands[0][1:], ['-I', '-B', '-m', 'pip', 'check'])
        self.assertFalse((self.production / 'legacy-environments.json').exists())
        releases.bind_legacy_environments(state_root=self.state, instance_id='one', production_root=self.production)
        launcher.launch_context(self.production)
        cfg = self.production / 'venv/pyvenv.cfg'
        cfg.write_text(cfg.read_text() + '\n# changed\n')
        with self.assertRaisesRegex(ValueError, 'environment changed'):
            launcher.launch_context(self.production)

    def test_legacy_rollback_validates_owner_links_and_environment_before_pointer_write(self):
        release, legacy = self.legacy_fixture()
        releases.bind_legacy_environments(state_root=self.state, instance_id='one', production_root=self.production)
        (self.production / 'previous').symlink_to(release)
        original = (self.production / 'current').readlink()
        registry = self.state / 'instances/registry.json'
        body = registry.read_bytes()
        registry.unlink()
        with patch.object(releases, '_atomic_link') as publish:
            with self.assertRaises(FileNotFoundError):
                releases.rollback_release(production_root=self.production)
            publish.assert_not_called()
        registry.write_bytes(body)
        (release / 'memory').unlink()
        (release / 'memory').symlink_to(self.source)
        with patch.object(releases, '_atomic_link') as publish:
            with self.assertRaisesRegex(ValueError, 'state binding'):
                releases.rollback_release(production_root=self.production)
            publish.assert_not_called()
        self.assertEqual((self.production / 'current').readlink(), original)

    def test_legacy_dependency_bytes_drift_blocks_launch_and_rollback(self):
        release, legacy = self.legacy_fixture()
        dependency = self.production / 'venv/synthetic_dependency.py'
        dependency.write_text('VALUE = 1\n')
        releases.bind_legacy_environments(state_root=self.state, instance_id='one', production_root=self.production)
        (self.production / 'previous').symlink_to(release)
        dependency.write_text('VALUE = 2\n')
        launcher = load_script('run_fawkes_release')
        with self.assertRaisesRegex(ValueError, 'environment changed'):
            launcher.launch_context(self.production)
        with patch.object(releases, '_atomic_link') as publish:
            with self.assertRaisesRegex(ValueError, 'environment changed'):
                releases.rollback_release(production_root=self.production)
            publish.assert_not_called()

    def test_missing_or_corrupt_audit_owner_cannot_satisfy_gate_or_create_state(self):
        from src.runtime.phase0_integrity import audit_phoenix_state
        missing = self.root / 'absent'
        self.assertFalse(audit_phoenix_state('one', root=missing)['gate_satisfied'])
        self.assertFalse(missing.exists())
        registry = self.state / 'instances/registry.json'
        for body in ('{', '{}', '{"schema_version":1,"instances":[]}',
                     '{"schema_version":1,"instances":[{"instance_id":"other"}]}',
                     '{"schema_version":1,"instances":[{"instance_id":"one"},{"instance_id":"one"}]}'):
            registry.write_text(body)
            self.assertFalse(audit_phoenix_state('one', root=self.state)['gate_satisfied'])
            self.assertEqual(registry.read_text(), body)

    def test_credential_echo_fallback_stops_before_reading_or_publishing(self):
        import getpass
        import warnings
        credentials = load_script('configure_fawkes_credentials')
        consumed = []
        def unprotected(label):
            warnings.warn('echo unavailable', getpass.GetPassWarning)
            consumed.append(label)
            return 'must never be read'
        config = self.root / 'private-config'
        with self.assertRaises(getpass.GetPassWarning):
            credentials.configure(config_root=config, prompt=unprotected)
        self.assertEqual(consumed, [])
        self.assertFalse((config / 'app.env').exists())
        self.assertEqual(list(config.iterdir()), [])

    def test_app_readiness_does_not_require_discord_or_read_credentials(self):
        readiness = load_script("verify_fawkes_production_prerequisites")
        config = self.root / "config"; config.mkdir()
        app = config / "app.env"; app.write_text("synthetic-only"); app.chmod(0o600)
        with patch.object(readiness, "launch_context", return_value=None), patch.object(
                Path, "read_text", side_effect=AssertionError("readiness must not read credentials")):
            self.assertTrue(readiness.verify_prerequisites(config_root=config)["metadata_ready"])
            with self.assertRaisesRegex(ValueError, "discord-bot.env"):
                readiness.verify_prerequisites(config_root=config, component="discord")
        app.chmod(0o644)
        with patch.object(readiness, "launch_context", return_value=None), self.assertRaisesRegex(ValueError, "permissions"):
            readiness.verify_prerequisites(config_root=config)

    def test_native_app_setup_preserves_existing_other_configs_and_never_overwrites(self):
        credentials = load_script("configure_fawkes_credentials")
        config = self.root / "config"; config.mkdir(mode=0o700)
        existing = config / "notification.env"; existing.write_text("unrelated synthetic"); existing.chmod(0o600)
        answers = iter(("synthetic-app", "synthetic-provider"))
        path = credentials.configure(config_root=config, prompt=lambda label: next(answers))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(existing.read_text(), "unrelated synthetic")
        self.assertFalse((config / "discord-bot.env").exists())
        with self.assertRaises(FileExistsError):
            credentials.configure(config_root=config, prompt=lambda label: self.fail("must not reprompt"))
        path.unlink(); path.symlink_to(existing)
        with self.assertRaises(FileExistsError):
            credentials.configure(config_root=config, prompt=lambda label: self.fail("must not follow symlink"))
        self.assertEqual(existing.read_text(), "unrelated synthetic")

    def test_credentials_reject_directory_replacement_before_publication(self):
        credentials = load_script("configure_fawkes_credentials")
        config = self.root / "config"; config.mkdir(mode=0o700)
        count = 0
        def prompt(label):
            nonlocal count
            count += 1
            if count == 2:
                config.rename(self.root / "old-config")
                config.mkdir(mode=0o700)
            return "synthetic"
        with self.assertRaisesRegex(ValueError, "directory changed"):
            credentials.configure(config_root=config, prompt=prompt)
        self.assertFalse((config / "app.env").exists())
        self.assertFalse((self.root / "old-config/app.env").exists())

    def test_runtime_root_backup_includes_policy_and_workshop_revisions(self):
        from src.runtime import phase0_integrity as integrity
        policy = self.state / "database/preferences/one/personal_recording.json"
        workshop = self.state / "memory/development/workshop/one/proposal.2.json"
        write_json(policy, {"instance_id": "one", "revision": 3, "mode": "private"})
        write_json(workshop, {"instance_id": "one", "revision": 2, "status": "proposed"})
        with patch.dict(os.environ, {"FAWKES_RUNTIME_STATE_ROOT": str(self.state)}), patch.object(
                integrity, "ROOT", self.source):
            audit = integrity.audit_phoenix_state("one")
            self.assertTrue(audit["gate_satisfied"])
            paths = {item["path"] for item in audit["findings"]}
            self.assertIn(str(policy.relative_to(self.state)), paths)
            self.assertIn(str(workshop.relative_to(self.state)), paths)
            backup, _ = integrity.create_complete_state_backup("one", self.root / "backups")
        restored = self.root / "restored"
        integrity.restore_complete_state_backup(backup, restored, instance_id="one")
        self.assertEqual((restored / policy.relative_to(self.state)).read_bytes(), policy.read_bytes())
        self.assertEqual((restored / workshop.relative_to(self.state)).read_bytes(), workshop.read_bytes())
        self.assertFalse((self.source / "database").exists())

    def test_corrupt_runtime_registry_cannot_be_hidden_by_empty_fallback(self):
        from src.runtime import phase0_integrity as integrity
        (self.state / "conversations/registry.json").write_text("{invalid")
        with patch.dict(os.environ, {"FAWKES_RUNTIME_STATE_ROOT": str(self.state)}), patch.object(
                integrity, "ROOT", self.source):
            self.assertFalse(integrity.audit_phoenix_state("one")["gate_satisfied"])
            with self.assertRaises(ValueError):
                integrity.create_complete_state_backup("one", self.root / "backups")

    def test_readonly_sqlite_does_not_create_after_disappearance_or_allow_writes(self):
        import sqlite3
        from src.runtime import phase0_integrity as integrity
        path = self.state / "database/memory_processing.sqlite3"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE memory_work_items(instance_id TEXT)")
        connection.execute("INSERT INTO memory_work_items VALUES ('one')")
        connection.commit(); connection.close()
        before = path.read_bytes()
        with integrity._read_database(path) as connection:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("DELETE FROM memory_work_items")
        self.assertEqual(path.read_bytes(), before)
        connect = sqlite3.connect
        def disappear(*args, **kwargs):
            path.unlink()
            return connect(*args, **kwargs)
        with patch.object(integrity.sqlite3, "connect", side_effect=disappear):
            self.assertFalse(integrity.audit_phoenix_state("one", root=self.state)["gate_satisfied"])
        self.assertFalse(path.exists())

    def test_readonly_sqlite_connection_closes_on_query_error(self):
        import sqlite3
        from src.runtime import phase0_integrity as integrity
        path = self.state / "database/memory_processing.sqlite3"
        path.write_bytes(b"synthetic placeholder")
        class BrokenConnection:
            closed = False
            def execute(self, query):
                if query != "PRAGMA query_only=ON":
                    raise sqlite3.OperationalError("synthetic query failure")
            def close(self):
                self.closed = True
        connection = BrokenConnection()
        with patch.object(integrity.sqlite3, "connect", return_value=connection) as connect:
            self.assertFalse(integrity.audit_phoenix_state("one", root=self.state)["gate_satisfied"])
        self.assertTrue(connection.closed)
        self.assertTrue(connect.call_args.kwargs["uri"])
        self.assertTrue(connect.call_args.args[0].endswith("?mode=ro"))

    def test_backup_ledger_does_not_recreate_disappeared_source(self):
        import sqlite3
        from src.runtime import phase0_integrity as integrity
        path = self.state / "database/memory_processing.sqlite3"
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE memory_work_items(instance_id TEXT)")
        connection.commit(); connection.close()
        connect = sqlite3.connect
        def disappear(*args, **kwargs):
            path.unlink()
            self.assertTrue(kwargs["uri"])
            self.assertTrue(args[0].endswith("?mode=ro"))
            return connect(*args, **kwargs)
        with patch.object(integrity.sqlite3, "connect", side_effect=disappear):
            with self.assertRaises(sqlite3.OperationalError):
                integrity._filtered_work_ledger("one", self.state, self.root / "backup-files")
        self.assertFalse(path.exists())
        self.assertFalse((self.root / "backup-files/database/memory_processing.sqlite3").exists())

    def test_backup_ledger_closes_both_connections_on_copy_failure(self):
        import sqlite3
        from src.runtime import phase0_integrity as integrity
        path = self.state / "database/memory_processing.sqlite3"
        path.write_bytes(b"synthetic placeholder")
        class Connection:
            closed = False
            def execute(self, query):
                self.assertion = query
            def backup(self, destination):
                raise sqlite3.OperationalError("synthetic copy failure")
            def close(self):
                self.closed = True
        source, destination = Connection(), Connection()
        with patch.object(integrity.sqlite3, "connect", side_effect=(source, destination)):
            with self.assertRaises(sqlite3.OperationalError):
                integrity._filtered_work_ledger("one", self.state, self.root / "backup-files")
        self.assertEqual(source.assertion, "PRAGMA query_only=ON")
        self.assertTrue(source.closed)
        self.assertTrue(destination.closed)
