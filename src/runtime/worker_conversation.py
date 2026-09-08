"""Public conversation and exact queued replies to one explicitly bound Worker.

The local app-server must already own that thread. This module never starts or
resumes a thread, starts a model turn, answers approvals, or selects permissions.
"""
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import select
import socket
import stat
import struct
import subprocess
import time

PINNED_CODEX_SHA256 = '56ef98ab4032d317ab26e9b5e5a175650717351edb16ed9cde0cb6d1734d62da'
UUID = re.compile(r'^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$')
IDENTIFIER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$')
MAX_FRAME = 8_000_000
MAX_TRANSFER = 16_000_000
MAX_REPLY = 16_000
# Worst-case JSON escaping is six bytes per accepted UTF-8 byte. Reserve
# another 32 KiB for bounded cursors, identity/receipt metadata and checksum.
MAX_REPLY_RECORD = MAX_REPLY * 6 + 32_768
MAX_PUBLIC_MESSAGE = 256_000
MAX_PROJECTION = 480_000
REQUEST_SECONDS = 12


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def sha(body):
    return hashlib.sha256(body).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate conversation field')
        result[key] = value
    return result


class ConversationUnavailable(RuntimeError):
    pass


class LocalWorkerProxy:
    """Bounded single-reader client of the installed local control socket only."""
    METHODS = frozenset({'thread/read', 'thread/items/list', 'thread/turns/list', 'thread/queue/add', 'thread/queue/list'})

    def __init__(self, *, executable, socket_path, thread_id, cwd, popen=subprocess.Popen):
        self.executable = Path(executable)
        self.socket = Path(socket_path)
        self.thread_id = thread_id
        self.cwd = str(Path(cwd).resolve())
        self.popen = popen
        if not UUID.fullmatch(thread_id) or not self.executable.is_absolute() or not self.socket.is_absolute():
            raise ValueError('explicit local Worker identity required')

    def __call__(self, method, params):
        if method not in self.METHODS or params.get('threadId') != self.thread_id:
            raise PermissionError('method or Worker identity outside configured conversation')
        if sha(self.executable.read_bytes()) != PINNED_CODEX_SHA256:
            raise ConversationUnavailable('The pinned Worker client changed; qualification is required.')
        try:
            node = self.socket.lstat()
            parent = self.socket.parent.stat()
        except FileNotFoundError as exc:
            raise ConversationUnavailable('This Worker is not connected to its shared local app-server.') from exc
        if not stat.S_ISSOCK(node.st_mode) or node.st_uid != os.getuid() or parent.st_uid != os.getuid() or parent.st_mode & 0o077:
            raise ConversationUnavailable('The local Worker control socket is not privately owned.')
        # The proxy's version does not prove the daemon's version. Verify the
        # actual local socket peer executable without sending any protocol input.
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(2); peer.connect(str(self.socket))
            pid, uid, _ = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid() or sha(Path(f'/proc/{pid}/exe').read_bytes()) != PINNED_CODEX_SHA256:
                raise ConversationUnavailable('The actual Worker daemon is not the qualified executable.')
        process = self.popen([str(self.executable), 'app-server', 'proxy', '--sock', str(self.socket)],
                             cwd=self.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, bufsize=0)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        os.set_blocking(process.stdin.fileno(), False)
        buffer = bytearray(); received = 0; frames = 0
        deadline = time.monotonic() + REQUEST_SECONDS

        def send(value):
            body = canonical(value) + b'\n'
            if len(body) > 100_000:
                raise ValueError('Worker request exceeds bound')
            pending = memoryview(body)
            while pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([], [process.stdin], [], remaining)[1]:
                    raise ConversationUnavailable('Worker request write timed out.')
                try: written = os.write(process.stdin.fileno(), pending)
                except BlockingIOError: continue
                if written <= 0: raise ConversationUnavailable('Worker request pipe closed.')
                pending = pending[written:]

        def receive(expected):
            nonlocal buffer, received, frames
            while time.monotonic() < deadline:
                if b'\n' not in buffer:
                    events = selector.select(max(0, min(.5, deadline - time.monotonic())))
                    if not events:
                        continue
                    part = os.read(process.stdout.fileno(), 65536)
                    if not part:
                        raise ConversationUnavailable('Worker connection closed without an acknowledgement.')
                    received += len(part); buffer.extend(part)
                    if received > MAX_TRANSFER or len(buffer) > MAX_FRAME:
                        raise ConversationUnavailable('Worker response exceeds its bounded reader.')
                    continue
                line, _, rest = buffer.partition(b'\n'); buffer = bytearray(rest)
                frames += 1
                if frames > 2000 or len(line) > MAX_FRAME:
                    raise ConversationUnavailable('Worker response exceeds its bounded reader.')
                value = json.loads(line, object_pairs_hook=unique)
                if not isinstance(value, dict):
                    raise ConversationUnavailable('Malformed Worker frame.')
                if 'method' in value:
                    if 'id' in value:
                        # This connection is not an approval/permission owner.
                        raise ConversationUnavailable('A native request requires its existing decision owner.')
                    continue
                if type(value.get('id')) is not int or value['id'] != expected:
                    raise ConversationUnavailable('Worker response identity mismatch.')
                if 'error' in value or 'result' not in value:
                    raise ConversationUnavailable('The Worker rejected this conversation request.')
                if not isinstance(value['result'], dict):
                    raise ConversationUnavailable('Malformed Worker result.')
                return value['result']
            raise ConversationUnavailable('Worker acknowledgement timed out; delivery is not confirmed.')

        try:
            send({'id': 1, 'method': 'initialize', 'params': {
                'clientInfo': {'name': 'fawkes_console_conversation', 'version': '1'},
                'capabilities': {'experimentalApi': True}}})
            receive(1)
            send({'method': 'initialized', 'params': {}})
            send({'id': 2, 'method': method, 'params': params})
            return receive(2)
        finally:
            selector.close()
            # Terminate only this short-lived proxy, never the daemon/Worker.
            for handle in (process.stdin, process.stdout):
                try: handle.close()
                except OSError: pass
            if process.poll() is None:
                process.terminate()
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=2)


class WorkerConversation:
    def __init__(self, *, thread_id, cwd, rpc, store):
        if not UUID.fullmatch(thread_id):
            raise ValueError('exact Worker thread required')
        self.thread_id = thread_id; self.cwd = str(Path(cwd).resolve())
        self.rpc = rpc; self.store = store
        self.root = store.root / 'worker-replies' / thread_id

    def _read_thread(self):
        thread = self.rpc('thread/read', {'threadId': self.thread_id, 'includeTurns': False}).get('thread')
        if not isinstance(thread, dict) or thread.get('id') != self.thread_id or thread.get('cwd') != self.cwd:
            raise ConversationUnavailable('The observed Worker does not match the configured session.')
        state = thread.get('status')
        if not isinstance(state, dict) or state.get('type') not in {'active', 'idle', 'notLoaded', 'systemError'}:
            raise ConversationUnavailable('Worker execution state is unavailable.')
        return thread

    @staticmethod
    def _public(entry):
        if not isinstance(entry, dict) or not isinstance(entry.get('item'), dict):
            raise ValueError('invalid Worker history entry')
        item = entry['item']; kind = item.get('type')
        if kind == 'agentMessage':
            if item.get('phase') not in (None, 'commentary', 'final_answer'):
                raise ValueError('invalid public Worker message phase')
            text = item.get('text'); role = 'worker'; phase = item.get('phase')
        elif kind == 'userMessage':
            content = item.get('content')
            if not isinstance(content, list): raise ValueError('invalid public user message')
            pieces = []
            for part in content:
                if not isinstance(part, dict): raise ValueError('invalid public user input')
                if part.get('type') == 'text' and isinstance(part.get('text'), str):
                    pieces.append(part['text'])
                else:
                    pieces.append('[Non-text attachment; view it in the original Worker session.]')
            text = '\n'.join(pieces); role = 'user'; phase = None
        else:
            return None
        if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_PUBLIC_MESSAGE:
            raise ConversationUnavailable('A complete public message exceeds the display bound; it was not truncated.')
        for name, value in (('message', item.get('id')), ('turn', entry.get('turnId'))):
            if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
                raise ValueError('invalid public ' + name + ' identity')
        return {'message_id': item['id'], 'turn_id': entry['turnId'], 'role': role,
                'phase': phase, 'text': text, 'content_sha256': sha(text.encode('utf-8')),
                'client_id': item.get('clientId') if role == 'user' else None}

    def _page(self, cursor=None, turn_id=None):
        if cursor is not None and (not isinstance(cursor, str) or len(cursor.encode()) > 4096):
            raise ValueError('invalid conversation cursor')
        params = {'threadId': self.thread_id, 'limit': 20, 'sortDirection': 'desc'}
        if cursor: params['cursor'] = cursor
        if turn_id: params['turnId'] = turn_id
        value = self.rpc('thread/items/list', params)
        data = value.get('data'); following = value.get('nextCursor')
        if not isinstance(data, list) or len(data) > 20 or (following is not None and (not isinstance(following, str) or len(following.encode()) > 4096)):
            raise ConversationUnavailable('Worker history pagination is malformed.')
        if turn_id and any(not isinstance(item, dict) or item.get('turnId') != turn_id for item in data):
            raise ConversationUnavailable('Worker history turn differs from the requested turn.')
        identities = [item.get('item', {}).get('id') for item in data if isinstance(item, dict) and isinstance(item.get('item'), dict)]
        if len(identities) != len(data) or len(set(identities)) != len(identities):
            raise ConversationUnavailable('Worker history contains duplicated or malformed identities.')
        return [public for item in data if (public := self._public(item)) is not None], following

    def projection(self, cursor=None):
        thread = self._read_thread()
        messages, following = self._page(cursor)
        latest = None
        turns = self.rpc('thread/turns/list', {'threadId': self.thread_id, 'limit': 8,
            'sortDirection': 'desc', 'itemsView': 'notLoaded'}).get('data')
        if not isinstance(turns, list) or len(turns) > 8:
            raise ConversationUnavailable('Worker turn completion evidence is malformed.')
        seen_turns = set()
        # A streamed final-phase item is not necessarily a COMPLETE final answer.
        # Read completed turns separately so a long active turn cannot obscure
        # the previous verified final message with hundreds of tool events.
        for turn in turns:
            if not isinstance(turn, dict) or not IDENTIFIER.fullmatch(str(turn.get('id', ''))):
                raise ConversationUnavailable('Worker turn identity is malformed.')
            if turn['id'] in seen_turns or turn.get('status') not in {'completed', 'inProgress', 'interrupted', 'failed'}:
                raise ConversationUnavailable('Worker turn completion evidence is ambiguous.')
            seen_turns.add(turn['id'])
            if turn.get('status') != 'completed': continue
            values, _ = self._page(turn_id=turn['id'])
            latest = next((m for m in values if m['role'] == 'worker' and m['phase'] == 'final_answer'), None)
            if latest: break
        state = thread['status']['type']
        result = {'schema_version': 'fawkes.worker_conversation.v1', 'thread_id': self.thread_id,
            'verified_at': timestamp(), 'state': state,
            'can_reply': state in {'active', 'idle'} and thread.get('canAcceptDirectInput') is True,
            'model_configured': thread.get('model'), 'effort_configured': thread.get('reasoningEffort'),
            'model_runtime_confirmed': False, 'messages': messages, 'next_cursor': following,
            'latest_final': latest, 'latest_final_status': 'available' if latest else 'not_found_in_bounded_lookup',
            'source_updated_at': thread.get('updatedAt'), 'creates_authority': False}
        if len(canonical(result)) > MAX_PROJECTION:
            raise ConversationUnavailable('Complete conversation page exceeds display capacity; nothing was truncated.')
        return result

    def exact_final(self, *, thread_id, message_id, content_sha256):
        if thread_id != self.thread_id: raise ValueError('Worker identity changed')
        final = self.projection()['latest_final']
        if final is None or final['message_id'] != message_id or final['content_sha256'] != content_sha256:
            raise ValueError('The latest final message changed. Refresh before copying.')
        return {**final, 'thread_id': self.thread_id}

    def _prepare(self):
        self.store._prepare()
        # Publish every directory entry before an external queue operation.
        # Repeat barriers for existing directories too: a previous attempt may
        # have stopped between mkdir and fsync. Existence is not durability.
        for path in (self.root.parent, self.root):
            path.mkdir(exist_ok=True, mode=0o700); path.chmod(0o700)
            self.store._fsync_directory(path)
            self.store._fsync_directory(path.parent)

    def _write(self, path, value):
        result = {**value, 'record_sha256': sha(canonical(value))}
        body = canonical(result)
        if len(body) > MAX_REPLY_RECORD: raise ValueError('reply record exceeds bound')
        self.store._write_atomic(path, body)

    def _read(self, path):
        body = path.read_bytes()
        if len(body) > MAX_REPLY_RECORD: raise ValueError('reply record exceeds bound')
        value = json.loads(body, object_pairs_hook=unique)
        if value.get('record_sha256') != sha(canonical({k:v for k,v in value.items() if k != 'record_sha256'})):
            raise ValueError('reply record integrity failed')
        if value.get('thread_id') != self.thread_id: raise ValueError('reply thread differs')
        return value

    def send_reply(self, *, thread_id, reply_id, text):
        if thread_id != self.thread_id or not UUID.fullmatch(str(reply_id)):
            raise ValueError('exact reply and thread identity required')
        if not isinstance(text, str) or not text.strip() or '\0' in text or len(text.encode()) > MAX_REPLY:
            raise ValueError('reply must contain 1–16000 UTF-8 bytes without NUL')
        self._prepare()
        path = self.root / (reply_id + '.json')
        with (self.root / 'send.lock').open('a+b') as lock:
            os.chmod(lock.name, 0o600); fcntl.flock(lock, fcntl.LOCK_EX)
            if path.exists():
                value = self._read(path)
                if value['text'] != text: raise ValueError('reply identity is already bound to different text')
                return self._reply_status(reply_id)
            thread = self._read_thread()
            if thread['status']['type'] not in {'active', 'idle'} or thread.get('canAcceptDirectInput') is not True:
                raise ConversationUnavailable('This exact Worker is not loaded and accepting replies.')
            value = {'thread_id': self.thread_id, 'reply_id': reply_id, 'text': text,
                     'content_sha256': sha(text.encode()), 'created_at': timestamp(), 'status': 'pending'}
            self._write(path, value)  # Durable intent before any send; uncertainty is never retried.
            try:
                response = self.rpc('thread/queue/add', {'threadId': self.thread_id,
                    'clientUserMessageId': reply_id, 'input': [{'type': 'text', 'text': text}]})
                queued = response.get('queuedSubmission')
                inputs = queued.get('input') if isinstance(queued, dict) else None
                matching = (isinstance(inputs, list) and len(inputs) == 1
                    and isinstance(inputs[0], dict) and set(inputs[0]) <= {'type', 'text', 'text_elements'}
                    and inputs[0].get('type') == 'text' and inputs[0].get('text') == text
                    and inputs[0].get('text_elements', []) == [])
                if not isinstance(queued, dict) or queued.get('clientUserMessageId') != reply_id or not matching or not IDENTIFIER.fullmatch(str(queued.get('id', ''))):
                    raise ConversationUnavailable('Reply acknowledgement does not match the request.')
                value.update(status='queued', queued_submission_id=queued['id'])
            except Exception:
                value.update(status='unknown', explanation='Worker acknowledgement was not confirmed. Do not send a duplicate.')
            value['updated_at'] = timestamp(); self._write(path, value)
            return value

    def reply_status(self, reply_id):
        self._prepare()
        with (self.root / 'send.lock').open('a+b') as lock:
            os.chmod(lock.name, 0o600); fcntl.flock(lock, fcntl.LOCK_EX)
            return self._reply_status(reply_id)

    def _reply_status(self, reply_id):
        if not UUID.fullmatch(str(reply_id)): raise ValueError('invalid reply identity')
        value = self._read(self.root / (reply_id + '.json'))
        if value['status'] == 'received': return value
        if value['status'] == 'pending' and (datetime.now(timezone.utc) - datetime.fromisoformat(value['created_at'])).total_seconds() > 20:
            value = {**value, 'status': 'unknown', 'explanation': 'Interrupted before a durable Worker acknowledgement. No automatic resend.'}
            self._write(self.root / (reply_id + '.json'), {k:v for k,v in value.items() if k != 'record_sha256'})
        try:
            self._read_thread()
            # Recheck the head for newly consumed input while advancing a durable
            # older-page cursor. At most TWO 20-item pages per call, irrespective
            # of history size; reload/recovery resumes rather than starting over.
            cursors = [None]
            saved_cursor = value.get('reconcile_cursor')
            if saved_cursor is not None: cursors.append(saved_cursor)
            next_cursor = None
            for cursor in cursors:
                messages, following = self._page(cursor)
                if following is not None and following == cursor:
                    raise ConversationUnavailable('Worker receipt cursor did not advance.')
                for message in messages:
                    if message.get('client_id') == reply_id:
                        if message['role'] != 'user' or message['text'] != value['text']:
                            raise ValueError('Worker receipt text mismatch')
                        value = {**value, 'status': 'received', 'turn_id': message['turn_id'],
                                 'message_id': message['message_id'], 'received_observed_at': timestamp()}
                        value.pop('reconcile_cursor', None)
                        self._write(self.root / (reply_id + '.json'), {k:v for k,v in value.items() if k != 'record_sha256'})
                        return value
                next_cursor = following
            value = {**value, 'reconcile_cursor': next_cursor}
            self._write(self.root / (reply_id + '.json'), {k:v for k,v in value.items() if k != 'record_sha256'})
        except ConversationUnavailable:
            return {**value, 'observation': 'unavailable'}
        return value
