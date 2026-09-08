import json


class CorrectionAssessment:
    def __init__(
        self,
        *,
        is_correction,
        confidence=0.0,
        reasoning=None,
    ):
        self.is_correction = bool(is_correction)
        self.confidence = float(confidence)
        self.reasoning = reasoning


def evaluate_correction(
    evaluator,
    *,
    user_message,
    conversation_context=(),
):
    """
    Determine whether a user message is explicitly correcting Fawkes.

    This is intentionally separate from ordinary memory evaluation.
    A correction is a developmental signal, not automatically a durable
    user memory.
    """
    result = evaluator.evaluate_correction(
        user_message=user_message,
        conversation_context=tuple(conversation_context),
    )

    if result is None:
        return None

    if not isinstance(result, CorrectionAssessment):
        raise TypeError(
            "Correction evaluator must return CorrectionAssessment or None"
        )

    if not 0.0 <= result.confidence <= 1.0:
        raise ValueError(
            "Correction confidence must be between 0 and 1"
        )

    return result
