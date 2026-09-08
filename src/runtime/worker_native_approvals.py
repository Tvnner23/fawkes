"""Authenticated decisions on native requests from ONE existing Codex thread.

Codex remains the native permission owner. This does not broaden the separate
managed Attention approve-once contract, send chat input, create a thread/turn,
run a command, edit policy files, or infer consent. A single connection reader
owns native request IDs; HTTP submits only a hash-bound offered choice to it.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import copy
import fcntl
import json
import os
import queue
import select
import socket
import stat
import struct
import threading
import time
import uuid

import websocket
from . import worker_conversation as core
from .worker_conversation_socket import _BudgetSocket, _BoundedFrames

METHOD = 'item/commandExecution/requestApproval'
MAX_RECORD = 200_000
MAX_PENDING = 32
TTL_SECONDS = 900
RPC_SECONDS = 12


def _identifier(value):
    return isinstance(value, str) and bool(core.IDENTIFIER.fullmatch(value))


def describe_request(value, thread_id):
    """Strict supported subset of the pinned 0.153.4 command request contract.

    Unsupported action kinds/permission overlays are visibly left to the PC.
    Explanatory reason/actions never replace the complete authoritative command.
    """
    if not isinstance(value, dict) or set(value) != {'id', 'method', 'params'}:
        raise ValueError('Native request envelope is incomplete or unfamiliar')
    request_id = value['id']
    if not ((type(request_id) is int and -(2**53)<request_id<2**53) or _identifier(request_id)):
        raise ValueError('Native request ID is invalid')
    p = value['params']
    known = {'threadId','turnId','itemId','approvalId','command','cwd','reason','commandActions',
             'availableDecisions','proposedExecpolicyAmendment','proposedNetworkPolicyAmendments',
             'networkApprovalContext','additionalPermissions','environmentId','kind','startedAtMs'}
    if value['method'] != METHOD or not isinstance(p, dict) or set(p)-known:
        raise ValueError('This native request type needs the PC terminal')
    if p.get('threadId') != thread_id or not all(_identifier(p.get(k)) for k in ('turnId','itemId')):
        raise ValueError('Native request is not bound to this Worker operation')
    if p.get('kind','command') != 'command':
        raise ValueError('Only command approvals are supported here; answer terminal-input requests on the PC')
    if any(p.get(k) not in (None,[]) for k in ('networkApprovalContext','additionalPermissions','proposedNetworkPolicyAmendments')):
        raise ValueError('This request has additional native permission material; answer it on the PC')
    if (not isinstance(p.get('command'),str) or not p['command'].strip() or '\0' in p['command']
            or len(p['command'].encode())>64_000 or not isinstance(p.get('cwd'),str) or not p['cwd']
            or type(p.get('startedAtMs')) is not int or p['startedAtMs']<=0):
        raise ValueError('Complete command, working directory and request timestamp are required')
    for field in ('reason','environmentId','approvalId'):
        if p.get(field) is not None and not isinstance(p[field],str):raise ValueError('Malformed '+field)
    actions=p.get('commandActions')
    if actions is not None:
        if not isinstance(actions,list):raise ValueError('Malformed parsed command actions; use the PC')
        variants={'read':({'type','command','name','path'},{'name','path'}),
                  'listFiles':({'type','command','path'},set()),
                  'search':({'type','command','path','query'},set()),
                  'unknown':({'type','command'},set())}
        for action in actions:
            if not isinstance(action,dict) or not isinstance(action.get('type'),str) or action['type'] not in variants:
                raise ValueError('Unfamiliar parsed command action; use the PC')
            allowed,required=variants[action['type']]
            if (set(action)-allowed or not ({'type','command'}|required)<=set(action)
                    or not isinstance(action['command'],str)
                    or any(not isinstance(action[k],str) for k in required)
                    or any(action.get(k) is not None and not isinstance(action[k],str) for k in ('path','query'))):
                raise ValueError('Incomplete or unfamiliar parsed command action material; use the PC')
    decisions=p.get('availableDecisions')
    if not isinstance(decisions,list) or not 1<=len(decisions)<=8:
        raise ValueError('The native server did not provide its selectable choices')
    choices=[]
    for decision in decisions:
        if isinstance(decision,str) and decision in ('accept','acceptForSession','decline','cancel'):
            label,scope={
                'accept':('Yes, proceed once','Only this command request. No saved permission.'),
                'acceptForSession':('Yes, for this session','The native session approval cache may allow matching future requests for the rest of this Worker session. The server does not expose its cache matching rule.'),
                'decline':('Deny command','The command is declined; Codex may continue the turn.'),
                'cancel':('No, stop and let me steer','Decline the command and interrupt the current turn. Use the separate reply box to tell Codex what to do differently.')
            }[decision]
        elif (isinstance(decision,dict) and set(decision)=={'acceptWithExecpolicyAmendment'}
              and isinstance(decision['acceptWithExecpolicyAmendment'],dict)
              and set(decision['acceptWithExecpolicyAmendment'])=={'execpolicy_amendment'}):
            prefix=decision['acceptWithExecpolicyAmendment']['execpolicy_amendment']
            if (not isinstance(prefix,list) or not prefix or len(prefix)>128
                    or any(not isinstance(x,str) or not x or '\0' in x for x in prefix)
                    or prefix!=p.get('proposedExecpolicyAmendment')):
                raise ValueError('Saved permission does not match the exact native proposal')
            label='Yes, and save this command-prefix permission'
            scope='Persistent native execpolicy rule: future commands with this exact token prefix may run without asking. It is not limited to this task. Exact prefix tokens: '+json.dumps(prefix,ensure_ascii=False)
        else:raise ValueError('An offered native choice is not supported here; use the PC')
        choice_id=core.sha(core.canonical(decision))
        if any(c['choice_id']==choice_id for c in choices):raise ValueError('Duplicate native choices')
        choices.append({'choice_id':choice_id,'label':label,'scope':scope,'native_decision':copy.deepcopy(decision)})
    if len(core.canonical(value))>MAX_RECORD//2:raise ValueError('Native request exceeds its complete display bound')
    return {'command':p['command'],'cwd':p['cwd'],'reason':p.get('reason'),
            'environment':p.get('environmentId') or 'Not reported','turn_id':p['turnId'],
            'item_id':p['itemId'],'approval_id':p.get('approvalId'),'command_actions':copy.deepcopy(actions),'choices':choices}


class NativeApprovalRelay:
    def __init__(self, *, executable, socket_path, thread_id, cwd, store):
        if not core.UUID.fullmatch(thread_id):raise ValueError('Exact Worker required')
        self.executable=Path(executable);self.socket=Path(socket_path)
        self.thread_id=thread_id;self.cwd=str(Path(cwd).resolve());self.store=store
        self.root=store.root/'native-approvals'/thread_id
        self.lock=threading.RLock();self.stop_event=threading.Event();self.outgoing=queue.Queue(maxsize=32)
        self.records={};self.pending={};self.epoch=None;self.verified_at=None;self.connected=False
        self.terminal_items={}
        self.thread=None;self.lease=None;self.error='Native approval connection has not started'

    def _save(self, record):
        value={k:v for k,v in record.items() if k!='record_sha256'}
        value['record_sha256']=core.sha(core.canonical(value));body=core.canonical(value)
        if len(body)>MAX_RECORD:raise ValueError('Approval audit record exceeds bound')
        self.store._write_atomic(self.root/(value['request_key']+'.json'),body)
        self.records[value['request_key']]=value
        return value

    def _prepare(self):
        self.store._prepare()
        for path in (self.root.parent,self.root):
            path.mkdir(exist_ok=True,mode=0o700)
            node=path.lstat()
            if not stat.S_ISDIR(node.st_mode) or node.st_uid!=os.getuid() or node.st_mode&0o077:raise PermissionError('Approval audit root must be private')
            self.store._fsync_directory(path);self.store._fsync_directory(path.parent)
        fd=os.open(self.root/'owner.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        self.lease=os.fdopen(fd,'r+b')
        node=os.fstat(fd)
        if not stat.S_ISREG(node.st_mode) or node.st_uid!=os.getuid() or node.st_mode&0o077:
            self.lease.close();self.lease=None;raise PermissionError('Native owner lock must be a private regular file')
        fcntl.flock(self.lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for path in self.root.glob('*.json'):
            node=path.lstat()
            if not stat.S_ISREG(node.st_mode) or node.st_uid!=os.getuid() or node.st_mode&0o077 or node.st_size>MAX_RECORD:raise ValueError('Invalid retained approval record')
            value=json.loads(path.read_bytes(),object_pairs_hook=core.unique)
            if (value.get('thread_id')!=self.thread_id or path.stem!=value.get('request_key')
                    or value.get('record_sha256')!=core.sha(core.canonical({k:v for k,v in value.items() if k!='record_sha256'}))):raise ValueError('Retained approval integrity differs')
            self.records[path.stem]=value
            if value['status'] in ('pending','submitted','unsupported','response_window_expired','unavailable','response_rejected'):
                self._save({**value,'status':'connection_lost','closed_at':core.timestamp(),
                            'explanation':'Prior live connection ended. No saved decision is replayed.'})

    def start(self):
        if self.thread is not None:raise RuntimeError('Approval relay already started')
        self._prepare();self.thread=threading.Thread(target=self._run,name='fawkes-native-approvals',daemon=True);self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=18)
        if self.thread and self.thread.is_alive():return # Keep owner lock held.
        if self.lease:self.lease.close();self.lease=None

    def _disconnect(self, reason):
        with self.lock:
            self.connected=False;self.error=reason
            for key in list(self.pending.values()):
                r=self.records[key]
                if r['status'] in ('pending','submitted','unsupported','response_window_expired','unavailable','response_rejected'):
                    self._save({**r,'status':'connection_lost','closed_at':core.timestamp(),
                        'explanation':'Native connection lost. Selection/outcome is not confirmed; no automatic replay.'})
            self.pending.clear()

    def observe(self, value):
        """Called only by the connection's single reader, also exercised offline."""
        with self.lock:
            method=value.get('method');p=value.get('params')
            if method is None and 'error' in value:
                key=self.pending.get(core.canonical(value.get('id')).decode())
                if key:
                    r=self.records[key]
                    self._save({**r,'status':'response_rejected','response_rejected_at':core.timestamp(),
                        'explanation':'Codex rejected a response on this connection. Native resolution and execution are not confirmed; inspect the PC terminal.'})
                    return
                raise ValueError('Uncorrelated native protocol error')
            if not isinstance(p,dict) or p.get('threadId')!=self.thread_id:return
            if 'id' in value:
                wire_id=core.canonical(value['id']).decode()
                if wire_id in self.pending:
                    if self.records[self.pending[wire_id]]['request']!=value:raise ValueError('Native ID reused with different material')
                    return
                if len(self.pending)>=MAX_PENDING:raise ValueError('Too many native requests')
                now=datetime.now(timezone.utc);request_key=core.sha(core.canonical({'epoch':self.epoch,'request':value}))
                logical=core.sha(core.canonical({'method':method,'params':p}))
                try:description=describe_request(value,self.thread_id);status='pending';error=None
                except ValueError as exc:description=None;status='unsupported';error=str(exc)
                if (p.get('turnId'),p.get('itemId')) in self.terminal_items or (p.get('turnId'),None) in self.terminal_items:
                    status='resolved';error='This operation has a terminal observation; no further decision can be sent.'
                elif any(r.get('logical_request_sha256')==logical and r.get('selection') for r in self.records.values()):
                    status='unavailable';error='An earlier Pi selection is retained but not safely replayable. Check the PC terminal.'
                record={'request_key':request_key,'thread_id':self.thread_id,'connection_epoch':self.epoch,
                    'logical_request_sha256':logical,
                    'action_sha256':core.sha(core.canonical(value)),'request':copy.deepcopy(value),'description':description,
                    'created_at':now.isoformat(),'expires_at':(now+timedelta(seconds=TTL_SECONDS)).isoformat(),
                    'status':status,'explanation':error,'selection':None,'operation':None}
                self._save(record)
                if status!='resolved':self.pending[wire_id]=request_key
            elif method=='serverRequest/resolved':
                wire_id=core.canonical(p.get('requestId')).decode();key=self.pending.pop(wire_id,None)
                if key:
                    r=self.records[key];self._save({**r,'status':'resolved','resolved_at':core.timestamp(),
                        'explanation':'Codex cleared this request. A resolution notification alone does not identify the winning PC/Pi choice or prove command execution.'})
            elif method=='item/completed' and isinstance(p.get('item'),dict):
                item=p['item']
                if item.get('type')!='commandExecution' or item.get('status') not in ('completed','failed','declined'):return
                self.terminal_items[(p.get('turnId'),item.get('id'))]=True
                if len(self.terminal_items)>4096:self.terminal_items.pop(next(iter(self.terminal_items)))
                for r in list(self.records.values()):
                    original=r['request']['params']
                    if original.get('turnId')==p.get('turnId') and original.get('itemId')==item.get('id'):
                        wire_id=core.canonical(r['request']['id']).decode()
                        if self.pending.get(wire_id)==r['request_key']:
                            self.pending.pop(wire_id)
                        self._save({**r,'status':'resolved','operation':{'status':item['status'],'exit_code':item.get('exitCode'),
                            'observed_at':core.timestamp(),'item_id':item['id'],'turn_id':p['turnId']}})
            elif method=='turn/completed' and isinstance(p.get('turn'),dict):
                turn=p['turn']
                if turn.get('status') not in ('completed','failed','interrupted'):return
                self.terminal_items[(turn.get('id'),None)]=True
                if len(self.terminal_items)>4096:self.terminal_items.pop(next(iter(self.terminal_items)))
                for wire_id,key in list(self.pending.items()):
                    r=self.records[key]
                    if r['request']['params'].get('turnId')==turn.get('id'):
                        self.pending.pop(wire_id)
                        self._save({**r,'status':'resolved','resolved_at':core.timestamp(),
                            'explanation':'The waiting turn ended ('+turn['status']+'). This alone does not prove the command executed.'})

    def projection(self, cursor=None):
        with self.lock:
            fresh=self.connected and self.verified_at is not None and 0<=time.time()-self.verified_at<12
            now=datetime.now(timezone.utc)
            for key in list(self.pending.values()):
                r=self.records[key]
                if r['status'] in ('pending','unsupported','submitted') and datetime.fromisoformat(r['expires_at'])<=now:
                    self._save({**r,'status':'response_window_expired',
                        'explanation':'The local Pi response window ended, not the native request. No further Pi decision can be sent; answer the still-pending PC terminal.'})
            all_records=sorted(self.records.values(),key=lambda r:(r['created_at'],r['request_key']),reverse=True)
            # Native ownership, not Pi actionability, defines the unresolved queue.
            # An unsafe-to-replay selection still requires PC-directed attention.
            unresolved=set(self.pending.values())
            active=[r for r in all_records if r['connection_epoch']==self.epoch and r['request_key'] in unresolved and r['status']!='resolved']
            records=[r for r in all_records if r not in active]
            if cursor is not None:
                indices=[i for i,r in enumerate(records) if r['request_key']==cursor]
                if len(indices)!=1:raise ValueError('Unknown approval history cursor')
                records=records[indices[0]+1:]
            def public(r):
                v={k:copy.deepcopy(r[k]) for k in ('request_key','thread_id','logical_request_sha256','action_sha256','created_at','expires_at','status','description','explanation','selection','operation')}
                v['actionable']=bool(fresh and r['connection_epoch']==self.epoch and r['status']=='pending'
                    and self.pending.get(core.canonical(r['request']['id']).decode())==r['request_key']
                    and datetime.fromisoformat(r['expires_at'])>datetime.now(timezone.utc))
                v['native_pending']=bool(r['connection_epoch']==self.epoch and r['request_key'] in unresolved and r['status']!='resolved')
                v['needs_decision']=bool(fresh and v['native_pending'] and r['status']!='submitted')
                if r['status']=='pending' and not v['actionable']:v['status']='unavailable'
                return v
            return {'thread_id':self.thread_id,'connected':fresh,'verified_at':datetime.fromtimestamp(self.verified_at,timezone.utc).isoformat() if self.verified_at else None,
                'explanation':None if fresh else self.error,'requests':[public(r) for r in (active+records[:20] if cursor is None else records[:20])],
                'next_cursor':records[19]['request_key'] if len(records)>20 else None,
                'pending_count':len(active)}

    def decide(self, *, thread_id, request_key, action_sha256, choice_id, submission_id, authenticated):
        if authenticated is not True or thread_id!=self.thread_id:raise PermissionError('Authenticated same-Worker decision required')
        if not core.UUID.fullmatch(str(submission_id)):raise ValueError('Exact submission ID required')
        with self.lock:
            r=self.records.get(request_key)
            if not r or r['action_sha256']!=action_sha256:raise ValueError('Native action binding differs')
            if core.sha(core.canonical(r['request']))!=r['action_sha256']:raise ValueError('Retained native action changed')
            old=r.get('selection')
            if old:
                if old['submission_id']==submission_id and old['choice_id']==choice_id:return copy.deepcopy(r)
                raise ValueError('This native request already has a Pi selection')
            if (not self.connected or not self.verified_at or not 0<=time.time()-self.verified_at<12
                    or r['connection_epoch']!=self.epoch or r['status']!='pending'
                    or datetime.fromisoformat(r['expires_at'])<=datetime.now(timezone.utc)):
                raise ValueError('Native request is stale, resolved or disconnected')
            description=describe_request(r['request'],self.thread_id)
            matches=[c for c in description['choices'] if c['choice_id']==choice_id]
            if len(matches)!=1:raise ValueError('Choice was not offered for this exact native request')
            if self.outgoing.full():raise RuntimeError('Native response queue is full; nothing submitted')
            r=self._save({**r,'status':'submitted','selection':{'submission_id':submission_id,'choice_id':choice_id,
                'label':matches[0]['label'],'scope':matches[0]['scope'],'recorded_at':core.timestamp(),
                'state':'recorded_not_sent','decided_by':'authenticated_tanner'}})
            self.outgoing.put_nowait(request_key)
            return copy.deepcopy(r)

    def _send_selection(self, key, send):
        with self.lock:
            r=self.records[key]
            if core.sha(core.canonical(r['request']))!=r['action_sha256']:raise ValueError('Native action changed before response')
            if (not self.connected or not self.verified_at or not 0<=time.time()-self.verified_at<12
                    or r['connection_epoch']!=self.epoch or r['status']!='submitted'
                    or r['selection']['state']!='recorded_not_sent'
                    or self.pending.get(core.canonical(r['request']['id']).decode())!=key
                    or datetime.fromisoformat(r['expires_at'])<=datetime.now(timezone.utc)):
                if r['status']=='submitted' and r['selection']['state']=='recorded_not_sent':
                    self._save({**r,'status':'unavailable','selection':{**r['selection'],'state':'not_sent'},
                        'explanation':'Request freshness or exact live ownership was lost before sending. No response was sent.'})
                return # Resolved/expired selections never become a new command's answer.
            choices=describe_request(r['request'],self.thread_id)['choices']
            choice=next(c for c in choices if c['choice_id']==r['selection']['choice_id'])
            # Durable maybe-sent barrier BEFORE the native external effect.
            r=self._save({**r,'selection':{**r['selection'],'state':'sending_outcome_unknown'}})
            send({'id':r['request']['id'],'result':{'decision':choice['native_decision']}})
            self._save({**r,'selection':{**r['selection'],'state':'sent_awaiting_native_resolution','sent_at':core.timestamp()}})

    def _run(self):
        while not self.stop_event.is_set():
            try:self._connection()
            except Exception as exc:
                try:self._disconnect('Native approval connection unavailable: '+type(exc).__name__)
                except Exception:self.connected=False;self.error='Approval audit storage unavailable'
            self.stop_event.wait(2)

    def _connection(self):
        node=self.socket.lstat();parent=self.socket.parent.lstat()
        if (not stat.S_ISSOCK(node.st_mode) or not stat.S_ISDIR(parent.st_mode) or node.st_uid!=os.getuid()
                or parent.st_uid!=os.getuid() or parent.st_mode&0o077
                or core.sha(self.executable.read_bytes())!=core.PINNED_CODEX_SHA256):raise PermissionError('Qualified local native socket required')
        peer=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);ws=None
        try:
            peer.settimeout(2);peer.connect(str(self.socket))
            pid,uid,_=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if uid!=os.getuid() or core.sha(Path(f'/proc/{pid}/exe').read_bytes())!=core.PINNED_CODEX_SHA256:raise PermissionError('Native peer identity changed')
            wire=_BudgetSocket(peer,time.monotonic()+12)
            ws=websocket.create_connection('ws://localhost/',socket=wire,timeout=12,suppress_origin=True,redirect_limit=0,enable_multithread=False)
            if ws.getstatus()!=101:raise ValueError('Native upgrade failed')
            wire.handshake=False;ws.frame_buffer=_BoundedFrames(ws._recv,False)
            def send(v):
                body=core.canonical(v)
                if len(body)>100_000:raise ValueError('Native response bound exceeded')
                wire.deadline=time.monotonic()+12;wire.sent=0;ws.send(body.decode())
            def receive(deadline=None):
                wire.deadline=deadline or time.monotonic()+RPC_SECONDS;wire.received=0;body=bytearray();continuing=False
                for _ in range(2000):
                    if self.stop_event.is_set() or time.monotonic()>=wire.deadline:raise TimeoutError('Native read stopped or timed out')
                    f=ws.recv_frame()
                    if f.mask_value:raise ValueError('Masked native frame')
                    if f.opcode==websocket.ABNF.OPCODE_PING:ws.pong(f.data);continue
                    if f.opcode==websocket.ABNF.OPCODE_PONG:continue
                    if f.opcode==websocket.ABNF.OPCODE_TEXT:
                        if continuing:raise ValueError('Native message interleaved')
                    elif f.opcode==websocket.ABNF.OPCODE_CONT:
                        if not continuing:raise ValueError('Unexpected native continuation')
                    else:raise ValueError('Native connection ended or returned a binary message')
                    body.extend(f.data)
                    if len(body)>core.MAX_FRAME:raise ValueError('Native message bound exceeded')
                    continuing=not f.fin
                    if not continuing:
                        v=json.loads(body,object_pairs_hook=core.unique)
                        if not isinstance(v,dict):raise ValueError('Malformed native frame')
                        return v
                raise ValueError('Native frame count exceeded')
            def rpc(identity,method,params):
                send({'id':identity,'method':method,'params':params})
                deadline=time.monotonic()+RPC_SECONDS
                for _ in range(2000):
                    v=receive(deadline)
                    if 'method' in v:self.observe(v);continue
                    if 'error' in v and v.get('id')!=identity:self.observe(v);continue
                    if type(v.get('id')) is not int or v['id']!=identity or 'error'in v or not isinstance(v.get('result'),dict):raise ValueError('Native handshake/read failed')
                    return v['result']
                raise ValueError('Native RPC notification bound exceeded')
            self.epoch=uuid.uuid4().hex
            rpc(-1,'initialize',{'clientInfo':{'name':'fawkes_native_worker_approvals','version':'1'},'capabilities':{'experimentalApi':True}})
            send({'method':'initialized','params':{}})
            def validate_thread(v):
                t=v.get('thread')
                if not isinstance(t,dict) or t.get('id')!=self.thread_id or t.get('cwd')!=self.cwd or t.get('status',{}).get('type') not in ('active','idle'):
                    raise ValueError('Same Worker is not already loaded')
            validate_thread(rpc(-2,'thread/read',{'threadId':self.thread_id,'includeTurns':False}))
            # Installed schema specifies this is a rejoin for a running thread.
            # No input, path/history, model, permission or instruction overrides.
            validate_thread(rpc(-3,'thread/resume',{'threadId':self.thread_id,'excludeTurns':True}))
            with self.lock:self.connected=True;self.verified_at=time.time();self.error=None
            last_check=time.monotonic();counter=-4
            while not self.stop_event.is_set():
                if time.monotonic()-last_check>=4:
                    validate_thread(rpc(counter,'thread/read',{'threadId':self.thread_id,'includeTurns':False}));counter-=1
                    with self.lock:self.verified_at=time.time()
                    last_check=time.monotonic()
                if ws.frame_buffer.recv_buffer or select.select([peer],[],[],.1)[0]:
                    self.observe(receive())
                    continue # Drain already-arrived PC resolutions before writing.
                try:key=self.outgoing.get_nowait()
                except queue.Empty:continue
                self._send_selection(key,send)
        finally:
            if ws is not None:ws.shutdown()
            peer.close();self._disconnect('Native approval connection closed; no selection replayed')
