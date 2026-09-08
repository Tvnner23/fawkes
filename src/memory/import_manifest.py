import json
from pathlib import Path


def write_import_manifest(
    audits,
    path,
):
    """
    Write a human-reviewable JSON manifest.

    This contains audit decisions only. It does not create persistent
    memory records.
    """
    records = []

    for audit in audits:
        records.append(
            {
                "candidate_id": audit.candidate_id,
                "content": audit.content,
                "memory_type": audit.memory_type,
                "tier": audit.tier,
                "decision": audit.decision,
                "confidence": audit.confidence,
                "importance": audit.importance,
                "reasoning": audit.reasoning,
                "source_message_ids": list(
                    audit.source_message_ids
                ),
                "source_archive_ids": list(
                    audit.source_archive_ids
                ),
            }
        )

    output = Path(path)
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(
            records,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return output
