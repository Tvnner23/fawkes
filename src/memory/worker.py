"""Resumable canonical-candidate processing and approved memory persistence."""

from dataclasses import asdict

from src.capture.canonical import canonical_messages, message_allows_memory_learning
from src.memory.archive_context import (
    ArchiveContextReviewRequired, MemoryLearningPaused, build_archive_context,
    memory_learning_enabled,
)
from src.memory.mutation import MemoryRecoveryRequired
from src.memory.archive_retrieval import list_conversation_ids
from src.memory.consolidate import consolidate_assessment
from src.memory.gate import looks_like_artifact
from src.memory.import_policy import classify_import_candidate
from src.memory.ledger import (
    LEDGER_PATH,
    claim_next_work_item,
    discover_candidate,
    get_work_item,
    list_work_items,
    update_work_item,
)
from src.memory.retrieval import retrieve_memories
from src.memory.semantic import SemanticMemoryAssessment, evaluate_semantically
from src.memory.store import IncompleteMemoryMutation, MemoryOwnershipReview, find_memory_by_work_item, list_memories_for_context


PROCESSOR_VERSION = "memory-v1"


class EvidenceAttributionError(ValueError):
    """The proposed meaning is not safely attributable to archive evidence."""


def _queue_discovered(item, message_instance, *, path):
    if item['status'] != 'discovered':
        return item
    if message_instance is None:
        return update_work_item(item['work_item_id'], status='review',
            decision='review', decision_reason='Unscoped Archive evidence requires an explicit ownership/migration decision; discovery does not assign an owner.', path=path)
    return update_work_item(item['work_item_id'], status='queued', path=path)


def discover_conversation(
    conversation_id,
    *,
    instance_id,
    include_unscoped=False,
    limit=None,
    path=LEDGER_PATH,
):
    """Record each canonical user revision without changing the archive."""
    discovered = []
    if not memory_learning_enabled(instance_id):
        return discovered
    for message in canonical_messages(conversation_id,instance_id=instance_id,include_unscoped=include_unscoped):
        if message.get("role") != "user" or not message_allows_memory_learning(message):
            continue
        message_instance = message.get("instance_id")
        if message_instance != instance_id and not (
            include_unscoped and message_instance is None
        ):
            continue
        if not memory_learning_enabled(instance_id):
            break
        item = discover_candidate(
            instance_id=instance_id,
            conversation_id=conversation_id,
            message_id=message["message_id"],
            canonical_revision=message["source_archive_id"],
            source_archive_ids=(message["source_archive_id"],),
            candidate_content=message["content"],
            candidate_created_at=message.get("created_at"),
            processor_version=PROCESSOR_VERSION,
            path=path,
        )
        item = _queue_discovered(item, message_instance, path=path)
        discovered.append(item)
        if limit is not None and len(discovered) >= limit:
            break
    return discovered


def discover_history(
    *, instance_id, limit=None, include_unscoped=False, path=LEDGER_PATH
):
    """Incrementally discover conversations in a stable order."""
    if not memory_learning_enabled(instance_id):
        return []
    existing_keys = {
        (
            item["conversation_id"],
            item["message_id"],
            item["canonical_revision"],
            item["processor_version"],
        )
        for item in list_work_items(instance_id=instance_id, path=path)
    }
    items = []
    for conversation_id in list_conversation_ids(
        instance_id=instance_id,
        include_unscoped=include_unscoped,
    ):
        for message in canonical_messages(conversation_id,instance_id=instance_id,include_unscoped=include_unscoped):
            if message.get("role") != "user" or not message_allows_memory_learning(message):
                continue
            message_instance = message.get("instance_id")
            if message_instance != instance_id and not (
                include_unscoped and message_instance is None
            ):
                continue
            key = (
                conversation_id,
                message["message_id"],
                message["source_archive_id"],
                PROCESSOR_VERSION,
            )
            if key in existing_keys:
                continue
            if not memory_learning_enabled(instance_id):
                return items
            item = discover_candidate(
                instance_id=instance_id,
                conversation_id=conversation_id,
                message_id=message["message_id"],
                canonical_revision=message["source_archive_id"],
                source_archive_ids=(message["source_archive_id"],),
                candidate_content=message["content"],
                candidate_created_at=message.get("created_at"),
                processor_version=PROCESSOR_VERSION,
                path=path,
            )
            item = _queue_discovered(item, message_instance, path=path)
            items.append(item)
            existing_keys.add(key)
            if limit is not None and len(items) >= limit:
                return items
    return items


def _context(item):
    try:
        context = build_archive_context(
            item["conversation_id"], instance_id=item['instance_id'],
            center_message_id=item["message_id"], before=20, after=20,
            memory_learning_only=True)
    except ValueError as exc:
        # Invalid/ambiguous retained attribution is not transient I/O. Leave
        # genuine OSError failures on the ordinary retryable path.
        raise ArchiveContextReviewRequired(str(exc)) from exc
    if any(entry.get('instance_id') != item['instance_id'] for entry in context):
        raise EvidenceAttributionError('Archive context does not belong to the current instance')
    if any(not message_allows_memory_learning(entry) for entry in context):
        raise EvidenceAttributionError('Archive context does not allow Memory learning')
    if any(entry.get('message_id')==item['message_id'] and
           entry.get('source_archive_id')!=item['canonical_revision'] for entry in context):
        raise EvidenceAttributionError('Candidate Archive revision changed; explicit reevaluation is required')
    return context


def _validated_evidence(item, assessment, context):
    """Return explicitly attributed evidence or reject unsafe attribution."""
    if not assessment.should_remember:
        return (item["message_id"],), tuple(item["source_archive_ids"])

    if any(entry.get('instance_id') != item['instance_id'] for entry in context):
        raise EvidenceAttributionError('Archive evidence does not belong to the current instance')
    if any(not message_allows_memory_learning(entry) for entry in context):
        raise EvidenceAttributionError('Archive evidence does not allow Memory learning')

    message_ids = tuple(dict.fromkeys(assessment.supporting_message_ids))
    archive_ids = tuple(dict.fromkeys(assessment.supporting_archive_ids))
    if not message_ids or item["message_id"] not in message_ids:
        raise EvidenceAttributionError(
            "remembered meaning must cite the candidate message as evidence"
        )

    available = {
        item["message_id"]: item["canonical_revision"],
        **{
        entry.get("message_id"): entry.get("source_archive_id")
        for entry in context
        if entry.get("message_id") and entry.get("source_archive_id")
        },
    }
    if any(message_id not in available for message_id in message_ids):
        raise EvidenceAttributionError(
            "assessment cites a message outside bounded context"
        )

    expected_archive_ids = tuple(
        dict.fromkeys(available[message_id] for message_id in message_ids)
    )
    if set(archive_ids) != set(expected_archive_ids):
        raise EvidenceAttributionError(
            "supporting archive IDs must exactly match supporting messages"
        )
    return message_ids, expected_archive_ids


def evaluate_next(
    *, instance_id, evaluator, exclude_work_item_ids=(), path=LEDGER_PATH
):
    """Evaluate one queued item and persist its disposition before mutation."""
    if not memory_learning_enabled(instance_id):
        return None
    item = claim_next_work_item(
        instance_id=instance_id,
        statuses=("queued", "failed_evaluation_retryable"),
        exclude_work_item_ids=exclude_work_item_ids,
        path=path,
    )
    if item is None:
        return None
    try:
        content = (item.get("candidate_content") or "").strip()
        if not content:
            raise ValueError("candidate content is missing from the ledger")

        context = _context(item)
        if not memory_learning_enabled(instance_id):
            update_work_item(item["work_item_id"], status="queued", path=path)
            return None
        if looks_like_artifact(content):
            assessment = SemanticMemoryAssessment(
                should_remember=False,
                memory_type="artifact",
                meaning=None,
                confidence=1.0,
                importance=0.0,
                reasoning="Deterministic artifact gate rejected the candidate.",
            )
        else:
            assessment = evaluate_semantically(
                evaluator,
                content=content,
                conversation_context=context,
            )

        if not memory_learning_enabled(instance_id):
            update_work_item(item["work_item_id"], status="queued", path=path)
            return None
        if looks_like_artifact(content):
            evidence_message_ids = (item["message_id"],)
            evidence_archive_ids = tuple(item["source_archive_ids"])
        else:
            evidence_message_ids, evidence_archive_ids = _validated_evidence(
                item, assessment, context
            )

        if not assessment.should_remember:
            decision, tier = "reject", "X" if assessment.memory_type == "artifact" else "D"
            audit = {
                "tier": tier,
                "decision": decision,
                "reasoning": assessment.reasoning or "Not durable memory.",
            }
        elif not assessment.memory_type or not assessment.meaning:
            decision = "review"
            audit = {
                "tier": "C",
                "decision": decision,
                "reasoning": assessment.reasoning or "Assessment is incomplete.",
            }
        else:
            classified = classify_import_candidate(
                candidate_id=item["work_item_id"],
                content=assessment.meaning,
                memory_type=assessment.memory_type,
                confidence=assessment.confidence,
                importance=assessment.importance,
                reasoning=assessment.reasoning or "Semantic evaluator decision.",
                source_message_ids=evidence_message_ids,
                source_archive_ids=evidence_archive_ids,
            )
            audit = asdict(classified)
            decision = classified.decision

        return update_work_item(
            item["work_item_id"],
            status={"accept": "accepted", "review": "review", "reject": "rejected"}[decision],
            assessment={"semantic": asdict(assessment), "audit": audit},
            decision=decision,
            decision_reason=audit["reasoning"],
            path=path,
        )
    except (EvidenceAttributionError, ArchiveContextReviewRequired, MemoryRecoveryRequired) as exc:
        semantic = asdict(assessment) if "assessment" in locals() else None
        reasoning = f"Evidence attribution requires review: {exc}"
        return update_work_item(
            item["work_item_id"],
            status="review",
            assessment={
                "semantic": semantic,
                "audit": {
                    "tier": "C",
                    "decision": "review",
                    "reasoning": reasoning,
                },
            },
            decision="review",
            decision_reason=reasoning,
            path=path,
        )
    except Exception as exc:
        return update_work_item(
            item["work_item_id"],
            status="failed_evaluation_retryable",
            error=f"{type(exc).__name__}: {exc}",
            path=path,
        )


def evaluate_batch(*, instance_id, evaluator, limit=10, path=LEDGER_PATH):
    results = []
    attempted = set()
    for _ in range(max(0, int(limit))):
        item = evaluate_next(
            instance_id=instance_id,
            evaluator=evaluator,
            exclude_work_item_ids=attempted,
            path=path,
        )
        if item is None:
            break
        results.append(item)
        attempted.add(item["work_item_id"])
    return results


def _assessment_from_item(item):
    payload = (item.get("assessment") or {}).get("semantic")
    if not payload:
        raise ValueError("accepted work item has no semantic assessment")
    return SemanticMemoryAssessment(**payload)


def apply_next_accepted(
    *, instance_id, matcher=None, semantic_retriever=None,
    include_unscoped=False, exclude_work_item_ids=(), path=LEDGER_PATH
):
    """Apply one explicitly accepted assessment at the persistence boundary."""
    if not memory_learning_enabled(instance_id):
        return None
    item = claim_next_work_item(
        instance_id=instance_id,
        statuses=("accepted", "failed_consolidation_retryable"),
        target_status="consolidating",
        exclude_work_item_ids=exclude_work_item_ids,
        path=path,
    )
    if item is None:
        return None

    try:
        # Store lookup recovers a durable pending record/event operation before
        # returning its result. Recovery failure must remain retryable, not be
        # mistaken for completion or leave an unreported consolidating item.
        prior = find_memory_by_work_item(
            item["work_item_id"], instance_id=instance_id
        )
        if prior is not None:
            return update_work_item(
                item["work_item_id"],
                status="consolidated",
                resulting_memory_ids=(prior["memory_id"],),
                decision_reason="Recovered complete prior Memory mutation.",
                path=path,
            )
        assessment = _assessment_from_item(item)
        context = _context(item)
        supporting_message_ids, supporting_archive_ids = _validated_evidence(
            item, assessment, context
        )
        active = list_memories_for_context(
            status="active",
            instance_id=instance_id,
            include_unscoped=include_unscoped,
        )
        if semantic_retriever is not None:
            active = semantic_retriever.rank(
                query=assessment.meaning,
                memories=active,
                limit=5,
            )
        else:
            active = retrieve_memories(
                assessment.meaning,
                limit=5,
                instance_id=instance_id,
                include_unscoped=include_unscoped,
            )

        if not memory_learning_enabled(instance_id):
            update_work_item(item["work_item_id"], status="accepted", path=path)
            return None
        result = consolidate_assessment(
            assessment,
            source_message_ids=supporting_message_ids,
            source_archive_ids=supporting_archive_ids,
            source_work_item_ids=(item["work_item_id"],),
            instance_id=instance_id,
            matcher=matcher,
            existing_memories=active,
            conversation_context=context,
        )
        if result.action in {"needs_review", "conflict_detected"}:
            return update_work_item(
                item["work_item_id"],
                status="review",
                resulting_memory_ids=((result.memory_id,) if result.memory_id else ()),
                decision="review",
                decision_reason=f"Consolidation result: {result.action}",
                path=path,
            )
        return update_work_item(
            item["work_item_id"],
            status="consolidated",
            resulting_memory_ids=((result.memory_id,) if result.memory_id else ()),
            decision_reason=f"Consolidation result: {result.action}",
            path=path,
        )
    except MemoryLearningPaused:
        update_work_item(item["work_item_id"], status="accepted", path=path)
        return None
    except (EvidenceAttributionError, ArchiveContextReviewRequired, IncompleteMemoryMutation, MemoryOwnershipReview, MemoryRecoveryRequired) as exc:
        return update_work_item(
            item["work_item_id"],
            status="review",
            decision="review",
            decision_reason=f"Memory evidence requires review: {exc}",
            path=path,
        )
    except Exception as exc:
        return update_work_item(
            item["work_item_id"],
            status="failed_consolidation_retryable",
            error=f"{type(exc).__name__}: {exc}",
            path=path,
        )


def apply_accepted_batch(
    *, instance_id, limit=10, matcher=None, semantic_retriever=None,
    include_unscoped=False, path=LEDGER_PATH
):
    results = []
    attempted = set()
    for _ in range(max(0, int(limit))):
        item = apply_next_accepted(
            instance_id=instance_id,
            matcher=matcher,
            semantic_retriever=semantic_retriever,
            include_unscoped=include_unscoped,
            exclude_work_item_ids=attempted,
            path=path,
        )
        if item is None:
            break
        results.append(item)
        attempted.add(item["work_item_id"])
    return results


def retry_work_item(work_item_id, *, path=LEDGER_PATH):
    item = get_work_item(work_item_id, path=path)
    if item is None:
        raise KeyError(f"Unknown work item: {work_item_id}")
    status = (
        "accepted"
        if item["status"] in {
            "consolidating",
            "failed_consolidation_retryable",
        }
        else "queued"
    )
    return update_work_item(work_item_id, status=status, error=None, path=path)
