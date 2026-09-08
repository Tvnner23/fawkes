"""Presentation against actual canonical typed requests and claim-window policy."""
import json,subprocess,unittest
from pathlib import Path
from src.runtime.codex_app_server import typed_approval,approval_response
from src.runtime.development_attention import APPROVE_ONCE_CLAIM_SECONDS

ROOT=Path(__file__).resolve().parents[1]
def explain(event,decision=None):
    script="const fs=require('fs'),vm=require('vm'),m={exports:{}};vm.runInNewContext(fs.readFileSync('src/app/static/native-attention.js','utf8'),{module:m,Date});const v=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(m.exports.explainRequest(v.event,v.decision)))"
    result=subprocess.run(['node','-e',script],input=json.dumps({'event':event,'decision':decision}),text=True,capture_output=True,check=True,cwd=ROOT)
    return json.loads(result.stdout)

class PermissionExplanationTests(unittest.TestCase):
    def request(self,kind='command'):
        method='item/commandExecution/requestApproval'
        params={'threadId':'t','turnId':'u','itemId':'i','kind':kind,'command':'fixture marker only','cwd':'/fixture','reason':'SAMPLE only','availableDecisions':['accept','decline','cancel']}
        result=typed_approval(method,params,campaign_id='c',invocation_id='inv',worker={'worker_id':'fixture'},process_id=42)
        return {**result,'protocol_binding':result['protocol'],'expires_at':'2030-09-11T02:14:03Z'},params

    def test_actual_write_stdin_projection_is_not_described_as_command_execution(self):
        event,params=self.request('writeStdin');description=explain(event)
        self.assertNotIn('approve_once',event['protocol_binding']['native_decision_choices'])
        self.assertIn('Send input to a running command',description['what'])
        self.assertIn('Terminal-input',description['scopeDetails'])
        with self.assertRaises(OSError):approval_response(event['protocol_binding']['method'],'approve_once',params)
        self.assertEqual(approval_response(event['protocol_binding']['method'],'deny',params),{'decision':'decline'})

    def test_actual_command_and_unknown_display_subtype(self):
        event,_=self.request();self.assertIn('Run a command requested',explain(event)['what'])
        event['requested_authority']='display was truncated {'
        self.assertIn('subtype is unavailable',explain(event)['what'])

    def test_claim_window_matches_owner_and_uses_recorded_deadline(self):
        event,_=self.request()
        self.assertIn(f'{APPROVE_ONCE_CLAIM_SECONDS}-second',explain(event)['duration'])
        decision={'choice':'approve_once','consumed':False,'claim_expires_at':'2030-09-11T02:14:50Z'}
        text=explain(event,decision)['duration']
        self.assertIn('Owner-recorded claim deadline',text)
        self.assertIn('Response deadline',text)
        self.assertIn('are separate',text)
        self.assertNotIn('unused approval expires by',text)

if __name__=='__main__':unittest.main()
