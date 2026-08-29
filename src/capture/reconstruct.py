from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = ROOT / "archive" / "raw"
META_DIR = ROOT / "archive" / "meta"

MESSAGE_RE = re.compile(r"(?m)^(User|Fawkes):(?: )?")


def load_snapshots(conversation_id: str):
    snapshots = []

    for meta_path in sorted(META_DIR.glob("*.json")):
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))

        if metadata.get("conversation_id") != conversation_id:
            continue

        if metadata.get("ingest_method") != "browser_live":
            continue

        raw_path = RAW_DIR / metadata["raw_file"]
        raw_bytes = raw_path.read_bytes()

        encoding = metadata.get("encoding") or "utf-8"
        text = raw_bytes.decode(encoding)

        snapshots.append(
            {
                "archive_id": metadata["archive_id"],
                "created_at": metadata["created_at"],
                "text": text,
            }
        )

    snapshots.sort(key=lambda item: item["created_at"])
    return snapshots


def parse_messages(text: str):
    matches = list(MESSAGE_RE.finditer(text))
    messages = []

    for index, match in enumerate(matches):
        start = match.end()

        if index + 1 < len(matches):
            end = matches[index + 1].start()
        else:
            end = len(text)

        role = "user" if match.group(1) == "User" else "assistant"
        content = text[start:end].strip()

        messages.append(
            {
                "role": role,
                "content": content,
            }
        )

    return messages


def messages_compatible(first: dict, second: dict):
    if first["role"] != second["role"]:
        return False

    first_content = first["content"]
    second_content = second["content"]

    return (
        first_content == second_content
        or first_content.startswith(second_content)
        or second_content.startswith(first_content)
    )


def prefer_more_complete(first: dict, second: dict):
    if len(second["content"]) > len(first["content"]):
        return second.copy()

    return first.copy()


def find_contained(base: list, incoming: list):
    if not incoming or len(incoming) > len(base):
        return None

    limit = len(base) - len(incoming) + 1

    for start in range(limit):
        if all(
            messages_compatible(base[start + offset], incoming[offset])
            for offset in range(len(incoming))
        ):
            return start

    return None


def find_suffix_prefix_overlap(base: list, incoming: list):
    maximum = min(len(base), len(incoming))

    for size in range(maximum, 0, -1):
        if all(
            messages_compatible(
                base[len(base) - size + offset],
                incoming[offset],
            )
            for offset in range(size)
        ):
            return size

    return 0


def merge_snapshot(base: list, incoming: list):
    if not base:
        return [message.copy() for message in incoming], True

    if not incoming:
        return base, True

    contained_at = find_contained(base, incoming)

    if contained_at is not None:
        merged = [message.copy() for message in base]

        for offset, message in enumerate(incoming):
            index = contained_at + offset
            merged[index] = prefer_more_complete(merged[index], message)

        return merged, True

    overlap = find_suffix_prefix_overlap(base, incoming)

    if overlap == 0:
        return base, False

    merged = [message.copy() for message in base]
    base_start = len(merged) - overlap

    for offset in range(overlap):
        index = base_start + offset
        merged[index] = prefer_more_complete(
            merged[index],
            incoming[offset],
        )

    merged.extend(
        message.copy()
        for message in incoming[overlap:]
    )

    return merged, True


def reconstruct_conversation(conversation_id: str):
    snapshots = load_snapshots(conversation_id)

    reconstructed = []
    conflicts = []
    source_archive_ids = []

    for snapshot in snapshots:
        messages = parse_messages(snapshot["text"])
        source_archive_ids.append(snapshot["archive_id"])

        reconstructed, merged = merge_snapshot(
            reconstructed,
            messages,
        )

        if not merged:
            conflicts.append(snapshot["archive_id"])

    return {
        "schema_version": 1,
        "conversation_id": conversation_id,
        "snapshot_count": len(snapshots),
        "source_archive_ids": source_archive_ids,
        "message_count": len(reconstructed),
        "conflicts": conflicts,
        "messages": reconstructed,
    }
