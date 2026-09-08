"""Operational commands for incremental, observable Phoenix memory work."""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from src.instances import get_or_create_default_instance
from src.memory.ledger import (
    get_work_item,
    list_work_items,
    recover_stale_work_items,
    update_work_item,
    work_item_status_counts,
)
from src.memory.openai_provider import OpenAISemanticMemoryProvider
from src.memory.semantic_provider import ModelSemanticMemoryEvaluator
from src.memory.semantic_retrieval import SemanticMemoryRetriever
from src.memory.store import list_memories, list_memory_events, load_memory
from src.memory.worker import (
    apply_accepted_batch,
    discover_conversation,
    discover_history,
    evaluate_batch,
    retry_work_item,
)


def _parser():
    parser = argparse.ArgumentParser(
        description="Inspect and operate the resumable Fawkes memory pipeline."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")

    discover = sub.add_parser("discover")
    discover.add_argument("--conversation")
    discover.add_argument("--limit", type=int, default=100)
    discover.add_argument("--include-legacy-unscoped", action="store_true")

    process = sub.add_parser("process")
    process.add_argument("--limit", type=int, default=10)
    process.add_argument("--yes", action="store_true")

    apply_cmd = sub.add_parser("apply")
    apply_cmd.add_argument("--limit", type=int, default=10)
    apply_cmd.add_argument("--yes", action="store_true")
    apply_cmd.add_argument("--include-legacy-unscoped", action="store_true")

    recover = sub.add_parser("recover-stale")
    recover.add_argument("--minutes", type=int, default=30)

    decide = sub.add_parser("decide")
    decide.add_argument("work_item_id")
    decide.add_argument("decision", choices=("accept", "reject"))
    decide.add_argument("--note", default="")

    retry = sub.add_parser("retry")
    retry.add_argument("work_item_id")

    show = sub.add_parser("show")
    show.add_argument("work_item_id")

    provenance = sub.add_parser("provenance")
    provenance.add_argument("memory_id")
    return parser


def _require_paid_confirmation(args, operation):
    if args.yes:
        return
    raise SystemExit(
        f"{operation} can make paid model calls. Re-run with --yes and a "
        "small --limit after reviewing `memory status`."
    )


def _print_records(records):
    print(json.dumps(records, indent=2, ensure_ascii=False, default=str))


def main(argv=None):
    args = _parser().parse_args(argv)
    phoenix = get_or_create_default_instance()
    instance_id = phoenix["instance_id"]

    if args.command == "status":
        active = list_memories(status="active", instance_id=instance_id)
        legacy = [
            memory
            for memory in list_memories(status="active")
            if memory.get("instance_id") is None
        ]
        _print_records(
            {
                "instance": phoenix,
                "work_items_by_status": work_item_status_counts(
                    instance_id=instance_id
                ),
                "instance_active_memories": len(active),
                "legacy_unscoped_active_memories": len(legacy),
            }
        )
        return 0

    if args.command == "discover":
        if args.limit <= 0:
            raise SystemExit("--limit must be positive")
        if args.conversation:
            records = discover_conversation(
                args.conversation,
                instance_id=instance_id,
                include_unscoped=args.include_legacy_unscoped,
                limit=args.limit,
            )
        else:
            records = discover_history(
                instance_id=instance_id,
                limit=args.limit,
                include_unscoped=args.include_legacy_unscoped,
            )
        _print_records(
            {"discovered_or_existing": len(records), "work_items": records}
        )
        return 0

    if args.command == "process":
        _require_paid_confirmation(args, "Memory evaluation")
        provider = OpenAISemanticMemoryProvider()
        records = evaluate_batch(
            instance_id=instance_id,
            evaluator=ModelSemanticMemoryEvaluator(provider),
            limit=args.limit,
        )
        _print_records(records)
        return 0

    if args.command == "apply":
        _require_paid_confirmation(args, "Semantic memory consolidation")
        provider = OpenAISemanticMemoryProvider()
        records = apply_accepted_batch(
            instance_id=instance_id,
            limit=args.limit,
            matcher=provider,
            semantic_retriever=SemanticMemoryRetriever(provider),
            include_unscoped=args.include_legacy_unscoped,
        )
        _print_records(records)
        return 0

    if args.command == "recover-stale":
        if args.minutes < 1:
            raise SystemExit("--minutes must be at least 1")
        recovered = recover_stale_work_items(
            instance_id=instance_id,
            older_than=datetime.now(timezone.utc) - timedelta(minutes=args.minutes),
        )
        _print_records({"recovered": recovered})
        return 0

    if args.command == "decide":
        item = get_work_item(args.work_item_id)
        if item is None or item["instance_id"] != instance_id:
            raise SystemExit("Work item was not found for this Phoenix instance.")
        status = "accepted" if args.decision == "accept" else "rejected"
        updated = update_work_item(
            args.work_item_id,
            status=status,
            decision=args.decision,
            decision_reason=args.note or "Explicit operator decision.",
        )
        _print_records(updated)
        return 0

    if args.command == "retry":
        item = get_work_item(args.work_item_id)
        if item is None or item["instance_id"] != instance_id:
            raise SystemExit("Work item was not found for this Phoenix instance.")
        _print_records(retry_work_item(args.work_item_id))
        return 0

    if args.command == "show":
        item = get_work_item(args.work_item_id)
        if item is None or item["instance_id"] != instance_id:
            raise SystemExit("Work item was not found for this Phoenix instance.")
        _print_records(item)
        return 0

    if args.command == "provenance":
        memory = load_memory(args.memory_id)
        if memory is None or memory.get("instance_id") != instance_id:
            raise SystemExit("Memory was not found for this Phoenix instance.")
        work_ids = set(memory.get("source_work_item_ids", ()))
        work_items = [
            item
            for item in list_work_items(instance_id=instance_id)
            if item["work_item_id"] in work_ids
        ]
        _print_records(
            {
                "memory": memory,
                "work_items": work_items,
                "memory_events": list_memory_events(args.memory_id),
                "source_archive_ids": memory.get("source_archive_ids", ()),
            }
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
