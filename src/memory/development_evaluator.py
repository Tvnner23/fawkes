from src.memory.development import DevelopmentProposal


class DevelopmentEvaluator:
    """
    Provider-independent contract for identifying possible Fawkes improvements.
    """

    def __init__(self, provider):
        self.provider = provider

    def evaluate(
        self,
        *,
        experience,
        prior_development=(),
        source_memory_ids=(),
        source_message_ids=(),
    ) -> DevelopmentProposal | None:
        result = self.provider.evaluate_development(
            experience=experience,
            prior_development=tuple(prior_development),
        )

        if result is None:
            return None

        if not isinstance(result, DevelopmentProposal):
            raise TypeError(
                "Development provider must return DevelopmentProposal or None"
            )

        return DevelopmentProposal(
            category=result.category,
            observation=result.observation,
            proposed_change=result.proposed_change,
            rationale=result.rationale,
            confidence=result.confidence,
            source_memory_ids=tuple(source_memory_ids),
            source_message_ids=tuple(source_message_ids),
        )
