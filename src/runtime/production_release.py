"""Exact, atomic production releases built from the Development workspace.

Release code is immutable after materialization. Durable Fawkes state remains
in the established canonical workspace paths and is linked into each release;
promotion changes code, never Phoenix identity or continuity.
"""

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid


DEVELOPMENT_ROOT = Path("/home/tvnner/fawkes")
PRODUCTION_ROOT = Path("/home/tvnner/.local/lib/fawkes-production")
RELEASES_ROOT = PRODUCTION_ROOT / "releases"
CURRENT_LINK = PRODUCTION_ROOT / "current"
PREVIOUS_LINK = PRODUCTION_ROOT / "previous"
SHARED_STATE = {
    "archive": DEVELOPMENT_ROOT / "archive",
    "database": DEVELOPMENT_ROOT / "database",
    "memory": DEVELOPMENT_ROOT / "memory",
    "library": DEVELOPMENT_ROOT / "library",
    "conversations": DEVELOPMENT_ROOT / "conversations",
    "instances": DEVELOPMENT_ROOT / "instances",
    "backups": DEVELOPMENT_ROOT / "backups",
    "logs": DEVELOPMENT_ROOT / "logs",
}
SCRIPT_NAMES = {
    "run_fawkes_discord_bot.py", "initialize_fawkes_discord_cursors.py",
    "fawkes_component_failure.py", "fawkes_failure_notifier.py",
    "show_fawkes_component_receipts.py", "wait_fawkes_app_ready.py",
    "fawkes_stack_status.sh", "fawkes_attention_events.py",
    "verify_fawkes_production_prerequisites.py",
    "run_fawkes_release.py",
}
DEVELOPMENT_RUNTIME_CLOSURE = frozenset({
    "src/runtime/codex_app_server.py",
    "src/runtime/codex_app_server_01534_schemas.json",
    "src/runtime/development_attention.py",
    "src/runtime/codex_development_campaign.py",
    "src/runtime/codex_development_handoff.py",
    "src/runtime/codex_worker_adapter.py",
    "src/runtime/codex_write_builder_adapter.py",
    "src/runtime/wsl_codex_reviewer.py",
    "src/runtime/worker_exchange.py",
    "src/app/server.py",
    "src/app/static/app.js",
    "scripts/fawkes_attention_events.py",
})


def _digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _release_path(root, release_id):
    if not re.fullmatch(r"fawkes-release-[0-9a-f]{64}", release_id):
        raise ValueError("invalid exact release ID")
    root = Path(root).resolve()
    path = root / "releases" / release_id
    if path.exists() and path.resolve().parent != root / "releases":
        raise ValueError("release escaped its owner")
    return path


def release_files(source=DEVELOPMENT_ROOT):
    source = Path(source).resolve()
    paths = [source / "requirements.txt"]
    paths.extend((source / "src").rglob("*.py"))
    paths.append(source / "src/runtime/codex_app_server_01534_schemas.json")
    paths.extend(path for path in (source / "src/app/static").rglob("*") if path.is_file())
    paths.extend(path for path in (source / "config").rglob("*") if path.is_file())
    paths.extend(path for path in (source / "deploy").rglob("*") if path.is_file())
    paths.extend(source / "scripts" / name for name in sorted(SCRIPT_NAMES))
    result = []
    for path in sorted(set(paths), key=lambda item: item.relative_to(source).as_posix()):
        resolved = path.resolve(strict=True)
        resolved.relative_to(source)
        if not resolved.is_file():
            raise ValueError(f"production source is not a regular file: {path}")
        result.append((path.relative_to(source).as_posix(), resolved))
    if source == DEVELOPMENT_ROOT:
        included = {relative for relative, _ in result}
        missing = DEVELOPMENT_RUNTIME_CLOSURE - included
        if missing:
            raise ValueError("production Development runtime closure is incomplete: " + ", ".join(sorted(missing)))
    return result


def _record(path):
    value = json.loads(Path(path).read_text())
    claimed = value.get("record_sha256")
    canonical = json.dumps({k: v for k, v in value.items() if k != "record_sha256"},
                           sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    if not claimed or claimed != _digest_bytes(canonical.encode()):
        raise ValueError("accepted integration evidence digest mismatch")
    return value


def accepted_source_binding(source, integration_path, acceptance_receipt_sha256,
                            accepted_integration_record_sha256):
    """Consume existing accepted lifecycle evidence; a clean checkout is not acceptance."""
    from src.runtime.disposable_verifier import candidate_manifest
    source = Path(source).resolve(strict=True)
    integration_path = Path(integration_path).resolve(strict=True)
    integrated = _record(integration_path)
    if integrated["record_sha256"] != accepted_integration_record_sha256:
        raise ValueError("integration record differs from the trusted handoff")
    terminal_path = integration_path.with_name("git-observation.json")
    terminal = _record(terminal_path)
    closed_path = integration_path.parents[2] / "evidence/closed-review.json"
    closed = json.loads(closed_path.read_text())
    receipt = closed["review_result"]["review_acceptance_receipt"]
    application = integrated["application_receipt"]
    application_binding = application.get("binding", {})
    review = terminal["reviews"][-1]
    expected = {
        "schema_version": 2, "record_type": "codex_independent_review_acceptance_receipt",
        "status": "accepted", "creates_authority": False,
        "campaign_id": terminal["campaign_id"], "package_id": application.get("package_id"),
        "review_report_id": application.get("review_report_id"),
        "candidate_snapshot_id": integrated.get("review_context_snapshot_id"),
        "mutation_manifest_sha256": integrated.get("mutation_digest_sha256"),
        "allowed_scope_sha256": application.get("allowed_scope_sha256"),
        "exact_change_evidence_sha256": application.get("exact_change_evidence_sha256"),
        "candidate_retention_receipt_sha256": application_binding.get("candidate_retention_receipt_sha256"),
        "review_invocation_id": application_binding.get("review_invocation_id"),
        "review_package_id": application_binding.get("review_package_id"),
        "review_package_sha256": application_binding.get("review_package_sha256"),
        "reviewer_worker_id": application_binding.get("reviewer_worker_id"),
        "reviewer_role": "wsl_read_only_code_health_review",
    }
    required_ids = ("package_id", "review_report_id", "source_report_id", "review_package_id",
                    "review_invocation_id", "reviewer_worker_id", "delivery_receipt_id",
                    "verification_receipt_id")
    required_hashes = ("mutation_manifest_sha256", "allowed_scope_sha256",
        "exact_change_evidence_sha256", "candidate_retention_receipt_sha256",
        "review_package_sha256", "review_report_sha256", "acceptance_condition_ids_sha256",
        "authoritative_preimages_sha256", "replay_identity")
    conditions = terminal.get("acceptance_condition_ids", [])
    conditions_hash = _digest_bytes(json.dumps(sorted(conditions), ensure_ascii=False,
                                                separators=(",", ":")).encode())
    if (any(receipt.get(key) != value for key, value in expected.items())
            or any(not isinstance(receipt.get(key), str) or not receipt[key] for key in required_ids)
            or any(not re.fullmatch("[0-9a-f]{64}", str(receipt.get(key, ""))) for key in required_hashes)
            or receipt.get("verdict") not in {"pass", "pass_with_caveats"}
            or not conditions or receipt["acceptance_condition_ids_sha256"] != conditions_hash
            or set(review.get("acceptance_condition_ids_satisfied", [])) != set(conditions)
            or review.get("violated_acceptance_condition_ids") != [] or review.get("defects") != []
            or receipt.get("recipient", {}).get("worker_id") != receipt["reviewer_worker_id"]
            or receipt.get("recipient", {}).get("role") != receipt["reviewer_role"]
            or application.get("schema_version") != 1
            or application.get("record_type") != "codex_post_review_authoritative_application_receipt"
            or application.get("status") != "applied_verified_after_review"
            or application.get("campaign_id") != terminal["campaign_id"]
            or application.get("candidate_snapshot_id") != receipt["candidate_snapshot_id"]
            or application_binding.get("candidate_snapshot_id") != receipt["candidate_snapshot_id"]
            or application.get("mutation_manifest_sha256") != receipt["mutation_manifest_sha256"]
            or terminal.get("record_type") != "codex_development_campaign"
            or integrated["git_receipt"].get("record_type") != "reviewed_git_commit_terminal_receipt_v01"):
        raise ValueError("exact canonical accepted receipt shape and bindings are required")
    valid = (closed.get("canonical_accepted") is True
        and receipt.get("status") == "accepted"
        and receipt.get("record_sha256") == acceptance_receipt_sha256
        and integrated.get("status") == "integrated"
        and terminal.get("status") == "succeeded"
        and closed["closed"]["campaign_id"] == terminal["campaign_id"]
        and closed["closed"]["reviews"][-1]["review_acceptance_receipt"] == receipt
        and terminal["reviews"][-1]["review_acceptance_receipt"] == receipt
        and integrated["acceptance_receipt_sha256"] == acceptance_receipt_sha256
        and integrated["application_receipt"] == terminal["application_evidence"]
        and integrated["git_receipt"] == terminal["git_commit_evidence"]
        and integrated["application_receipt"]["application_count"] == 1
        and integrated["git_receipt"]["status"] == "committed"
        and integrated["git_receipt"]["head"] == integrated["integration_commit"]
        and integrated["git_receipt"]["review_receipt_sha256"] == acceptance_receipt_sha256
        and integrated["git_receipt"]["application_receipt_sha256"] == integrated["application_receipt"]["record_sha256"]
        and integrated["application_receipt"]["review_acceptance_receipt_sha256"] == acceptance_receipt_sha256)
    if not valid:
        raise ValueError("source lacks exact accepted integration linkage")
    for evidence in (receipt, integrated["application_receipt"], integrated["git_receipt"], closed["closed"]):
        body = json.dumps({k: v for k, v in evidence.items() if k != "record_sha256"},
                          sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        if evidence.get("record_sha256") != _digest_bytes(body.encode()):
            raise ValueError("accepted receipt digest mismatch")
    def git(*args):
        return subprocess.run(["git", "--no-optional-locks", "-C", str(source), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    head = git("rev-parse", "HEAD")
    if head != integrated["integration_commit"] or git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("source is not the exact clean integrated commit")
    snapshot = candidate_manifest(source)["candidate_snapshot_id"]
    if snapshot != integrated["product_candidate_snapshot_id"]:
        raise ValueError("accepted source snapshot mismatch")
    return {"integration_commit": head, "candidate_snapshot_id": snapshot,
            "integration_record_sha256": accepted_integration_record_sha256,
            "acceptance_receipt_sha256": acceptance_receipt_sha256,
            "campaign_id": terminal["campaign_id"], "creates_authority": False,
            "evidence": [{"path": str(path), "sha256": _digest_bytes(path.read_bytes())}
                         for path in (integration_path, terminal_path, closed_path)]}


def state_owner_binding(state_root, instance_id):
    """Validate existing ownership metadata only; never initialize or move state."""
    root = Path(state_root).resolve(strict=True)
    for name in ("archive", "database", "memory", "library", "conversations", "instances"):
        if not (root / name).is_dir():
            raise ValueError(f"existing state directory unavailable: {name}")
    registry_path = root / "instances/registry.json"
    registry = json.loads(registry_path.read_text())
    matches = [item for item in registry.get("instances", []) if item.get("name") == "Fawkes"]
    selected = [item for item in registry.get("instances", []) if item.get("instance_id") == instance_id]
    if (registry.get("schema_version") != 1 or len(matches) != 1
            or len(selected) != 1 or matches[0].get("instance_id") != instance_id):
        raise ValueError("state root does not bind the exact existing Fawkes instance")
    return {"root": str(root), "instance_id": instance_id,
            "registry_sha256": _digest_bytes(registry_path.read_bytes())}


def materialize_release(*, source, state_root, instance_id, accepted_integration,
                        acceptance_receipt_sha256, accepted_integration_record_sha256,
                        production_root=PRODUCTION_ROOT,
                        validation_reference):
    source, production_root = Path(source).resolve(), Path(production_root)
    releases = production_root / "releases"
    acceptance = accepted_source_binding(source, accepted_integration, acceptance_receipt_sha256,
                                        accepted_integration_record_sha256)
    owner = state_owner_binding(state_root, instance_id)
    from src.runtime.disposable_verifier import candidate_manifest
    inventory = candidate_manifest(source)
    if inventory['candidate_snapshot_id'] != acceptance['candidate_snapshot_id']:
        raise ValueError('accepted source inventory changed')
    accepted_files = {entry['path']:entry for entry in inventory['files']}
    entries = []
    for relative, path in release_files(source):
        if relative not in accepted_files:
            raise ValueError('packaged path outside accepted source inventory: ' + relative)
        body = path.read_bytes()
        if _digest_bytes(body) != accepted_files[relative]['sha256']:
            raise ValueError('packaged content differs from accepted source: ' + relative)
        entries.append({"path": relative, "sha256": _digest_bytes(body), "size_bytes": len(body)})
    identity_body = json.dumps({"files": entries, "accepted_source": acceptance, "state_owner": owner},
                               sort_keys=True, separators=(",", ":")).encode()
    release_id = "fawkes-release-" + _digest_bytes(identity_body)
    target = releases / release_id
    if target.exists():
        verify_release(target)
        return json.loads((target / "release.json").read_text())
    staging = releases / f".{release_id}.{uuid.uuid4().hex}.staging"
    staging.mkdir(parents=True, mode=0o755)
    try:
        for entry in entries:
            source_path = source / entry["path"]
            destination = staging / entry["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, destination)
            if _digest_bytes(destination.read_bytes()) != entry['sha256']:
                raise ValueError('accepted source changed while copying')
            os.chmod(destination, 0o755 if entry["path"].startswith("scripts/") else 0o644)
        state_links = {}
        for name in SHARED_STATE:
            link_target = Path(owner["root"]) / name
            if link_target.exists():
                (staging / name).symlink_to(link_target, target_is_directory=True)
                state_links[name] = str(link_target)
        if accepted_source_binding(source, accepted_integration, acceptance_receipt_sha256,
                                   accepted_integration_record_sha256) != acceptance:
            raise ValueError("accepted source changed during materialization")
        if state_owner_binding(state_root, instance_id) != owner:
            raise ValueError('state owner changed during materialization')
        record = {"schema_version": 2, "release_id": release_id,
                  "created_at": datetime.now(timezone.utc).isoformat(),
                  "source_root": str(source), "validation_reference": validation_reference,
                  "files": entries, "state_links": state_links,
                  "accepted_source": acceptance, "state_owner": owner,
                  "creates_phoenix_identity": False}
        record["manifest_sha256"] = _digest_bytes(json.dumps(
            record, sort_keys=True, separators=(",", ":")).encode())
        (staging / "release.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        os.chmod(staging / "release.json", 0o444)
        staging.rename(target)
        for path in target.rglob("*"):
            if path.is_file() and not path.is_symlink():
                os.chmod(path, path.stat().st_mode & ~0o222)
        return record
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_release(path):
    path = Path(path).resolve()
    record = json.loads((path / "release.json").read_text())
    claimed = record.pop("manifest_sha256")
    actual = _digest_bytes(json.dumps(record, sort_keys=True, separators=(",", ":")).encode())
    if claimed != actual:
        raise ValueError("production release manifest integrity mismatch")
    _legacy_verifier().verify_code_inventory(path, record)
    for entry in record["files"]:
        candidate = (path / entry["path"]).resolve(strict=True)
        candidate.relative_to(path)
        if _digest_bytes(candidate.read_bytes()) != entry["sha256"]:
            raise ValueError(f"production release file digest mismatch: {entry['path']}")
    if record.get("schema_version") == 2:
        owner = record["state_owner"]
        if state_owner_binding(owner["root"], owner["instance_id"]) != owner:
            raise ValueError('production state owner identity changed')
        for name, target in record["state_links"].items():
            if (name not in SHARED_STATE or not (path / name).is_symlink()
                    or (path / name).resolve(strict=True) != Path(owner["root"]) / name
                    or Path(target) != Path(owner["root"]) / name):
                raise ValueError("production state binding mismatch")
    return {**record, "manifest_sha256": claimed}


def _atomic_link(link, target):
    link.parent.mkdir(parents=True, exist_ok=True)
    temporary = link.with_name(f".{link.name}.{uuid.uuid4().hex}.tmp")
    temporary.symlink_to(target)
    temporary.replace(link)


def environment_identity(environment):
    """Bind complete installed dependency bytes, links and executable identity."""
    environment = Path(environment).resolve(strict=True)
    python = environment / 'bin/python'
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError('release interpreter unavailable or not executable')
    nodes = []
    for parent, dirs, files in os.walk(environment, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(parent) / name
            relative = path.relative_to(environment).as_posix()
            if relative == 'ready.json':
                continue
            node = {'path':relative, 'mode':path.lstat().st_mode & 0o777}
            if path.is_symlink():
                target = path.resolve(strict=True)
                node.update(type='symlink', target=os.readlink(path))
                if target.is_file():
                    node['resolved_sha256'] = _digest_bytes(target.read_bytes())
                elif not target.is_dir() or not target.is_relative_to(environment):
                    raise ValueError('environment directory link escapes its owner')
            elif path.is_file():
                node.update(type='file', sha256=_digest_bytes(path.read_bytes()))
            elif path.is_dir():
                node['type'] = 'directory'
            else:
                raise ValueError('unsupported environment node')
            nodes.append(node)
    return _digest_bytes(json.dumps(sorted(nodes, key=lambda n:n['path']),
        sort_keys=True, separators=(',', ':')).encode())


def prepare_environment(release_id, *, production_root=PRODUCTION_ROOT, runner=subprocess.run):
    """Prepare only this immutable release's environment, never the current venv.

    The injected runner is solely a synthetic-test seam. CLI uses subprocess.run.
    Failed environments are retained without a ready receipt for diagnosis.
    """
    root = Path(production_root).resolve()
    release = _release_path(root, release_id)
    record = verify_release(release)
    if record.get("schema_version") != 2:
        raise ValueError("new environment preparation requires an accepted bound release")
    environment = root / "environments" / release_id
    if environment.exists():
        return verify_environment(release, production_root=root)
    environment.mkdir(parents=True)
    python = environment / "bin/python"
    clean_env = {key: value for key, value in os.environ.items()
                 if key in {"PATH", "LANG", "LC_ALL", "SYSTEMROOT", "TMPDIR"}}
    clean_env.update(PYTHONDONTWRITEBYTECODE="1", PIP_CONFIG_FILE=os.devnull)
    commands = ([sys.executable, "-m", "venv", str(environment)],
                [str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-input",
                 "-r", str(release / "requirements.txt")],
                [str(python), "-m", "pip", "check"],
                [str(python), "-I", "-B", "-c",
                 "import openai,pypdf,websocket; from langgraph.graph import StateGraph; "
                 "from langgraph.checkpoint.sqlite import SqliteSaver"])
    for command in commands:
        runner(command, cwd=str(environment), env=clean_env, check=True,
               capture_output=True, text=True)
    if not python.is_file() or not (environment / "pyvenv.cfg").is_file():
        raise ValueError("prepared environment is incomplete")
    # Recheck source and state links before declaring readiness. No app/provider
    # is constructed by the import-only dependency probe.
    verify_release(release)
    ready = {"schema_version": 1, "release_id": release_id,
             "manifest_sha256": record["manifest_sha256"], "status": "ready",
             "environment": str(environment),
             "environment_identity_sha256": environment_identity(environment),
             "pyvenv_cfg_sha256": _digest_bytes((environment / "pyvenv.cfg").read_bytes()),
             "requirements_sha256": _digest_bytes((release / "requirements.txt").read_bytes())}
    ready["record_sha256"] = _digest_bytes(json.dumps(ready, sort_keys=True, ensure_ascii=False,
                                                     separators=(",", ":")).encode())
    (environment / "ready.json").write_text(json.dumps(ready, sort_keys=True, indent=2) + "\n")
    (environment / "ready.json").chmod(0o444)
    return ready


def verify_environment(release, *, production_root=PRODUCTION_ROOT):
    release = Path(release).resolve(strict=True)
    record = verify_release(release)
    environment = Path(production_root).resolve() / "environments" / record["release_id"]
    if release != _release_path(production_root, record["release_id"]).resolve(strict=True):
        raise ValueError("environment belongs to another release owner")
    ready = _record(environment / "ready.json")
    if (record.get("schema_version") != 2 or ready.get("status") != "ready"
            or ready.get("release_id") != record["release_id"]
            or ready.get("manifest_sha256") != record["manifest_sha256"]
            or ready.get("environment") != str(environment)
            or ready.get("environment_identity_sha256") != environment_identity(environment)
            or not (environment / "bin/python").is_file()
            or ready.get("pyvenv_cfg_sha256") != _digest_bytes((environment / "pyvenv.cfg").read_bytes())
            or ready.get("requirements_sha256") != _digest_bytes((release / "requirements.txt").read_bytes())):
        raise ValueError("release environment is not verified and ready")
    return ready


def _legacy_verifier():
    # The stable launcher must also verify schema-1 code whose old owner module
    # has no new environment API. Reuse that same maintained verifier here.
    import importlib.util
    path = Path(__file__).resolve().parents[2] / 'scripts/run_fawkes_release.py'
    spec = importlib.util.spec_from_file_location('_fawkes_legacy_verifier', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bind_legacy_environments(*, state_root, instance_id, production_root=PRODUCTION_ROOT, runner=subprocess.run):
    """Explicitly preserve only currently bound schema-1 release rollback ability."""
    root = Path(production_root).resolve()
    owner = state_owner_binding(state_root, instance_id)
    path = root / "legacy-environments.json"
    if path.exists() or path.is_symlink():
        raise ValueError("legacy environment binding already exists; preserve it")
    bindings = {}
    for name in ("current", "previous"):
        link = root / name
        if not link.is_symlink():
            continue
        release = link.resolve(strict=True)
        record = verify_release(release)
        if record.get("schema_version") != 1:
            continue
        identity = _legacy_verifier().legacy_environment_identity(root, release, runner=runner)
        for state_name in ("archive", "database", "memory", "library", "conversations", "instances"):
            if (not (release / state_name).is_symlink()
                    or (release / state_name).resolve(strict=True) != Path(owner["root"]) / state_name):
                raise ValueError("legacy release uses a different state owner")
        bindings[str(release)] = {"manifest_sha256": record["manifest_sha256"], "state_owner": owner,
                                  'environment_identity': identity}
    with path.open("x") as handle:
        json.dump({"schema_version": 1, "releases": bindings}, handle, sort_keys=True, indent=2)
        handle.write("\n")
    path.chmod(0o444)
    return {"legacy_releases_bound": len(bindings)}


def _release_event(root, action, record, previous=None):
    event_root = Path(root) / "release-events"
    event_root.mkdir(parents=True, exist_ok=True)
    value = {"schema_version": 1, "event_id": f"release-event-{uuid.uuid4()}",
             "timestamp_utc": datetime.now(timezone.utc).isoformat(), "action": action,
             "release_id": record["release_id"], "manifest_sha256": record["manifest_sha256"],
             "previous_release_id": previous, "creates_phoenix_identity": False}
    path = event_root / f"{value['timestamp_utc'].replace(':', '')}-{value['event_id']}.json"
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    return value


def promote_release(release_id, *, production_root=PRODUCTION_ROOT):
    root = Path(production_root)
    target = _release_path(root, release_id)
    record = verify_release(target)
    verify_environment(target, production_root=root)
    launcher = root / "run_fawkes_release.py"
    if not launcher.is_file() or launcher.read_bytes() != (target / "scripts/run_fawkes_release.py").read_bytes():
        raise ValueError("verified release launcher must be installed before promotion")
    current = root / "current"
    previous = root / "previous"
    previous_id = None
    if current.is_symlink():
        if current.resolve(strict=True) == target.resolve(strict=True):
            # Retry after a service-start failure must not overwrite rollback.
            return record
        previous_id = current.resolve().name
        _atomic_link(previous, current.resolve())
    _atomic_link(current, target.resolve())
    _release_event(root, "promote", record, previous_id)
    return record


def rollback_release(*, production_root=PRODUCTION_ROOT):
    root = Path(production_root)
    previous = root / "previous"
    if not previous.is_symlink():
        raise RuntimeError("no previous approved Fawkes release is available")
    target = previous.resolve()
    record = verify_release(target)
    if record.get("schema_version") == 2:
        verify_environment(target, production_root=root)
    else:
        _legacy_verifier().verify_legacy_binding(root.resolve(), target, record)
    current = root / "current"
    old_current = current.resolve() if current.is_symlink() else None
    _atomic_link(current, target)
    if old_current is not None:
        _atomic_link(previous, old_current)
    record = verify_release(target)
    _release_event(root, "rollback", record, old_current.name if old_current else None)
    return record
