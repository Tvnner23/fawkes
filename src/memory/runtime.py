from src.memory.archive_context import build_archive_context, memory_learning_enabled
from src.memory.openai_provider import OpenAISemanticMemoryProvider
from src.memory.semantic_provider import ModelSemanticMemoryEvaluator
from src.memory.extract import extract_memory_candidates
from src.memory.pipeline import process_candidates


def build_memory_evaluator(*, provider=None, model=None):
    """
    Build the semantic evaluator used by the Fawkes memory runtime.

    Provider selection remains isolated here so the rest of the memory
    system depends only on the semantic evaluator contract.
    """
    if provider is None:
        provider = OpenAISemanticMemoryProvider(model=model)

    return ModelSemanticMemoryEvaluator(provider)



def process_memory_conversation(
    conversation_id: str,
    *,
    evaluator=None,
    provider=None,
    model=None,
    matcher=None,
    retrieval_limit=5,
    instance_id=None,
    include_unscoped=False,
):
    """
    Run one conversation through Fawkes memory processing.

    The canonical conversation is used as semantic context. The archive
    remains the immutable source of truth and is never modified here.
    """
    if not memory_learning_enabled(instance_id):
        return []
    if evaluator is None:
        if provider is None:
            provider = OpenAISemanticMemoryProvider(
                model=model,
            )

        evaluator = ModelSemanticMemoryEvaluator(
            provider,
        )

    if matcher is None and provider is not None:
        matcher = provider

    conversation_context = build_archive_context(
        conversation_id,instance_id=instance_id,include_unscoped=include_unscoped,
        memory_learning_only=True,
    )

    candidates = extract_memory_candidates(conversation_id,instance_id=instance_id,include_unscoped=include_unscoped)

    return process_candidates(
        candidates,
        evaluator=evaluator,
        matcher=matcher,
        conversation_context=conversation_context,
        retrieval_limit=retrieval_limit,
        instance_id=instance_id,
        include_unscoped=include_unscoped,
    )
