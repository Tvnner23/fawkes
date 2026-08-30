import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.memory.store as store


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


class FawkesMemoryRuntimeFlowTests(unittest.TestCase):
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
                },
                {
                    "role": "user",
                    "content": "Yeah, that's the one.",
                },
            ),
        )


if __name__ == "__main__":
    unittest.main()


class FawkesRuntimeContractTests(unittest.TestCase):
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
