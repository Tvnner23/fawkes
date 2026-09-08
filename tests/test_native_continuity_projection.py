import copy
import json
import unittest

from src.runtime.native_continuity_projection import (
    NativeContinuityProjection, NativeArchiveCandidateGenerator,
    interpret_native_continuity_query,
    stable_native_evidence_id,
    NativeSourceRepresentationPreference,
)
from src.runtime.production_retrieval_adapters import TwoStageEvidenceAdapter, TwoStageRetrievalCoordinator
from src.runtime.evidence_eligibility import EvidenceUseContext


def candidate(evidence_id, conversation_id, text, created_at, **extra):
    item = {"instance_id": "fawkes", "domain": "native_archive",
            "evidence_id": evidence_id, "message_id": evidence_id,
            "conversation_id": conversation_id, "source_archive_id": "archive-" + evidence_id,
            "created_at": created_at, "text": text,
            "authority_class": "native_canonical_evidence",
            "original_evidence_reference": {"archive_id": "archive-" + evidence_id,
                                              "message_id": evidence_id}}
    item.update(extra); return item


def metadata(item):
    return {key: item[key] for key in ("instance_id", "domain", "evidence_id",
                                        "conversation_id", "created_at",
                                        "original_evidence_reference")}


class NativeContinuityProjectionTests(unittest.TestCase):
    def test_stable_identity_temporal_neighbors_and_cross_conversation_ambiguity(self):
        items = [
            candidate("a1", "conversation-a", "Atlas belongs to the home project", "2026-01-01T00:00:00+00:00"),
            candidate("a2", "conversation-a", "Atlas needs a network scan", "2026-01-01T00:01:00+00:00"),
            candidate("b1", "conversation-b", "Atlas is also the course prototype", "2026-01-02T00:00:00+00:00"),
        ]
        projector = NativeContinuityProjection()
        first, audit = projector.project(instance_id="fawkes", query="Which one was that Atlas project?",
                                         candidates=items, metadata_catalog=[metadata(x) for x in items])
        second, repeated = projector.project(instance_id="fawkes", query="Which one was that Atlas project?",
                                             candidates=copy.deepcopy(items), metadata_catalog=[metadata(x) for x in items])
        self.assertEqual(first, second); self.assertEqual(audit, repeated)
        self.assertEqual(audit["status"], "current")
        self.assertTrue(audit["ambiguity_set_ids"])
        self.assertEqual(first[0]["neighbor_relationships"][0]["relation"], "next")
        self.assertEqual(first[1]["neighbor_relationships"][0]["relation"], "previous")
        self.assertEqual(len({x["native_evidence_identity"] for x in first}), 3)
        self.assertTrue(all(x["entity_resolution_status"] == "unresolved_lexical_mentions" for x in first))

    def test_duplicates_and_declared_contradictions_remain_distinct(self):
        items = [
            candidate("x1", "one", "The router choice is wired backhaul", "2026-01-01T00:00:00+00:00", contradiction_group_id="claim-router"),
            candidate("x2", "two", "The router choice is wired backhaul", "2026-01-02T00:00:00+00:00", contradiction_group_id="claim-router"),
        ]
        projected, audit = NativeContinuityProjection().project(
            instance_id="fawkes", query="router choice", candidates=items,
            metadata_catalog=[metadata(x) for x in items])
        self.assertEqual([x["evidence_id"] for x in projected], ["x1", "x2"])
        self.assertEqual(len(audit["duplicate_group_ids"]), 1)
        self.assertEqual(audit["contradiction_group_ids"], ["claim-router"])
        self.assertFalse(audit["canonical_records_merged"])
        self.assertFalse(audit["truth_resolution_performed"])
        self.assertNotIn("wired backhaul", json.dumps(audit))

    def test_foreign_scope_fails_closed_and_stale_frontier_is_detected(self):
        item = candidate("x", "one", "Atlas project", "2026-01-01T00:00:00+00:00")
        with self.assertRaises(PermissionError):
            NativeContinuityProjection().project(instance_id="other", query="Atlas",
                candidates=[item], metadata_catalog=[metadata(item)])
        projected, audit = NativeContinuityProjection().project(instance_id="fawkes", query="Atlas",
            candidates=[item], metadata_catalog=[metadata(item)], built_from_frontier_sha256="old-frontier")
        self.assertEqual(audit["status"], "stale")
        self.assertNotIn("continuity_projection_id", projected[0])
        self.assertFalse(audit["projection_applied"])
        self.assertTrue(audit["rebuildable"]); self.assertTrue(audit["originals_authoritative"])

    def test_projection_has_no_source_or_authority_side_effects(self):
        items = [candidate("x", "one", "Atlas project", "2026-01-01T00:00:00+00:00")]
        before = copy.deepcopy(items)
        projected, audit = NativeContinuityProjection().project(instance_id="fawkes", query="Atlas",
            candidates=items, metadata_catalog=[metadata(x) for x in items])
        self.assertEqual(items, before)
        self.assertEqual(projected[0]["authority_class"], "native_canonical_evidence")
        self.assertFalse(audit["automatic_inherited_history"])


class NativeCandidateGenerationTests(unittest.TestCase):
    def metadata(self, evidence_id, conversation, created, terms, privacy="potentially_private"):
        return {"instance_id":"fawkes","domain":"native_archive","evidence_id":evidence_id,
            "authority_class":"native_canonical_evidence","conversation_id":conversation,
            "created_at":created,"local_lexical_terms":list(terms),
            "owner_principal_id":"rider:tanner","privacy_classification":privacy,
            "original_evidence_reference":{"id":evidence_id},"provenance_valid":True,
            "automatic_use_enabled":True,"source_schema_version":2,"eligibility_flags":[]}

    def test_temporal_neighbor_deduplication_and_bounded_thread_expansion(self):
        records=[self.metadata(f"a{i}","thread-a",f"2026-01-{i+1:02d}T12:00:00+00:00",
                               ("atlas",) if i==2 else ("unrelated",)) for i in range(8)]
        records += [self.metadata("b1","thread-b","2026-01-03T13:00:00+00:00",("atlas",))]
        generator=NativeArchiveCandidateGenerator()
        first,audit=generator.generate(query="Atlas between 2026-01-02 and 2026-01-06",
            eligible_metadata=records,max_total=6,max_per_conversation=3)
        second,repeated=generator.generate(query="Atlas between 2026-01-02 and 2026-01-06",
            eligible_metadata=copy.deepcopy(records),max_total=6,max_per_conversation=3)
        self.assertEqual(first,second); self.assertEqual(audit,repeated)
        self.assertLessEqual(len([x for x in first if x["conversation_id"]=="thread-a"]),3)
        self.assertEqual(len({x["evidence_id"] for x in first}),len(first))
        a2=next(x for x in first if x["evidence_id"]=="a2")
        self.assertGreaterEqual(len(a2["candidate_generation_reasons"]),2)
        self.assertEqual(audit["interpretation"]["temporal_constraint"]["kind"],"between_dates")
        self.assertFalse(audit["automatic_inherited_history"])
        self.assertNotIn("Atlas",json.dumps(audit))

    def test_temporal_constraint_excludes_out_of_window_direct_lexical_match(self):
        records=[self.metadata("yesterday","c1","2026-08-30T15:00:00+00:00",("course",)),
                 self.metadata("today","c2","2026-08-31T15:00:00+00:00",("course",))]
        generated,audit=NativeArchiveCandidateGenerator().generate(
            query="Which course was yesterday?",eligible_metadata=records,
            request_timestamp="2026-08-31T15:00:00+00:00",rider_timezone="America/Chicago")
        self.assertEqual([item["evidence_id"] for item in generated],["yesterday"])
        self.assertEqual(audit["interpretation"]["temporal_constraint"]["kind"],"yesterday")

    def test_reference_intent_with_direct_matches_across_conversations_is_ambiguous(self):
        records=[self.metadata("home","c1","2026-08-12T10:00:00+00:00",("atlas","project")),
                 self.metadata("course","c2","2026-08-13T10:00:00+00:00",("atlas","project"))]
        generated,audit=NativeArchiveCandidateGenerator().generate(
            query="Which one was that Atlas project?",eligible_metadata=records)
        self.assertEqual({item["evidence_id"] for item in generated},{"home","course"})
        ambiguity=audit["reference_ambiguity_sets"][0]
        self.assertEqual(ambiguity["basis"],"multiple_direct_native_reference_matches")
        self.assertEqual(ambiguity["candidate_evidence_ids"],["course","home"])

    def test_documented_discussed_thing_phrase_enables_verified_multihop_traversal(self):
        seed=self.metadata("seed","c1","2026-08-14T10:00:00+00:00",("atlas",))
        middle=self.metadata("middle","c2","2026-08-14T11:00:00+00:00",("context",))
        target=self.metadata("target","c3","2026-08-14T12:00:00+00:00",("outcome",))
        for item in (seed,middle,target):
            item["original_evidence_reference"]={"archive_id":"archive-"+item["evidence_id"],
                                                   "message_id":"message-"+item["evidence_id"]}
        seed["native_reference_relationships"]=[{"relationship":"reference_to",
            "qualification_status":"verified","target":middle["original_evidence_reference"]}]
        middle["native_reference_relationships"]=[{"relationship":"thread_related",
            "qualification_status":"verified","target":target["original_evidence_reference"]}]
        generated,audit=NativeArchiveCandidateGenerator().generate(
            query="the thing we discussed about Atlas",eligible_metadata=[seed,middle,target],
            max_thread_hops=2)
        self.assertEqual({item["evidence_id"] for item in generated},{"seed","middle","target"})
        self.assertTrue(audit["interpretation"]["reference_intent"])
        self.assertEqual(audit["relationship_expansion_count"],2)

    def test_cross_conversation_ambiguity_and_contradiction_candidates_survive(self):
        records=[self.metadata("one","c1","2026-01-01T00:00:00+00:00",("atlas",)),
                 self.metadata("two","c2","2026-01-02T00:00:00+00:00",("atlas",))]
        generated,audit=NativeArchiveCandidateGenerator().generate(
            query="Which one was that Atlas?",eligible_metadata=records)
        bodies=[candidate(x["evidence_id"],x["conversation_id"],"Atlas has opposing status",
                          x["created_at"],contradiction_group_id="claim-atlas") for x in generated]
        projected,projection=NativeContinuityProjection().project(instance_id="fawkes",
            query="Which one was that Atlas?",candidates=bodies,
            metadata_catalog=[metadata(x) for x in bodies])
        self.assertEqual({x["evidence_id"] for x in projected},{"one","two"})
        self.assertTrue(projection["ambiguity_set_ids"])
        self.assertEqual(projection["contradiction_group_ids"],["claim-atlas"])
        self.assertFalse(projection["truth_resolution_performed"])

    def test_expanded_neighbor_must_pass_eligibility_independently(self):
        records=[self.metadata("seed","c1","2026-01-01T00:00:00+00:00",("atlas",)),
                 self.metadata("denied-neighbor","c1","2026-01-01T00:01:00+00:00",("private",),privacy="restricted")]
        bodies={"seed":"Atlas project seed","denied-neighbor":"RESTRICTED NEIGHBOR BODY"}
        class Adapter(TwoStageEvidenceAdapter):
            domain_id="native_archive"; authority_class="native_canonical_evidence"; adapter_version="fixture-native-v1"
            def __init__(self): self.materialized=[]; self.generator=NativeArchiveCandidateGenerator()
            def enumerate_metadata(inner,*,instance_id): return copy.deepcopy(records)
            def generate_candidate_metadata(inner,query,eligible_metadata,**kwargs): return inner.generator.generate(query=query,eligible_metadata=eligible_metadata,**kwargs)
            def materialize(inner,reference,*,instance_id): inner.materialized.append(reference["id"]); return {"text":bodies[reference["id"]]}
        adapter=Adapter()
        context=EvidenceUseContext(instance_id="fawkes",rider_principal_id="rider:tanner",
            capability_id="chat.respond",capability_authorized=True,
            provider_mode="configured_external_provider",provider_authorized=True)
        plan=TwoStageRetrievalCoordinator("fawkes","rider:tanner",adapters=(adapter,)).plan(
            "Atlas",evidence_use_context=context)
        self.assertEqual(adapter.materialized,["seed"])
        self.assertEqual([x["evidence_id"] for x in plan["selected_evidence"]],["seed"])
        self.assertIn("privacy_requires_explicit_authorization",[x["reason"] for x in plan["exclusions"]])
        self.assertNotIn("RESTRICTED NEIGHBOR BODY",json.dumps(plan))

    def test_malformed_date_is_not_a_temporal_authorization_signal(self):
        interpretation,terms=interpret_native_continuity_query("on 2026-99-99 Atlas")
        self.assertIsNone(interpretation["temporal_constraint"])

    def test_request_time_timezone_and_dst_are_bound_deterministically(self):
        kwargs={"request_timestamp":"2026-03-09T12:00:00+00:00","rider_timezone":"America/Chicago"}
        first,_=interpret_native_continuity_query("What did we discuss yesterday?",**kwargs)
        second,_=interpret_native_continuity_query("What did we discuss yesterday?",**kwargs)
        self.assertEqual(first,second)
        self.assertEqual(first["request_timestamp"],kwargs["request_timestamp"])
        self.assertEqual(first["rider_timezone"],"America/Chicago")
        self.assertEqual(first["temporal_constraint"]["start"],"2026-03-08T06:00:00+00:00")
        self.assertEqual(first["temporal_constraint"]["end"],"2026-03-09T04:59:59.999999+00:00")

    def test_last_week_last_month_and_n_units_ago_windows(self):
        kwargs={"request_timestamp":"2026-08-31T15:00:00+00:00","rider_timezone":"America/Chicago"}
        week,_=interpret_native_continuity_query("What happened last week?",**kwargs)
        month,_=interpret_native_continuity_query("What happened last month?",**kwargs)
        ago,_=interpret_native_continuity_query("What happened 3 days ago?",**kwargs)
        weeks_ago,_=interpret_native_continuity_query("What happened 2 weeks ago?",**kwargs)
        months_ago,_=interpret_native_continuity_query("What happened 2 months ago?",**kwargs)
        self.assertEqual(week["temporal_constraint"]["kind"],"last_week")
        self.assertEqual(month["temporal_constraint"]["kind"],"last_month")
        self.assertEqual(month["temporal_constraint"]["start"],"2026-07-01T05:00:00+00:00")
        self.assertEqual(ago["temporal_constraint"]["kind"],"3_days_ago")
        self.assertEqual(weeks_ago["temporal_constraint"]["kind"],"2_weeks_ago")
        self.assertEqual(months_ago["temporal_constraint"]["kind"],"2_months_ago")

    def test_missing_timezone_uses_documented_utc_fallback(self):
        interpreted,_=interpret_native_continuity_query("today",
            request_timestamp="2026-08-31T23:00:00-05:00")
        self.assertEqual(interpreted["rider_timezone"],"UTC")
        self.assertEqual(interpreted["timezone_source"],"deterministic_utc_fallback")
        self.assertEqual(interpreted["temporal_constraint"]["start"],"2026-09-01T00:00:00+00:00")

    def test_generic_conversation_reference_preserves_multiple_recent_anchors(self):
        records=[self.metadata("one","c1","2026-08-29T10:00:00+00:00",("alpha",)),
                 self.metadata("two","c2","2026-08-30T10:00:00+00:00",("beta",))]
        generated,audit=NativeArchiveCandidateGenerator().generate(
            query="What was that conversation?",eligible_metadata=records,
            request_timestamp="2026-08-31T12:00:00+00:00",rider_timezone="UTC")
        self.assertEqual({x["evidence_id"] for x in generated},{"one","two"})
        self.assertEqual(len(audit["reference_ambiguity_sets"]),1)
        self.assertEqual(audit["reference_ambiguity_sets"][0]["basis"],
                         "multiple_recent_conversations_no_reference_resolution")

    def test_directional_previous_message_expansion_is_conservative(self):
        records=[self.metadata("one","c1","2026-08-29T10:00:00+00:00",("alpha",)),
                 self.metadata("two","c1","2026-08-29T10:01:00+00:00",("target",)),
                 self.metadata("three","c1","2026-08-29T10:02:00+00:00",("omega",))]
        generated,audit=NativeArchiveCandidateGenerator().generate(
            query="previous message about target",eligible_metadata=records,
            request_timestamp="2026-08-31T12:00:00+00:00",rider_timezone="UTC")
        ids={x["evidence_id"] for x in generated}
        self.assertEqual(ids,{"one","two"})
        self.assertNotIn("three",ids)

    def test_multi_hop_thread_navigation_is_bounded_and_deterministic(self):
        records=[self.metadata(str(index),"c1",f"2026-08-29T10:0{index}:00+00:00",
                               ("target",) if index==3 else ("context",))
                 for index in range(7)]
        generator=NativeArchiveCandidateGenerator()
        kwargs={"query":"earlier in that conversation about target",
                "eligible_metadata":records,"max_thread_hops":2,
                "max_per_conversation":6}
        first,audit=generator.generate(**kwargs)
        second,repeated=generator.generate(**{**kwargs,"eligible_metadata":copy.deepcopy(records)})
        self.assertEqual(first,second); self.assertEqual(audit,repeated)
        self.assertEqual({x["evidence_id"] for x in first},{"1","2","3"})
        second_hop=next(x for x in first if x["evidence_id"]=="1")
        reason=next(x for x in second_hop["candidate_generation_reasons"]
                    if x["reason"]=="conversation_thread_hop")
        self.assertEqual(reason["hop_depth"],2)
        self.assertEqual(reason["relationship_type"],"thread_previous")
        self.assertNotIn("0",{x["evidence_id"] for x in first})
        self.assertEqual(audit["max_thread_hops"],2)

    def test_verified_reference_traversal_preserves_ambiguity_and_limits(self):
        records=[self.metadata("seed","c1","2026-08-29T10:00:00+00:00",("atlas",)),
                 self.metadata("left","c2","2026-08-29T10:01:00+00:00",("left",)),
                 self.metadata("right","c3","2026-08-29T10:02:00+00:00",("right",)),
                 self.metadata("deep","c4","2026-08-29T10:03:00+00:00",("deep",))]
        for item in records:
            item["original_evidence_reference"]={"archive_id":"archive-"+item["evidence_id"],
                                                   "message_id":item["evidence_id"]}
        records[0]["native_reference_relationships"]=[
            {"relationship":"reference_to","qualification_status":"verified",
             "target":records[1]["original_evidence_reference"]},
            {"relationship":"reference_to","qualification_status":"verified",
             "target":records[2]["original_evidence_reference"]}]
        records[1]["native_reference_relationships"]=[
            {"relationship":"thread_related","qualification_status":"verified",
             "target":records[3]["original_evidence_reference"]}]
        generated,audit=NativeArchiveCandidateGenerator().generate(
            query="What was that Atlas thing we discussed?",eligible_metadata=records,
            max_thread_hops=2,max_relationship_expansions=2)
        self.assertEqual(audit["relationship_expansion_count"],2)
        self.assertEqual({x["evidence_id"] for x in generated},{"seed","left","right"})
        self.assertEqual(len(audit["reference_ambiguity_sets"]),1)
        self.assertEqual(audit["reference_ambiguity_sets"][0]["candidate_evidence_ids"],
                         ["left","right"])
        self.assertNotIn("deep",audit["generated_evidence_ids"])

    def test_verified_reference_cannot_reach_ineligible_target(self):
        seed=self.metadata("seed","c1","2026-08-29T10:00:00+00:00",("atlas",))
        denied=self.metadata("denied","c2","2026-08-29T10:01:00+00:00",("secret",),
                             privacy="restricted")
        for item in (seed,denied):
            item["original_evidence_reference"]={"archive_id":"archive-"+item["evidence_id"],
                                                   "message_id":item["evidence_id"]}
        seed["native_reference_relationships"]=[{"relationship":"reference_to",
            "qualification_status":"verified","target":denied["original_evidence_reference"]}]
        bodies={"seed":"Atlas seed","denied":"DENIED REFERENCE BODY"}
        class Adapter(TwoStageEvidenceAdapter):
            domain_id="native_archive"; authority_class="native_canonical_evidence"; adapter_version="fixture-native-v2"
            def __init__(inner): inner.materialized=[]; inner.generator=NativeArchiveCandidateGenerator()
            def enumerate_metadata(inner,*,instance_id): return copy.deepcopy([seed,denied])
            def generate_candidate_metadata(inner,query,eligible_metadata,**kwargs): return inner.generator.generate(query=query,eligible_metadata=eligible_metadata,**kwargs)
            def materialize(inner,reference,*,instance_id): inner.materialized.append(reference["message_id"]); return {"text":bodies[reference["message_id"]]}
        adapter=Adapter(); context=EvidenceUseContext(instance_id="fawkes",rider_principal_id="rider:tanner",
            capability_id="chat.respond",capability_authorized=True,
            provider_mode="configured_external_provider",provider_authorized=True)
        plan=TwoStageRetrievalCoordinator("fawkes","rider:tanner",adapters=(adapter,)).plan(
            "What was that Atlas thing?",evidence_use_context=context)
        self.assertEqual(adapter.materialized,["seed"])
        self.assertNotIn("DENIED REFERENCE BODY",json.dumps(plan))
        self.assertIn("privacy_requires_explicit_authorization",
                      [x["reason"] for x in plan["exclusions"]])
        self.assertFalse(plan["automatic_inherited_history"])

    def test_same_source_message_id_in_different_conversations_stays_distinct(self):
        base={"instance_id":"fawkes","message_id":"reused-message","source_archive_id":"archive"}
        one=stable_native_evidence_id({**base,"conversation_id":"one"})
        two=stable_native_evidence_id({**base,"conversation_id":"two"})
        self.assertNotEqual(one,two)


class NativeSourcePreferenceTests(unittest.TestCase):
    def item(self,evidence_id,archive_id,message_id,representation,*,target=None,contradiction=None):
        relationships=[]
        if target:
            relationships=[{"relationship":"duplicate_of","qualification_status":"verified",
                            "target":{"archive_id":target[0],"message_id":target[1]}}]
        item={"instance_id":"fawkes","domain":"native_archive","evidence_id":evidence_id,
              "conversation_id":"conversation-"+evidence_id,"created_at":"2026-01-01T00:00:00+00:00",
              "authority_class":"native_canonical_evidence","local_lexical_terms":["atlas"],
              "original_evidence_reference":{"archive_id":archive_id,"message_id":message_id},
              "representation_provenance":{"schema_version":1,"representation_class":representation,
                                             "relationships":relationships},
              "eligibility":{"policy_version":"production-evidence-eligibility-v1"},
              "candidate_generation_reasons":[{"reason":"direct_lexical_metadata_match"}]}
        if contradiction:item["contradiction_group_id"]=contradiction
        return item

    def test_verified_source_original_is_preferred_without_canonical_merge(self):
        original=self.item("original","archive-original","message-original","source_original")
        copy_item=self.item("copy","archive-copy","message-copy","duplicate_copy",
                            target=("archive-original","message-original"))
        source=[original,copy_item]; before=copy.deepcopy(source)
        selected,audit=NativeSourceRepresentationPreference().apply(
            generated_candidates=source,eligible_metadata=source)
        self.assertEqual([x["evidence_id"] for x in selected],["original"])
        self.assertEqual(source,before)
        self.assertEqual(audit["context_redundancy_reduction"],1)
        self.assertFalse(audit["canonical_records_merged"])
        preference=next(x for x in audit["decisions"] if x["decision"]=="suppress_redundant_context_copy")
        self.assertEqual(preference["preferred_eligibility_policy_version"],
                         "production-evidence-eligibility-v1")

    def test_insufficient_or_conflicting_provenance_preserves_candidates(self):
        original=self.item("original","archive-original","message-original","source_original")
        uncertain=self.item("uncertain","archive-copy","message-copy","duplicate_copy")
        contradictory=self.item("contradictory","archive-conflict","message-conflict","duplicate_copy",
                                target=("archive-original","message-original"),contradiction="claim-1")
        selected,audit=NativeSourceRepresentationPreference().apply(
            generated_candidates=[original,uncertain,contradictory],
            eligible_metadata=[original,uncertain,contradictory])
        self.assertEqual({x["evidence_id"] for x in selected},{"original","uncertain","contradictory"})
        self.assertIn("provenance_insufficient",[x["reason"] for x in audit["decisions"]])
        self.assertIn("contradiction_relationship_preserved",[x["reason"] for x in audit["decisions"]])
        self.assertFalse(audit["truth_resolution_performed"])

    def test_ineligible_original_cannot_be_selected_through_copy_edge(self):
        original=self.item("original","archive-original","message-original","source_original")
        copy_item=self.item("copy","archive-copy","message-copy","duplicate_copy",
                            target=("archive-original","message-original"))
        selected,audit=NativeSourceRepresentationPreference().apply(
            generated_candidates=[copy_item],eligible_metadata=[copy_item])
        self.assertEqual([x["evidence_id"] for x in selected],["copy"])
        self.assertEqual(audit["decisions"][0]["reason"],"qualified_target_not_independently_eligible")

    def test_verified_copy_chain_prefers_ultimate_source_original(self):
        original=self.item("original","archive-original","message-original","source_original")
        derived=self.item("derived","archive-derived","message-derived","derived_copy",
                          target=("archive-original","message-original"))
        duplicate=self.item("duplicate","archive-duplicate","message-duplicate","duplicate_copy",
                            target=("archive-derived","message-derived"))
        selected,audit=NativeSourceRepresentationPreference().apply(
            generated_candidates=[duplicate],eligible_metadata=[duplicate,derived,original])
        self.assertEqual([x["evidence_id"] for x in selected],["original"])
        decision=audit["decisions"][0]
        self.assertEqual([x["target_evidence_id"] for x in decision["provenance_chain"]],
                         ["derived","original"])

    def test_cyclic_provenance_preserves_all_generated_candidates(self):
        first=self.item("first","archive-first","message-first","duplicate_copy",
                        target=("archive-second","message-second"))
        second=self.item("second","archive-second","message-second","derived_copy",
                         target=("archive-first","message-first"))
        selected,audit=NativeSourceRepresentationPreference().apply(
            generated_candidates=[first,second],eligible_metadata=[first,second])
        self.assertEqual({x["evidence_id"] for x in selected},{"first","second"})
        self.assertEqual({x["reason"] for x in audit["decisions"]},
                         {"provenance_cycle_or_self_reference"})

    def test_preference_is_deterministic_and_body_free(self):
        original=self.item("original","archive-original","message-original","source_original")
        copy_item=self.item("copy","archive-copy","message-copy","duplicate_copy",
                            target=("archive-original","message-original"))
        first,audit=NativeSourceRepresentationPreference().apply(generated_candidates=[copy_item,original],eligible_metadata=[copy_item,original])
        second,repeated=NativeSourceRepresentationPreference().apply(generated_candidates=copy.deepcopy([copy_item,original]),eligible_metadata=copy.deepcopy([copy_item,original]))
        self.assertEqual(first,second);self.assertEqual(audit,repeated)
        self.assertNotIn("Atlas secret body",json.dumps(audit))

    def _coordinator_record(self,item,privacy):
        return {**item,"owner_principal_id":"rider:tanner","privacy_classification":privacy,
                "provenance_valid":True,"automatic_use_enabled":True,"source_schema_version":2,
                "eligibility_flags":[]}

    def test_coordinator_reduces_budget_and_materializes_only_eligible_preference(self):
        original=self._coordinator_record(self.item("original","archive-original","message-original","source_original"),"potentially_private")
        copy_item=self._coordinator_record(self.item("copy","archive-copy","message-copy","duplicate_copy",
                            target=("archive-original","message-original")),"potentially_private")
        source=[original,copy_item]; before=copy.deepcopy(source)
        class Adapter(TwoStageEvidenceAdapter):
            domain_id="native_archive";authority_class="native_canonical_evidence";adapter_version="preference-fixture-v1"
            def __init__(inner):inner.materialized=[];inner.preference=NativeSourceRepresentationPreference()
            def enumerate_metadata(inner,*,instance_id):return copy.deepcopy(source)
            def prefer_representations(inner,generated_metadata,*,eligible_metadata):return inner.preference.apply(generated_candidates=generated_metadata,eligible_metadata=eligible_metadata)
            def materialize(inner,reference,*,instance_id):inner.materialized.append(reference["archive_id"]);return {"text":"Atlas evidence"}
        adapter=Adapter();context=EvidenceUseContext(instance_id="fawkes",rider_principal_id="rider:tanner",
            capability_id="chat.respond",capability_authorized=True,provider_mode="configured_external_provider",provider_authorized=True)
        plan=TwoStageRetrievalCoordinator("fawkes","rider:tanner",adapters=(adapter,)).plan("Atlas",evidence_use_context=context,total_budget_chars=500)
        self.assertEqual(adapter.materialized,["archive-original"])
        self.assertEqual([x["evidence_id"] for x in plan["selected_evidence"]],["original"])
        self.assertEqual(plan["representation_preference"]["native_archive"]["context_redundancy_reduction"],1)
        self.assertLess(plan["allocation"]["per_domain_used"]["native_archive"],len("Atlas evidence")*2)
        self.assertEqual(source,before)

    def test_coordinator_does_not_piggyback_denied_original(self):
        original=self._coordinator_record(self.item("original","archive-original","message-original","source_original"),"restricted")
        copy_item=self._coordinator_record(self.item("copy","archive-copy","message-copy","duplicate_copy",
                            target=("archive-original","message-original")),"potentially_private")
        source=[original,copy_item]
        class Adapter(TwoStageEvidenceAdapter):
            domain_id="native_archive";authority_class="native_canonical_evidence";adapter_version="preference-fixture-v1"
            def __init__(inner):inner.materialized=[];inner.preference=NativeSourceRepresentationPreference()
            def enumerate_metadata(inner,*,instance_id):return copy.deepcopy(source)
            def prefer_representations(inner,generated_metadata,*,eligible_metadata):return inner.preference.apply(generated_candidates=generated_metadata,eligible_metadata=eligible_metadata)
            def materialize(inner,reference,*,instance_id):inner.materialized.append(reference["archive_id"]);return {"text":"Atlas copy"}
        adapter=Adapter();context=EvidenceUseContext(instance_id="fawkes",rider_principal_id="rider:tanner",
            capability_id="chat.respond",capability_authorized=True,provider_mode="configured_external_provider",provider_authorized=True)
        plan=TwoStageRetrievalCoordinator("fawkes","rider:tanner",adapters=(adapter,)).plan("Atlas",evidence_use_context=context)
        self.assertEqual(adapter.materialized,["archive-copy"])
        self.assertEqual([x["evidence_id"] for x in plan["selected_evidence"]],["copy"])
        self.assertIn("privacy_requires_explicit_authorization",[x["reason"] for x in plan["exclusions"]])


if __name__ == "__main__": unittest.main()
