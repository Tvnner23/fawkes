import unittest

from src.memory.openai_provider import OpenAISemanticMemoryProvider

from src.memory.semantic import SemanticMemoryAssessment
from src.memory.semantic_provider import ModelSemanticMemoryEvaluator


class FakeProvider:
    def __init__(self):
        self.received = None

    def evaluate_memory(self, *, content, conversation_context=()):
        self.received = {
            "content": content,
            "conversation_context": tuple(conversation_context),
        }

        return SemanticMemoryAssessment(
            should_remember=True,
            memory_type="decision",
            meaning="The rider chose networking as his career direction.",
            confidence=0.97,
            importance=0.92,
        )


class InvalidProvider:
    def evaluate_memory(self, *, content, conversation_context=()):
        return {"should_remember": True}


class FawkesSemanticProviderTests(unittest.TestCase):
    def test_provider_result_is_returned_through_adapter(self):
        provider = FakeProvider()
        evaluator = ModelSemanticMemoryEvaluator(provider)

        context = (
            {"role": "assistant", "content": "Networking or cybersecurity?"},
            {"role": "user", "content": "Networking."},
        )

        result = evaluator.evaluate(
            content="That's the one.",
            conversation_context=context,
        )

        self.assertIsInstance(result, SemanticMemoryAssessment)
        self.assertTrue(result.should_remember)
        self.assertEqual(
            result.meaning,
            "The rider chose networking as his career direction.",
        )
        self.assertEqual(result.confidence, 0.97)
        self.assertEqual(result.importance, 0.92)
        self.assertEqual(
            provider.received["content"],
            "That's the one.",
        )
        self.assertEqual(
            provider.received["conversation_context"],
            context,
        )

    def test_invalid_provider_result_is_rejected(self):
        evaluator = ModelSemanticMemoryEvaluator(InvalidProvider())

        with self.assertRaises(TypeError):
            evaluator.evaluate(content="Remember this.")


if __name__ == "__main__":
    unittest.main()


class FawkesOpenAIProviderContractTests(unittest.TestCase):
    def test_provider_rejects_invalid_model_result(self):
        class FakeResponse:
            output_text = '{"should_remember": true}'

        class FakeResponses:
            def create(self, **kwargs):
                return FakeResponse()

        class FakeClient:
            responses = FakeResponses()

        provider = OpenAISemanticMemoryProvider(
            client=FakeClient(),
            model="test-model",
        )

        with self.assertRaises((KeyError, TypeError, ValueError)):
            provider.evaluate_memory(
                content="I prefer networking.",
            )


class FawkesRelationshipProviderPromptTests(unittest.TestCase):
    def test_openai_provider_prompt_includes_relationship_continuity_rules(self):
        from src.memory.openai_provider import OpenAISemanticMemoryProvider

        class FakeResponse:
            output_text = (
                '{"should_remember": false, '
                '"memory_type": null, '
                '"meaning": null, '
                '"confidence": 0.5, '
                '"importance": 0.5, '
                '"reasoning": "test", '
                '"supporting_message_ids": [], '
                '"supporting_archive_ids": []}'
            )

        class FakeResponses:
            def __init__(self):
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return FakeResponse()

        class FakeClient:
            def __init__(self):
                self.responses = FakeResponses()

        client = FakeClient()
        provider = OpenAISemanticMemoryProvider(
            client=client,
            model="test-model",
        )

        provider.evaluate_memory(
            content="you little fawker",
            conversation_context=(
                {
                    "role": "assistant",
                    "content": "Absolutely, dingus.",
                },
                {
                    "role": "user",
                    "content": "you little fawker",
                },
            ),
        )

        prompt = client.responses.calls[0]["input"][0]["content"]

        self.assertIn("inside jokes", prompt)
        self.assertIn("shared references", prompt)
        self.assertIn("relationship moments", prompt)
        self.assertIn("recurrence evidence", prompt)
        self.assertIn("one-off joke", prompt)
        self.assertIn("must not silently contribute facts", prompt)
        self.assertIn("supporting_message_ids", prompt)
        self.assertIn("source archive ID", prompt)
        self.assertIn("education_institution", prompt)
        self.assertIn("degree", prompt)
        self.assertIn("career_direction", prompt)
        self.assertIn("career_goal", prompt)
        self.assertIn("must not be collapsed", prompt)
        self.assertIn("not evidence of the name of their degree", prompt)


if __name__ == "__main__":
    unittest.main()


class FawkesDevelopmentProviderTests(unittest.TestCase):
    def test_openai_provider_can_evaluate_development(self):
        from src.memory.development import DevelopmentProposal
        from src.memory.openai_provider import OpenAISemanticMemoryProvider

        class FakeResponse:
            output_text = (
                '{"should_propose": true, '
                '"category": "system_improvement", '
                '"observation": "Full conversation context was too large.", '
                '"proposed_change": "Use bounded context windows.", '
                '"rationale": "Relevant local context preserves meaning while reducing request size.", '
                '"confidence": 0.95}'
            )

        class FakeResponses:
            def __init__(self):
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return FakeResponse()

        class FakeClient:
            def __init__(self):
                self.responses = FakeResponses()

        client = FakeClient()
        provider = OpenAISemanticMemoryProvider(
            client=client,
            model="test-model",
        )

        result = provider.evaluate_development(
            experience="The full archive caused an oversized model request.",
        )

        self.assertIsInstance(result, DevelopmentProposal)
        self.assertEqual(result.category, "system_improvement")
        self.assertEqual(
            result.proposed_change,
            "Use bounded context windows.",
        )
        self.assertEqual(result.confidence, 0.95)
        self.assertEqual(
            client.responses.calls[0]["model"],
            "test-model",
        )


if __name__ == "__main__":
    unittest.main()


class FawkesDevelopmentNegativeProviderTests(unittest.TestCase):
    def test_openai_provider_returns_none_when_no_improvement_is_needed(self):
        from src.memory.openai_provider import OpenAISemanticMemoryProvider

        class FakeResponse:
            output_text = (
                '{"should_propose": false, '
                '"category": null, '
                '"observation": null, '
                '"proposed_change": null, '
                '"rationale": "The experience does not reveal a meaningful system improvement.", '
                '"confidence": 0.98}'
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

        result = provider.evaluate_development(
            experience="The user said good morning and Fawkes responded.",
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()


class FawkesDevelopmentSimilarityProviderTests(unittest.TestCase):
    def test_openai_provider_can_rank_related_development_history(self):
        from src.memory.openai_provider import OpenAISemanticMemoryProvider

        class FakeResponse:
            output_text = '{"ranked_ids": ["proposal-1"]}'

        class FakeResponses:
            def __init__(self):
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return FakeResponse()

        class FakeClient:
            def __init__(self):
                self.responses = FakeResponses()

        client = FakeClient()

        provider = OpenAISemanticMemoryProvider(
            client=client,
            model="test-model",
        )

        proposals = (
            {
                "proposal_id": "proposal-1",
                "observation": "The archive context was too large.",
                "proposed_change": "Use bounded context windows.",
            },
            {
                "proposal_id": "proposal-2",
                "observation": "A provider returned invalid data.",
                "proposed_change": "Validate provider results.",
            },
        )

        result = provider.rank_development(
            experience="The model is receiving too much conversation history.",
            proposals=proposals,
        )

        self.assertEqual(
            result[0]["proposal_id"],
            "proposal-1",
        )
        self.assertEqual(
            len(result),
            1,
        )
        self.assertEqual(
            client.responses.calls[0]["model"],
            "test-model",
        )


if __name__ == "__main__":
    unittest.main()


class FawkesDevelopmentHistoryPromptTests(unittest.TestCase):
    def test_development_prompt_includes_prior_history(self):
        from src.memory.openai_provider import OpenAISemanticMemoryProvider

        class FakeResponse:
            output_text = (
                '{"should_propose": false, '
                '"category": null, '
                '"observation": null, '
                '"proposed_change": null, '
                '"rationale": "Existing development history already addresses this.", '
                '"confidence": 0.95}'
            )

        class FakeResponses:
            def __init__(self):
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return FakeResponse()

        class FakeClient:
            def __init__(self):
                self.responses = FakeResponses()

        client = FakeClient()

        provider = OpenAISemanticMemoryProvider(
            client=client,
            model="test-model",
        )

        provider.evaluate_development(
            experience="The model received too much conversation history.",
            prior_development=(
                {
                    "proposal_id": "proposal-1",
                    "observation": "Archive context was too large.",
                    "proposed_change": "Use bounded context windows.",
                },
            ),
        )

        prompt = client.responses.calls[0]["input"][0]["content"]
        user_input = client.responses.calls[0]["input"][1]["content"]

        self.assertIn("prior developmental history", prompt.lower())
        self.assertIn("already encountered", prompt.lower())
        self.assertIn("proposal-1", user_input)
        self.assertIn("bounded context windows", user_input)


if __name__ == "__main__":
    unittest.main()
