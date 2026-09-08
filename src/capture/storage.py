"""Complete local Archive metadata reads; no import-time storage mutation."""
import json
import os
from pathlib import Path
import stat


def metadata_paths(directory, *, allow_missing=False):
    directory=Path(directory)
    try:
        entries=os.scandir(directory)
    except FileNotFoundError:
        if allow_missing:return []
        raise
    # Only absence at open is optional. A scan that fails after opening cannot
    # establish an empty source, even when the reported error is ENOENT.
    with entries:
        paths=[directory/e.name for e in entries
               if e.name.endswith('.json') and not e.name.startswith('.')]
    return sorted(paths)


def decode_object(text):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('Ambiguous duplicate Archive JSON field')
            result[key]=value
        return result
    def nonfinite(value):raise ValueError('Non-finite Archive JSON value')
    value=json.loads(text,object_pairs_hook=pairs,parse_constant=nonfinite)
    if not isinstance(value,dict):raise ValueError('Archive record is not an object')
    return value


def read_metadata(path):
    path=Path(path)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('Archive metadata must be a regular non-symlink file')
    value=decode_object(path.read_text(encoding='utf-8'))
    validate_metadata(value,path)
    return value


def validate_metadata(value,path):
    """Writers must not acknowledge metadata the retained reader cannot use."""
    path=Path(path)
    if not isinstance(value,dict):raise ValueError('Archive metadata is not an object')
    for name in ('archive_id','instance_id','conversation_id','capture_event_id','capture_type'):
        item=value.get(name)
        if item is not None and (not isinstance(item,str) or not item):
            raise ValueError('Malformed Archive '+name)
    if not value.get('archive_id') or value['archive_id']!=path.stem:
        raise ValueError('Archive metadata identity does not match its file')
