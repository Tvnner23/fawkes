import tempfile
import unittest
from pathlib import Path

from src.runtime.retrieval_planner import (
    ProjectionDescriptor, StaticEvidenceAdapter, UnifiedRetrievalPlanner,
)
from src.runtime.retrieval_replay import load_flight, record_live_flight, replay_flight


def candidate(owner, domain, evidence_id, text, authority, **extra):
    return {"instance_id": owner, "domain": domain, "evidence_id": evidence_id,
            "text": text, "authority_class": authority,
            "original_evidence_reference": {"domain": domain, "id": evidence_id}, **extra}


def adapter(domain, items, *, authority=None, **kwargs):
    authority = authority or f"{domain}_authority"
    return StaticEvidenceAdapter(domain, items, authority_class=authority, **kwargs)


class UnifiedRetrievalPlannerTests(unittest.TestCase):
    def test_same_query_is_deterministic_across_distinct_domains(self):
        adapters = [
            adapter("native_archive", [candidate("fawkes", "native_archive", "a1", "same query native", "native_archive_authority")]),
            adapter("memory", [candidate("fawkes", "memory", "m1", "same query memory", "memory_authority")]),
            adapter("library", [candidate("fawkes", "library", "l1", "same query library", "library_authority")]),
        ]
        planner = UnifiedRetrievalPlanner("fawkes", adapters=adapters)
        first = planner.plan("same query", total_budget_chars=900)
        second = planner.plan("same query", total_budget_chars=900)
        self.assertEqual(first, second)
        self.assertEqual([item["domain"] for item in first["selected_evidence"]],
                         ["native_archive", "memory", "library"])
        self.assertEqual({item["authority_class"] for item in first["selected_evidence"]},
                         {"native_archive_authority", "memory_authority", "library_authority"})

    def test_ownership_privacy_authorization_and_availability_precede_ranking(self):
        calls = []

        class ObservedAdapter(StaticEvidenceAdapter):
            def retrieve(self, query, *, instance_id, limit):
                calls.append(self.domain_id)
                return super().retrieve(query, instance_id=instance_id, limit=limit)

        private = ObservedAdapter("library", [], authority_class="library_authority",
                                  required_grants=("library.private.read",))
        unavailable = ObservedAdapter("future_domain", [], authority_class="future_authority",
                                      available=False)
        plan = UnifiedRetrievalPlanner("fawkes", adapters=(private, unavailable)).plan("query")
        self.assertEqual(calls, [])
        self.assertEqual(plan["domain_status"]["library"]["reason"], "authorization_missing")
        self.assertEqual(plan["domain_status"]["future_domain"]["reason"], "domain_unavailable")

    def test_foreign_candidate_degrades_domain_without_leaking(self):
        foreign = candidate("other", "memory", "m1", "private sibling evidence", "memory_authority")
        plan = UnifiedRetrievalPlanner("fawkes", adapters=(adapter("memory", [foreign]),)).plan("private")
        self.assertEqual(plan["selected_evidence"], [])
        self.assertEqual(plan["domain_status"]["memory"]["reason"], "retrieval_degraded")
        self.assertNotIn("private sibling evidence", str(plan))

    def test_stale_and_malformed_projections_are_excluded(self):
        stale = ProjectionDescriptor(domain="memory", processor_id="fixture", processor_version="1",
            method="lexical", source_frontier_sha256="new", built_from_frontier_sha256="old")
        current = ProjectionDescriptor(domain="library", processor_id="fixture", processor_version="1",
            method="semantic", model_id="fixture-model", model_version="1",
            source_frontier_sha256="same", built_from_frontier_sha256="same")
        self.assertEqual(current.status, "current")
        self.assertEqual(current.projection_id, current.projection_id)
        plan = UnifiedRetrievalPlanner("fawkes", adapters=(
            adapter("memory", [], projection=stale), adapter("library", [], projection="malformed"),
        )).plan("query")
        self.assertEqual(plan["domain_status"]["memory"]["reason"], "projection_stale")
        self.assertEqual(plan["domain_status"]["library"]["reason"], "projection_malformed")

    def test_inherited_provenance_and_unknown_identity_boundaries_survive(self):
        inherited = candidate("fawkes", "inherited_history", "ih1", "founding evidence",
            "immutable_imported_source_evidence", history_era="inherited_history",
            relationship_provenance="founding_developmental", identity_attribution="unassessed",
            native_boundary_status="boundary_unknown",
            provider_source={"provider": "chatgpt", "original_digest": "abc"}, export_id="export-1")
        provider = adapter("inherited_history", [inherited],
            authority="immutable_imported_source_evidence", automatic_enabled=True,
            required_grants=("history.inherited.auto",))
        plan = UnifiedRetrievalPlanner("fawkes", adapters=(provider,)).plan(
            "founding", grants=("history.inherited.auto",))
        selected = plan["selected_evidence"][0]
        self.assertEqual(selected["history_era"], "inherited_history")
        self.assertEqual(selected["relationship_provenance"], "founding_developmental")
        self.assertEqual(selected["identity_attribution"], "unassessed")
        self.assertEqual(selected["native_boundary_status"], "boundary_unknown")
        self.assertNotEqual(selected["identity_attribution"], "proven_native")

    def test_proven_native_inference_is_rejected(self):
        bad = candidate("fawkes", "inherited_history", "ih1", "bad", "imported",
            history_era="inherited_history", relationship_provenance="founding_developmental",
            identity_attribution="proven_native", native_boundary_status="boundary_unknown",
            provider_source={"provider": "fixture"}, export_id="export-1")
        plan = UnifiedRetrievalPlanner("fawkes", adapters=(adapter(
            "inherited_history", [bad], authority="imported", automatic_enabled=True),)).plan("bad")
        self.assertEqual(plan["selected_evidence"], [])
        self.assertEqual(plan["domain_status"]["inherited_history"]["reason"], "retrieval_degraded")

    def test_contradictions_remain_distinct_and_noisy_domain_cannot_starve_peer(self):
        memory_items = [candidate("fawkes", "memory", f"m{i}", "A" * 40,
                                  "memory_authority", uncertainty="disputed") for i in range(10)]
        archive_items = [candidate("fawkes", "native_archive", "a1", "B" * 40,
                                   "native_archive_authority", contradiction_group_id="claim-1"),
                         candidate("fawkes", "native_archive", "a2", "C" * 40,
                                   "native_archive_authority", contradiction_group_id="claim-1")]
        plan = UnifiedRetrievalPlanner("fawkes", adapters=(adapter("memory", memory_items),
            adapter("native_archive", archive_items))).plan("claim", total_budget_chars=256)
        selected_domains = [item["domain"] for item in plan["selected_evidence"]]
        self.assertIn("memory", selected_domains); self.assertIn("native_archive", selected_domains)
        conflicts = [item for item in plan["selected_evidence"] if item.get("contradiction_group_id") == "claim-1"]
        self.assertEqual([item["evidence_id"] for item in conflicts], ["a1", "a2"])
        self.assertEqual(plan["allocation"]["per_domain_budget"], {"memory": 128, "native_archive": 128})

    def test_planning_has_no_durable_or_identity_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            sentinel = Path(tmp) / "state"; sentinel.write_text("unchanged")
            plan = UnifiedRetrievalPlanner("fawkes", adapters=(adapter("memory", []),)).plan("query")
            self.assertEqual(sentinel.read_text(), "unchanged")
            self.assertFalse(any(plan["side_effects"].values()))
            self.assertEqual(list(Path(tmp).iterdir()), [sentinel])

    def test_plan_is_flight_recorder_and_replay_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = UnifiedRetrievalPlanner("fawkes", adapters=(adapter("memory", [
                candidate("fawkes", "memory", "m1", "evidence", "memory_authority")]),)).plan("evidence")
            trace = {"capability_selection": ["retrieval.plan"],
                     "retrieval_plan": {"policy_version": plan["policy_version"]},
                     "queries": [{"domain": "planner", "text": plan["query"]}],
                     "candidates": plan["candidates"], "exclusions": plan["exclusions"],
                     "context_allocation": plan["allocation"], "warnings": plan["warnings"],
                     "deterministic_replay_inputs": {"sha256": plan["deterministic_replay_input_sha256"]}}
            record_live_flight(instance_id="fawkes", conversation_id="c1", request_message_id="q1",
                response_message_id="r1", response_archive_id="a1", request_text="evidence",
                model="fixture", context_receipt_id="r1", root=tmp,
                result={"text": "answer", "memories": [], "archive_passages": [],
                        "library_passages": [], "conversation_context": [], "retrieval_trace": trace})
            flight = load_flight("fawkes", "r1", root=tmp)
            self.assertEqual(flight["candidates"][0]["candidate_id"],
                             plan["candidates"][0]["candidate_id"])
            self.assertNotIn("text", flight["candidates"][0])
            replay = replay_flight(instance_id="fawkes", flight_id="r1", candidate_id="planner",
                candidate_version="2", root=tmp,
                runner=lambda detached: {"selected_evidence": detached["selected_evidence"]})
            self.assertFalse(replay["ordinary_history_mutated"])


if __name__ == "__main__":
    unittest.main()
