"""Native command decision lineage; synthetic peers only, no model or Pi."""
import copy
from datetime import datetime,timezone,timedelta
from pathlib import Path
import tempfile,time,unittest
from src.app.server import ConsoleUpdateStore
from src.runtime.worker_native_approvals import NativeApprovalRelay,describe_request,METHOD
from tests.test_worker_conversation import THREAD,REPLY

def request(identity=110):
    prefix=['python','-B','tests/synthetic.py']
    return {'id':identity,'method':METHOD,'params':{'threadId':THREAD,'turnId':'turn-exact','itemId':'item-exact',
        'startedAtMs':int(time.time()*1000),'kind':'command','command':'python -B tests/synthetic.py','cwd':'/tmp/fixture',
        'environmentId':'local','reason':'Run the focused test, according to the Worker.',
        'proposedExecpolicyAmendment':prefix,'availableDecisions':['accept',{'acceptWithExecpolicyAmendment':{'execpolicy_amendment':prefix}},'cancel']}}

class NativeApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=ConsoleUpdateStore(Path(self.tmp.name)/'updates');self.owner=self.make();self.owner._prepare();self.addCleanup(self.owner.close)
        self.owner.epoch='synthetic-connection-1';self.owner.connected=True;self.owner.verified_at=time.time()
        self.native=request();self.owner.observe(self.native)
    def make(self):return NativeApprovalRelay(executable='/not/launched',socket_path='/not/opened',thread_id=THREAD,cwd='/tmp/fixture',store=self.store)
    def record(self):return next(iter(self.owner.records.values()))
    def decide(self,index=0,**changes):
        r=self.record();args={'thread_id':THREAD,'request_key':r['request_key'],'action_sha256':r['action_sha256'],
            'choice_id':r['description']['choices'][index]['choice_id'],'submission_id':REPLY,'authenticated':True};args.update(changes)
        return self.owner.decide(**args)
    def test_offered_order_and_saved_prefix_scope(self):
        d=describe_request(self.native,THREAD)
        self.assertEqual([c['native_decision'] for c in d['choices']],self.native['params']['availableDecisions'])
        self.assertIn('not limited to this task',d['choices'][1]['scope']);self.assertIn('tests/synthetic.py',d['choices'][1]['scope'])
    def test_plain_reason_never_replaces_action(self):
        for field,value in [('command',None),('command',[]),('command',''),('cwd',None),('startedAtMs',True)]:
            with self.subTest(field=field,value=value):
                q=copy.deepcopy(self.native);q['params'][field]=value
                with self.assertRaises(ValueError):describe_request(q,THREAD)
    def test_unknown_broader_and_stdin_requests_need_pc(self):
        for field,value in [('kind','writeStdin'),('additionalPermissions',{'network':{'enabled':True}}),('networkApprovalContext',{'host':'example.test'}),('futurePermission',True)]:
            q=copy.deepcopy(self.native);q['params'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):describe_request(q,THREAD)
    def test_missing_or_duplicated_choices_not_invented(self):
        for choices in (None,[],['accept','accept'],['newDecision']):
            q=copy.deepcopy(self.native);q['params']['availableDecisions']=choices
            with self.subTest(choices=choices),self.assertRaises(ValueError):describe_request(q,THREAD)
    def test_changed_saved_prefix_rejected(self):
        q=copy.deepcopy(self.native);q['params']['proposedExecpolicyAmendment']=['python']
        with self.assertRaises(ValueError):describe_request(q,THREAD)
    def test_selection_not_effect_before_single_reader_send(self):
        r=self.decide();self.assertEqual(r['selection']['state'],'recorded_not_sent');sent=[]
        self.owner._send_selection(r['request_key'],sent.append)
        self.assertEqual(sent,[{'id':110,'result':{'decision':'accept'}}])
        self.owner._send_selection(r['request_key'],sent.append);self.assertEqual(len(sent),1)
        self.assertIsNone(self.record()['operation']);self.assertEqual(self.record()['status'],'submitted')
    def test_saved_permission_is_exact_native_object(self):
        r=self.decide(1);sent=[];self.owner._send_selection(r['request_key'],sent.append)
        self.assertEqual(sent[0]['result']['decision'],self.native['params']['availableDecisions'][1])
    def test_deny_cancel_and_session_choices_match_native(self):
        for choice in ('decline','cancel','acceptForSession'):
            with self.subTest(choice=choice):
                q=request(111+len(self.owner.records));q['params']['availableDecisions']=[choice];self.owner.observe(q)
                r=list(self.owner.records.values())[-1];c=r['description']['choices'][0]
                v=self.owner.decide(thread_id=THREAD,request_key=r['request_key'],action_sha256=r['action_sha256'],choice_id=c['choice_id'],submission_id=REPLY,authenticated=True)
                sent=[];self.owner._send_selection(v['request_key'],sent.append);self.assertEqual(sent[0]['result']['decision'],choice)
    def test_pc_wins_before_pi_tap(self):
        self.owner.observe({'method':'serverRequest/resolved','params':{'threadId':THREAD,'requestId':110}})
        with self.assertRaises(ValueError):self.decide()
        self.assertIsNone(self.record()['selection']);self.assertEqual(self.record()['status'],'resolved')
    def test_pc_wins_after_intent_before_send(self):
        r=self.decide();self.owner.observe({'method':'serverRequest/resolved','params':{'threadId':THREAD,'requestId':110}})
        sent=[];self.owner._send_selection(r['request_key'],sent.append);self.assertEqual(sent,[])
    def test_same_duplicate_gets_receipt_different_choice_rejected(self):
        first=self.decide();self.assertEqual(first,self.decide())
        with self.assertRaises(ValueError):self.decide(1)
        self.assertEqual(self.owner.outgoing.qsize(),1)
    def test_wrong_binding_auth_thread_or_option_no_send(self):
        for delta in ({'authenticated':False},{'thread_id':REPLY},{'action_sha256':'0'*64},{'choice_id':'0'*64},{'submission_id':'invalid'}):
            with self.subTest(delta=delta),self.assertRaises((ValueError,PermissionError)):self.decide(**delta)
        self.assertEqual(self.owner.outgoing.qsize(),0)
    def test_completion_closes_card_without_resolution_notification(self):
        self.owner.observe({'method':'item/completed','params':{'threadId':THREAD,'turnId':'turn-exact','item':{'type':'commandExecution','id':'item-exact','status':'failed','exitCode':1}}})
        self.assertEqual(self.record()['operation']['status'],'failed')
        self.assertIsNone(self.record()['selection'])
        with self.assertRaises(ValueError):self.decide()
    def test_wrong_operation_does_not_complete_request(self):
        self.owner.observe({'method':'item/completed','params':{'threadId':THREAD,'turnId':'another-turn','item':{'type':'commandExecution','id':'item-exact','status':'completed'}}})
        self.assertIsNone(self.record()['operation']);self.assertTrue(self.owner.projection()['requests'][0]['actionable'])
    def test_duplicate_native_id_different_action_rejected(self):
        self.owner.observe(copy.deepcopy(self.native));self.assertEqual(len(self.owner.records),1)
        q=copy.deepcopy(self.native);q['params']['command']='something else'
        with self.assertRaises(ValueError):self.owner.observe(q)
    def test_response_path_revalidates_material(self):
        r=self.decide();self.owner.records[r['request_key']]['request']['params']['command']='different'
        with self.assertRaises(ValueError):self.owner._send_selection(r['request_key'],lambda _:self.fail('must not send'))
    def test_expiry_and_stale_observation_do_not_authorize(self):
        r=self.record();self.owner.records[r['request_key']]['expires_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        with self.assertRaises(ValueError):self.decide()
        self.assertFalse(self.owner.projection()['requests'][0]['actionable'])
    def test_connection_loss_and_recovery_never_replay_selection(self):
        r=self.decide();self.owner._disconnect('synthetic loss');self.owner.close()
        successor=self.make();successor._prepare();self.addCleanup(successor.close)
        self.assertEqual(successor.records[r['request_key']]['status'],'connection_lost');self.assertTrue(successor.outgoing.empty())
        successor.epoch='next';successor.connected=True;successor.verified_at=time.time();successor.observe(self.native)
        self.assertFalse(any(x['actionable'] for x in successor.projection()['requests']))
    def test_one_owner_lock_and_private_audit(self):
        other=self.make()
        with self.assertRaises(BlockingIOError):other._prepare()
        other.close()
        for p in self.owner.root.glob('*.json'):self.assertEqual(p.stat().st_mode&0o777,0o600)
    def test_send_failure_is_not_retried(self):
        r=self.decide()
        def failed(_):raise OSError('synthetic lost send')
        with self.assertRaises(OSError):self.owner._send_selection(r['request_key'],failed)
        sent=[];self.owner._send_selection(r['request_key'],sent.append);self.assertEqual(sent,[])

    def test_old_actionable_request_not_hidden_by_resolved_history(self):
        original=self.record()['request_key']
        for i in range(25):
            q=request(200+i);q['params']['itemId']='history-'+str(i);self.owner.observe(q)
            self.owner.observe({'method':'serverRequest/resolved','params':{'threadId':THREAD,'requestId':200+i}})
        p=self.owner.projection();self.assertEqual(p['pending_count'],1)
        self.assertTrue(next(r for r in p['requests'] if r['request_key']==original)['actionable'])
        older=self.owner.projection(p['next_cursor']);self.assertEqual(len(older['requests']),5)
        self.assertNotIn(original,[r['request_key'] for r in older['requests']])

    def test_expiry_is_recorded_and_stale_unsent_selection_is_not_claimed_sent(self):
        r=self.decide();self.owner.verified_at=time.time()-13
        self.owner._send_selection(r['request_key'],lambda _:self.fail('stale send'))
        self.assertEqual(self.record()['selection']['state'],'not_sent')
        self.assertEqual(self.record()['status'],'unavailable')

    def test_protocol_error_is_not_success_or_execution(self):
        self.decide();self.owner.observe({'id':110,'error':{'code':-1,'message':'synthetic rejection'}})
        self.assertEqual(self.record()['status'],'response_rejected');self.assertIsNone(self.record()['operation'])
        self.assertEqual(self.owner.projection()['pending_count'],1)
        self.assertTrue(self.owner.projection()['requests'][0]['needs_decision'])
        self.assertFalse(self.owner.projection()['requests'][0]['actionable'])
        self.owner.observe({'method':'serverRequest/resolved','params':{'threadId':THREAD,'requestId':110}})
        self.assertEqual(self.owner.projection()['pending_count'],0)

    def test_terminal_observation_before_replayed_request_cannot_authorize(self):
        self.owner.observe({'method':'item/completed','params':{'threadId':THREAD,'turnId':'turn-exact','item':{'type':'commandExecution','id':'item-exact','status':'completed','exitCode':0}}})
        q=request(120);self.owner.observe(q)
        self.assertFalse(any(r['actionable'] for r in self.owner.projection()['requests']))

    def test_pending_entry_remains_until_native_resolution_even_after_selection(self):
        self.decide();self.assertEqual(self.owner.projection()['pending_count'],1)
        self.owner.observe({'method':'serverRequest/resolved','params':{'threadId':THREAD,'requestId':110}})
        self.assertEqual(self.owner.projection()['pending_count'],0)

    def test_local_window_expiry_does_not_claim_native_request_ended(self):
        r=self.record();self.owner.records[r['request_key']]['expires_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        p=self.owner.projection();self.assertEqual(p['pending_count'],1)
        self.assertTrue(p['requests'][0]['needs_decision']);self.assertFalse(p['requests'][0]['actionable'])
        self.assertEqual(p['requests'][0]['status'],'response_window_expired')

    def test_turn_interruption_clears_request_without_inventing_execution(self):
        self.owner.observe({'method':'turn/completed','params':{'threadId':THREAD,'turn':{'id':'turn-exact','status':'interrupted'}}})
        self.assertEqual(self.owner.projection()['pending_count'],0);self.assertIsNone(self.record()['operation'])
        q=request(777);self.owner.observe(q)
        self.assertFalse(any(r['actionable'] for r in self.owner.projection()['requests']))

    def test_backwards_clock_is_unknown_not_permission_freshness(self):
        self.owner.verified_at=time.time()+30
        self.assertFalse(self.owner.projection()['connected'])
        with self.assertRaises(ValueError):self.decide()

    def test_unreplayable_selection_still_needs_pc_after_reconnect_and_restart(self):
        self.decide();self.owner._disconnect('lost before acknowledgement');self.owner.close()
        successor=self.make();successor._prepare();self.addCleanup(successor.close)
        successor.epoch='reconnected';successor.connected=True;successor.verified_at=time.time()
        successor.observe(self.native)
        for i in range(25):
            q=request(800+i);q['params']['itemId']='resolved-'+str(i);successor.observe(q)
            successor.observe({'method':'serverRequest/resolved','params':{'threadId':THREAD,'requestId':800+i}})
        p=successor.projection();self.assertTrue(p['connected']);self.assertEqual(p['pending_count'],1)
        current=[r for r in p['requests'] if r['native_pending']]
        self.assertEqual(len(current),1);self.assertTrue(current[0]['needs_decision'])
        self.assertFalse(current[0]['actionable']);self.assertEqual(current[0]['status'],'unavailable')
        self.assertIn('PC terminal',current[0]['explanation'])
        self.assertTrue(successor.outgoing.empty())
        successor.observe({'method':'serverRequest/resolved','params':{'threadId':THREAD,'requestId':110}})
        p=successor.projection();self.assertEqual(p['pending_count'],0)
        self.assertFalse(any(r['native_pending'] or r['needs_decision'] for r in p['requests']))

    def test_unsent_stale_selection_remains_pc_attention_after_fresh_sync(self):
        r=self.decide();self.owner.verified_at=time.time()-13;sent=[]
        self.owner._send_selection(r['request_key'],sent.append)
        self.assertFalse(self.owner.projection()['connected'])
        self.owner.verified_at=time.time()
        p=self.owner.projection();self.assertEqual(p['pending_count'],1)
        self.assertTrue(p['requests'][0]['needs_decision']);self.assertTrue(p['requests'][0]['native_pending'])
        self.assertFalse(p['requests'][0]['actionable'])
        self.owner._send_selection(r['request_key'],sent.append);self.assertEqual(sent,[])
        self.owner.observe({'method':'turn/completed','params':{'threadId':THREAD,'turn':{'id':'turn-exact','status':'interrupted'}}})
        self.assertEqual(self.owner.projection()['pending_count'],0)

    def test_supported_nested_action_variants_preserved_for_display_and_response(self):
        variants=[{'type':'read','command':'cat file','name':'file','path':'/tmp/file'},
            {'type':'listFiles','command':'ls','path':None},
            {'type':'search','command':'rg phrase','query':'phrase','path':'/tmp'},
            {'type':'unknown','command':'synthetic'}, {'type':'listFiles','command':'ls'},
            {'type':'search','command':'rg phrase'}]
        for actions in (None,[],variants):
            with self.subTest(actions=actions):
                q=request(900+len(self.owner.records));q['params']['commandActions']=actions
                self.assertEqual(describe_request(q,THREAD)['command_actions'],actions)
                self.owner.observe(q);r=list(self.owner.records.values())[-1]
                selected=self.owner.decide(thread_id=THREAD,request_key=r['request_key'],action_sha256=r['action_sha256'],
                    choice_id=r['description']['choices'][0]['choice_id'],submission_id=REPLY,authenticated=True)
                sent=[];self.owner._send_selection(selected['request_key'],sent.append)
                self.assertEqual(sent,[{'id':q['id'],'result':{'decision':'accept'}}])

    def test_unknown_malformed_nested_action_material_not_offered_or_sent(self):
        invalid=[{},'read',{'type':[],'command':'x'},{'type':'futureAction','newMaterial':{'path':'/tmp'}},
            {'type':'read','command':'cat file','name':'file'},
            {'type':'read','command':'cat file','name':1,'path':'/tmp/file'},
            {'type':'read','command':'cat file','name':'file','path':None},
            {'type':'search','command':'rg','query':[]},
            {'type':'listFiles','command':False}, {'type':'unknown','command':'x','extra':'unknown'}]
        for actions in ({},'read',*[ [v] for v in invalid ]):
            with self.subTest(actions=actions):
                q=request(950+len(self.owner.records));q['params']['commandActions']=actions
                with self.assertRaises(ValueError):describe_request(q,THREAD)
                self.owner.observe(q);r=list(self.owner.records.values())[-1]
                p=next(v for v in self.owner.projection()['requests'] if v['request_key']==r['request_key'])
                self.assertIsNone(p['description']);self.assertTrue(p['needs_decision']);self.assertFalse(p['actionable'])
        # Revalidate nested meanings at the actual send boundary, independently
        # of digest mismatch. A corrupted-but-rehashed stored description cannot
        # make an unfamiliar native action into an approved response.
        from src.runtime.worker_conversation import sha,canonical
        r=self.decide()
        stored=self.owner.records[r['request_key']]
        stored['request']['params']['commandActions']=[{'type':'futureAction','command':'x'}]
        stored['action_sha256']=sha(canonical(stored['request']))
        with self.assertRaises(ValueError):
            self.owner._send_selection(r['request_key'],lambda _:self.fail('unfamiliar native material sent'))

    def test_late_old_completion_cannot_remove_reused_id_for_new_operation(self):
        old=self.record()['request_key'];self.owner._disconnect('epoch1 ended')
        self.owner.epoch='epoch2';self.owner.connected=True;self.owner.verified_at=time.time()
        q=request(110);q['params']['itemId']='different-operation';self.owner.observe(q)
        new=list(self.owner.records.values())[-1]
        self.owner.observe({'method':'item/completed','params':{'threadId':THREAD,'turnId':'turn-exact',
            'item':{'id':'item-exact','type':'commandExecution','status':'completed','exitCode':0}}})
        p=self.owner.projection();self.assertEqual(p['pending_count'],1)
        current=next(r for r in p['requests'] if r['request_key']==new['request_key'])
        self.assertTrue(current['actionable']);self.assertTrue(current['needs_decision']);self.assertTrue(current['native_pending'])
        self.assertEqual(self.owner.records[old]['operation']['status'],'completed')
        selected=self.owner.decide(thread_id=THREAD,request_key=new['request_key'],action_sha256=new['action_sha256'],
            choice_id=new['description']['choices'][0]['choice_id'],submission_id=REPLY,authenticated=True)
        sent=[];self.owner._send_selection(selected['request_key'],sent.append)
        self.assertEqual(sent,[{'id':110,'result':{'decision':'accept'}}])

    def test_actionability_requires_exact_current_pending_mapping(self):
        r=self.record();self.owner.pending.clear()
        value=next(v for v in self.owner.projection()['requests'] if v['request_key']==r['request_key'])
        self.assertFalse(value['actionable']);self.assertFalse(value['native_pending']);self.assertFalse(value['needs_decision'])

if __name__=='__main__':unittest.main()
