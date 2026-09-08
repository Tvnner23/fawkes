"""Bounded WebSocket JSON-RPC on the pinned, private local Worker socket.

The official direct Unix listener speaks WebSocket, not the legacy daemon proxy's
raw byte stream. This client never starts/resumes a thread or answers approvals.
"""
import json
import os
from pathlib import Path
import socket
import stat
import struct
import time

import websocket
from websocket._abnf import frame_buffer

from . import worker_conversation as core

MAX_HANDSHAKE = 8192
MAX_OUTGOING = 500_000


class _BudgetSocket:
    """One absolute deadline and finite wire budget, including the HTTP upgrade."""
    def __init__(self, sock, deadline):
        self.sock = sock
        self.deadline = deadline
        self.received = 0
        self.sent = 0
        self.handshake = True

    def __getattr__(self, name):
        return getattr(self.sock, name)

    def _arm(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise core.ConversationUnavailable('Worker acknowledgement timed out; delivery is not confirmed.')
        self.sock.settimeout(remaining)

    def recv(self, size, flags=0):
        self._arm()
        bound = MAX_HANDSHAKE if self.handshake else core.MAX_TRANSFER
        body = self.sock.recv(min(size, max(1, bound - self.received + 1), 65536), flags)
        self.received += len(body)
        if self.received > bound:
            raise core.ConversationUnavailable('Worker response exceeds its bounded reader.')
        return body

    def send(self, body, flags=0):
        self._arm()
        if self.sent + len(body) > MAX_OUTGOING:
            raise core.ConversationUnavailable('Worker outgoing protocol budget exceeded.')
        count = self.sock.send(body, flags)
        self.sent += count
        return count


class _BoundedFrames(frame_buffer):
    def recv_length(self):
        super().recv_length()
        if self.length > core.MAX_FRAME:
            raise core.ConversationUnavailable('Worker frame exceeds its bounded reader.')
        if self.header[4] >= 8 and (self.length > 125 or not self.header[0]):
            raise core.ConversationUnavailable('Invalid Worker control frame.')


class LocalWorkerWebSocket(core.LocalWorkerProxy):
    """Same request allowlist/identity, using the installed direct listener contract."""
    def __call__(self, method, params):
        if method not in self.METHODS or not isinstance(params, dict) or params.get('threadId') != self.thread_id:
            raise PermissionError('method or Worker identity outside configured conversation')
        if core.sha(self.executable.read_bytes()) != core.PINNED_CODEX_SHA256:
            raise core.ConversationUnavailable('The pinned Worker client changed; qualification is required.')
        try:
            node = self.socket.lstat()
            parent = self.socket.parent.lstat()
        except FileNotFoundError as exc:
            raise core.ConversationUnavailable('This Worker is not connected to its shared local app-server.') from exc
        if (not stat.S_ISSOCK(node.st_mode) or not stat.S_ISDIR(parent.st_mode)
                or node.st_uid != os.getuid() or parent.st_uid != os.getuid() or parent.st_mode & 0o077):
            raise core.ConversationUnavailable('The local Worker control socket is not privately owned.')
        deadline = time.monotonic() + core.REQUEST_SECONDS
        peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        ws = None
        completed = False
        try:
            peer.settimeout(min(2, core.REQUEST_SECONDS))
            peer.connect(str(self.socket))
            pid, uid, _ = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid() or core.sha(Path(f'/proc/{pid}/exe').read_bytes()) != core.PINNED_CODEX_SHA256:
                raise core.ConversationUnavailable('The actual Worker server is not the qualified executable.')
            wire = _BudgetSocket(peer, deadline)
            # A supplied AF_UNIX connection prevents DNS/TCP/proxy retrieval.
            # No cookies, bearer credentials, extensions or Origin are sent.
            ws = websocket.create_connection('ws://localhost/', socket=wire,
                timeout=max(.001, deadline-time.monotonic()), suppress_origin=True,
                redirect_limit=0, enable_multithread=False)
            if ws.getstatus() != 101:
                raise core.ConversationUnavailable('Worker did not accept the local WebSocket upgrade.')
            wire.handshake = False
            ws.frame_buffer = _BoundedFrames(ws._recv, False)
            frames = 0

            def send(value):
                body = core.canonical(value)
                if len(body) > 100_000:
                    raise ValueError('Worker request exceeds bound')
                wire._arm()
                ws.send(body.decode('utf-8'))

            def receive(expected):
                nonlocal frames
                message = bytearray()
                continuing = False
                while True:
                    wire._arm()
                    frame = ws.recv_frame()
                    frames += 1
                    if frames > 2000:
                        raise core.ConversationUnavailable('Worker response exceeds its bounded reader.')
                    if frame.mask_value:
                        raise core.ConversationUnavailable('Worker server sent an invalid masked frame.')
                    if frame.opcode == websocket.ABNF.OPCODE_CLOSE:
                        raise core.ConversationUnavailable('Worker connection closed without an acknowledgement.')
                    if frame.opcode == websocket.ABNF.OPCODE_PING:
                        ws.pong(frame.data)
                        continue
                    if frame.opcode == websocket.ABNF.OPCODE_PONG:
                        continue
                    if frame.opcode == websocket.ABNF.OPCODE_TEXT:
                        if continuing:
                            raise core.ConversationUnavailable('Invalid Worker message continuation.')
                    elif frame.opcode == websocket.ABNF.OPCODE_CONT:
                        if not continuing:
                            raise core.ConversationUnavailable('Unexpected Worker message continuation.')
                    else:
                        raise core.ConversationUnavailable('Worker returned a non-text protocol message.')
                    if len(message) + len(frame.data) > core.MAX_FRAME:
                        raise core.ConversationUnavailable('Worker message exceeds its bounded reader.')
                    message.extend(frame.data)
                    continuing = not frame.fin
                    if continuing:
                        continue
                    value = json.loads(message.decode('utf-8'), object_pairs_hook=core.unique)
                    message.clear()
                    if not isinstance(value, dict):
                        raise core.ConversationUnavailable('Malformed Worker frame.')
                    if 'method' in value:
                        if 'id' in value:
                            raise core.ConversationUnavailable('A native request requires its existing decision owner.')
                        continue
                    if type(value.get('id')) is not int or value['id'] != expected:
                        raise core.ConversationUnavailable('Worker response identity mismatch.')
                    if 'error' in value or not isinstance(value.get('result'), dict):
                        raise core.ConversationUnavailable('The Worker rejected this conversation request.')
                    return value['result']

            send({'id': 1, 'method': 'initialize', 'params': {
                'clientInfo': {'name': 'fawkes_console_conversation', 'version': '1'},
                'capabilities': {'experimentalApi': True}}})
            receive(1)
            send({'method': 'initialized', 'params': {}})
            send({'id': 2, 'method': method, 'params': params})
            result = receive(2)
            completed = True
            return result
        except (OSError, websocket.WebSocketException) as exc:
            raise core.ConversationUnavailable('Worker connection failed; delivery is not confirmed.') from exc
        finally:
            # Close this connection only. Never stop the shared server or Worker.
            if ws is not None:
                if completed:
                    try:
                        ws.close(timeout=max(.001, min(1, deadline-time.monotonic())))
                    except Exception:
                        pass  # Shutdown below still closes the owned connection.
                ws.shutdown()
            peer.close()
