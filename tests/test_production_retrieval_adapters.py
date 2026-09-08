import copy
import unittest

from src.runtime.evidence_eligibility import EvidenceUseContext
from src.runtime.production_retrieval_adapters import TwoStageEvidenceAdapter, TwoStageRetrievalCoordinator


class FixtureAdapter(TwoStageEvidenceAdapter):
    adapter_version = "fixture-v1"
    def __init__(self, domain, authority, records, bodies):
        self.domain_id=domain; self.authority_class=authority; self.records=records; self.bodies=bodies; self.calls=[]
    def enumerate_metadata(self, *, instance_id): self.calls.append("enumerate"); return copy.deepcopy(self.records)
    def materialize(self, reference, *, instance_id): self.calls.append("materialize:"+reference["id"]); return {"text": self.bodies[reference["id"]]}
    def rank_local(self, query, candidates, *, limit): self.calls.append("rank"); return super().rank_local(query,candidates,limit=limit)


def record(domain="memory", privacy="potentially_private", owner="rider:tanner", instance="fawkes", eid="e1", **kw):
    x={"instance_id":instance,"domain":domain,"evidence_id":eid,"authority_class":domain+"_authority",
       "owner_principal_id":owner,"privacy_classification":privacy,"original_evidence_reference":{"id":eid},
       "provenance_valid":True,"automatic_use_enabled":True,"source_schema_version":2,"eligibility_flags":[]}
    x.update(kw); return x


class TwoStageAdapterTests(unittest.TestCase):
    def context(self, **kw):
        x=dict(instance_id="fawkes",rider_principal_id="rider:tanner",capability_id="chat.respond",
               capability_authorized=True,provider_mode="configured_external_provider",provider_authorized=True)
        x.update(kw); return EvidenceUseContext(**x)

    def test_eligibility_precedes_materialization_and_ranking(self):
        a=FixtureAdapter("memory","memory_authority",[record()],{"e1":"relevant evidence"})
        plan=TwoStageRetrievalCoordinator("fawkes","rider:tanner",adapters=(a,)).plan("relevant",evidence_use_context=self.context())
        self.assertEqual(a.calls,["enumerate","materialize:e1","rank"])
        events=[x["event"] for x in plan["enforcement_order"]]
        self.assertLess(events.index("eligibility"),events.index("materialize")); self.assertLess(events.index("materialize"),events.index("rank"))

    def test_denied_evidence_never_materializes_or_reaches_semantic_provider(self):
        a=FixtureAdapter("memory","memory_authority",[record(privacy="restricted")],{"e1":"secret"})
        class Ranker:
            def __init__(self): self.calls=[]
            def rank(self,**kw): self.calls.append(kw); return []
        ranker=Ranker(); plan=TwoStageRetrievalCoordinator("fawkes","rider:tanner",adapters=(a,),semantic_ranker=ranker).plan("secret",evidence_use_context=self.context())
        self.assertEqual(a.calls,["enumerate","rank"]); self.assertEqual(ranker.calls,[])
        self.assertEqual(plan["exclusions"][0]["reason"],"privacy_requires_explicit_authorization")

    def test_provider_denial_cannot_be_bypassed_by_local_degradation(self):
        a=FixtureAdapter("memory","memory_authority",[record(privacy="highly_private",sensitive_category="health")],{"e1":"health evidence"})
        plan=TwoStageRetrievalCoordinator("fawkes","rider:tanner",adapters=(a,)).plan("health",evidence_use_context=self.context(sensitive_request_categories=("health",)))
        self.assertNotIn("materialize:e1",a.calls); self.assertEqual(plan["selected_evidence"],[])
        self.assertEqual(plan["exclusions"][0]["reason"],"provider_transmission_denied")

    def test_foreign_unknown_quarantined_and_high_score_are_hard_denials(self):
        records=[record(instance="other",eid="f"),record(privacy="unknown",eid="u"),record(eid="q",eligibility_flags=["quarantined"],retrieval_score=999)]
        a=FixtureAdapter("memory","memory_authority",records,{"f":"x","u":"x","q":"x"})
        plan=TwoStageRetrievalCoordinator("fawkes","rider:tanner",adapters=(a,)).plan("x",evidence_use_context=self.context())
        self.assertEqual(plan["selected_evidence"],[]); self.assertFalse(any(x.startswith("materialize") for x in a.calls))

    def test_domains_remain_distinct_and_allocation_is_deterministic(self):
        adapters=[]
        for domain in ("native_archive","memory","library"):
            adapters.append(FixtureAdapter(domain,domain+"_authority",[record(domain=domain,eid=domain)],{domain:"shared relevant"}))
        c=TwoStageRetrievalCoordinator("fawkes","rider:tanner",adapters=adapters)
        first=c.plan("shared",evidence_use_context=self.context(),total_budget_chars=300)
        second=c.plan("shared",evidence_use_context=self.context(),total_budget_chars=300)
        self.assertEqual(first["selected_evidence"],second["selected_evidence"])
        self.assertEqual({x["domain"] for x in first["selected_evidence"]},{"native_archive","memory","library"})
        self.assertFalse(first["automatic_inherited_history"])

    def test_legacy_compatibility_is_derived_without_source_mutation(self):
        legacy=record(privacy=None,owner=None,continuity_ownership_basis="scoped_instance_record",source_schema_version=1)
        before=copy.deepcopy(legacy); a=FixtureAdapter("memory","memory_authority",[legacy],{"e1":"legacy relevant"})
        plan=TwoStageRetrievalCoordinator("fawkes","rider:tanner",adapters=(a,)).plan("legacy",evidence_use_context=self.context())
        self.assertEqual(legacy,before); self.assertEqual(plan["selected_evidence"][0]["privacy_classification"],"legacy_private_unclassified")

    def test_ranker_failure_falls_back_only_over_already_eligible_set(self):
        a=FixtureAdapter("library","library_authority",[record(domain="library")],{"e1":"fallback relevant"})
        class Broken: 
            def rank(self,**kw): raise RuntimeError("down")
        plan=TwoStageRetrievalCoordinator("fawkes","rider:tanner",adapters=(a,),semantic_ranker=Broken()).plan("fallback",evidence_use_context=self.context())
        self.assertEqual(len(plan["selected_evidence"]),1); self.assertIn("degraded to local",plan["warnings"][0])


if __name__=="__main__": unittest.main()
