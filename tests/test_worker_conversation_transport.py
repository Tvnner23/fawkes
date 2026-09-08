"""Real pipes and synthetic peers only; no Codex process or model call."""
import json, os, socket, subprocess, sys, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
from src.runtime import worker_conversation as module
from tests.test_worker_conversation import THREAD

class ProxyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.sock=self.root/'control.sock'
        self.listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.listener.bind(str(self.sock));self.listener.listen(1);self.addCleanup(self.listener.close)
        self.processes=[];self.commands=[]
    def proxy(self,mode='normal'):
        # Socket credential check still exercises the real current process;
        # only the expected executable digest is rebound to Python in this test.
        executable=Path(sys.executable)
        expected=module.sha(executable.read_bytes())
        self.patch=patch.object(module,'PINNED_CODEX_SHA256',expected);self.patch.start();self.addCleanup(self.patch.stop)
        def accept():
            try:
                self.listener.settimeout(.2)
                conn,_=self.listener.accept();conn.close()
            except (socket.timeout,OSError):pass # Rejected pre-connect cases create no peer.
        thread=threading.Thread(target=accept,daemon=True);thread.start()
        self.addCleanup(lambda:thread.join(timeout=.3))
        output=self.root/'outgoing.json'
        script=r'''
import json,os,sys,time
mode,output=sys.argv[1:]
init=json.loads(sys.stdin.readline())
print(json.dumps({'id':1,'result':{'userAgent':'synthetic fixture'}}),flush=True)
ack=json.loads(sys.stdin.readline());request=json.loads(sys.stdin.readline())
with open(output,'w') as f:json.dump([init,ack,request],f)
if mode=='timeout':time.sleep(5)
elif mode=='approval':
 print(json.dumps({'id':999,'method':'item/commandExecution/requestApproval','params':{'synthetic':True}}),flush=True);time.sleep(5)
elif mode=='malformed':print('not-json',flush=True)
elif mode=='wrong-id':print(json.dumps({'id':3,'result':{}}),flush=True)
elif mode=='duplicate':print('{"id":2,"result":{},"result":{}}',flush=True)
elif mode=='oversize':os.write(1,b'x'*2000);time.sleep(5)
else:
 print(json.dumps({'method':'thread/status/changed','params':{'type':'synthetic'}}),flush=True)
 body=json.dumps({'id':2,'result':{'text':'café 🐦\r\n'+'x'*100000}},ensure_ascii=False).encode()+b'\n'
 for pos in range(0,len(body),37):os.write(1,body[pos:pos+37])
'''
        def spawn(command,**kwargs):
            self.commands.append(command)
            proc=subprocess.Popen([sys.executable,'-c',script,mode,str(output)],**kwargs)
            self.processes.append(proc);return proc
        return module.LocalWorkerProxy(executable=executable,socket_path=self.sock,thread_id=THREAD,cwd=str(self.root),popen=spawn)
    def test_fragmented_large_utf8_exact_response_and_outgoing_unchanged(self):
        value=self.proxy()('thread/read',{'threadId':THREAD,'includeTurns':False})
        self.assertEqual(value['text'],'café 🐦\r\n'+'x'*100000)
        requests=json.loads((self.root/'outgoing.json').read_text())
        self.assertEqual([x['method'] for x in requests],['initialize','initialized','thread/read'])
        self.assertEqual(requests[2]['params'],{'threadId':THREAD,'includeTurns':False})
        self.assertEqual(self.commands[0][1:],['app-server','proxy','--sock',str(self.sock)])
        self.assertTrue(all(p.poll() is not None for p in self.processes))
    def test_unexpected_approval_is_not_answered(self):
        with self.assertRaisesRegex(module.ConversationUnavailable,'decision owner'):
            self.proxy('approval')('thread/read',{'threadId':THREAD})
        self.assertEqual(len(json.loads((self.root/'outgoing.json').read_text())),3)
        self.assertTrue(all(p.poll() is not None for p in self.processes))
    def test_timeout_cleans_only_proxy(self):
        with patch.object(module,'REQUEST_SECONDS',.15),self.assertRaises(module.ConversationUnavailable):
            self.proxy('timeout')('thread/read',{'threadId':THREAD})
        self.assertTrue(all(p.poll() is not None for p in self.processes))
        self.assertTrue(self.sock.exists())
    def test_malformed_wrong_identity_duplicate_and_oversize_fail(self):
        # Separate test instance for each private socket prevents a stale peer.
        for mode in ('malformed','wrong-id','duplicate','oversize'):
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as unused:
                    case=ProxyTests('test_fragmented_large_utf8_exact_response_and_outgoing_unchanged')
                    case.setUp()
                    try:
                        with patch.object(module,'MAX_FRAME',1000),self.assertRaises((module.ConversationUnavailable,ValueError)):
                            case.proxy(mode)('thread/read',{'threadId':THREAD})
                        self.assertTrue(all(p.poll() is not None for p in case.processes))
                    finally:case.doCleanups()
    def test_wrong_client_fails_before_spawn(self):
        proxy=module.LocalWorkerProxy(executable=sys.executable,socket_path=self.sock,thread_id=THREAD,cwd=str(self.root),popen=lambda *a,**k:self.fail('spawned'))
        with self.assertRaises(module.ConversationUnavailable):proxy('thread/read',{'threadId':THREAD})
    def test_non_private_parent_fails_before_spawn(self):
        proxy=self.proxy();self.root.chmod(0o755)
        with self.assertRaises(module.ConversationUnavailable):proxy('thread/read',{'threadId':THREAD})
        self.assertFalse(self.processes);self.root.chmod(0o700)

if __name__=='__main__':unittest.main()
