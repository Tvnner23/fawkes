"""Exact, explicitly enabled Windows clipboard delivery for saved console updates.

No permissions, campaigns, provider jobs or clipboard polling are created here.
The accepted PC launcher supplies pinned Windows identity; other servers default
to no clipboard writer. A retry observes its old attempt and never repeats it.
"""
import base64
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import secrets
import subprocess
import time

MAX_BYTES = 96000
EXECUTABLE = Path('/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe')

def digest(body):
    return hashlib.sha256(body).hexdigest()

def now():
    return datetime.now(timezone.utc).isoformat()

def unique_object(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('duplicate clipboard field')
        value[key]=item
    return value

class WindowsClipboardWriter:
    """One fixed STA operation under the configured Windows user/session."""
    def __init__(self, *, executable_sha256, windows_sid, windows_session_id,
                 run=subprocess.run, clock=time.time):
        if not re.fullmatch('[a-f0-9]{64}', executable_sha256):
            raise ValueError('expected Windows executable hash required')
        if not re.fullmatch(r'S-1-[0-9-]+', windows_sid) or type(windows_session_id) is not int or windows_session_id<=0:
            raise ValueError('expected interactive Windows identity required')
        self.sha=executable_sha256;self.sid=windows_sid;self.session=windows_session_id
        self.run=run;self.clock=clock

    def __call__(self, update, attempt_id, intent_path):
        text=update['content'];body=text.encode('utf-8')
        if not body or len(body)>MAX_BYTES or '\0' in text or digest(body)!=update['content_sha256']:
            raise ValueError('saved clipboard content identity invalid')
        if not re.fullmatch('console-update-[a-f0-9]{64}',update['snapshot_id']) or not re.fullmatch('[a-f0-9]{32}',attempt_id):
            raise ValueError('clipboard operation identity invalid')
        distribution=os.environ.get('WSL_DISTRO_NAME','')
        intent_path=Path(intent_path)
        if (not re.fullmatch('[A-Za-z0-9._-]{1,64}',distribution)
                or not intent_path.is_absolute() or '..' in intent_path.parts
                or intent_path.name!='native-latest-intent.txt'
                or len(str(intent_path))>3000
                or any(c in str(intent_path) for c in '\\\r\n\0')):
            raise ValueError('local Windows-readable intent binding invalid')
        windows_intent=str(PureWindowsPath('//wsl.localhost/'+distribution,*intent_path.parts[1:]))
        if digest(EXECUTABLE.read_bytes())!=self.sha:
            raise PermissionError('configured Windows executable changed')
        script=Path(__file__).with_suffix('.ps1').read_text()
        command=[str(EXECUTABLE),'-NoProfile','-NonInteractive','-STA','-EncodedCommand',
                 base64.b64encode(script.encode('utf-16-le')).decode('ascii')]
        request={'snapshot_id':update['snapshot_id'],'attempt_id':attempt_id,
                 'byte_length':len(body),'content_sha256':digest(body),
                 'content_b64':base64.b64encode(body).decode('ascii'),
                 'expires_epoch':int(self.clock())+12,'windows_sid':self.sid,
                 'windows_session_id':self.session,'latest_intent_path':windows_intent}
        # No content, credential or clipboard data appears in argv or stderr logs.
        result=self.run(command,input=json.dumps(request).encode('ascii'),
                        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=15,check=False)
        if result.returncode!=0 or len(result.stdout)>4096:
            raise RuntimeError('Windows clipboard acknowledgement unavailable')
        reply=json.loads(result.stdout.decode('utf-8-sig'),object_pairs_hook=unique_object)
        required={'snapshot_id','attempt_id','byte_length','content_sha256','windows_sid','windows_session_id','status','code'}
        if not isinstance(reply,dict) or set(reply) not in (required,required|{'copied_at'}):
            raise ValueError('Windows clipboard acknowledgement fields invalid')
        if not isinstance(reply['code'],str) or not re.fullmatch('[a-z_]{1,80}',reply['code']):
            raise ValueError('Windows clipboard error code invalid')
        for key in ('snapshot_id','attempt_id','byte_length','content_sha256','windows_sid','windows_session_id'):
            if type(reply.get(key)) is not type(request[key]) or reply[key]!=request[key]:
                raise ValueError('Windows clipboard acknowledgement identity mismatch')
        if reply.get('status') not in ('copied','failed','unknown'):
            raise ValueError('Windows clipboard status invalid')
        if reply['status']=='copied':
            if reply.get('code')!='verified_windows_readback' or not isinstance(reply.get('copied_at'),str):
                raise ValueError('Windows clipboard verification absent')
            stamp=datetime.fromisoformat(reply['copied_at'].replace('Z','+00:00')).timestamp()
            if abs(stamp-self.clock())>30:raise ValueError('Windows clipboard acknowledgement stale')
        return {k:reply[k] for k in ('status','code','copied_at') if k in reply}

class ConsoleClipboardDelivery:
    """Serialized durable receipts, separate from immutable snapshot content."""
    def __init__(self, updates, writer=None, *, clock=time.time):
        self.updates=updates;self.writer=writer;self.clock=clock
        self.root=updates.root/'windows-clipboard'

    def _write(self,path,value):
        record={**value};record['record_sha256']=digest(self.updates._canonical(value))
        self.updates._write_atomic(path,self.updates._canonical(record))

    def _read(self,path):
        raw=path.read_bytes()
        if len(raw)>4096:raise ValueError('clipboard receipt exceeds bound')
        value=json.loads(raw,object_pairs_hook=unique_object)
        if value['record_sha256']!=digest(self.updates._canonical({k:v for k,v in value.items() if k!='record_sha256'})):
            raise ValueError('clipboard receipt integrity mismatch')
        return value

    def status(self,update):
        path=self.root/(update['snapshot_id']+'.json')
        if not path.exists():return {'status':'not_requested','snapshot_id':update['snapshot_id']}
        value=self._read(path)
        if value['snapshot_id']!=update['snapshot_id'] or value['content_sha256']!=update['content_sha256']:
            raise ValueError('clipboard receipt snapshot mismatch')
        latest=self._read(self.root/'latest.json')
        if latest['snapshot_id']!=update['snapshot_id']:
            return {**value,'status':'superseded'}
        if value['status']=='pending' and self.clock()>value['deadline_epoch']:
            return {**value,'status':'unknown','code':'interrupted_or_acknowledgement_missing'}
        return value

    def send(self, **save_arguments):
        self.updates._prepare();self.root.mkdir(mode=0o700,exist_ok=True)
        self.updates._fsync_directory(self.updates.root)
        with (self.root/'delivery.lock').open('a+b') as lock:
            os.chmod(lock.name,0o600)
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError('Another Windows clipboard delivery is pending')
            update=self.updates.save(**save_arguments)
            path=self.root/(update['snapshot_id']+'.json')
            if path.exists():return {**update,'windows_clipboard':self.status(update)}
            latest_path=self.root/'latest.json'
            latest=self._read(latest_path) if latest_path.exists() else None
            # An interrupted older save must not overwrite a subsequently sent
            # newer snapshot. Uncertain/reversed ordering fails conservatively.
            if (update.get('campaign_id')!=save_arguments['projection'].get('current_campaign_id')
                    or (latest and latest['snapshot_id']!=update['snapshot_id']
                        and update['created_at']<=latest['snapshot_created_at'])):
                return {**update,'windows_clipboard':{'status':'superseded','snapshot_id':update['snapshot_id']}}
            value={'snapshot_id':update['snapshot_id'],'content_sha256':update['content_sha256'],
                   'attempt_id':secrets.token_hex(16),'created_at':now(),
                   'deadline_epoch':self.clock()+20,'status':'pending','destination':'Windows clipboard'}
            # Latest intent first. A crash before attempt persistence cannot run
            # a write; a persisted attempt is never replayed after uncertainty.
            self._write(self.root/'latest.json',{'snapshot_id':update['snapshot_id'],'snapshot_created_at':update['created_at']})
            self._write(path,value)
            # Publish before dispatch, under the service lock. The native helper
            # reads this exact bounded fence AFTER acquiring its Windows mutex.
            # A surviving older helper cannot write after a newer confirmation:
            # either it holds the mutex first, or it sees the newer durable fence.
            intent_path=self.root/'native-latest-intent.txt'
            intent=(value['attempt_id']+'\n'+update['snapshot_id']+'\n'+update['content_sha256']+'\n').encode('ascii')
            self.updates._write_atomic(intent_path,intent)
            try:
                outcome={'status':'unavailable','code':'windows_clipboard_not_configured'} if self.writer is None else self.writer(update,value['attempt_id'],intent_path)
                if outcome.get('status') not in ('copied','failed','unknown','unavailable'):
                    raise ValueError('invalid writer status')
            except Exception:
                outcome={'status':'unknown','code':'windows_clipboard_acknowledgement_missing'}
            self._write(path,{**value,**outcome,'completed_at':now()})
            return {**update,'windows_clipboard':self.status(update)}
