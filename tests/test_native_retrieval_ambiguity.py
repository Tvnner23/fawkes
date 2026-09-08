import copy
import json
import tempfile
import unittest
from unittest.mock import patch

from src.runtime.chat import FawkesChatRuntime
from src.runtime.native_retrieval_ambiguity import NativeRetrievalAmbiguityPolicy
from src.runtime.production_planner_builder import ServedProductionPlannerBuilder
from src.runtime.evidence_eligibility import POLICY_VERSION as ELIGIBILITY_POLICY_VERSION
from src.runtime.retrieval_planner import POLICY_VERSION as PLANNER_VERSION


class NativeRetrievalAmbiguityTests(unittest.TestCase):
    def evidence(self, evidence_id, conversation, created):
        return {"instance_id":"fawkes","domain":"native_archive",
                "evidence_id":evidence_id,"conversation_id":conversation,
                "created_at":created,"authority_class":"native_canonical_evidence"}

    def audit(self, basis="multiple_recent_conversations_no_reference_resolution"):
        return {"native_archive":{"reference_ambiguity_sets":[{
            "ambiguity_set_id":"reference-ambiguity-stable",
            "candidate_evidence_ids":["one","two"],"basis":basis}],
            "ambiguity_choice_descriptors":[{"ambiguity_set_id":"reference-ambiguity-stable",
                "choices":[{"evidence_id":"one","created_at":"2026-08-28T10:00:00+00:00"},
                           {"evidence_id":"two","created_at":"2026-08-29T11:00:00+00:00"}]}]}}

    def decision(self, basis="multiple_recent_conversations_no_reference_resolution"):
        return NativeRetrievalAmbiguityPolicy().evaluate(
            instance_id="fawkes",rider_principal_id="rider:tanner",
            request_message_id="request-1",correlation_id="request-1",
            candidate_generation=self.audit(basis),selected_evidence=[
                self.evidence("one","conversation-one","2026-08-28T10:00:00+00:00"),
                self.evidence("two","conversation-two","2026-08-29T11:00:00+00:00")])

    def test_decision_and_choice_ids_are_deterministic_body_free_and_distinct(self):
        first=self.decision(); second=self.decision()
        self.assertEqual(first,second)
        choices=first["ambiguity_sets"][0]["choices"]
        self.assertEqual(len({x["choice_id"] for x in choices}),2)
        self.assertNotIn("conversation-one",json.dumps(first))
        self.assertTrue(first["clarification_required"])

    def test_safe_bounded_joint_inclusion_does_not_interrupt(self):
        decision=self.decision("multiple_temporal_native_anchors_safe_joint_inclusion")
        self.assertFalse(decision["clarification_required"])
        self.assertIsNone(NativeRetrievalAmbiguityPolicy().question(decision))

    def test_selection_is_bound_to_exact_set_scope_turn_and_choice(self):
        policy=NativeRetrievalAmbiguityPolicy(); decision=self.decision()
        choice=decision["ambiguity_sets"][0]["choices"][0]
        response={"ambiguity_set_id":"reference-ambiguity-stable","choice_id":choice["choice_id"]}
        selected=policy.validate_selection(decision,response,instance_id="fawkes",
            rider_principal_id="rider:tanner",originating_request_message_id="request-1",
            correlation_id="request-1")
        self.assertEqual(selected["selected_evidence_id"],"one")
        self.assertFalse(selected["authorization_granted"])
        for changes in ({"originating_request_message_id":"wrong-turn"},
                        {"instance_id":"foreign"},{"correlation_id":"wrong"}):
            args={"instance_id":"fawkes","rider_principal_id":"rider:tanner",
                  "originating_request_message_id":"request-1","correlation_id":"request-1",**changes}
            with self.assertRaisesRegex(PermissionError,"scope_or_turn"):
                policy.validate_selection(decision,response,**args)
        tampered=copy.deepcopy(decision); tampered["ambiguity_sets"][0]["choices"][0]["evidence_id"]="denied"
        with self.assertRaisesRegex(PermissionError,"tampered"):
            policy.validate_selection(tampered,response,instance_id="fawkes",
                rider_principal_id="rider:tanner",originating_request_message_id="request-1",
                correlation_id="request-1")

    def test_only_selected_eligible_candidates_become_choices(self):
        audit=self.audit()
        audit["native_archive"]["ambiguity_choice_descriptors"][0]["choices"]=[
            {"evidence_id":"one","created_at":"2026-08-28T10:00:00+00:00"}]
        decision=NativeRetrievalAmbiguityPolicy().evaluate(instance_id="fawkes",
            rider_principal_id="rider:tanner",request_message_id="r1",correlation_id="r1",
            candidate_generation=audit,selected_evidence=[
                self.evidence("one","c1","2026-08-28T10:00:00+00:00")])
        self.assertEqual(decision["ambiguity_sets"],[])
        self.assertFalse(decision["clarification_required"])

    def test_live_runtime_requests_clarification_without_provider_or_permit(self):
        calls=[]; decision=self.decision()
        class Responses:
            def create(inner,**kwargs): calls.append(kwargs); raise AssertionError("provider must not run")
        builder=lambda **kwargs:{"selected_evidence":[self.evidence("one","c1","2026-08-28T10:00:00+00:00")],
            "policy_version":"unified-retrieval-foundation-v1","adapter_versions":{},
            "evidence_eligibility_policy_version":"production-evidence-eligibility-v1",
            "candidate_generation":self.audit(),"ambiguity_decision":decision,"conversation":(),
            "continuity":{"attempted":False,"status":"not_requested"},"warnings":[],
            "retrieval_audit":{"ambiguity_decision":decision}}
        runtime=FawkesChatRuntime(client=type("Client",(),{"responses":Responses()})(),model="test-model",
            instance_id="fawkes",research_enabled=False,retrieval_path="planner",
            planner_context_builder=builder,evidence_transmission_root=tempfile.mkdtemp())
        result=runtime.respond(user_message="Which conversation?",conversation_id="c1",
                               current_message_id="request-1")
        self.assertIn("Which one do you mean?",result["text"])
        self.assertEqual(calls,[])
        self.assertEqual(result["archive_passages"],[])
        self.assertEqual(result["retrieval_audit"]["transmission_authorization"]["status"],"not_attempted")
        self.assertFalse(result["ambiguity_decision"]["authorization_granted"])

    def test_production_builder_reruns_plan_and_constrains_only_intended_set(self):
        one={**self.evidence("one","c1","2026-08-28T10:00:00+00:00"),"text":"ONE"}
        two={**self.evidence("two","c2","2026-08-29T10:00:00+00:00"),"text":"TWO"}
        generation=self.audit()
        base={"policy_version":PLANNER_VERSION,"selected_evidence":[one,two],"candidates":[one,two],
              "eligible_domains":["native_archive"],"exclusions":[],"allocation":{},"warnings":[],
              "continuity_projections":{},"candidate_generation":generation,
              "representation_preference":{},"deterministic_replay_input_sha256":"fresh-plan",
              "automatic_inherited_history":False}
        class Coordinator:
            def __init__(inner):inner.calls=0
            def plan(inner,*args,**kwargs):inner.calls+=1;return copy.deepcopy(base)
        builder=ServedProductionPlannerBuilder.__new__(ServedProductionPlannerBuilder)
        builder.instance_id="fawkes";builder.rider_principal_id="rider:tanner"
        builder.context_messages=20;builder.total_budget_chars=8000;builder.limit_per_domain=20
        builder.adapters=();builder.coordinator=Coordinator();builder.ambiguity_policy=NativeRetrievalAmbiguityPolicy()
        consumption={"selected_evidence_id":"one","ambiguity_candidate_evidence_ids":["one","two"],
            "choice_id":"choice-one","ambiguity_set_id":"reference-ambiguity-stable",
            "originating_ambiguity_decision_id":"decision-old","originating_retrieval_plan_identity":"old-plan",
            "authorization_granted":False}
        with patch("src.runtime.production_planner_builder.build_archive_context",return_value=()):
            result=builder(instance_id="fawkes",user_message="Which conversation?",conversation_id="c",
                request_message_id="new-turn",clarification_consumption=consumption)
        self.assertEqual(builder.coordinator.calls,1)
        self.assertEqual([x["evidence_id"] for x in result["selected_evidence"]],["one"])
        self.assertEqual(result["clarification_consumption"]["status"],"consumed")
        self.assertTrue(result["clarification_consumption"]["fresh_eligibility_result_identity"])
        self.assertFalse(result["clarification_consumption"]["authorization_granted"])

    def test_fresh_denial_never_substitutes_other_ambiguity_candidate(self):
        two={**self.evidence("two","c2","2026-08-29T10:00:00+00:00"),"text":"TWO"}
        base={"policy_version":PLANNER_VERSION,"selected_evidence":[two],"candidates":[two],
              "eligible_domains":["native_archive"],"exclusions":[{"evidence_id":"one","reason":"privacy_requires_explicit_authorization"}],
              "allocation":{},"warnings":[],"continuity_projections":{},"candidate_generation":self.audit(),
              "representation_preference":{},"deterministic_replay_input_sha256":"fresh-denied",
              "automatic_inherited_history":False}
        builder=ServedProductionPlannerBuilder.__new__(ServedProductionPlannerBuilder)
        builder.instance_id="fawkes";builder.rider_principal_id="rider:tanner";builder.context_messages=20
        builder.total_budget_chars=8000;builder.limit_per_domain=20;builder.adapters=()
        builder.coordinator=type("Coordinator",(),{"plan":lambda inner,*args,**kwargs:copy.deepcopy(base)})()
        builder.ambiguity_policy=NativeRetrievalAmbiguityPolicy()
        consumption={"selected_evidence_id":"one","ambiguity_candidate_evidence_ids":["one","two"],
            "choice_id":"choice-one","ambiguity_set_id":"reference-ambiguity-stable"}
        with patch("src.runtime.production_planner_builder.build_archive_context",return_value=()):
            with self.assertRaisesRegex(PermissionError,"no_longer_eligible"):
                builder(instance_id="fawkes",user_message="Which conversation?",conversation_id="c",
                    request_message_id="new-turn",clarification_consumption=consumption)

    def test_consumed_choice_gets_fresh_exact_set_permit_and_provider_revalidation(self):
        query="Which conversation?"
        chosen={"instance_id":"fawkes","owner_principal_id":"authenticated-rider:fawkes",
            "domain":"native_archive","evidence_id":"one","authority_class":"native_canonical_evidence",
            "original_evidence_reference":{"archive_id":"a1","message_id":"m1"},
            "adapter_version":"native-archive-two-stage-v2","text":"CHOSEN BODY",
            "eligibility":{"policy_version":ELIGIBILITY_POLICY_VERSION,"instance_id":"fawkes",
                "privacy_classification":"potentially_private","selected_for_context":True,
                "provider_transmission":{"allowed":True,"reason":"authorized","provider_route":{
                    "provider_policy_id":"private-chat-policy","provider_class":"openai-compatible",
                    "model":"test-model","route_version":"1"}}}}
        decision=NativeRetrievalAmbiguityPolicy().evaluate(instance_id="fawkes",
            rider_principal_id="authenticated-rider:fawkes",request_message_id="origin",
            correlation_id="origin",candidate_generation=self.audit(),selected_evidence=[
                chosen,{**chosen,"evidence_id":"two","created_at":"2026-08-29T10:00:00+00:00"}],
            planner_version=PLANNER_VERSION,eligibility_policy_version=ELIGIBILITY_POLICY_VERSION,
            retrieval_plan_identity="old-plan",query_sha256=__import__("hashlib").sha256(query.encode()).hexdigest())
        choice=decision["ambiguity_sets"][0]["choices"][0]
        calls=[]; captured=[]
        class Responses:
            def create(inner,**kwargs):calls.append(kwargs);return type("Response",(),{"output_text":"answer","usage":None})()
        def builder(**kwargs):
            captured.append(kwargs["clarification_consumption"])
            empty=NativeRetrievalAmbiguityPolicy().evaluate(instance_id="fawkes",
                rider_principal_id="authenticated-rider:fawkes",request_message_id=kwargs["request_message_id"],
                correlation_id=kwargs["request_message_id"],candidate_generation={},selected_evidence=[],
                planner_version=PLANNER_VERSION,eligibility_policy_version=ELIGIBILITY_POLICY_VERSION,
                retrieval_plan_identity="fresh-plan",query_sha256=decision["query_sha256"])
            return {"selected_evidence":[chosen],"policy_version":PLANNER_VERSION,
                "evidence_eligibility_policy_version":ELIGIBILITY_POLICY_VERSION,
                "adapter_versions":{"native_archive":"native-archive-two-stage-v2"},"conversation":(),
                "continuity":{"attempted":False,"status":"not_requested"},"warnings":[],
                "ambiguity_decision":empty,"clarification_consumption":{"status":"consumed"}}
        runtime=FawkesChatRuntime(client=type("Client",(),{"responses":Responses()})(),model="test-model",
            instance_id="fawkes",research_enabled=False,retrieval_path="planner",
            planner_context_builder=builder,evidence_transmission_root=tempfile.mkdtemp())
        result=runtime.respond(user_message="the first",conversation_id="c",current_message_id="new",
            retrieval_clarification={"decision":decision,"response":{"ambiguity_set_id":choice["ambiguity_set_id"] if "ambiguity_set_id" in choice else "reference-ambiguity-stable",
                "choice_id":choice["choice_id"]},"original_query":query})
        self.assertEqual(captured[0]["selected_evidence_id"],"one")
        self.assertEqual(result["retrieval_audit"]["transmission_authorization"]["authorized_evidence_ids"],["one"])
        self.assertIn("CHOSEN BODY",str(calls[-1]["input"]))

    def test_policy_version_mismatch_degrades_to_zero_without_choice_fallback(self):
        query="Which conversation?"; calls=[]; builder_calls=[]
        decision=NativeRetrievalAmbiguityPolicy().evaluate(instance_id="fawkes",
            rider_principal_id="authenticated-rider:fawkes",request_message_id="origin",
            correlation_id="origin",candidate_generation=self.audit(),selected_evidence=[
                self.evidence("one","c1","2026-08-28T10:00:00+00:00"),
                self.evidence("two","c2","2026-08-29T10:00:00+00:00")],
            planner_version="stale-planner",eligibility_policy_version=ELIGIBILITY_POLICY_VERSION,
            retrieval_plan_identity="old",query_sha256=__import__("hashlib").sha256(query.encode()).hexdigest())
        choice=decision["ambiguity_sets"][0]["choices"][0]
        class Responses:
            def create(inner,**kwargs):calls.append(kwargs);return type("Response",(),{"output_text":"zero evidence answer","usage":None})()
        runtime=FawkesChatRuntime(client=type("Client",(),{"responses":Responses()})(),model="test-model",
            instance_id="fawkes",research_enabled=False,retrieval_path="planner",
            planner_context_builder=lambda **kwargs:builder_calls.append(kwargs),
            evidence_transmission_root=tempfile.mkdtemp())
        result=runtime.respond(user_message="the first",conversation_id="c",current_message_id="new",
            retrieval_clarification={"decision":decision,"response":{
                "ambiguity_set_id":"reference-ambiguity-stable","choice_id":choice["choice_id"]},
                "original_query":query})
        self.assertEqual(builder_calls,[])
        self.assertEqual(result["archive_passages"],[])
        self.assertIn("clarification_planner_version_mismatch",
                      result["retrieval_audit"]["clarification_consumption"]["reason"])
        self.assertFalse(any("CHOSEN" in str(call) for call in calls))


if __name__ == "__main__": unittest.main()
