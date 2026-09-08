"""Public page frontiers and completion evidence, without provider calls."""
import copy,unittest
from tests import test_worker_conversation as existing
from src.runtime.worker_conversation import ConversationUnavailable

class HistoryContinuityTests(existing.ConversationTests):
    def test_tools_only_pages_retain_identifiers_not_private_bodies(self):
        self.rpc.history=[existing.item('reasoning',text='PRIVATE REASONING',identity='r1'),
            existing.item('commandExecution',text='PRIVATE TOOL',identity='t1')]
        value=self.worker.projection()
        self.assertEqual(value['page_item_ids'],['r1','t1']);self.assertEqual(value['messages'],[])
        self.assertNotIn('PRIVATE',str(value));self.assertEqual(value['message_order'],'newest_first')
    def test_completed_turns_after_first_final_are_still_validated(self):
        for row in ({'id':'turn-final','status':'completed'},{'id':'old','status':'invented'},{'id':123,'status':'completed'}):
            with self.subTest(row=row):
                self.rpc.turns=[{'id':'turn-final','status':'completed'},row]
                with self.assertRaises(ConversationUnavailable):self.worker.projection()
    def test_all_supported_completed_turn_ids_survive_latest_final_lookup(self):
        self.rpc.turns=[{'id':'turn-final','status':'completed'},{'id':'turn-before','status':'completed'},
            {'id':'turn-running','status':'inProgress'}]
        value=self.worker.projection();self.assertEqual(value['completed_turn_ids'],['turn-final','turn-before'])
    def test_duplicate_tool_or_public_identity_rejected_before_display(self):
        for kind in ('reasoning','userMessage','agentMessage'):
            with self.subTest(kind=kind):
                row=existing.item(kind,identity='same',content=[{'type':'text','text':'same'}]);self.rpc.history=[row,copy.deepcopy(row)]
                with self.assertRaises(ConversationUnavailable):self.worker.projection()
    def test_empty_cursor_not_silently_reset_to_head(self):
        with self.assertRaises(ValueError):self.worker.projection('')

    def test_ninth_and_older_completed_turn_evidence_is_bounded_and_resumable(self):
        original=self.rpc.__call__;calls=[]
        turns=[{'id':'turn-'+str(i),'status':'completed'} for i in range(25,0,-1)]
        old_messages=[existing.item(text='old final',turn='turn-1',identity='old-final'),
            existing.item(text='old commentary',phase='commentary',turn='turn-1',identity='old-commentary')]
        def rpc(method,params):
            calls.append((method,copy.deepcopy(params)))
            if method=='thread/turns/list':
                start=int(params.get('cursor','0'));return {'data':turns[start:start+8],'nextCursor':str(start+8) if start+8<len(turns) else None}
            if method=='thread/items/list':
                if params.get('turnId')=='turn-25':return {'data':[existing.item(turn='turn-25',identity='new-final')],'nextCursor':None}
                return {'data':old_messages,'nextCursor':None}
            return original(method,params)
        self.rpc=rpc;self.worker=self.make()
        page=self.worker.projection('old-items');self.assertNotIn('turn-1',page['completed_turn_ids'])
        self.assertEqual(page['next_turn_cursor'],'8')
        cursor=page['next_turn_cursor'];seen=[]
        while cursor:
            before=len(calls);page=self.make().projection('old-items',turn_cursor=cursor)
            self.assertLessEqual(sum(m=='thread/turns/list' for m,_ in calls[before:]),2)
            self.assertEqual(page['latest_final']['turn_id'],'turn-25')
            seen+=page['completed_turn_ids'];cursor=page['next_turn_cursor']
        self.assertIn('turn-1',seen);self.assertEqual(page['messages'],self.worker.projection('old-items')['messages'])
        self.assertTrue(all(params.get('itemsView')=='notLoaded' for method,params in calls if method=='thread/turns/list'))
        self.assertFalse(any(method in ('turn/start','thread/queue/add') for method,_ in calls))

    def test_completion_cursor_rejects_cycles_malformed_and_ambiguous_rows(self):
        original=self.rpc.__call__
        for bad in ({'data':[],'nextCursor':'again'}, {'data':[],'nextCursor':[]},
                    {'data':[{'id':'x','status':'completed'},{'id':'x','status':'completed'}],'nextCursor':None}):
            def rpc(method,params):
                return bad if method=='thread/turns/list' and params.get('cursor') else original(method,params)
            self.rpc=rpc;self.worker=self.make()
            with self.subTest(bad=bad),self.assertRaises(ConversationUnavailable):self.worker.projection(turn_cursor='again')
        for bad in ('',[], 'x'*4097):
            with self.subTest(cursor=bad),self.assertRaises(ValueError):self.worker.projection(turn_cursor=bad)

    def test_active_turn_identity_does_not_claim_old_commentary_is_current(self):
        self.rpc.turns=[{'id':'new-active','status':'inProgress'},{'id':'turn-final','status':'completed'},{'id':'old-failed','status':'failed'}]
        value=self.worker.projection()
        self.assertEqual(value['active_turn_ids'],['new-active'])
        self.assertNotIn('new-active',value['known_turn_ids'])
        self.assertIn('old-failed',value['known_turn_ids']);self.assertNotIn('old-failed',value['completed_turn_ids'])

if __name__=='__main__':unittest.main()
