"""Real private Unix sockets, synthetic protocol peer; no native/model invocation."""
import base64
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import websocket
from src.runtime import worker_conversation as core
from src.runtime.worker_conversation_socket import LocalWorkerWebSocket
from tests.test_worker_conversation import THREAD


class SocketTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'worker.sock'
        self.listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.listener.bind(str(self.path));self.listener.listen(1)
        self.addCleanup(self.listener.close)
        self.requests=[];self.errors=[];self.stopped=threading.Event()
        self.pin=patch.object(core,'PINNED_CODEX_SHA256',core.sha(Path(sys.executable).read_bytes()))
        self.pin.start();self.addCleanup(self.pin.stop)

    def peer(self,mode):
        connection=None
        try:
            connection,_=self.listener.accept();connection.settimeout(2)
            header=bytearray()
            while not header.endswith(b'\r\n\r\n'):
                b=connection.recv(1)
                if not b:return
                header.extend(b)
                if len(header)>8192:raise AssertionError('large client handshake')
            self.header=header.decode('ascii')
            key=next(line.split(':',1)[1].strip() for line in self.header.split('\r\n') if line.lower().startswith('sec-websocket-key:'))
            accept=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            if mode=='redirect':
                connection.sendall(b'HTTP/1.1 302 Found\r\nLocation: http://not-authorized.invalid/\r\nContent-Length: 0\r\n\r\n');return
            if mode=='large_header':
                connection.sendall(b'HTTP/1.1 101 Switching Protocols\r\nX-Oversize: '+b'x'*9000);return
            connection.sendall(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+accept+'\r\n\r\n').encode())
            ws=websocket.WebSocket();ws.sock=connection;ws.connected=True
            self.requests.append(json.loads(ws.recv()))
            def send(body,opcode=1,fin=1,masked=False):
                frame=websocket.ABNF.create_frame(body,opcode,fin)
                frame.mask_value=int(masked)
                connection.sendall(frame.format())
            send(json.dumps({'id':1,'result':{}}))
            self.requests.append(json.loads(ws.recv()));self.requests.append(json.loads(ws.recv()))
            if mode=='timeout':self.stopped.wait(2);return
            if mode=='approval':send(json.dumps({'id':99,'method':'item/commandExecution/requestApproval','params':{}}))
            elif mode=='wrong_id':send('{"id":3,"result":{}}')
            elif mode=='duplicate':send('{"id":2,"result":{},"result":{}}')
            elif mode=='error':send('{"id":2,"error":{"code":-1,"message":"fixture"}}')
            elif mode=='malformed':send('not json')
            elif mode=='binary':send(b'not text',opcode=2)
            elif mode=='masked':send('{"id":2,"result":{}}',masked=True)
            elif mode=='wrong_cont':send(b'{}',opcode=0)
            elif mode=='oversize_header':connection.sendall(b'\x81\x7f'+struct.pack('!Q',core.MAX_FRAME+1));self.stopped.wait(2)
            elif mode=='oversize_message':send(b'x'*600,fin=0);send(b'x'*600,opcode=0)
            elif mode=='oversize_ping':send(b'x'*126,opcode=9)
            elif mode=='fragmented_pong':send(b'x',opcode=10,fin=0)
            elif mode=='frame_count':
                for _ in range(2100):send('{}',opcode=10)
            elif mode=='aggregate':
                for _ in range(10):send(json.dumps({'method':'notice','params':'x'*500}))
            elif mode=='close':send(b'',opcode=8)
            else:
                send(b'ping',opcode=9)
                pong=ws.recv_frame();self.pong=(pong.opcode,pong.data)
                body=json.dumps({'id':2,'result':{'text':'café 🐦\r\n'+'x'*100000}},ensure_ascii=False).encode()
                send(body[:12],fin=0);send(body[12:333],opcode=0,fin=0);send(body[333:],opcode=0)
        except (BrokenPipeError,ConnectionResetError,websocket.WebSocketConnectionClosedException):pass
        except Exception as error:self.errors.append(error)
        finally:
            if connection:connection.close()

    def run_peer(self,mode='normal'):
        t=threading.Thread(target=self.peer,args=(mode,),daemon=True);t.start()
        def finish():self.stopped.set();t.join(3);self.assertFalse(t.is_alive());self.assertFalse(self.errors,self.errors)
        self.addCleanup(finish)
        return LocalWorkerWebSocket(executable=sys.executable,socket_path=self.path,thread_id=THREAD,cwd=self.root)

    def test_exact_fragmented_unicode_request_and_protocol_ping(self):
        proxy=self.run_peer()
        response=proxy('thread/read',{'threadId':THREAD,'includeTurns':False})
        self.assertEqual(response['text'],'café 🐦\r\n'+'x'*100000)
        self.assertEqual([x['method'] for x in self.requests],['initialize','initialized','thread/read'])
        self.assertEqual(self.requests[-1]['params'],{'threadId':THREAD,'includeTurns':False})
        self.assertEqual(self.pong,(10,b'ping'))
        self.assertNotIn('Origin:',self.header)
        self.assertNotIn('Authorization:',self.header)
        self.assertTrue(self.path.exists())

    def test_unexpected_approval_has_no_response(self):
        with self.assertRaisesRegex(core.ConversationUnavailable,'decision owner'):
            self.run_peer('approval')('thread/read',{'threadId':THREAD})
        self.assertEqual(len(self.requests),3)

    def test_absolute_timeout_closes_connection_not_server(self):
        start=time.monotonic()
        with patch.object(core,'REQUEST_SECONDS',.2),self.assertRaises(core.ConversationUnavailable):
            self.run_peer('timeout')('thread/read',{'threadId':THREAD})
        self.assertLess(time.monotonic()-start,1)
        self.assertTrue(self.path.exists())

    def test_invalid_responses_and_bounds(self):
        for mode in ('wrong_id','duplicate','error','malformed','binary','masked','wrong_cont','oversize_header','oversize_message','oversize_ping','fragmented_pong','frame_count','aggregate','close','redirect','large_header'):
            with self.subTest(mode=mode):
                case=SocketTests();case.setUp()
                try:
                    limits={'MAX_FRAME':1000} if mode.startswith('oversize') else {'MAX_TRANSFER':3000} if mode=='aggregate' else {}
                    with (patch.multiple(core,**limits) if limits else nullcontext()),self.assertRaises((core.ConversationUnavailable,ValueError)):
                        case.run_peer(mode)('thread/read',{'threadId':THREAD})
                finally:case.doCleanups()

    def test_disallowed_method_or_wrong_thread_never_connects(self):
        proxy=LocalWorkerWebSocket(executable=sys.executable,socket_path=self.path,thread_id=THREAD,cwd=self.root)
        for method,params in [('thread/resume',{'threadId':THREAD}),('turn/start',{'threadId':THREAD}),('thread/read',{'threadId':'other'})]:
            with self.assertRaises(PermissionError):proxy(method,params)

    def test_wrong_client_and_nonprivate_parent(self):
        proxy=LocalWorkerWebSocket(executable=sys.executable,socket_path=self.path,thread_id=THREAD,cwd=self.root)
        with patch.object(core,'PINNED_CODEX_SHA256','0'*64),self.assertRaises(core.ConversationUnavailable):proxy('thread/read',{'threadId':THREAD})
        self.root.chmod(0o755)
        try:
            with self.assertRaisesRegex(core.ConversationUnavailable,'privately owned'):proxy('thread/read',{'threadId':THREAD})
        finally:self.root.chmod(0o700)

if __name__=='__main__':unittest.main()
