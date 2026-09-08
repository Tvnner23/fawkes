"""Offline 0.153.4 Reviewer-only contract regressions; never contact a model."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from src.runtime import codex_app_server as app

class Stream(io.StringIO):
    def close(self): pass

class Process:
    pid=321
    returncode=None
    def __init__(self,frames):
        self.stdin=Stream();self.stdout=Stream(''.join((json.dumps(f) if not isinstance(f,str) else f)+'\n' for f in frames));self.stderr=Stream()
        self.terminated=0;self.killed=0
    def poll(self):return self.returncode
    def terminate(self):self.terminated+=1;self.returncode=-15
    def wait(self,timeout=None):return self.returncode
    def kill(self):self.killed+=1;self.returncode=-9

START=[{'id':1,'result':{}},{'id':2,'result':{'thread':{'id':'t'}}},{'id':3,'result':{'turn':{'id':'u'}}}]
ITEM={'method':'item/completed','params':{'threadId':'t','turnId':'u','item':{'id':'answer','type':'agentMessage','text':'{"compatible":true}','questions':None}}}
END={'method':'turn/completed','params':{'threadId':'t','turn':{'id':'u','status':'completed'}}}
PARAMS={'threadId':'t','turnId':'u','itemId':'action','command':'true','cwd':'/fixture','availableDecisions':['accept','decline','cancel']}
APPROVAL={'id':7,'method':'item/commandExecution/requestApproval','params':PARAMS}
RESOLVED={'method':'serverRequest/resolved','params':{'threadId':'t','requestId':7}}

class CompatibilityTests(unittest.TestCase):
    def run_frames(self,frames,handler=None,sandbox='read-only',timeout=2):
        self.process=Process(frames)
        transport=app.CodexAppServerTransport(protocol_version=app.REVIEWER_PROTOCOL_VERSION,popen=lambda *a,**k:self.process,timeout_seconds=timeout)
        with tempfile.TemporaryDirectory() as root,patch.object(transport,'qualify',return_value={'protocol_version':app.REVIEWER_PROTOCOL_VERSION}):
            self.output=Path(root)/'result.json'
            result=transport.run(cwd=root,prompt='synthetic',output_schema={'type':'object'},output_path=self.output,sandbox=sandbox,campaign_id='c',invocation_id='i',worker={'worker_id':'r'},environment={},approval_handler=handler,allow_detached_continuation=False)
            return result,json.loads(self.output.read_text())
    def test_default_remains_01510(self):
        self.assertEqual(app.CodexAppServerTransport().protocol_version,app.PROTOCOL_VERSION)
    def test_unsupported_profile_rejected(self):
        with self.assertRaises(app.CodexAppServerError):app.CodexAppServerTransport(protocol_version='0.153.4')
    def test_wrong_cli_rejected_before_generation(self):
        t=app.CodexAppServerTransport(protocol_version=app.REVIEWER_PROTOCOL_VERSION)
        with patch.object(app.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'codex-cli 0.151.0','')) as run:
            with self.assertRaisesRegex(app.CodexAppServerError,'expected codex-cli 0.153.4'):t.qualify({})
            self.assertEqual(run.call_count,1)
    def test_complete_real_schema_identity_and_tampering(self):
        # Supplied by the external qualifier; the candidate does not supply expected hashes to itself.
        schemas=Path(os.environ['FAWKES_COMPAT_TEST_SCHEMAS'])
        t=app.CodexAppServerTransport(protocol_version=app.REVIEWER_PROTOCOL_VERSION)
        def generate(command,**kwargs):
            if command[-1]=='--version':return subprocess.CompletedProcess(command,0,'codex-cli 0.153.4','')
            shutil.copytree(schemas,Path(command[-1]),dirs_exist_ok=True)
            if tamper[0]:(Path(command[-1])/'v2/TurnCompletedNotification.json').write_text('{}')
            return subprocess.CompletedProcess(command,0,'','')
        tamper=[False]
        with patch.object(app.subprocess,'run',side_effect=generate):
            self.assertEqual(t.qualify({})['generated_schema_count'],19)
            tamper[0]=True
            with self.assertRaisesRegex(app.CodexAppServerError,'schema changed'):t.qualify({})
    def test_manifest_tamper_rejected(self):
        t=app.CodexAppServerTransport(protocol_version=app.REVIEWER_PROTOCOL_VERSION)
        with patch.object(app.Path,'read_bytes',return_value=b'{}'):
            with self.assertRaisesRegex(app.CodexAppServerError,'manifest changed'):t._qualify_reviewer_schemas({})
    def test_success_and_read_only_outgoing_contract(self):
        result,body=self.run_frames(START+[ITEM,END]);self.assertEqual(body,{'compatible':True})
        messages=[json.loads(l) for l in self.process.stdin.getvalue().splitlines()]
        self.assertEqual([x['method'] for x in messages],['initialize','initialized','thread/start','turn/start'])
        self.assertEqual(messages[2]['params']['sandbox'],'read-only')
        self.assertEqual(messages[2]['params']['approvalPolicy'],'on-request')
        self.assertEqual((result.thread_id,result.turn_id),('t','u'));self.assertEqual(self.process.terminated,1)
    def test_write_profile_rejected_before_launch(self):
        with self.assertRaisesRegex(app.CodexAppServerError,'read-only'):self.run_frames([],sandbox='workspace-write')
        self.assertEqual(self.process.terminated,0)
    def test_failed_interrupted_unknown_completion(self):
        for status in ('failed','interrupted','unknown'):
            end=json.loads(json.dumps(END));end['params']['turn']['status']=status
            with self.subTest(status=status),self.assertRaises(app.CodexAppServerError):self.run_frames(START+[ITEM,end])
            self.assertEqual(self.process.terminated,1)
    def test_malformed_frame_and_missing_output_fail(self):
        for tail in (['not JSON'],[END]):
            with self.subTest(tail=tail),self.assertRaises(app.CodexAppServerError):self.run_frames(START+tail)
            self.assertEqual(self.process.terminated,1)
    def test_terminal_and_item_lineage_rejected(self):
        for original in (END,ITEM):
            frame=json.loads(json.dumps(original));frame['params']['threadId']='neighbor'
            with self.subTest(frame=frame),self.assertRaisesRegex(app.CodexAppServerError,'identity mismatch'):self.run_frames(START+[frame])
    def test_exact_approval_and_single_claim(self):
        seen=[];claims=[]
        def handler(request,**kw):seen.append(request);return {'choice':'approve_once','claim':lambda:claims.append(1)}
        self.run_frames(START+[APPROVAL,RESOLVED,ITEM,END],handler)
        self.assertEqual(claims,[1]);self.assertEqual(seen[0]['protocol']['version'],app.REVIEWER_PROTOCOL_VERSION)
        self.assertEqual(seen[0]['protocol']['process_id'],321)
        self.assertIn({'id':7,'result':{'decision':'accept'}},[json.loads(x) for x in self.process.stdin.getvalue().splitlines()])
    def test_duplicate_and_substituted_resolution_fail(self):
        for resolution in (RESOLVED,{'method':'serverRequest/resolved','params':{'threadId':'t','requestId':8}}):
            claims=[]
            with self.subTest(resolution=resolution),self.assertRaises(app.CodexAppServerError):
                self.run_frames(START+[APPROVAL,RESOLVED,resolution],lambda *a,**k:{'choice':'approve_once','claim':lambda:claims.append(1)})
            self.assertEqual(claims,[1])
    def test_unknown_and_broader_requests_never_reach_handler(self):
        for method in ('item/permissions/requestApproval','item/commandExecution/writeStdin','unknown/request'):
            seen=[];frame={'id':7,'method':method,'params':PARAMS}
            with self.subTest(method=method),self.assertRaises(app.CodexAppServerError):self.run_frames(START+[frame],lambda *a,**k:seen.append(a))
            self.assertFalse(seen)
    def test_approval_wrong_turn_and_missing_handler(self):
        changed=json.loads(json.dumps(APPROVAL));changed['params']['turnId']='other'
        for frame in (APPROVAL,changed):
            with self.subTest(frame=frame),self.assertRaises(app.CodexAppServerError):self.run_frames(START+[frame])
    def test_read_only_write_denied_without_handler(self):
        frame={'id':7,'method':'item/fileChange/requestApproval','params':{'threadId':'t','turnId':'u','itemId':'patch','reason':'write'}}
        self.run_frames(START+[frame,ITEM,END]);self.assertIn('"decision": "cancel"',self.process.stdin.getvalue().replace(':',': '))
    def test_deny_and_cancel_cleanup(self):
        self.run_frames(START+[APPROVAL,ITEM,END],lambda *a,**k:{'choice':'deny'})
        self.assertIn('decline',self.process.stdin.getvalue())
        with self.assertRaisesRegex(app.CodexAppServerError,'cancelled'):self.run_frames(START+[APPROVAL],lambda *a,**k:{'choice':'cancel_campaign'})
        self.assertEqual(self.process.terminated,1)
    def test_timeout_cleanup_no_respawn(self):
        with self.assertRaisesRegex(app.CodexAppServerError,'timed out'):self.run_frames([],timeout=0)
        self.assertEqual(self.process.terminated,1)

    def test_reviewer_process_loss_never_enters_detached_continuation(self):
        for phase in ('during_decision', 'after_acknowledgement'):
            for explicit in (False, True):
                with self.subTest(phase=phase, explicit=explicit), tempfile.TemporaryDirectory() as root:
                    process=Process(START+[APPROVAL]+([RESOLVED] if phase=='after_acknowledgement' else []))
                    original_write=process.stdin.write
                    def write(value):
                        result=original_write(value)
                        if json.loads(value).get('id')==7:process.returncode=1
                        return result
                    process.stdin.write=write
                    claims=[];launches=[]
                    def popen(*args,**kwargs):launches.append(1);return process
                    def handler(*args,**kwargs):
                        if phase=='during_decision':process.returncode=1
                        return {'choice':'approve_once','claim':lambda:claims.append(1)}
                    transport=app.CodexAppServerTransport(protocol_version=app.REVIEWER_PROTOCOL_VERSION,popen=popen,timeout_seconds=3)
                    with patch.object(transport,'qualify',return_value={}),patch.object(transport,'_continue_detached') as retry:
                        options={'allow_detached_continuation':True} if explicit else {}
                        with self.assertRaises(app.CodexAppServerError) as caught:
                            transport.run(cwd=root,prompt='synthetic',output_schema={'type':'object'},output_path=Path(root)/'output.json',sandbox='read-only',campaign_id='fixture',invocation_id='fixture-only',worker={'worker_id':'fixture'},environment={},approval_handler=handler,**options)
                        self.assertEqual(caught.exception.category,'stale_app_server_process' if phase=='during_decision' else 'unexpected_exit')
                        retry.assert_not_called()
                        self.assertEqual(len(launches),1)
                        self.assertEqual(len(claims),0 if phase=='during_decision' else 1)
                        self.assertFalse((Path(root)/'output.json').exists())

if __name__=='__main__':unittest.main()
