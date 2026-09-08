"""Real Unix/WebSocket fake peer: large traffic followed by exact native resolution."""
import base64,hashlib,json,os,socket,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
import websocket
from src.app.server import ConsoleUpdateStore
from src.runtime import worker_conversation as core,worker_native_approvals as native
from tests.test_worker_native_approvals import request
from tests.test_worker_conversation import THREAD,REPLY

class NativeSocketTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'native.sock'
        self.listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.listener.bind(str(self.path));self.listener.listen(1)
        self.addCleanup(self.listener.close);self.ready=threading.Event();self.release=threading.Event();self.done=threading.Event()
        self.calls=[];self.responses=[];self.errors=[];self.failure=[]
        self.owner=native.NativeApprovalRelay(executable=sys.executable,socket_path=self.path,thread_id=THREAD,cwd=self.root,store=ConsoleUpdateStore(self.root/'store'))
        self.owner._prepare();self.addCleanup(self.owner.close)
        pin=patch.object(core,'PINNED_CODEX_SHA256',core.sha(Path(sys.executable).read_bytes()));pin.start();self.addCleanup(pin.stop)
    def peer(self,mode):
        c=None
        try:
            c,_=self.listener.accept();c.settimeout(3);header=bytearray()
            while not header.endswith(b'\r\n\r\n'):header.extend(c.recv(1))
            key=next(x.split(':',1)[1].strip() for x in header.decode().split('\r\n') if x.lower().startswith('sec-websocket-key:'))
            accept=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
            c.sendall(('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+accept+'\r\n\r\n').encode())
            ws=websocket.WebSocket();ws.sock=c;ws.connected=True
            def frame(data,opcode=1,fin=1):
                f=websocket.ABNF.create_frame(data,opcode,fin);f.mask_value=0;c.sendall(f.format())
            def send(v):frame(json.dumps(v,ensure_ascii=False).encode())
            while True:
                call=json.loads(ws.recv());self.calls.append(call)
                if call['method']=='initialized':continue
                if mode=='rpc_flood':
                    for _ in range(3000):send({'method':'irrelevant','params':{}})
                    return
                if mode=='timeout':self.release.wait(2);return
                result={} if call['method']=='initialize' else {'thread':{'id':THREAD,'cwd':str(self.root),'status':{'type':'active'}}}
                send({'id':call['id'],'result':result})
                if call['method']=='thread/resume':break
            q=request();q['params']['cwd']=str(self.root)
            q['params']['commandActions']=[{'type':'read','command':'cat file','name':'file','path':str(self.root/'file')}]
            if mode=='late_old':q['params']['itemId']='new-operation'
            if mode=='invalid_action':q['params']['commandActions']=[{'type':'futureAction','newMaterial':{'path':'unfamiliar'}}]
            send(q)
            if mode=='late_old':send({'method':'item/completed','params':{'threadId':THREAD,'turnId':'turn-exact',
                'item':{'id':'item-exact','type':'commandExecution','status':'completed','exitCode':0}}})
            # Noise includes > the historically suspicious frame length and split UTF-8.
            body=json.dumps({'method':'item/commandExecution/outputDelta','params':{'threadId':THREAD,'delta':'雪'*190000}},ensure_ascii=False).encode()
            frame(body[:137],fin=0);frame(b'ping',9);frame(body[137:40000],0,0);frame(body[40000:],0)
            self.ready.set()
            if mode=='invalid_action':self.release.wait(2)
            if mode in ('pc','invalid_action'):
                send({'method':'serverRequest/resolved','params':{'threadId':THREAD,'requestId':110}})
            else:
                while True:
                    f=ws.recv_frame()
                    if f.opcode==10:continue
                    value=json.loads(f.data)
                    if 'method' in value:
                        self.calls.append(value);send({'id':value['id'],'result':{'thread':{'id':THREAD,'cwd':str(self.root),'status':{'type':'active'}}}});continue
                    self.responses.append(value);break
                send({'method':'serverRequest/resolved','params':{'threadId':THREAD,'requestId':110}})
            send({'method':'item/completed','params':{'threadId':THREAD,'turnId':'turn-exact','item':{'type':'commandExecution','id':q['params']['itemId'],'status':'completed','exitCode':0}}})
            self.done.set();self.release.wait(2)
        except (BrokenPipeError,ConnectionResetError,websocket.WebSocketConnectionClosedException):pass
        except Exception as exc:self.errors.append(exc)
        finally:
            if c:c.close()
    def start_peer(self,mode):
        server=threading.Thread(target=self.peer,args=(mode,),daemon=True);server.start()
        def run():
            try:self.owner._connection()
            except Exception as exc:self.failure.append(exc)
        client=threading.Thread(target=run,daemon=True);client.start()
        def close():
            self.release.set();self.owner.stop_event.set();server.join(4);client.join(4)
            self.assertFalse(server.is_alive());self.assertFalse(client.is_alive());self.assertFalse(self.errors,self.errors)
        self.addCleanup(close)
        return client
    def wait_for(self,predicate):
        end=time.monotonic()+3
        while time.monotonic()<end:
            if predicate():return
            time.sleep(.01)
        self.fail('Synthetic native condition was not observed')
    def test_fragmented_large_unicode_then_pi_response_and_exact_terminal(self):
        self.start_peer('pi');self.assertTrue(self.ready.wait(3));self.wait_for(lambda:self.owner.connected and bool(self.owner.records))
        r=next(iter(self.owner.records.values()));self.owner.decide(thread_id=THREAD,request_key=r['request_key'],action_sha256=r['action_sha256'],choice_id=r['description']['choices'][0]['choice_id'],submission_id=REPLY,authenticated=True)
        self.assertTrue(self.done.wait(3));self.wait_for(lambda:next(iter(self.owner.records.values()))['operation'] is not None)
        self.assertEqual(self.responses,[{'id':110,'result':{'decision':'accept'}}])
        self.assertEqual(self.owner.projection()['pending_count'],0)
        self.assertEqual([c['method'] for c in self.calls[:4]],['initialize','initialized','thread/read','thread/resume'])
        self.assertEqual(self.calls[3]['params'],{'threadId':THREAD,'excludeTurns':True})
        self.assertFalse(any(c.get('method') in ('turn/start','turn/steer') for c in self.calls))
    def test_pc_resolution_after_large_message_never_sends_pi_response(self):
        self.start_peer('pc');self.assertTrue(self.done.wait(3));self.wait_for(lambda:bool(self.owner.records) and next(iter(self.owner.records.values()))['operation'] is not None)
        r=next(iter(self.owner.records.values()))
        with self.assertRaises(ValueError):self.owner.decide(thread_id=THREAD,request_key=r['request_key'],action_sha256=r['action_sha256'],choice_id=r['description']['choices'][0]['choice_id'],submission_id=REPLY,authenticated=True)
        self.assertEqual(self.responses,[])
    def test_unfamiliar_nested_action_is_pc_only_over_actual_socket(self):
        self.start_peer('invalid_action');self.assertTrue(self.ready.wait(3))
        self.wait_for(lambda:self.owner.connected and bool(self.owner.records))
        r=self.owner.projection()['requests'][0]
        self.assertTrue(r['native_pending']);self.assertTrue(r['needs_decision'])
        self.assertFalse(r['actionable']);self.assertIsNone(r['description'])
        with self.assertRaises(ValueError):
            self.owner.decide(thread_id=THREAD,request_key=r['request_key'],action_sha256=r['action_sha256'],
                choice_id='0'*64,submission_id=REPLY,authenticated=True)
        self.release.set();self.assertTrue(self.done.wait(3));self.assertEqual(self.responses,[])
    def test_late_historical_completion_preserves_new_request_on_wire(self):
        self.owner.epoch='old-connection';self.owner.observe(request());self.owner._disconnect('old ended')
        self.start_peer('late_old');self.assertTrue(self.ready.wait(3))
        self.wait_for(lambda:self.owner.connected and any(r['request']['params']['itemId']=='new-operation' for r in self.owner.records.values()))
        current=next(r for r in self.owner.projection()['requests'] if r['description']['item_id']=='new-operation')
        self.assertTrue(current['actionable']);self.assertTrue(current['native_pending'])
        self.owner.decide(thread_id=THREAD,request_key=current['request_key'],action_sha256=current['action_sha256'],
            choice_id=current['description']['choices'][0]['choice_id'],submission_id=REPLY,authenticated=True)
        self.assertTrue(self.done.wait(3));self.assertEqual(self.responses,[{'id':110,'result':{'decision':'accept'}}])
    def test_rpc_flood_is_bounded_not_infinite_progress(self):
        with patch.object(native,'RPC_SECONDS',.2):
            client=self.start_peer('rpc_flood');client.join(2);self.assertFalse(client.is_alive())
        self.assertTrue(self.failure);self.assertFalse(self.owner.connected)
    def test_timeout_cleans_connection_and_keeps_server_socket(self):
        with patch.object(native,'RPC_SECONDS',.2):
            client=self.start_peer('timeout');client.join(1);self.assertFalse(client.is_alive())
        self.assertTrue(self.failure);self.assertTrue(self.path.exists());self.assertFalse(self.owner.connected)

if __name__=='__main__':unittest.main()
