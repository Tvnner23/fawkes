"""Recoverable local record/event writes for the existing JSON Memory store.

One operation stages its complete postimages before publishing a durable intent.
Readers take the same lock and finish interrupted publication before observing
state. This is derived-Memory recovery, never Archive mutation or authorization.
Runtime directories must be owned by the caller; hostile same-account writers
are not a supported isolation boundary. Uncoordinated changes fail closed.
"""
from functools import wraps
from pathlib import Path
import hashlib
import json
import os
import stat
import threading
import uuid

_local = threading.local()
_lock = threading.RLock()


class MemoryRecoveryRequired(ValueError):
    """Invalid or conflicting retained state requires an explicit decision."""


def _encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _directory(path):
    path = Path(path).absolute()
    if path.resolve() != path:
        raise MemoryRecoveryRequired("Memory storage directory cannot traverse a symlink")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not stat.S_ISDIR(path.stat().st_mode):
        raise MemoryRecoveryRequired("Memory storage directory is unavailable")
    # A preceding attempt may have stopped after mkdir but before synchronizing
    # its parent. Existing entries therefore need this fence too, before intent
    # publication. Work bottom-up so every ancestor name is durable on POSIX.
    for parent in path.parents:
        _sync_directory(parent)
    return path


def _target(path, roots):
    if not isinstance(path,(str,Path)):
        raise MemoryRecoveryRequired("Memory mutation target path is malformed")
    path = Path(path).absolute()
    if path.parent not in roots or not path.name.endswith('.json') or path.name.startswith('.'):
        raise MemoryRecoveryRequired("Memory mutation target is outside record/event storage")
    try:
        mode=path.lstat().st_mode
    except FileNotFoundError:
        mode=None
    if mode is not None and not stat.S_ISREG(mode):
        raise MemoryRecoveryRequired("Memory mutation target is not a regular file")
    return path


def _sync_directory(path):
    if os.name == 'posix':
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def durable_write(path, text):
    """Atomic replacement plus filesystem synchronization; injectable in tests."""
    temporary = path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _current(path):
    # exists()/glob() can suppress OSError on supported Python versions. Only
    # an explicit ENOENT is absence; access and enumeration failures must retry.
    try:
        return path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return None
    except UnicodeError as exc:
        raise MemoryRecoveryRequired('Retained Memory text is not valid UTF-8') from exc


def _publish(intent, roots, pending):
    if not isinstance(intent, dict) or set(intent) != {'roots','writes','sha256'}:
        raise MemoryRecoveryRequired("Malformed pending Memory mutation")
    body = {k:intent[k] for k in ('roots','writes')}
    if intent['sha256'] != hashlib.sha256(_encode(body).encode()).hexdigest():
        raise MemoryRecoveryRequired("Pending Memory mutation digest mismatch")
    if body['roots'] != [str(root) for root in roots] or not isinstance(body['writes'], list) or not body['writes']:
        raise MemoryRecoveryRequired("Pending Memory mutation storage binding mismatch")
    checked = []
    seen = set()
    # Validate every pre/postimage before publishing any part of the operation.
    for entry in body['writes']:
        if not isinstance(entry, dict) or set(entry) != {'path','before','after'}:
            raise MemoryRecoveryRequired("Malformed pending Memory write")
        path = _target(entry['path'], roots)
        if path in seen or not isinstance(entry['after'], str) or not isinstance(entry['before'], (str,type(None))):
            raise MemoryRecoveryRequired("Malformed or duplicate pending Memory target")
        seen.add(path)
        _decode_retained(entry['after'])
        current = _current(path)
        if current not in (entry['before'], entry['after']):
            raise MemoryRecoveryRequired("Memory recovery conflicts with an uncoordinated change")
        checked.append((path,entry,current))
    # An earlier process may have renamed the intent but failed its directory
    # fsync. No postimage may be published until that recovery route is durable.
    # On failure leave both the intent and all checked postimages untouched.
    _sync_directory(pending.parent)
    for path,entry,current in checked:
        if current != entry['after']:
            durable_write(path,entry['after'])
    # A prior process may have renamed a matching postimage but stopped before
    # syncing its directory. Matching bytes alone do not prove durable naming.
    for directory in sorted({path.parent for path,_,_ in checked}):
        _sync_directory(directory)
    pending.unlink()
    _sync_directory(pending.parent)


def write_json(path, value):
    state = getattr(_local,'state',None)
    if state is None:
        raise RuntimeError("Memory write must belong to a serialized mutation")
    path = _target(path,state['roots'])
    text = _encode(value)+'\n'
    if path not in state['writes']:
        state['writes'][path] = {'path':str(path),'before':_current(path),'after':text}
    else:
        state['writes'][path]['after'] = text


def read_json(path):
    state = getattr(_local,'state',None)
    if state is None:
        raise RuntimeError("Memory read must belong to a serialized operation")
    path = _target(path,state['roots'])
    entry = state['writes'].get(path)
    text = entry['after'] if entry else _current(path)
    return _decode_retained(text) if text is not None else None


def _decode_retained(text):
    if not isinstance(text,str):
        raise MemoryRecoveryRequired('Retained Memory text is missing or malformed')
    def unique_fields(pairs):
        result={}
        for key,value in pairs:
            if key in result:
                raise MemoryRecoveryRequired('Retained Memory JSON has ambiguous duplicate fields')
            result[key]=value
        return result
    def invalid_constant(value):
        raise MemoryRecoveryRequired('Retained Memory JSON contains a non-finite number')
    try:
        value=json.loads(text,object_pairs_hook=unique_fields,parse_constant=invalid_constant)
    except (ValueError,UnicodeError) as exc:
        raise MemoryRecoveryRequired('Retained Memory JSON is malformed; explicit recovery required') from exc
    if not isinstance(value,dict):
        raise MemoryRecoveryRequired('Retained Memory JSON must be an object; explicit recovery required')
    return value


def json_paths(directory):
    state = _local.state
    directory = Path(directory).absolute()
    # Consume the complete scan before returning any result. A partial failed
    # iterator may not establish absence or publish an incomplete record set.
    with os.scandir(directory) as entries:
        paths={directory/entry.name for entry in entries
               if entry.name.endswith('.json') and not entry.name.startswith('.')}
    paths.update(p for p in state['writes'] if p.parent == directory)
    return sorted(paths)


def _file_lock(fd, acquire):
    if os.name == 'posix':
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX if acquire else fcntl.LOCK_UN)
    elif os.name == 'nt':
        import msvcrt
        os.lseek(fd,0,os.SEEK_SET)
        msvcrt.locking(fd,msvcrt.LK_LOCK if acquire else msvcrt.LK_UNLCK,1)
    else:
        raise RuntimeError("No supported Memory mutation lock on this platform")


def transactional(roots_callback):
    def decorate(function):
        @wraps(function)
        def call(*args,**kwargs):
            with _lock:
                roots = tuple(_directory(p) for p in roots_callback())
                if len(set(roots)) != 2:
                    raise MemoryRecoveryRequired("Memory record and event directories must differ")
                nested = getattr(_local,'state',None)
                if nested is not None:
                    if nested['roots'] != roots:
                        raise MemoryRecoveryRequired("Memory storage changed during an operation")
                    return function(*args,**kwargs)
                lockpath = roots[0]/'.mutation.lock'
                if lockpath.is_symlink():
                    raise MemoryRecoveryRequired("Memory lock cannot be a symlink")
                fd = os.open(lockpath,os.O_RDWR | os.O_CREAT | getattr(os,'O_NOFOLLOW',0),0o600)
                acquired = False
                try:
                    if not stat.S_ISREG(os.fstat(fd).st_mode):
                        raise MemoryRecoveryRequired("Memory lock is not a regular file")
                    if os.fstat(fd).st_size == 0:
                        os.write(fd,b'0');os.fsync(fd)
                    _file_lock(fd,True)
                    acquired = True
                    pending = roots[0]/'.pending-mutation.json'
                    try:
                        pending_mode=pending.lstat().st_mode
                    except FileNotFoundError:
                        pending_mode=None
                    if pending_mode is not None and not stat.S_ISREG(pending_mode):
                        raise MemoryRecoveryRequired("Memory recovery intent must be a regular file")
                    if pending_mode is not None:
                        try:
                            intent=_decode_retained(_current(pending))
                            _publish(intent,roots,pending)
                        except (ValueError,UnicodeError) as exc:
                            raise MemoryRecoveryRequired(str(exc)) from exc
                    state = {'roots':roots,'writes':{}}
                    _local.state = state
                    try:
                        result = function(*args,**kwargs)
                        if state['writes']:
                            body = {'roots':[str(p) for p in roots],'writes':list(state['writes'].values())}
                            intent = {**body,'sha256':hashlib.sha256(_encode(body).encode()).hexdigest()}
                            durable_write(pending,_encode(intent)+'\n')
                            _publish(intent,roots,pending)
                        return result
                    finally:
                        _local.state = None
                finally:
                    try:
                        if acquired:
                            _file_lock(fd,False)
                    finally:
                        os.close(fd)
        return call
    return decorate
