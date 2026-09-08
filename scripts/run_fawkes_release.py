#!/usr/bin/env python3
"""Stable launcher installed outside current so an explicitly bound old release can roll back."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess

PRODUCTION_ROOT = Path("/home/tvnner/.local/lib/fawkes-production")


def verify_code_inventory(release, record):
    """Reject unlisted/shadowing code before importing any release module."""
    release = Path(release).resolve(strict=True)
    listed = [entry['path'] for entry in record['files']]
    if (len(set(listed)) != len(listed) or any(
            not isinstance(name, str) or Path(name).is_absolute()
            or Path(name).as_posix() != name or '..' in Path(name).parts
            or name == 'release.json' for name in listed)):
        raise ValueError('invalid release inventory')
    expected = set(listed) | {'release.json'}
    directories = {p.as_posix() for name in expected for p in Path(name).parents if p != Path('.')}
    links = record.get('state_links', {})
    if not isinstance(links, dict) or not set(links) <= {
            'archive', 'database', 'memory', 'library', 'conversations', 'instances', 'backups', 'logs'}:
        raise ValueError('invalid release state links')
    found, found_links = set(), set()
    for parent, dirs, files in os.walk(release, followlinks=False):
        for name in dirs + files:
            path = Path(parent) / name
            relative = path.relative_to(release).as_posix()
            if relative in links:
                if not path.is_symlink() or path.resolve(strict=True) != Path(links[relative]).resolve(strict=True):
                    raise ValueError('release state binding mismatch')
                found_links.add(relative)
            elif path.is_symlink():
                raise ValueError('unlisted release symlink')
            elif path.is_dir():
                if relative not in directories:
                    raise ValueError('unlisted release directory: ' + relative)
            elif path.is_file() and relative in expected:
                found.add(relative)
            else:
                raise ValueError('unlisted release file: ' + relative)
    if found != expected or found_links != set(links):
        raise ValueError('release inventory incomplete')


def installed_environment_digest(environment):
    """Bind dependency contents as well as metadata, without importing release code."""
    environment = Path(environment).resolve(strict=True)
    nodes = []
    for parent, dirs, files in os.walk(environment, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(parent) / name
            node = {'path':path.relative_to(environment).as_posix(), 'mode':path.lstat().st_mode & 0o777}
            if path.is_symlink():
                target = path.resolve(strict=True)
                node.update(type='symlink', target=os.readlink(path))
                if target.is_file():
                    node['resolved_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
                elif not target.is_dir() or not target.is_relative_to(environment):
                    raise ValueError('legacy environment directory link escapes its owner')
            elif path.is_file():
                node.update(type='file', sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            elif path.is_dir():
                node['type'] = 'directory'
            else:
                raise ValueError('unsupported legacy environment node')
            nodes.append(node)
    return hashlib.sha256(json.dumps(sorted(nodes,key=lambda n:n['path']),
        sort_keys=True,separators=(',',':')).encode()).hexdigest()


def legacy_environment_identity(root, release, *, runner=subprocess.run):
    """Recheck the old environment without installing packages or calling a provider."""
    environment = Path(root).resolve(strict=True) / 'venv'
    python = environment / 'bin/python'
    cfg = environment / 'pyvenv.cfg'
    requirements = Path(release) / 'requirements.txt'
    if not python.is_file() or not os.access(python, os.X_OK) or not cfg.is_file():
        raise ValueError('legacy interpreter/environment unavailable')
    clean = {key: value for key, value in os.environ.items() if key in {'PATH', 'LANG', 'LC_ALL'}}
    clean.update(PYTHONDONTWRITEBYTECODE='1', PIP_CONFIG_FILE=os.devnull)
    contents = installed_environment_digest(environment)
    probe = '''import importlib,importlib.metadata as m,json,pathlib,sys
from pip._vendor.packaging.requirements import Requirement
modules={'openai':'openai','pypdf':'pypdf','websocket-client':'websocket',
 'langgraph':'langgraph.graph','langgraph-checkpoint-sqlite':'langgraph.checkpoint.sqlite'}
for line in pathlib.Path(sys.argv[1]).read_text().splitlines():
    line=line.strip()
    if not line or line.startswith('#'): continue
    r=Requirement(line)
    if r.marker and not r.marker.evaluate(): continue
    if r.url or not r.specifier.contains(m.version(r.name),prereleases=True):
        raise ValueError('legacy requirement not satisfied: '+r.name)
    key=r.name.lower().replace('_','-')
    if key not in modules: raise ValueError('legacy requirement lacks an import probe: '+r.name)
    importlib.import_module(modules[key])
print(json.dumps({'prefix':str(pathlib.Path(sys.prefix).resolve()),'version':sys.version,
 'packages':sorted((d.metadata['Name'],d.version) for d in m.distributions())}))
'''
    runner([str(python), '-I', '-B', '-m', 'pip', 'check'], cwd=str(environment),
           env=clean, check=True, capture_output=True, text=True, timeout=30)
    checked = runner([str(python), '-I', '-B', '-c', probe, str(requirements)],
        cwd=str(environment), env=clean, check=True, capture_output=True, text=True, timeout=30)
    detail = json.loads(checked.stdout)
    if detail.get('prefix') != str(environment.resolve()):
        raise ValueError('legacy interpreter belongs to another environment')
    if installed_environment_digest(environment) != contents:
        raise ValueError('legacy environment changed during verification')
    return {'environment':str(environment), 'interpreter_sha256':hashlib.sha256(python.read_bytes()).hexdigest(),
            'installed_contents_sha256':contents,
            'pyvenv_cfg_sha256':hashlib.sha256(cfg.read_bytes()).hexdigest(),
            'requirements_sha256':hashlib.sha256(requirements.read_bytes()).hexdigest(),
            'runtime':detail}


def verify_legacy_binding(root, release, record, *, runner=subprocess.run):
    binding = json.loads((Path(root) / 'legacy-environments.json').read_text())['releases'].get(str(release))
    if not binding or binding['manifest_sha256'] != record['manifest_sha256']:
        raise ValueError('legacy release/environment binding unavailable')
    state = binding['state_owner']
    state_root = Path(state['root']).resolve(strict=True)
    registry_path = state_root / 'instances/registry.json'
    registry = json.loads(registry_path.read_text())
    matches = [item for item in registry.get('instances', []) if item.get('name') == 'Fawkes']
    selected = [item for item in registry.get('instances', []) if item.get('instance_id') == state['instance_id']]
    if (registry.get('schema_version') != 1 or len(matches) != 1
            or len(selected) != 1
            or matches[0].get('instance_id') != state['instance_id']
            or hashlib.sha256(registry_path.read_bytes()).hexdigest() != state['registry_sha256']):
        raise ValueError('legacy state identity changed')
    for name in ('archive', 'database', 'memory', 'library', 'conversations', 'instances'):
        if (not (Path(release) / name).is_symlink() or not (state_root / name).is_dir()
                or (Path(release) / name).resolve(strict=True) != state_root / name):
            raise ValueError('legacy state binding changed')
    if legacy_environment_identity(root, release, runner=runner) != binding.get('environment_identity'):
        raise ValueError('legacy environment changed or was never verified')
    return state


def launch_context(production_root=PRODUCTION_ROOT):
    root = Path(production_root).resolve(strict=True)
    current = root / "current"
    if not current.is_symlink():
        raise ValueError("no explicitly promoted current release")
    release = current.resolve(strict=True)
    if release.parent != root / "releases":
        raise ValueError("current release is outside the release owner")
    manifest = json.loads((release / "release.json").read_text())
    claimed = manifest.pop("manifest_sha256")
    if hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest() != claimed:
        raise ValueError("release manifest integrity mismatch")
    verify_code_inventory(release, manifest)
    for entry in manifest["files"]:
        file = (release / entry["path"]).resolve(strict=True)
        if not file.is_relative_to(release) or hashlib.sha256(file.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("release file integrity mismatch")
    if "src/runtime/production_release.py" not in {entry["path"] for entry in manifest["files"]}:
        raise ValueError("release owner is not in the verified inventory")
    spec = importlib.util.spec_from_file_location("_fawkes_release_owner",
        release / "src/runtime/production_release.py")
    owner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    record = owner.verify_release(release)
    if record.get("schema_version") == 2:
        owner.verify_environment(release, production_root=root)
        python = root / "environments" / record["release_id"] / "bin/python"
        state = record["state_owner"]
    elif record.get("schema_version") == 1:
        # No generic fallback: only a release captured from actual current or
        # previous before installing this launcher can use the old shared venv.
        state = verify_legacy_binding(root, release, record)
        python = root / "venv/bin/python"
    else:
        raise ValueError("unsupported release schema")
    if not python.is_file():
        raise ValueError("bound release interpreter unavailable")
    state_root = Path(state["root"])
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment.update(FAWKES_RUNTIME_STATE_ROOT=str(state_root),
        FAWKES_INSTANCE_ID=state['instance_id'],
        FAWKES_DEVELOPMENT_ROOT=record["source_root"],
        FAWKES_APP_SESSION_ROOT=str(state_root / "database/app_sessions"),
        FAWKES_CONSOLE_UPDATE_ROOT=str(state_root / "database/console_updates"),
        PYTHONDONTWRITEBYTECODE="1")
    return python, release, environment


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        raise ValueError("a release-local Python entrypoint is required")
    python, release, environment = launch_context()
    os.chdir(release)
    os.execve(str(python), [str(python), "-B", *args], environment)


if __name__ == "__main__":
    main()
