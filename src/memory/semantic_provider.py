from src.memory.semantic import SemanticMemoryAssessment


class ModelSemanticMemoryEvaluator:
    """
    Provider adapter for semantic memory evaluation.

    The memory system depends only on the SemanticMemoryEvaluator contract.
    The actual model/provider is injected into this adapter.
    """

    def __init__(self, provider):
        self.provider = provider

    def evaluate(
        self,
        *,
        content: str,
        conversation_context=(),
    ) -> SemanticMemoryAssessment:
        result = self.provider.evaluate_memory(
            content=content,
            conversation_context=tuple(conversation_context),
        )

        if not isinstance(result, SemanticMemoryAssessment):
            raise TypeError(
                "Semantic memory provider must return "
                "SemanticMemoryAssessment"
            )

        return result
