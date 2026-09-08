import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.memory.store as store
from tests.recording_archive_fixtures import LegacyArchiveSources


class FawkesLiveScopedMemoryContextTests(unittest.TestCase):
    def test_live_context_uses_only_memories_owned_by_its_instance(self):
        from src.runtime.chat import FawkesChatRuntime

        class FakeClient:
            pass

        class CapturingRetriever:
            def __init__(self):
                self.candidates = None

            def rank(self, *, query, memories, limit):
                self.candidates = list(memories)
                return self.candidates[:limit]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(store, "MEMORY_RECORDS_DIR", root / "records"), patch.object(
                store, "MEMORY_EVENTS_DIR", root / "events"
            ):
                owned = store.create_memory(
                    "project",
                    "Fawkes uses provenance-aware memory.",
                    instance_id="fawkes",
                    source_message_ids=("message-1",),
                    source_archive_ids=("archive-1",),
                )
                store.create_memory(
                    "project",
                    "Another Phoenix's private project.",
                    instance_id="other",
                )
                runtime = FawkesChatRuntime(
                    client=FakeClient(),
                    model="test-model",
                    instance_id="fawkes",
                )
                retriever = CapturingRetriever()
                runtime.semantic_retriever = retriever
                with patch(
                    "src.runtime.chat.retrieve_archive_passages", return_value=[]
                ):
                    context = runtime.build_context(
                        user_message="What does Fawkes remember?"
                    )

        self.assertEqual(
            [memory["memory_id"] for memory in retriever.candidates],
            [owned.memory_id],
        )
        self.assertEqual(context["memories"][0]["instance_id"], "fawkes")
        self.assertEqual(
            context["memories"][0]["source_archive_ids"], ["archive-1"]
        )


class FawkesLiveRuntimeResilienceTests(unittest.TestCase):
    class FakeResponse:
        output_text = "A durable core response."
        usage = None

    class FakeClient:
        class Responses:
            def create(self, **kwargs):
                return FawkesLiveRuntimeResilienceTests.FakeResponse()

        responses = Responses()

    class FailingComponent:
        def rank(self, **kwargs):
            raise ConnectionError("temporary retrieval outage")

        def evaluate_correction(self, **kwargs):
            raise ConnectionError("temporary correction outage")

    def test_default_model_makes_runtime_startable_without_model_env(self):
        from src.runtime.chat import FawkesChatRuntime

        with patch.dict("os.environ", {}, clear=True):
            runtime = FawkesChatRuntime(client=self.FakeClient())

        self.assertEqual(runtime.model, "gpt-5.6-luna")

    def test_runtime_requires_proactive_but_disciplined_recall(self):
        from src.runtime.chat import FawkesChatRuntime

        captured = {}

        class CapturingClient:
            class Responses:
                def create(self, **kwargs):
                    captured.update(kwargs)
                    return FawkesLiveRuntimeResilienceTests.FakeResponse()

            responses = Responses()

        class EmptyRetriever:
            def rank(self, **kwargs):
                return []

        class NoCorrection:
            def evaluate_correction(self, **kwargs):
                from src.memory.correction import CorrectionAssessment

                return CorrectionAssessment(
                    is_correction=False,
                    confidence=1.0,
                    reasoning="Not a correction.",
                )

        runtime = FawkesChatRuntime(
            client=CapturingClient(), model="test-model", instance_id=None
        )
        runtime.paid_call_guard.require_confirmation = False
        runtime.semantic_retriever = EmptyRetriever()
        runtime.correction_evaluator = NoCorrection()
        runtime.respond(user_message="What should we work on today?")

        system_prompt = captured["input"][0]["content"]
        self.assertIn("proactively using supplied", system_prompt)
        self.assertIn("need to explicitly ask", system_prompt)
        self.assertIn("Current conversational intent takes priority", system_prompt)
        self.assertIn("stale procedures", system_prompt)

    def test_optional_component_failures_do_not_abort_core_response(self):
        from src.runtime.chat import FawkesChatRuntime

        runtime = FawkesChatRuntime(
            client=self.FakeClient(), model="test-model", instance_id=None
        )
        runtime.paid_call_guard.require_confirmation = False
        runtime.semantic_retriever = self.FailingComponent()
        runtime.correction_evaluator = self.FailingComponent()

        with patch("src.runtime.chat.retrieve_memories", return_value=[]):
            result = runtime.respond(
                user_message="Talk with me.", conversation_history=()
            )

        self.assertEqual(result["text"], "A durable core response.")
        self.assertEqual(len(result["warnings"]), 2)
        self.assertIn("lexical fallback", result["warnings"][0])
        self.assertIn("Correction recognition", result["warnings"][1])

    def test_development_failure_does_not_discard_generated_response(self):
        from src.memory.correction import CorrectionAssessment
        from src.runtime.chat import FawkesChatRuntime

        class CorrectionEvaluator:
            def evaluate_correction(self, **kwargs):
                return CorrectionAssessment(
                    is_correction=True,
                    confidence=0.99,
                    reasoning="Explicit correction.",
                )

        class EmptyRetriever:
            def rank(self, **kwargs):
                return []

        runtime = FawkesChatRuntime(
            client=self.FakeClient(), model="test-model", instance_id=None
        )
        runtime.paid_call_guard.require_confirmation = False
        runtime.semantic_retriever = EmptyRetriever()
        runtime.correction_evaluator = CorrectionEvaluator()

        with patch(
            "src.runtime.chat.process_user_correction",
            side_effect=ConnectionError("temporary development outage"),
        ):
            result = runtime.respond(
                user_message="That was wrong.", conversation_history=()
            )

        self.assertEqual(result["text"], "A durable core response.")
        self.assertIn("Development learning failed", result["warnings"][0])

    def test_current_durably_captured_message_is_not_duplicated_as_context(self):
        from src.runtime.chat import FawkesChatRuntime

        class EmptyRetriever:
            def rank(self, **kwargs):
                return []

        runtime = FawkesChatRuntime(
            client=self.FakeClient(), model="test-model", instance_id="fawkes"
        )
        runtime.semantic_retriever = EmptyRetriever()
        conversation = (
            {
                "role": "assistant",
                "content": "Earlier response.",
                "message_id": "message-old",
            },
            {
                "role": "user",
                "content": "Current input.",
                "message_id": "message-current",
            },
        )
        passages = [
            {"message_id": "message-old", "content": "Earlier response."},
            {"message_id": "message-current", "content": "Current input."},
        ]
        with patch(
            "src.runtime.chat.build_archive_context", return_value=conversation
        ), patch(
            "src.runtime.chat.retrieve_archive_passages", return_value=passages
        ):
            context = runtime.build_context(
                conversation_id="conversation-1",
                user_message="Current input.",
                current_message_id="message-current",
            )

        self.assertEqual(
            [message["message_id"] for message in context["conversation"]],
            ["message-old"],
        )
        self.assertEqual(
            [passage["message_id"] for passage in context["archive_passages"]],
            ["message-old"],
        )


class FawkesMemoryRuntimeTests(unittest.TestCase):
    def test_runtime_builds_openai_memory_evaluator(self):
        from src.memory.runtime import build_memory_evaluator

        class FakeProvider:
            def evaluate_memory(self, *, content, conversation_context=()):
                raise AssertionError("Provider should not be called during construction")

        with patch(
            "src.memory.runtime.OpenAISemanticMemoryProvider",
            return_value=FakeProvider(),
        ) as provider_class:
            evaluator = build_memory_evaluator()

        provider_class.assert_called_once()
        self.assertIsNotNone(evaluator)
        self.assertEqual(
            evaluator.provider,
            provider_class.return_value,
        )


if __name__ == "__main__":
    unittest.main()


class FawkesMemoryRuntimeFlowTests(LegacyArchiveSources, unittest.TestCase):
    def test_runtime_processes_conversation_through_memory_pipeline(self):
        from src.memory.runtime import process_memory_conversation

        class FakeEvaluator:
            def evaluate(self, *, content, conversation_context=()):
                from src.memory.semantic import SemanticMemoryAssessment

                return SemanticMemoryAssessment(
                    should_remember=True,
                    memory_type="career_goal",
                    meaning="The user chose networking as their career direction.",
                    confidence=0.99,
                    importance=0.90,
                )

        canonical = (
            {
                "message_id": "message-1",
                "role": "assistant",
                "content": "So networking is the career direction you're choosing?",
            },
            {
                "message_id": "message-2",
                "role": "user",
                "content": "Yeah, that's the one.",
            },
        )

        with patch(
            "src.memory.runtime.build_archive_context",
            return_value=canonical,
        ), patch(
            "src.memory.runtime.extract_memory_candidates",
            return_value=[
                {
                    "candidate_id": "message-2",
                    "content": "Yeah, that's the one.",
                    "source_message_ids": ("message-2",),
                    "source_archive_ids": ("archive-2",),
                }
            ],
        ), tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with patch.object(
                store,
                "MEMORY_RECORDS_DIR",
                root / "records",
            ), patch.object(
                store,
                "MEMORY_EVENTS_DIR",
                root / "events",
            ):
                results = process_memory_conversation(
                    "conversation-1",
                    evaluator=FakeEvaluator(),
                )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].action, "created")


if __name__ == "__main__":
    unittest.main()


class FawkesArchiveContextTests(unittest.TestCase):
    def test_archive_context_returns_canonical_messages_for_model(self):
        from src.memory.archive_context import build_archive_context

        canonical = (
            {
                "message_id": "message-1",
                "role": "assistant",
                "content": "So networking is the career direction you're choosing?",
                "model_slug": "test-model",
                "created_at": "2026-08-29T00:00:00",
                "source_archive_id": "archive-1",
                "revision_count": 1,
            },
            {
                "message_id": "message-2",
                "role": "user",
                "content": "Yeah, that's the one.",
                "model_slug": "test-model",
                "created_at": "2026-08-29T00:01:00",
                "source_archive_id": "archive-2",
                "revision_count": 1,
            },
        )

        with patch(
            "src.memory.archive_context.canonical_messages",
            return_value=canonical,
        ):
            context = build_archive_context("conversation-1")

        self.assertEqual(
            context,
            (
                {
                    "role": "assistant",
                    "content": "So networking is the career direction you're choosing?",
                    "message_id": "message-1",
                    "created_at": "2026-08-29T00:00:00",
                    "source_archive_id": "archive-1",
                    "instance_id": None,
                },
                {
                    "role": "user",
                    "content": "Yeah, that's the one.",
                    "message_id": "message-2",
                    "created_at": "2026-08-29T00:01:00",
                    "source_archive_id": "archive-2",
                    "instance_id": None,
                },
            ),
        )


if __name__ == "__main__":
    unittest.main()


class FawkesRuntimeContractTests(LegacyArchiveSources, unittest.TestCase):
    def test_runtime_returns_memory_results_from_conversation(self):
        from src.memory.runtime import process_memory_conversation
        from src.memory.semantic import SemanticMemoryAssessment

        class FakeEvaluator:
            def evaluate(self, *, content, conversation_context=()):
                self.content = content
                self.context = conversation_context

                return SemanticMemoryAssessment(
                    should_remember=True,
                    memory_type="career_goal",
                    meaning="The user chose networking as their career direction.",
                    confidence=0.99,
                    importance=0.90,
                )

        evaluator = FakeEvaluator()

        canonical = (
            {
                "role": "assistant",
                "content": "So networking is the career direction you're choosing?",
            },
            {
                "role": "user",
                "content": "Yeah, that's the one.",
            },
        )

        candidates = [
            {
                "candidate_id": "message-2",
                "content": "Yeah, that's the one.",
                "source_message_ids": ("message-2",),
                "source_archive_ids": ("archive-2",),
            }
        ]

        with patch(
            "src.memory.runtime.build_archive_context",
            return_value=canonical,
        ), patch(
            "src.memory.runtime.extract_memory_candidates",
            return_value=candidates,
        ), tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with patch.object(
                store,
                "MEMORY_RECORDS_DIR",
                root / "records",
            ), patch.object(
                store,
                "MEMORY_EVENTS_DIR",
                root / "events",
            ):
                results = process_memory_conversation(
                    "conversation-1",
                    evaluator=evaluator,
                )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].action, "created")
        self.assertEqual(
            evaluator.content,
            "Yeah, that's the one.",
        )
        self.assertEqual(
            evaluator.context,
            canonical,
        )


if __name__ == "__main__":
    unittest.main()


class FawkesDevelopmentProposalTests(unittest.TestCase):
    def test_development_proposal_is_explicit_and_non_executable(self):
        from src.memory.development import propose_development

        proposal = propose_development(
            observation="Large conversation context caused an oversized API request.",
            proposed_change="Use candidate-centered context windows.",
            rationale="Relevant local context preserves meaning while reducing request size.",
            confidence=0.95,
        )

        self.assertEqual(
            proposal.category,
            "system_improvement",
        )
        self.assertEqual(
            proposal.proposed_change,
            "Use candidate-centered context windows.",
        )
        self.assertEqual(
            proposal.confidence,
            0.95,
        )


if __name__ == "__main__":
    unittest.main()


class FawkesDevelopmentStoreTests(unittest.TestCase):
    def test_development_proposal_can_be_persisted(self):
        from src.memory.development import propose_development
        from src.memory.development_store import save_development_proposal

        proposal = propose_development(
            observation="Fawkes encountered oversized context.",
            proposed_change="Use bounded candidate-centered context.",
            rationale="Reduce request size while preserving local meaning.",
            confidence=0.95,
        )

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "src.memory.development_store.DEVELOPMENT_DIR",
                Path(tmp),
            ):
                record = save_development_proposal(proposal)

                self.assertEqual(
                    record["status"],
                    "proposed",
                )
                self.assertEqual(
                    record["proposed_change"],
                    "Use bounded candidate-centered context.",
                )

                files = list(Path(tmp).glob("*.json"))
                self.assertEqual(len(files), 1)

                stored = json.loads(
                    files[0].read_text(encoding="utf-8")
                )

                self.assertEqual(
                    stored["proposal_id"],
                    record["proposal_id"],
                )
                self.assertEqual(
                    stored["status"],
                    "proposed",
                )


if __name__ == "__main__":
    unittest.main()


class FawkesDevelopmentProvenanceTests(unittest.TestCase):
    def test_development_proposal_preserves_experience_provenance(self):
        from src.memory.development import propose_development

        proposal = propose_development(
            observation="The archive dry run produced oversized requests.",
            proposed_change="Use bounded candidate-centered context.",
            rationale="The experience demonstrated that full-history context is too large.",
            confidence=0.95,
            source_memory_ids=("memory-123",),
            source_message_ids=("message-456",),
        )

        self.assertEqual(
            proposal.source_memory_ids,
            ("memory-123",),
        )
        self.assertEqual(
            proposal.source_message_ids,
            ("message-456",),
        )


if __name__ == "__main__":
    unittest.main()


class FawkesDevelopmentStoreProvenanceTests(unittest.TestCase):
    def test_saved_development_proposal_preserves_provenance(self):
        from src.memory.development import propose_development
        from src.memory.development_store import save_development_proposal

        proposal = propose_development(
            observation="A context window was too large.",
            proposed_change="Use bounded context.",
            rationale="Reduce model request size.",
            confidence=0.95,
            source_memory_ids=("memory-123",),
            source_message_ids=("message-456",),
        )

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "src.memory.development_store.DEVELOPMENT_DIR",
                Path(tmp),
            ):
                record = save_development_proposal(proposal)

                self.assertEqual(
                    record["source_memory_ids"],
                    ["memory-123"],
                )
                self.assertEqual(
                    record["source_message_ids"],
                    ["message-456"],
                )


if __name__ == "__main__":
    unittest.main()


class FawkesDevelopmentEvaluatorTests(unittest.TestCase):
    def test_development_evaluator_attaches_experience_provenance(self):
        from src.memory.development import propose_development
        from src.memory.development_evaluator import DevelopmentEvaluator

        expected = propose_development(
            observation="Fawkes encountered an oversized request.",
            proposed_change="Use bounded context windows.",
            rationale="Relevant local context is sufficient.",
            confidence=0.95,
        )

        class FakeProvider:
            def evaluate_development(
                self,
                *,
                experience,
                prior_development=(),
            ):
                return expected

        evaluator = DevelopmentEvaluator(FakeProvider())

        result = evaluator.evaluate(
            experience="The full archive exceeded the model request limit.",
            source_memory_ids=("memory-123",),
            source_message_ids=("message-456",),
        )

        self.assertIsNotNone(result)
        self.assertEqual(
            result.proposed_change,
            "Use bounded context windows.",
        )
        self.assertEqual(
            result.source_memory_ids,
            ("memory-123",),
        )
        self.assertEqual(
            result.source_message_ids,
            ("message-456",),
        )


if __name__ == "__main__":
    unittest.main()


class FawkesDevelopmentLoopTests(unittest.TestCase):
    def test_experience_can_become_persisted_development_proposal(self):
        from src.memory.development import propose_development
        from src.memory.development_evaluator import DevelopmentEvaluator
        from src.memory.development_store import save_development_proposal

        class FakeProvider:
            def evaluate_development(
                self,
                *,
                experience,
                prior_development=(),
            ):
                return propose_development(
                    observation="Fawkes encountered an oversized request.",
                    proposed_change="Use bounded candidate-centered context.",
                    rationale="Relevant local context preserves meaning while reducing request size.",
                    confidence=0.95,
                )

        evaluator = DevelopmentEvaluator(FakeProvider())

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "src.memory.development_store.DEVELOPMENT_DIR",
                Path(tmp),
            ):
                proposal = evaluator.evaluate(
                    experience="The full archive exceeded the model request limit.",
                    source_memory_ids=("memory-123",),
                    source_message_ids=("message-456",),
                )

                self.assertIsNotNone(proposal)

                record = save_development_proposal(proposal)

                self.assertEqual(
                    record["status"],
                    "proposed",
                )
                self.assertEqual(
                    record["source_memory_ids"],
                    ["memory-123"],
                )
                self.assertEqual(
                    record["source_message_ids"],
                    ["message-456"],
                )

                files = list(Path(tmp).glob("*.json"))
                self.assertEqual(len(files), 1)


if __name__ == "__main__":
    unittest.main()


class FawkesDevelopmentRetrievalTests(unittest.TestCase):
    def test_development_history_can_be_retrieved_by_experience(self):
        from src.memory.development_retrieval import (
            retrieve_development_proposals,
        )

        with tempfile.TemporaryDirectory() as tmp:
            development_dir = Path(tmp)

            records = [
                {
                    "proposal_id": "proposal-1",
                    "created_at": "2026-08-29T01:00:00+00:00",
                    "category": "system_improvement",
                    "observation": "The archive context was too large.",
                    "proposed_change": "Use bounded candidate-centered context.",
                    "rationale": "Reduce oversized model requests.",
                    "confidence": 0.95,
                    "status": "proposed",
                },
                {
                    "proposal_id": "proposal-2",
                    "created_at": "2026-08-29T02:00:00+00:00",
                    "category": "system_improvement",
                    "observation": "A provider returned invalid data.",
                    "proposed_change": "Validate provider results.",
                    "rationale": "Prevent malformed model output.",
                    "confidence": 0.90,
                    "status": "proposed",
                },
            ]

            for record in records:
                (
                    development_dir
                    / f"{record['proposal_id']}.json"
                ).write_text(
                    json.dumps(record),
                    encoding="utf-8",
                )

            with patch(
                "src.memory.development_retrieval.DEVELOPMENT_DIR",
                development_dir,
            ):
                results = retrieve_development_proposals(
                    "archive context oversized request",
                )

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0]["proposal_id"],
            "proposal-1",
        )


if __name__ == "__main__":
    unittest.main()


class FawkesDevelopmentSimilarityTests(unittest.TestCase):
    def test_development_similarity_provider_is_provider_independent(self):
        from src.memory.development_similarity import DevelopmentSimilarity

        proposals = (
            {
                "proposal_id": "proposal-1",
                "observation": "The archive context was too large.",
            },
            {
                "proposal_id": "proposal-2",
                "observation": "A provider returned invalid data.",
            },
        )

        class FakeProvider:
            def rank_development(self, *, experience, proposals):
                self.experience = experience
                self.proposals = proposals

                return [
                    proposals[0],
                    proposals[1],
                ]

        provider = FakeProvider()
        similarity = DevelopmentSimilarity(provider)

        results = similarity.rank(
            experience="The model is receiving too much history.",
            proposals=proposals,
            limit=1,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0]["proposal_id"],
            "proposal-1",
        )
        self.assertEqual(
            provider.experience,
            "The model is receiving too much history.",
        )


if __name__ == "__main__":
    unittest.main()


class FawkesDevelopmentHistoryTests(unittest.TestCase):
    def test_development_history_retrieval_combines_candidate_search_and_similarity(self):
        from src.memory.development_history import (
            retrieve_relevant_development,
        )

        candidates = [
            {
                "proposal_id": "proposal-1",
                "observation": "Archive context was too large.",
            },
            {
                "proposal_id": "proposal-2",
                "observation": "Provider returned invalid data.",
            },
        ]

        class FakeSimilarity:
            def __init__(self):
                self.experience = None
                self.proposals = None

            def rank(self, *, experience, proposals, limit):
                self.experience = experience
                self.proposals = proposals
                return list(proposals)[:limit]

        similarity = FakeSimilarity()

        with patch(
            "src.memory.development_history.retrieve_development_proposals",
            return_value=candidates,
        ):
            results = retrieve_relevant_development(
                "The model received too much history.",
                similarity=similarity,
                candidate_limit=20,
                result_limit=1,
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0]["proposal_id"],
            "proposal-1",
        )
        self.assertEqual(
            similarity.experience,
            "The model received too much history.",
        )
        self.assertEqual(
            similarity.proposals,
            candidates,
        )


if __name__ == "__main__":
    unittest.main()


class FawkesDevelopmentEvaluatorHistoryTests(unittest.TestCase):
    def test_development_evaluator_receives_prior_development_history(self):
        from src.memory.development import propose_development
        from src.memory.development_evaluator import DevelopmentEvaluator

        prior = (
            {
                "proposal_id": "proposal-1",
                "observation": "Archive context was too large.",
                "proposed_change": "Use bounded context windows.",
            },
        )

        expected = propose_development(
            observation="The current experience resembles a previous context problem.",
            proposed_change="Reuse the existing bounded-context approach.",
            rationale="A related development lesson already exists.",
            confidence=0.97,
        )

        class FakeProvider:
            def __init__(self):
                self.experience = None
                self.prior_development = None

            def evaluate_development(
                self,
                *,
                experience,
                prior_development=(),
            ):
                self.experience = experience
                self.prior_development = prior_development
                return expected

        provider = FakeProvider()
        evaluator = DevelopmentEvaluator(provider)

        result = evaluator.evaluate(
            experience="The model is again receiving too much history.",
            prior_development=prior,
            source_memory_ids=("memory-123",),
            source_message_ids=("message-456",),
        )

        self.assertIsNotNone(result)
        self.assertEqual(
            provider.experience,
            "The model is again receiving too much history.",
        )
        self.assertEqual(
            provider.prior_development,
            prior,
        )
        self.assertEqual(
            result.proposed_change,
            "Reuse the existing bounded-context approach.",
        )


if __name__ == "__main__":
    unittest.main()


class FawkesDevelopmentCycleTests(unittest.TestCase):
    def test_development_cycle_retrieves_history_before_evaluation(self):
        from src.memory.development import propose_development
        from src.memory.development_cycle import run_development_cycle

        prior = [
            {
                "proposal_id": "proposal-1",
                "observation": "Previous context-size problem.",
                "proposed_change": "Use bounded context.",
            },
        ]

        expected = propose_development(
            observation="A new related context problem occurred.",
            proposed_change="Extend bounded context handling.",
            rationale="The previous lesson is relevant but incomplete.",
            confidence=0.96,
        )

        class FakeSimilarity:
            def rank(self, *, experience, proposals, limit):
                return list(proposals)[:limit]

        class FakeEvaluator:
            def __init__(self):
                self.prior_development = None

            def evaluate(
                self,
                *,
                experience,
                prior_development=(),
                source_memory_ids=(),
                source_message_ids=(),
            ):
                self.prior_development = prior_development

                return type(expected)(
                    category=expected.category,
                    observation=expected.observation,
                    proposed_change=expected.proposed_change,
                    rationale=expected.rationale,
                    confidence=expected.confidence,
                    source_memory_ids=tuple(source_memory_ids),
                    source_message_ids=tuple(source_message_ids),
                )

        evaluator = FakeEvaluator()

        with patch(
            "src.memory.development_cycle.retrieve_relevant_development",
            return_value=prior,
        ):
            result = run_development_cycle(
                "The model again received too much history.",
                evaluator=evaluator,
                similarity=FakeSimilarity(),
                source_memory_ids=("memory-123",),
                source_message_ids=("message-456",),
            )

        self.assertEqual(
            result["prior_development"],
            prior,
        )
        self.assertEqual(
            evaluator.prior_development,
            prior,
        )
        self.assertIsNotNone(result["proposal"])
        self.assertEqual(
            result["proposal"].source_memory_ids,
            ("memory-123",),
        )
        self.assertEqual(
            result["proposal"].source_message_ids,
            ("message-456",),
        )


if __name__ == "__main__":
    unittest.main()


class FawkesImportAuditTests(unittest.TestCase):
    def test_import_audit_records_human_reviewable_decision(self):
        from src.memory.import_audit import create_import_audit

        audit = create_import_audit(
            candidate_id="message-123",
            content="Stable personal information about Tanner.",
            memory_type="user_fact",
            tier="A",
            decision="accept",
            confidence=0.94,
            importance=0.88,
            reasoning="Stable personal information with strong evidence.",
            source_message_ids=("message-123",),
            source_archive_ids=("archive-456",),
        )

        self.assertEqual(audit.candidate_id, "message-123")
        self.assertEqual(audit.tier, "A")
        self.assertEqual(audit.decision, "accept")
        self.assertEqual(audit.confidence, 0.94)
        self.assertEqual(audit.importance, 0.88)


if __name__ == "__main__":
    unittest.main()


class FawkesImportPolicyTests(unittest.TestCase):
    def test_core_candidate_becomes_s_tier(self):
        from src.memory.import_policy import classify_import_candidate

        audit = classify_import_candidate(
            candidate_id="message-1",
            content="My stable personal information.",
            memory_type="user_fact",
            confidence=0.96,
            importance=0.95,
            reasoning="Highly stable and important personal information.",
        )

        self.assertEqual(audit.tier, "S")
        self.assertEqual(audit.decision, "accept")

    def test_durable_candidate_becomes_a_tier(self):
        from src.memory.import_policy import classify_import_candidate

        audit = classify_import_candidate(
            candidate_id="message-2",
            content="I prefer this option.",
            memory_type="preference",
            confidence=0.90,
            importance=0.75,
            reasoning="Strong evidence of a durable preference.",
        )

        self.assertEqual(audit.tier, "A")
        self.assertEqual(audit.decision, "accept")

    def test_contextual_candidate_requires_review(self):
        from src.memory.import_policy import classify_import_candidate

        audit = classify_import_candidate(
            candidate_id="message-3",
            content="This was a potentially useful experience.",
            memory_type="experience",
            confidence=0.65,
            importance=0.40,
            reasoning="Potentially useful but not clearly durable.",
        )

        self.assertEqual(audit.tier, "C")
        self.assertEqual(audit.decision, "review")

    def test_low_value_candidate_is_d_tier(self):
        from src.memory.import_policy import classify_import_candidate

        audit = classify_import_candidate(
            candidate_id="message-4",
            content="A temporary conversation detail.",
            memory_type="knowledge",
            confidence=0.40,
            importance=0.20,
            reasoning="Likely ephemeral conversation detail.",
        )

        self.assertEqual(audit.tier, "D")
        self.assertEqual(audit.decision, "reject")

    def test_artifact_is_always_rejected(self):
        from src.memory.import_policy import classify_import_candidate

        audit = classify_import_candidate(
            candidate_id="message-5",
            content="Terminal or UI artifact.",
            memory_type="artifact",
            confidence=0.99,
            importance=0.99,
            reasoning="Terminal or UI artifact.",
        )

        self.assertEqual(audit.tier, "X")
        self.assertEqual(audit.decision, "reject")


if __name__ == "__main__":
    unittest.main()


class FawkesImportAuditProvenanceTests(unittest.TestCase):
    def test_import_audit_preserves_content_type_and_provenance(self):
        from src.memory.import_audit import create_import_audit

        audit = create_import_audit(
            candidate_id="message-789",
            content="You little fawker.",
            memory_type="inside_joke",
            tier="S",
            decision="accept",
            confidence=0.97,
            importance=0.91,
            reasoning="Recurring shared joke with strong relationship evidence.",
            source_message_ids=("message-789", "message-456"),
            source_archive_ids=("archive-123",),
        )

        self.assertEqual(
            audit.content,
            "You little fawker.",
        )
        self.assertEqual(
            audit.memory_type,
            "inside_joke",
        )
        self.assertEqual(
            audit.source_message_ids,
            ("message-789", "message-456"),
        )
        self.assertEqual(
            audit.source_archive_ids,
            ("archive-123",),
        )


if __name__ == "__main__":
    unittest.main()


class FawkesImportAuditProvenanceTests(unittest.TestCase):
    def test_import_audit_preserves_content_type_and_provenance(self):
        from src.memory.import_audit import create_import_audit

        audit = create_import_audit(
            candidate_id="message-789",
            content="You little fawker.",
            memory_type="inside_joke",
            tier="S",
            decision="accept",
            confidence=0.97,
            importance=0.91,
            reasoning="Recurring shared joke with strong relationship evidence.",
            source_message_ids=("message-789", "message-456"),
            source_archive_ids=("archive-123",),
        )

        self.assertEqual(
            audit.content,
            "You little fawker.",
        )
        self.assertEqual(
            audit.memory_type,
            "inside_joke",
        )
        self.assertEqual(
            audit.source_message_ids,
            ("message-789", "message-456"),
        )
        self.assertEqual(
            audit.source_archive_ids,
            ("archive-123",),
        )


if __name__ == "__main__":
    unittest.main()


class FawkesImportPipelineTests(unittest.TestCase):
    def test_candidate_and_assessment_become_a_complete_audit(self):
        from src.memory.import_pipeline import audit_import_candidate
        from src.memory.semantic import SemanticMemoryAssessment

        candidate = {
            "candidate_id": "message-789",
            "content": "You little fawker.",
            "source_message_ids": ("message-789",),
            "source_archive_ids": ("archive-123",),
        }

        assessment = SemanticMemoryAssessment(
            should_remember=True,
            memory_type="inside_joke",
            meaning="A recurring playful way Tanner addresses Fawkes.",
            confidence=0.97,
            importance=0.91,
            reasoning="Recurring shared joke with strong relationship evidence.",
        )

        audit = audit_import_candidate(
            candidate,
            assessment=assessment,
        )

        self.assertEqual(
            audit.candidate_id,
            "message-789",
        )
        self.assertEqual(
            audit.content,
            "You little fawker.",
        )
        self.assertEqual(
            audit.memory_type,
            "inside_joke",
        )
        self.assertEqual(
            audit.tier,
            "S",
        )
        self.assertEqual(
            audit.decision,
            "accept",
        )
        self.assertEqual(
            audit.source_message_ids,
            ("message-789",),
        )
        self.assertEqual(
            audit.source_archive_ids,
            ("archive-123",),
        )


if __name__ == "__main__":
    unittest.main()


class FawkesImportReviewTests(unittest.TestCase):
    def test_import_review_builds_tier_and_decision_summary(self):
        from src.memory.import_review import build_import_review
        from src.memory.semantic import SemanticMemoryAssessment

        candidates = (
            {
                "candidate_id": "message-1",
                "content": "I love this.",
                "source_message_ids": ("message-1",),
                "source_archive_ids": ("archive-1",),
            },
            {
                "candidate_id": "message-2",
                "content": "You little fawker.",
                "source_message_ids": ("message-2",),
                "source_archive_ids": ("archive-1",),
            },
        )

        assessments = (
            SemanticMemoryAssessment(
                should_remember=True,
                memory_type="preference",
                meaning="A durable preference.",
                confidence=0.90,
                importance=0.75,
                reasoning="Strong evidence of a durable preference.",
            ),
            SemanticMemoryAssessment(
                should_remember=True,
                memory_type="inside_joke",
                meaning="A recurring shared joke.",
                confidence=0.97,
                importance=0.91,
                reasoning="Recurring relationship humor.",
            ),
        )

        report = build_import_review(
            candidates,
            assessments,
        )

        self.assertEqual(
            report["tier_counts"]["A"],
            1,
        )
        self.assertEqual(
            report["tier_counts"]["S"],
            1,
        )
        self.assertEqual(
            report["decision_counts"]["accept"],
            2,
        )
        self.assertEqual(
            len(report["audits"]),
            2,
        )


if __name__ == "__main__":
    unittest.main()


class FawkesImportDecisionTests(unittest.TestCase):
    def test_human_can_accept_review_candidate(self):
        from src.memory.import_decision import create_import_decision

        decision = create_import_decision(
            candidate_id="message-123",
            decision="accept",
            note="Fawkes correctly identified this as important.",
        )

        self.assertEqual(
            decision.candidate_id,
            "message-123",
        )
        self.assertEqual(
            decision.decision,
            "accept",
        )
        self.assertEqual(
            decision.reviewer,
            "user",
        )
        self.assertEqual(
            decision.note,
            "Fawkes correctly identified this as important.",
        )

    def test_human_can_reject_review_candidate(self):
        from src.memory.import_decision import create_import_decision

        decision = create_import_decision(
            candidate_id="message-456",
            decision="reject",
            note="Fawkes overestimated the importance.",
        )

        self.assertEqual(
            decision.decision,
            "reject",
        )

    def test_invalid_human_decision_is_rejected(self):
        from src.memory.import_decision import create_import_decision

        with self.assertRaises(ValueError):
            create_import_decision(
                candidate_id="message-789",
                decision="maybe",
            )


if __name__ == "__main__":
    unittest.main()


class FawkesImportManifestTests(unittest.TestCase):
    def test_import_manifest_is_human_reviewable(self):
        from src.memory.import_audit import create_import_audit
        from src.memory.import_manifest import write_import_manifest

        audit = create_import_audit(
            candidate_id="message-123",
            content="You little fawker.",
            memory_type="inside_joke",
            tier="S",
            decision="accept",
            confidence=0.97,
            importance=0.91,
            reasoning="Recurring shared relationship humor.",
            source_message_ids=("message-123",),
            source_archive_ids=("archive-1",),
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "import_manifest.json"

            result = write_import_manifest(
                [audit],
                path,
            )

            self.assertEqual(result, path)
            self.assertTrue(path.exists())

            records = json.loads(
                path.read_text(encoding="utf-8")
            )

        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0]["content"],
            "You little fawker.",
        )
        self.assertEqual(
            records[0]["memory_type"],
            "inside_joke",
        )
        self.assertEqual(
            records[0]["tier"],
            "S",
        )
        self.assertEqual(
            records[0]["source_message_ids"],
            ["message-123"],
        )


if __name__ == "__main__":
    unittest.main()


class FawkesImportBatchTests(unittest.TestCase):
    def test_candidate_batch_is_bounded_and_not_persisted(self):
        from src.memory.import_batch import audit_candidate_batch
        from src.memory.semantic import SemanticMemoryAssessment

        candidates = [
            {
                "candidate_id": f"message-{i}",
                "content": f"Candidate {i}",
                "source_message_ids": (f"message-{i}",),
                "source_archive_ids": ("archive-1",),
                "conversation_context": (),
            }
            for i in range(5)
        ]

        class FakeEvaluator:
            def __init__(self):
                self.calls = []

            def evaluate(
                self,
                *,
                content,
                conversation_context=(),
            ):
                self.calls.append(content)

                return SemanticMemoryAssessment(
                    should_remember=True,
                    memory_type="knowledge",
                    meaning="Useful information.",
                    confidence=0.90,
                    importance=0.75,
                    reasoning="Strong evidence.",
                )

        evaluator = FakeEvaluator()

        audits = audit_candidate_batch(
            candidates,
            evaluator=evaluator,
            limit=2,
        )

        self.assertEqual(
            len(evaluator.calls),
            2,
        )
        self.assertEqual(
            len(audits),
            2,
        )
        self.assertEqual(
            audits[0].candidate_id,
            "message-0",
        )
        self.assertEqual(
            audits[1].candidate_id,
            "message-1",
        )


if __name__ == "__main__":
    unittest.main()


class FawkesImportRouterTests(unittest.TestCase):
    def test_empty_candidate_is_rejected_locally(self):
        from src.memory.import_router import route_import_candidate

        route = route_import_candidate(
            {
                "candidate_id": "message-1",
                "content": "",
            }
        )

        self.assertEqual(route.route, "local_reject")

    def test_tiny_candidate_is_rejected_locally(self):
        from src.memory.import_router import route_import_candidate

        route = route_import_candidate(
            {
                "candidate_id": "message-2",
                "content": "reloaded",
            }
        )

        self.assertEqual(route.route, "local_reject")

    def test_known_artifact_is_rejected_locally(self):
        from src.memory.import_router import route_import_candidate

        route = route_import_candidate(
            {
                "candidate_id": "message-3",
                "content": "A large terminal dump.",
                "is_artifact": True,
            }
        )

        self.assertEqual(route.route, "local_reject")

    def test_meaningful_candidate_can_be_sent_to_model(self):
        from src.memory.import_router import route_import_candidate

        route = route_import_candidate(
            {
                "candidate_id": "message-4",
                "content": "I want Fawkes to remember our running jokes.",
            }
        )

        self.assertEqual(route.route, "model")

    def test_batch_routing_requires_no_provider(self):
        from src.memory.import_router import route_import_batch

        candidates = [
            {
                "candidate_id": "message-1",
                "content": "reloaded",
            },
            {
                "candidate_id": "message-2",
                "content": "I want Fawkes to remember this important decision.",
            },
        ]

        routes = route_import_batch(candidates)

        self.assertEqual(
            routes[0].route,
            "local_reject",
        )
        self.assertEqual(
            routes[1].route,
            "model",
        )


if __name__ == "__main__":
    unittest.main()


class FawkesImportRouterEphemeralTests(unittest.TestCase):
    def test_known_ephemeral_response_is_rejected_locally(self):
        from src.memory.import_router import route_import_candidate

        route = route_import_candidate(
            {
                "candidate_id": "message-10",
                "content": "reloaded",
            }
        )

        self.assertEqual(
            route.route,
            "local_reject",
        )

    def test_ephemeral_matching_is_case_insensitive(self):
        from src.memory.import_router import route_import_candidate

        route = route_import_candidate(
            {
                "candidate_id": "message-11",
                "content": "  RELOADED  ",
            }
        )

        self.assertEqual(
            route.route,
            "local_reject",
        )

    def test_short_but_meaningful_content_still_reaches_model(self):
        from src.memory.import_router import route_import_candidate

        route = route_import_candidate(
            {
                "candidate_id": "message-12",
                "content": "Love it.",
            }
        )

        self.assertEqual(
            route.route,
            "model",
        )

    def test_joke_is_not_rejected_just_for_being_short(self):
        from src.memory.import_router import route_import_candidate

        route = route_import_candidate(
            {
                "candidate_id": "message-13",
                "content": "dingus",
            }
        )

        self.assertEqual(
            route.route,
            "model",
        )


if __name__ == "__main__":
    unittest.main()


class FawkesCostControlTests(unittest.TestCase):
    def test_cost_estimate_records_internal_external_cost(self):
        from src.runtime.cost_control import CostEstimate

        estimate = CostEstimate(
            provider="openai",
            model="test-model",
            estimated_cost=0.012,
            reason="Semantic memory evaluation",
        )

        self.assertEqual(estimate.provider, "openai")
        self.assertEqual(estimate.model, "test-model")
        self.assertEqual(estimate.estimated_cost, 0.012)

    def test_budget_allows_operation_within_limit(self):
        from src.runtime.cost_control import CostBudget, CostEstimate

        budget = CostBudget(limit=1.00)

        estimate = CostEstimate(
            provider="openai",
            model="test-model",
            estimated_cost=0.25,
            reason="Memory evaluation",
        )

        self.assertTrue(budget.can_afford(estimate))

        updated = budget.record(estimate)

        self.assertEqual(updated.spent, 0.25)
        self.assertEqual(updated.remaining, 0.75)

    def test_budget_blocks_operation_over_limit(self):
        from src.runtime.cost_control import CostBudget, CostEstimate

        budget = CostBudget(
            limit=1.00,
            spent=0.90,
        )

        estimate = CostEstimate(
            provider="openai",
            model="test-model",
            estimated_cost=0.25,
            reason="Expensive developmental reasoning",
        )

        self.assertFalse(budget.can_afford(estimate))

        with self.assertRaises(RuntimeError):
            budget.record(estimate)


if __name__ == "__main__":
    unittest.main()


class FawkesDeveloperReviewTests(unittest.TestCase):
    def test_review_item_preserves_original_reference(self):
        from src.memory.dev_review import (
            create_developer_review_item,
        )

        item = create_developer_review_item(
            candidate_id="message-123",
            reason="Fawkes classified this as uncertain and believes developer review is useful.",
            source="historical_import",
            original_reference="memory/import_manifest.json#message-123",
            content="Potentially important historical detail.",
            memory_type="experience",
            tier="C",
            confidence=0.62,
            importance=0.48,
        )

        self.assertEqual(
            item.candidate_id,
            "message-123",
        )
        self.assertEqual(
            item.original_reference,
            "memory/import_manifest.json#message-123",
        )
        self.assertEqual(
            item.tier,
            "C",
        )
        self.assertEqual(
            item.confidence,
            0.62,
        )

    def test_developer_review_item_can_be_persisted(self):
        from src.memory.dev_review import (
            create_developer_review_item,
            save_developer_review_item,
        )

        item = create_developer_review_item(
            candidate_id="message-456",
            reason="Potentially incorrect classification.",
            source="historical_import",
            original_reference="memory/import_manifest.json#message-456",
            content="Something Fawkes needs a human to inspect.",
            memory_type="inside_joke",
            tier="C",
            confidence=0.68,
            importance=0.55,
        )

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "src.memory.dev_review.DEV_REVIEW_DIR",
                Path(tmp),
            ):
                path = save_developer_review_item(item)

                self.assertTrue(path.exists())

                stored = json.loads(
                    path.read_text(encoding="utf-8")
                )

        self.assertEqual(
            stored["candidate_id"],
            "message-456",
        )
        self.assertEqual(
            stored["original_reference"],
            "memory/import_manifest.json#message-456",
        )
        self.assertEqual(
            stored["status"],
            "needs_review",
        )


if __name__ == "__main__":
    unittest.main()


class FawkesDeveloperReviewRoutingTests(unittest.TestCase):
    def test_only_review_decisions_enter_developer_review(self):
        from src.memory.dev_review import create_developer_review_item
        from src.memory.import_review import build_import_review
        from src.memory.semantic import SemanticMemoryAssessment

        candidates = (
            {
                "candidate_id": "message-accept",
                "content": "A durable important preference.",
            },
            {
                "candidate_id": "message-review",
                "content": "A potentially meaningful but uncertain detail.",
            },
            {
                "candidate_id": "message-reject",
                "content": "Temporary conversation noise.",
            },
        )

        assessments = (
            SemanticMemoryAssessment(
                should_remember=True,
                memory_type="preference",
                meaning="Durable preference.",
                confidence=0.95,
                importance=0.95,
                reasoning="Strong durable evidence.",
            ),
            SemanticMemoryAssessment(
                should_remember=True,
                memory_type="experience",
                meaning="Potentially useful experience.",
                confidence=0.65,
                importance=0.40,
                reasoning="Useful but uncertain.",
            ),
            SemanticMemoryAssessment(
                should_remember=False,
                memory_type="knowledge",
                meaning=None,
                confidence=0.30,
                importance=0.10,
                reasoning="Ephemeral conversation detail.",
            ),
        )

        report = build_import_review(
            candidates,
            assessments,
        )

        review_items = [
            create_developer_review_item(
                candidate_id=audit.candidate_id,
                reason=audit.reasoning,
                source="historical_import",
                original_reference=(
                    f"memory/import_manifest.json#{audit.candidate_id}"
                ),
                content=audit.content,
                memory_type=audit.memory_type,
                tier=audit.tier,
                confidence=audit.confidence,
                importance=audit.importance,
            )
            for audit in report["review_queue"]
        ]

        self.assertEqual(
            len(review_items),
            1,
        )
        self.assertEqual(
            review_items[0].candidate_id,
            "message-review",
        )
        self.assertEqual(
            review_items[0].tier,
            "C",
        )


if __name__ == "__main__":
    unittest.main()


class FawkesDeveloperReviewInboxTests(unittest.TestCase):
    def test_developer_review_inbox_can_list_pending_items(self):
        from src.memory.dev_review import (
            create_developer_review_item,
            list_developer_review_items,
            save_developer_review_item,
        )

        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)

            item = create_developer_review_item(
                candidate_id="message-123",
                reason="Fawkes is uncertain about this classification.",
                source="historical_import",
                original_reference="memory/import_manifest.json#message-123",
                content="Potentially meaningful historical detail.",
                memory_type="experience",
                tier="C",
                confidence=0.64,
                importance=0.42,
            )

            with patch(
                "src.memory.dev_review.DEV_REVIEW_DIR",
                review_dir,
            ):
                save_developer_review_item(item)

                results = list_developer_review_items()

        self.assertEqual(len(results), 1)
        self.assertEqual(
            results[0]["candidate_id"],
            "message-123",
        )
        self.assertEqual(
            results[0]["status"],
            "needs_review",
        )
        self.assertEqual(
            results[0]["original_reference"],
            "memory/import_manifest.json#message-123",
        )


if __name__ == "__main__":
    unittest.main()


class FawkesDeveloperReviewDecisionApplicationTests(unittest.TestCase):
    def test_human_decision_is_recorded_without_destroying_original_audit(self):
        from src.memory.dev_review import (
            apply_developer_review_decision,
            create_developer_review_item,
            save_developer_review_item,
        )

        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)

            item = create_developer_review_item(
                candidate_id="message-123",
                reason="Fawkes is uncertain about this classification.",
                source="historical_import",
                original_reference="memory/import_manifest.json#message-123",
                content="Potentially meaningful historical detail.",
                memory_type="experience",
                tier="C",
                confidence=0.64,
                importance=0.42,
            )

            with patch(
                "src.memory.dev_review.DEV_REVIEW_DIR",
                review_dir,
            ):
                save_developer_review_item(item)

                result = apply_developer_review_decision(
                    item.review_id,
                    decision="accept",
                    reviewer="user",
                    note="Confirmed this belongs in durable memory.",
                )

                stored = json.loads(
                    (
                        review_dir
                        / f"{item.review_id}.json"
                    ).read_text(
                        encoding="utf-8"
                    )
                )

        self.assertEqual(
            result["candidate_id"],
            "message-123",
        )
        self.assertEqual(
            result["content"],
            "Potentially meaningful historical detail.",
        )
        self.assertEqual(
            result["memory_type"],
            "experience",
        )
        self.assertEqual(
            result["tier"],
            "C",
        )
        self.assertEqual(
            result["status"],
            "reviewed",
        )
        self.assertEqual(
            result["human_decision"],
            "accept",
        )
        self.assertEqual(
            result["reviewer"],
            "user",
        )
        self.assertEqual(
            result["review_note"],
            "Confirmed this belongs in durable memory.",
        )
        self.assertIn(
            "reviewed_at",
            result,
        )

        # The original Fawkes assessment remains intact.
        self.assertEqual(
            stored["confidence"],
            0.64,
        )
        self.assertEqual(
            stored["importance"],
            0.42,
        )
        self.assertEqual(
            stored["reason"],
            "Fawkes is uncertain about this classification.",
        )

    def test_reviewed_item_cannot_be_decided_twice(self):
        from src.memory.dev_review import (
            apply_developer_review_decision,
            create_developer_review_item,
            save_developer_review_item,
        )

        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp)

            item = create_developer_review_item(
                candidate_id="message-456",
                reason="Needs human inspection.",
                source="historical_import",
                original_reference="memory/import_manifest.json#message-456",
                content="Review this.",
                memory_type="experience",
                tier="C",
                confidence=0.60,
                importance=0.40,
            )

            with patch(
                "src.memory.dev_review.DEV_REVIEW_DIR",
                review_dir,
            ):
                save_developer_review_item(item)

                apply_developer_review_decision(
                    item.review_id,
                    decision="reject",
                )

                with self.assertRaises(ValueError):
                    apply_developer_review_decision(
                        item.review_id,
                        decision="accept",
                    )


if __name__ == "__main__":
    unittest.main()


class FawkesReviewFeedbackTests(unittest.TestCase):
    def test_human_correction_becomes_learning_signal(self):
        from src.memory.review_feedback import record_review_feedback

        review_record = {
            "review_id": "review-123",
            "candidate_id": "message-123",
            "decision": "review",
            "tier": "C",
            "confidence": 0.64,
            "importance": 0.42,
        }

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "src.memory.review_feedback.FEEDBACK_DIR",
                Path(tmp),
            ):
                feedback = record_review_feedback(
                    review_record,
                    human_decision="accept",
                    reviewer="user",
                    note="This was actually important and should be remembered.",
                )

                files = list(Path(tmp).glob("*.json"))
                self.assertEqual(len(files), 1)

                stored = json.loads(
                    files[0].read_text(
                        encoding="utf-8"
                    )
                )

        self.assertEqual(
            feedback["review_id"],
            "review-123",
        )
        self.assertEqual(
            feedback["candidate_id"],
            "message-123",
        )
        self.assertEqual(
            feedback["fawkes_decision"],
            "review",
        )
        self.assertEqual(
            feedback["fawkes_tier"],
            "C",
        )
        self.assertEqual(
            feedback["fawkes_confidence"],
            0.64,
        )
        self.assertEqual(
            feedback["human_decision"],
            "accept",
        )
        self.assertEqual(
            feedback["note"],
            "This was actually important and should be remembered.",
        )
        self.assertEqual(
            stored["human_decision"],
            "accept",
        )

    def test_invalid_feedback_decision_is_rejected(self):
        from src.memory.review_feedback import record_review_feedback

        with self.assertRaises(ValueError):
            record_review_feedback(
                {
                    "review_id": "review-456",
                    "candidate_id": "message-456",
                },
                human_decision="maybe",
            )


if __name__ == "__main__":
    unittest.main()


class FawkesDeveloperReviewFeedbackIntegrationTests(unittest.TestCase):
    def test_review_decision_automatically_creates_feedback(self):
        from src.memory.dev_review import (
            apply_developer_review_decision,
            create_developer_review_item,
            save_developer_review_item,
        )

        with tempfile.TemporaryDirectory() as tmp:
            review_dir = Path(tmp) / "review"
            feedback_dir = Path(tmp) / "feedback"

            item = create_developer_review_item(
                candidate_id="message-999",
                reason="Fawkes is uncertain.",
                source="historical_import",
                original_reference="memory/import_manifest.json#message-999",
                content="Potentially important detail.",
                memory_type="experience",
                tier="C",
                confidence=0.61,
                importance=0.44,
            )

            with patch(
                "src.memory.dev_review.DEV_REVIEW_DIR",
                review_dir,
            ), patch(
                "src.memory.review_feedback.FEEDBACK_DIR",
                feedback_dir,
            ):
                save_developer_review_item(item)

                result = apply_developer_review_decision(
                    item.review_id,
                    decision="accept",
                    reviewer="user",
                    note="Confirmed as important.",
                )

                feedback_files = list(
                    feedback_dir.glob("*.json")
                )

                self.assertEqual(
                    len(feedback_files),
                    1,
                )

                feedback = json.loads(
                    feedback_files[0].read_text(
                        encoding="utf-8"
                    )
                )

        self.assertEqual(
            result["human_decision"],
            "accept",
        )
        self.assertEqual(
            feedback["review_id"],
            item.review_id,
        )
        self.assertEqual(
            feedback["candidate_id"],
            "message-999",
        )
        self.assertEqual(
            feedback["human_decision"],
            "accept",
        )
        self.assertEqual(
            feedback["note"],
            "Confirmed as important.",
        )


if __name__ == "__main__":
    unittest.main()


class FawkesImportCalibrationTests(unittest.TestCase):
    def test_calibration_report_measures_human_outcomes(self):
        from src.memory.import_calibration import (
            build_import_calibration_report,
        )

        records = [
            {
                "feedback_id": "feedback-1",
                "review_id": "review-1",
                "candidate_id": "message-1",
                "fawkes_decision": "review",
                "fawkes_tier": "C",
                "fawkes_confidence": 0.64,
                "fawkes_importance": 0.42,
                "human_decision": "accept",
                "memory_type": "experience",
            },
            {
                "feedback_id": "feedback-2",
                "review_id": "review-2",
                "candidate_id": "message-2",
                "fawkes_decision": "review",
                "fawkes_tier": "C",
                "fawkes_confidence": 0.68,
                "fawkes_importance": 0.55,
                "human_decision": "reject",
                "memory_type": "experience",
            },
            {
                "feedback_id": "feedback-3",
                "review_id": "review-3",
                "candidate_id": "message-3",
                "fawkes_decision": "review",
                "fawkes_tier": "B",
                "fawkes_confidence": 0.80,
                "fawkes_importance": 0.60,
                "human_decision": "accept",
                "memory_type": "preference",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            feedback_dir = Path(tmp)

            for record in records:
                (
                    feedback_dir
                    / f"{record['feedback_id']}.json"
                ).write_text(
                    json.dumps(record),
                    encoding="utf-8",
                )

            report = build_import_calibration_report(
                feedback_dir=feedback_dir,
            )

        self.assertEqual(
            report["total_reviewed"],
            3,
        )
        self.assertEqual(
            report["accepted"],
            2,
        )
        self.assertEqual(
            report["rejected"],
            1,
        )
        self.assertAlmostEqual(
            report["acceptance_rate"],
            2 / 3,
        )
        self.assertEqual(
            report["tier_counts"]["C"],
            2,
        )
        self.assertEqual(
            report["tier_counts"]["B"],
            1,
        )
        self.assertEqual(
            report["tier_outcomes"]["C"]["accepted"],
            1,
        )
        self.assertEqual(
            report["tier_outcomes"]["C"]["rejected"],
            1,
        )
        self.assertEqual(
            report["memory_type_outcomes"]["experience"]["reviewed"],
            2,
        )

    def test_empty_calibration_directory_is_safe(self):
        from src.memory.import_calibration import (
            build_import_calibration_report,
        )

        with tempfile.TemporaryDirectory() as tmp:
            report = build_import_calibration_report(
                feedback_dir=Path(tmp),
            )

        self.assertEqual(
            report["total_reviewed"],
            0,
        )
        self.assertEqual(
            report["acceptance_rate"],
            0.0,
        )


if __name__ == "__main__":
    unittest.main()


class FawkesImportDryRunTests(unittest.TestCase):
    def test_dry_run_estimates_external_cost_without_calling_provider(self):
        from src.memory.import_dry_run import build_import_dry_run
        from src.memory.import_router import ImportRoute

        routes = (
            ImportRoute(
                candidate_id="message-1",
                route="model",
                reason="semantic judgment required",
            ),
            ImportRoute(
                candidate_id="message-2",
                route="model",
                reason="semantic judgment required",
            ),
            ImportRoute(
                candidate_id="message-3",
                route="local_reject",
                reason="known ephemeral interaction artifact",
            ),
        )

        result = build_import_dry_run(
            routes=routes,
            estimated_cost_per_candidate=0.012,
        )

        self.assertEqual(
            result.total_candidates,
            3,
        )
        self.assertEqual(
            result.local_rejected,
            1,
        )
        self.assertEqual(
            result.model_candidates,
            2,
        )
        self.assertAlmostEqual(
            result.estimated_cost,
            0.024,
        )
        self.assertTrue(
            result.paid_provider_required,
        )
        self.assertIn(
            "PAID PROVIDER REQUIRED",
            result.warning,
        )

    def test_zero_cost_dry_run_does_not_claim_paid_provider_usage(self):
        from src.memory.import_dry_run import build_import_dry_run

        result = build_import_dry_run(
            routes=[],
            estimated_cost_per_candidate=0.012,
        )

        self.assertEqual(
            result.total_candidates,
            0,
        )
        self.assertEqual(
            result.model_candidates,
            0,
        )
        self.assertEqual(
            result.estimated_cost,
            0.0,
        )
        self.assertFalse(
            result.paid_provider_required,
        )
        self.assertIn(
            "NO PAID PROVIDER REQUIRED",
            result.warning,
        )


if __name__ == "__main__":
    unittest.main()


class FawkesPaidCallGuardTests(unittest.TestCase):
    def test_paid_call_is_estimated_before_authorization(self):
        from src.runtime.paid_call import PaidCallGuard

        messages = []

        guard = PaidCallGuard(
            cost_per_call=0.012,
            notifier=messages.append,
        )

        with self.assertRaises(PermissionError):
            guard.authorize(
                model="test-model",
                reason="chat response",
            )

        self.assertEqual(len(messages), 1)
        self.assertIn(
            "PAID PROVIDER CALL",
            messages[0],
        )
        self.assertIn(
            "$0.0120",
            messages[0],
        )

    def test_free_call_does_not_require_confirmation(self):
        from src.runtime.paid_call import PaidCallGuard

        guard = PaidCallGuard(
            cost_per_call=0.0,
        )

        estimate = guard.authorize(
            model="local-test-model",
            reason="local inference",
        )

        self.assertEqual(
            estimate.estimated_cost,
            0.0,
        )


if __name__ == "__main__":
    unittest.main()


class FawkesChatPaidGuardIntegrationTests(unittest.TestCase):
    def test_chat_runtime_checks_paid_guard_before_api_call(self):
        from src.runtime.chat import FawkesChatRuntime
        from src.runtime.paid_call import PaidCallGuard

        messages = []

        class FakeClient:
            def __init__(self):
                self.called = False

            class Responses:
                def __init__(self, outer):
                    self.outer = outer

                def create(self, **kwargs):
                    self.outer.called = True
                    raise AssertionError(
                        "API call should not happen before authorization"
                    )

            @property
            def responses(self):
                return self.Responses(self)

        client = FakeClient()

        runtime = FawkesChatRuntime(
            client=client,
            model="test-model",
        )

        runtime.paid_call_guard = PaidCallGuard(
            cost_per_call=0.012,
            notifier=messages.append,
        )

        with self.assertRaises(PermissionError):
            runtime.respond(
                user_message="Hello Fawkes.",
            )

        self.assertFalse(client.called)
        self.assertEqual(len(messages), 1)
        self.assertIn(
            "PAID PROVIDER CALL",
            messages[0],
        )


if __name__ == "__main__":
    unittest.main()


class FawkesMemoryExactDuplicateProtectionTests(unittest.TestCase):
    def test_exact_duplicate_is_strengthened_instead_of_created(self):
        from src.memory.consolidate import consolidate_assessment
        from src.memory.semantic import SemanticMemoryAssessment

        existing = {
            "memory_id": "memory-existing",
            "memory_type": "career_goal",
            "content": "The user chose networking as their career direction.",
            "status": "active",
            "confidence": 0.80,
        }

        assessment = SemanticMemoryAssessment(
            should_remember=True,
            memory_type="career_goal",
            meaning="The user chose networking as their career direction.",
            confidence=0.90,
            importance=0.80,
            reasoning="Exact duplicate evidence.",
        )

        with patch(
            "src.memory.consolidate.strengthen_memory"
        ) as strengthen:
            result = consolidate_assessment(
                assessment,
                existing_memories=(existing,),
            )

        self.assertEqual(
            result.action,
            "duplicate_strengthened",
        )
        self.assertEqual(
            result.memory_id,
            "memory-existing",
        )
        strengthen.assert_called_once()


if __name__ == "__main__":
    unittest.main()


class FawkesDevelopmentRuntimeTests(unittest.TestCase):
    def test_development_experience_becomes_persisted_proposal(self):
        from pathlib import Path
        from unittest.mock import patch

        from src.memory.development import propose_development
        from src.memory.development_runtime import (
            process_development_experience,
        )

        expected = propose_development(
            observation="Fawkes handled the user's correction incorrectly.",
            proposed_change="Route explicit user corrections into the development workbench.",
            rationale="Corrections are actionable development signals and should await human approval.",
            confidence=0.97,
            source_memory_ids=("memory-123",),
            source_message_ids=("message-456",),
        )

        class FakeEvaluator:
            def evaluate(
                self,
                *,
                experience,
                prior_development=(),
                source_memory_ids=(),
                source_message_ids=(),
            ):
                return expected

        class FakeSimilarity:
            def rank(self, *, experience, proposals, limit):
                return list(proposals)[:limit]

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "src.memory.development_store.DEVELOPMENT_DIR",
                Path(tmp),
            ), patch(
                "src.memory.development_runtime.save_development_proposal",
                side_effect=lambda proposal: {
                    "proposal_id": "proposal-123",
                    "status": "proposed",
                    "proposed_change": proposal.proposed_change,
                    "source_memory_ids": list(
                        proposal.source_memory_ids
                    ),
                    "source_message_ids": list(
                        proposal.source_message_ids
                    ),
                },
            ):
                result = process_development_experience(
                    "You are doing this wrong. Fix it.",
                    evaluator=FakeEvaluator(),
                    similarity=FakeSimilarity(),
                    source_memory_ids=("memory-123",),
                    source_message_ids=("message-456",),
                )

        self.assertIsNotNone(result["proposal"])
        self.assertIsNotNone(result["record"])
        self.assertEqual(
            result["record"]["status"],
            "proposed",
        )
        self.assertEqual(
            result["record"]["source_memory_ids"],
            ["memory-123"],
        )
        self.assertEqual(
            result["record"]["source_message_ids"],
            ["message-456"],
        )
        self.assertEqual(
            result["record"]["proposed_change"],
            "Route explicit user corrections into the development workbench.",
        )

    def test_empty_development_experience_is_rejected(self):
        from src.memory.development_runtime import (
            process_development_experience,
        )

        with self.assertRaises(ValueError):
            process_development_experience(
                "   ",
                evaluator=None,
                similarity=None,
            )


if __name__ == "__main__":
    unittest.main()


class FawkesUserCorrectionDevelopmentTests(LegacyArchiveSources, unittest.TestCase):
    def test_user_correction_preserves_context_and_creates_proposal(self):
        from src.memory.development import propose_development
        from src.memory.development_runtime import (
            process_user_correction,
        )

        captured = {}

        expected = propose_development(
            observation="Fawkes gave an inferior answer instead of addressing the request.",
            proposed_change="Answer the user's actual request directly while preserving safety boundaries.",
            rationale="Avoiding a difficult request by substituting an unrelated answer degrades usefulness.",
            confidence=0.98,
            source_memory_ids=("memory-1",),
            source_message_ids=("message-2",),
        )

        class FakeEvaluator:
            def evaluate(
                self,
                *,
                experience,
                prior_development=(),
                source_memory_ids=(),
                source_message_ids=(),
            ):
                captured["experience"] = experience
                captured["source_memory_ids"] = source_memory_ids
                captured["source_message_ids"] = source_message_ids
                return expected

        class FakeSimilarity:
            def rank(self, *, experience, proposals, limit):
                return list(proposals)[:limit]

        with patch(
            "src.memory.development_runtime.save_development_proposal",
            return_value={
                "proposal_id": "proposal-1",
                "status": "proposed",
            },
        ):
            result = process_user_correction(
                "You're doing this wrong. Answer what I'm actually asking.",
                evaluator=FakeEvaluator(),
                similarity=FakeSimilarity(),
                conversation_context=(
                    {
                        "role": "user",
                        "content": "Answer what I'm actually asking.",
                    },
                    {
                        "role": "assistant",
                        "content": "I can't help with that, but here's something else.",
                    },
                ),
                source_memory_ids=("memory-1",),
                source_message_ids=("message-2",),
            )

        self.assertIn(
            "User correction:",
            captured["experience"],
        )
        self.assertIn(
            "Conversation context:",
            captured["experience"],
        )
        self.assertIn(
            "Answer what I'm actually asking.",
            captured["experience"],
        )
        self.assertEqual(
            captured["source_memory_ids"],
            ("memory-1",),
        )
        self.assertEqual(
            captured["source_message_ids"],
            ("message-2",),
        )
        self.assertEqual(
            result["record"]["status"],
            "proposed",
        )


if __name__ == "__main__":
    unittest.main()


class FawkesCorrectionRecognitionTests(unittest.TestCase):
    def test_explicit_correction_is_recognized(self):
        from src.memory.correction import (
            CorrectionAssessment,
            evaluate_correction,
        )

        class FakeEvaluator:
            def evaluate_correction(
                self,
                *,
                user_message,
                conversation_context=(),
            ):
                self.user_message = user_message
                self.context = conversation_context

                return CorrectionAssessment(
                    is_correction=True,
                    confidence=0.98,
                    reasoning="The user explicitly says Fawkes is doing something wrong and tells him to fix it.",
                )

        evaluator = FakeEvaluator()

        result = evaluate_correction(
            evaluator,
            user_message="Fawkes, you're doing this wrong. Fix it.",
            conversation_context=(
                {
                    "role": "assistant",
                    "content": "An answer that did not satisfy the user.",
                },
            ),
        )

        self.assertTrue(result.is_correction)
        self.assertEqual(result.confidence, 0.98)
        self.assertIn("doing something wrong", result.reasoning)
        self.assertEqual(
            evaluator.user_message,
            "Fawkes, you're doing this wrong. Fix it.",
        )
        self.assertEqual(
            len(evaluator.context),
            1,
        )

    def test_normal_question_can_be_not_a_correction(self):
        from src.memory.correction import (
            CorrectionAssessment,
            evaluate_correction,
        )

        class FakeEvaluator:
            def evaluate_correction(
                self,
                *,
                user_message,
                conversation_context=(),
            ):
                return CorrectionAssessment(
                    is_correction=False,
                    confidence=0.97,
                    reasoning="The user is asking for information, not correcting Fawkes.",
                )

        result = evaluate_correction(
            FakeEvaluator(),
            user_message="How does DNS work?",
            conversation_context=(),
        )

        self.assertFalse(result.is_correction)
        self.assertGreaterEqual(result.confidence, 0.90)

    def test_invalid_correction_result_is_rejected(self):
        from src.memory.correction import evaluate_correction

        class FakeEvaluator:
            def evaluate_correction(
                self,
                *,
                user_message,
                conversation_context=(),
            ):
                return {
                    "is_correction": True,
                }

        with self.assertRaises(TypeError):
            evaluate_correction(
                FakeEvaluator(),
                user_message="Fix that.",
            )

    def test_invalid_confidence_is_rejected(self):
        from src.memory.correction import (
            CorrectionAssessment,
            evaluate_correction,
        )

        class FakeEvaluator:
            def evaluate_correction(
                self,
                *,
                user_message,
                conversation_context=(),
            ):
                return CorrectionAssessment(
                    is_correction=True,
                    confidence=1.5,
                )

        with self.assertRaises(ValueError):
            evaluate_correction(
                FakeEvaluator(),
                user_message="You're doing that wrong.",
            )


if __name__ == "__main__":
    unittest.main()


class FawkesChatCorrectionIntegrationTests(unittest.TestCase):
    def test_chat_response_can_trigger_development_proposal_from_correction(self):
        from src.runtime.chat import FawkesChatRuntime
        from src.runtime.paid_call import PaidCallGuard
        from src.memory.correction import CorrectionAssessment

        calls = []

        class FakeResponse:
            output_text = "You're right. I'll correct that."

        class FakeResponses:
            def create(self, **kwargs):
                calls.append(kwargs)
                return FakeResponse()

        class FakeClient:
            def __init__(self):
                self.responses = FakeResponses()

        class FakeCorrectionEvaluator:
            def evaluate_correction(
                self,
                *,
                user_message,
                conversation_context=(),
            ):
                return CorrectionAssessment(
                    is_correction=True,
                    confidence=0.99,
                    reasoning="The user explicitly corrected Fawkes.",
                )

        class FakeSimilarity:
            def rank(self, *, experience, proposals, limit):
                return list(proposals)[:limit]

        class FakeDevelopmentEvaluator:
            def evaluate(
                self,
                *,
                experience,
                prior_development=(),
                source_memory_ids=(),
                source_message_ids=(),
            ):
                from src.memory.development import propose_development

                return propose_development(
                    observation="Fawkes made a behavior the user explicitly corrected.",
                    proposed_change="Improve the behavior identified by the correction.",
                    rationale="Direct user corrections are evidence for development.",
                    confidence=0.99,
                    source_message_ids=source_message_ids,
                )

        runtime = FawkesChatRuntime(
            client=FakeClient(),
            model="test-model",
        )

        runtime.paid_call_guard = PaidCallGuard(
            cost_per_call=0.0,
        )

        class FakeSemanticRetriever:
            def rank(self, *, query, memories, limit):
                return list(memories)[:limit]

        runtime.semantic_retriever = FakeSemanticRetriever()
        runtime.correction_evaluator = FakeCorrectionEvaluator()
        runtime.development_evaluator = FakeDevelopmentEvaluator()
        runtime.development_similarity = FakeSimilarity()

        with patch(
            "src.runtime.chat.process_user_correction",
            return_value={
                "proposal": object(),
                "record": {
                    "proposal_id": "proposal-123",
                    "status": "proposed",
                },
            },
        ) as process_correction:
            result = runtime.respond(
                user_message="You're doing this wrong. Fix it.",
                conversation_history=(
                    {
                        "role": "assistant",
                        "content": "An incorrect response.",
                    },
                ),
            )

        self.assertEqual(
            result["text"],
            "You're right. I'll correct that.",
        )

        process_correction.assert_called_once()

        self.assertEqual(
            process_correction.call_args.kwargs["correction"],
            "You're doing this wrong. Fix it.",
        )

        self.assertEqual(
            len(calls),
            1,
        )


if __name__ == "__main__":
    unittest.main()


class FawkesWholeTurnPaidGuardTests(unittest.TestCase):
    def test_estimate_can_cover_multiple_provider_calls(self):
        from src.runtime.paid_call import PaidCallGuard

        guard = PaidCallGuard(
            cost_per_call=0.012,
        )

        estimate = guard.estimate(
            model="test-model",
            reason="complete Fawkes turn",
            estimated_calls=4,
        )

        self.assertEqual(
            estimate.estimated_calls,
            4,
        )
        self.assertEqual(
            estimate.estimated_cost,
            0.048,
        )

    def test_negative_or_zero_call_count_is_rejected(self):
        from src.runtime.paid_call import PaidCallGuard

        guard = PaidCallGuard(
            cost_per_call=0.012,
        )

        with self.assertRaises(ValueError):
            guard.estimate(
                model="test-model",
                reason="invalid",
                estimated_calls=0,
            )

    def test_chat_authorizes_whole_turn_once(self):
        from src.runtime.paid_call import PaidCallGuard

        messages = []

        guard = PaidCallGuard(
            cost_per_call=0.012,
            notifier=messages.append,
            require_confirmation=False,
        )

        estimate = guard.authorize(
            model="test-model",
            reason="complete conversational turn",
            estimated_calls=4,
        )

        self.assertEqual(
            estimate.estimated_calls,
            4,
        )
        self.assertEqual(
            estimate.estimated_cost,
            0.048,
        )
        self.assertEqual(
            len(messages),
            1,
        )
        self.assertIn(
            "up to 4 provider call(s)",
            messages[0],
        )


if __name__ == "__main__":
    unittest.main()


class FawkesConversationPersistenceTests(unittest.TestCase):
    def test_latest_conversation_can_be_recovered(self):
        from src.conversations import (
            create_conversation,
            get_latest_conversation,
        )

        with tempfile.TemporaryDirectory() as tmp:
            import src.conversations as conversations

            with patch.object(
                conversations,
                "CONVERSATION_DIR",
                Path(tmp),
            ), patch.object(
                conversations,
                "REGISTRY_PATH",
                Path(tmp) / "registry.json",
            ):
                first = create_conversation(
                    "First Fawkes Session",
                )

                second = create_conversation(
                    "Second Fawkes Session",
                )

                latest = get_latest_conversation()

        self.assertEqual(
            latest["conversation_id"],
            second["conversation_id"],
        )
        self.assertNotEqual(
            latest["conversation_id"],
            first["conversation_id"],
        )

    def test_latest_conversation_returns_none_when_empty(self):
        from src.conversations import get_latest_conversation
        import src.conversations as conversations

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(
                conversations,
                "CONVERSATION_DIR",
                Path(tmp),
            ), patch.object(
                conversations,
                "REGISTRY_PATH",
                Path(tmp) / "registry.json",
            ):
                result = get_latest_conversation()

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()


class FawkesChatCLIContinuityTests(unittest.TestCase):
    def test_restarted_session_recovers_canonical_conversation(self):
        import src.conversations as conversations
        import src.runtime.chat_cli as chat_cli

        conversation_id = "conversation-persistent"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with patch.object(
                conversations,
                "CONVERSATION_DIR",
                root / "conversations",
            ), patch.object(
                conversations,
                "REGISTRY_PATH",
                root / "conversations" / "registry.json",
            ), patch(
                "src.runtime.chat_cli.FawkesChatRuntime",
            ) as runtime_class, patch(
                "src.runtime.chat_cli.get_or_create_default_instance",
                return_value={
                    "instance_id": "fawkes-instance",
                    "name": "Fawkes",
                    "instance_type": "phoenix",
                },
            ), patch(
                "src.runtime.chat_cli.get_latest_conversation",
                return_value={
                    "conversation_id": conversation_id,
                    "title": "Fawkes CLI Session",
                    "instance_id": None,
                    "created_at": "2026-08-29T00:00:00+00:00",
                },
            ), patch(
                "src.runtime.chat_cli.ensure_archive_index",
                return_value={"rebuilt": False, "indexed": 0},
            ), patch(
                "src.runtime.chat_cli.build_archive_context",
                return_value=(
                    {
                        "role": "user",
                        "content": "My name is Tanner.",
                    },
                    {
                        "role": "assistant",
                        "content": "I remember.",
                    },
                ),
            ) as build_context, patch(
                "builtins.input",
                side_effect=["exit"],
            ):
                runtime_class.return_value.context_messages = 20

                chat_cli.main()

        build_context.assert_called_once_with(
            conversation_id,
            max_messages=20,
        )


if __name__ == "__main__":
    unittest.main()


class FawkesSemanticMemoryRetrievalTests(unittest.TestCase):
    def test_semantic_retriever_delegates_to_provider(self):
        from src.memory.semantic_retrieval import (
            SemanticMemoryRetriever,
        )

        captured = {}

        class FakeProvider:
            def rank_memories(
                self,
                *,
                query,
                memories,
            ):
                captured["query"] = query
                captured["memories"] = memories

                return [
                    memories[1],
                    memories[0],
                ]

        memories = (
            {
                "memory_id": "memory-1",
                "content": "The user is pursuing cybersecurity.",
            },
            {
                "memory_id": "memory-2",
                "content": "The user prefers command-first instructions.",
            },
        )

        retriever = SemanticMemoryRetriever(
            FakeProvider(),
        )

        result = retriever.rank(
            query="How does the user like Fawkes to work?",
            memories=memories,
            limit=1,
        )

        self.assertEqual(
            result,
            [memories[1]],
        )
        self.assertEqual(
            captured["query"],
            "How does the user like Fawkes to work?",
        )
        self.assertEqual(
            captured["memories"],
            memories,
        )

    def test_empty_candidates_require_no_provider_call(self):
        from src.memory.semantic_retrieval import (
            SemanticMemoryRetriever,
        )

        class FakeProvider:
            def rank_memories(self, **kwargs):
                raise AssertionError(
                    "Provider should not be called with no candidates"
                )

        result = SemanticMemoryRetriever(
            FakeProvider(),
        ).rank(
            query="anything",
            memories=(),
        )

        self.assertEqual(result, [])

    def test_invalid_provider_result_is_rejected(self):
        from src.memory.semantic_retrieval import (
            SemanticMemoryRetriever,
        )

        class FakeProvider:
            def rank_memories(self, **kwargs):
                return {"memory_id": "not-a-list"}

        with self.assertRaises(TypeError):
            SemanticMemoryRetriever(
                FakeProvider(),
            ).rank(
                query="anything",
                memories=(
                    {
                        "memory_id": "memory-1",
                        "content": "Something.",
                    },
                ),
            )


if __name__ == "__main__":
    unittest.main()


class FawkesSemanticMemoryProviderRetrievalTests(unittest.TestCase):
    def test_provider_semantically_ranks_memory_ids(self):
        from src.memory.openai_provider import (
            OpenAISemanticMemoryProvider,
        )

        calls = []

        class FakeResponse:
            output_text = (
                '{"ranked_ids": ["memory-2", "memory-1", "unknown"]}'
            )

        class FakeResponses:
            def create(self, **kwargs):
                calls.append(kwargs)
                return FakeResponse()

        class FakeClient:
            def __init__(self):
                self.responses = FakeResponses()

        provider = OpenAISemanticMemoryProvider(
            client=FakeClient(),
            model="test-model",
        )

        memories = (
            {
                "memory_id": "memory-1",
                "memory_type": "preference",
                "content": "The user prefers direct instructions.",
                "importance": 0.8,
                "confidence": 0.9,
            },
            {
                "memory_id": "memory-2",
                "memory_type": "user_fact",
                "content": "The user is studying cybersecurity.",
                "importance": 0.9,
                "confidence": 0.95,
            },
        )

        result = provider.rank_memories(
            query="What is the user studying?",
            memories=memories,
        )

        self.assertEqual(
            result,
            [memories[1], memories[0]],
        )

        self.assertEqual(
            len(calls),
            1,
        )

        self.assertEqual(
            calls[0]["model"],
            "test-model",
        )

    def test_provider_does_not_invent_memory_objects(self):
        from src.memory.openai_provider import (
            OpenAISemanticMemoryProvider,
        )

        class FakeResponse:
            output_text = (
                '{"ranked_ids": ["fake-memory"]}'
            )

        class FakeResponses:
            def create(self, **kwargs):
                return FakeResponse()

        class FakeClient:
            def __init__(self):
                self.responses = FakeResponses()

        provider = OpenAISemanticMemoryProvider(
            client=FakeClient(),
            model="test-model",
        )

        memories = (
            {
                "memory_id": "memory-real",
                "content": "The user likes networking.",
            },
        )

        result = provider.rank_memories(
            query="What does the user like?",
            memories=memories,
        )

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()


class FawkesSemanticMemoryProviderRetrievalTests(unittest.TestCase):
    def test_provider_semantically_ranks_memory_ids(self):
        from src.memory.openai_provider import (
            OpenAISemanticMemoryProvider,
        )

        calls = []

        class FakeResponse:
            output_text = (
                '{"ranked_ids": ["memory-2", "memory-1", "unknown"]}'
            )

        class FakeResponses:
            def create(self, **kwargs):
                calls.append(kwargs)
                return FakeResponse()

        class FakeClient:
            def __init__(self):
                self.responses = FakeResponses()

        provider = OpenAISemanticMemoryProvider(
            client=FakeClient(),
            model="test-model",
        )

        memories = (
            {
                "memory_id": "memory-1",
                "memory_type": "preference",
                "content": "The user prefers direct instructions.",
                "importance": 0.8,
                "confidence": 0.9,
            },
            {
                "memory_id": "memory-2",
                "memory_type": "user_fact",
                "content": "The user is studying cybersecurity.",
                "importance": 0.9,
                "confidence": 0.95,
            },
        )

        result = provider.rank_memories(
            query="What is the user studying?",
            memories=memories,
        )

        self.assertEqual(
            result,
            [memories[1], memories[0]],
        )

        self.assertEqual(
            len(calls),
            1,
        )

        self.assertEqual(
            calls[0]["model"],
            "test-model",
        )

    def test_provider_does_not_invent_memory_objects(self):
        from src.memory.openai_provider import (
            OpenAISemanticMemoryProvider,
        )

        class FakeResponse:
            output_text = (
                '{"ranked_ids": ["fake-memory"]}'
            )

        class FakeResponses:
            def create(self, **kwargs):
                return FakeResponse()

        class FakeClient:
            def __init__(self):
                self.responses = FakeResponses()

        provider = OpenAISemanticMemoryProvider(
            client=FakeClient(),
            model="test-model",
        )

        memories = (
            {
                "memory_id": "memory-real",
                "content": "The user likes networking.",
            },
        )

        result = provider.rank_memories(
            query="What does the user like?",
            memories=memories,
        )

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()


class FawkesOpenAIMemoryComparisonTests(unittest.TestCase):
    def test_openai_provider_semantically_compares_memories(self):
        from src.memory.openai_provider import OpenAISemanticMemoryProvider

        captured = {}

        class FakeResponse:
            output_text = (
                '{"relation":"duplicate",'
                '"confidence":0.97,'
                '"reasoning":"Both memories describe the same networking career direction."}'
            )

        class FakeResponses:
            def create(self, **kwargs):
                captured["kwargs"] = kwargs
                return FakeResponse()

        class FakeClient:
            def __init__(self):
                self.responses = FakeResponses()

        provider = OpenAISemanticMemoryProvider(
            client=FakeClient(),
            model="test-model",
        )

        existing = {
            "memory_id": "memory-1",
            "memory_type": "career_goal",
            "content": "The user chose networking as their career direction.",
            "confidence": 0.99,
            "importance": 0.90,
        }

        result = provider.compare(
            new_meaning="Focus primarily on networking.",
            new_memory_type="goal",
            existing_memory=existing,
            conversation_context=(
                {
                    "role": "user",
                    "content": "I want to focus primarily on networking.",
                },
            ),
        )

        self.assertEqual(result.relation, "duplicate")
        self.assertEqual(result.confidence, 0.97)
        self.assertIn(
            "same networking career direction",
            result.reasoning,
        )

        self.assertEqual(
            captured["kwargs"]["model"],
            "test-model",
        )


if __name__ == "__main__":
    unittest.main()
