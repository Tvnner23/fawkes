"""Rebuildable, instance-scoped search over canonical archive messages."""

from pathlib import Path
import json
import os
import re
import sqlite3

from src.capture.canonical import canonical_messages


ROOT = Path(__file__).resolve().parent.parent.parent
STATE_ROOT = Path(os.environ.get("FAWKES_RUNTIME_STATE_ROOT") or ROOT)
META_DIR = STATE_ROOT / "archive" / "meta"
INDEX_PATH = STATE_ROOT / "database" / "canonical_archive.sqlite3"

_STOP_WORDS = {
    "a", "about", "an", "and", "are", "as", "at", "be", "but", "by",
    "did", "do", "does", "for", "from", "had", "has", "have", "he",
    "her", "here", "him", "his", "how",
    "i", "if", "im", "in", "is", "it", "its", "me", "my", "of", "on", "or",
    "our", "she", "so", "that", "the", "their", "them", "there", "they",
    "re", "s", "should", "this", "to", "us", "ve", "was", "we", "were", "what", "when", "where",
    "which", "who", "why", "will", "with", "would", "you", "your",
}
_WEAK_CONVERSATIONAL_TERMS = {
    "again", "back", "hey", "hello", "hi", "okay", "ok", "ready",
    "sup", "yo",
}
_GREETING_RE = re.compile(
    r"^\s*(?:hey|hello|hi|hiya|howdy|yo|good\s+(?:morning|afternoon|evening))"
    r"(?:\s+there|\s+fawkes)?[\s!,.?]*$",
    flags=re.IGNORECASE,
)
_PROCEDURAL_QUERY_TERMS = {
    "bash", "code", "command", "commit", "file", "git", "gitignore",
    "install", "python", "repo", "repository", "run", "script", "terminal",
}


def _query_terms(query):
    return tuple(
        term.lower()
        for term in re.findall(r"[\w-]+", query, flags=re.UNICODE)
    )


def meaningful_query_terms(query):
    """Return terms strong enough to justify broad historical retrieval."""
    if not isinstance(query, str) or not query.strip() or _GREETING_RE.match(query):
        return ()
    return tuple(
        term
        for term in _query_terms(query)
        if term not in _STOP_WORDS and term not in _WEAK_CONVERSATIONAL_TERMS
    )


def _looks_procedural(content):
    lowered = content.lower()
    return (
        "```" in content
        or bool(re.search(r"(?:^|\n)\s*(?:run|paste|execute|type):?\s", lowered))
        or bool(re.search(r"\b(?:git|python|pip|npm|cat|sed|rg)\s+[-./\w]", lowered))
    )


def list_conversation_ids(*, instance_id=None, include_unscoped=False):
    conversation_ids = set()

    for path in META_DIR.glob("*.json"):
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        conversation_id = metadata.get("conversation_id")
        if not conversation_id:
            continue

        record_instance_id = metadata.get("instance_id")
        if instance_id is not None:
            if record_instance_id == instance_id:
                pass
            elif record_instance_id is None and include_unscoped:
                pass
            else:
                continue

        conversation_ids.add(conversation_id)

    return tuple(sorted(conversation_ids))


def _connect(path=INDEX_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS canonical_passages USING fts5(
            instance_id UNINDEXED,
            conversation_id UNINDEXED,
            message_id UNINDEXED,
            role UNINDEXED,
            content,
            created_at UNINDEXED,
            source_archive_id UNINDEXED,
            canonicalizer_version UNINDEXED
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS canonical_message_projection (
            instance_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_archive_id TEXT NOT NULL,
            canonicalizer_version TEXT NOT NULL,
            PRIMARY KEY (instance_id, conversation_id, message_id)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS continuity_conversation_time ON canonical_message_projection(instance_id, conversation_id, created_at)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS continuity_instance_time ON canonical_message_projection(instance_id, created_at)"
    )
    return connection


def rebuild_archive_index(
    *,
    instance_id,
    include_unscoped=False,
    path=INDEX_PATH,
):
    """Rebuild one Phoenix's derived passage index from canonical history."""
    connection = _connect(path)
    indexed = 0

    try:
        connection.execute(
            "DELETE FROM canonical_passages WHERE instance_id = ?",
            (instance_id,),
        )
        connection.execute(
            "DELETE FROM canonical_message_projection WHERE instance_id = ?",
            (instance_id,),
        )

        for conversation_id in list_conversation_ids(
            instance_id=instance_id,
            include_unscoped=include_unscoped,
        ):
            for message in canonical_messages(conversation_id):
                message_instance_id = message.get("instance_id")
                if message_instance_id == instance_id:
                    pass
                elif message_instance_id is None and include_unscoped:
                    pass
                else:
                    continue

                connection.execute(
                    """
                    INSERT INTO canonical_passages (
                        instance_id,
                        conversation_id,
                        message_id,
                        role,
                        content,
                        created_at,
                        source_archive_id,
                        canonicalizer_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        instance_id,
                        conversation_id,
                        message["message_id"],
                        message["role"],
                        message["content"],
                        message["created_at"],
                        message["source_archive_id"],
                        "structured-v1",
                    ),
                )
                connection.execute(
                    """INSERT OR REPLACE INTO canonical_message_projection (
                        instance_id, conversation_id, message_id, role, content,
                        created_at, source_archive_id, canonicalizer_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (instance_id, conversation_id, message["message_id"], message["role"],
                     message["content"], message["created_at"], message["source_archive_id"], "structured-v1"),
                )
                indexed += 1

        connection.commit()
    finally:
        connection.close()

    return indexed


def index_canonical_message(
    *,
    instance_id,
    conversation_id,
    message_id,
    role,
    content,
    created_at,
    source_archive_id,
    canonicalizer_version="structured-v1",
    path=None,
):
    """Idempotently make one durably archived message searchable."""
    if not instance_id:
        raise ValueError("instance_id is required for scoped archive indexing")
    connection = _connect(INDEX_PATH if path is None else path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            DELETE FROM canonical_passages
            WHERE instance_id = ? AND conversation_id = ? AND message_id = ?
            """,
            (instance_id, conversation_id, message_id),
        )
        connection.execute(
            """INSERT OR REPLACE INTO canonical_message_projection (
                instance_id, conversation_id, message_id, role, content,
                created_at, source_archive_id, canonicalizer_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (instance_id, conversation_id, message_id, role, content, created_at,
             source_archive_id, canonicalizer_version),
        )
        connection.execute(
            """
            INSERT INTO canonical_passages (
                instance_id, conversation_id, message_id, role, content,
                created_at, source_archive_id, canonicalizer_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                instance_id,
                conversation_id,
                message_id,
                role,
                content,
                created_at,
                source_archive_id,
                canonicalizer_version,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def ensure_archive_index(
    *, instance_id, include_unscoped=False, path=INDEX_PATH
):
    """Build missing derived search state without rewriting archive evidence."""
    index_path = Path(path)
    needs_rebuild = not index_path.exists()
    if not needs_rebuild:
        try:
            connection = sqlite3.connect(index_path)
            row = connection.execute(
                "SELECT COUNT(*) FROM canonical_passages WHERE instance_id = ?",
                (instance_id,),
            ).fetchone()
            projection = connection.execute(
                "SELECT COUNT(*) FROM canonical_message_projection WHERE instance_id = ?",
                (instance_id,),
            ).fetchone()
            needs_rebuild = row is None or int(row[0]) == 0 or projection is None or int(projection[0]) != int(row[0])
        except sqlite3.DatabaseError:
            needs_rebuild = True
        finally:
            if "connection" in locals():
                connection.close()

    if not needs_rebuild:
        return {"rebuilt": False, "indexed": 0}

    indexed = rebuild_archive_index(
        instance_id=instance_id,
        include_unscoped=include_unscoped,
        path=index_path,
    )
    return {"rebuilt": True, "indexed": indexed}


def _fts_query(query):
    terms = meaningful_query_terms(query)
    return " OR ".join(f'"{term}"' for term in terms)


def retrieve_archive_passages(
    query,
    *,
    instance_id,
    limit=5,
    path=INDEX_PATH,
    exclude_conversation_id=None,
    exclude_message_ids=(),
    minimum_overlap=None,
):
    if limit <= 0:
        return []

    match = _fts_query(query)
    if not match or not Path(path).exists():
        return []

    connection = _connect(path)
    try:
        fetch_limit = max(int(limit) * 5, int(limit))
        rows = connection.execute(
            """
            SELECT
                instance_id,
                conversation_id,
                message_id,
                role,
                content,
                created_at,
                source_archive_id,
                canonicalizer_version,
                bm25(canonical_passages) AS retrieval_score
            FROM canonical_passages
            WHERE canonical_passages MATCH ?
              AND instance_id = ?
            ORDER BY retrieval_score
            LIMIT ?
            """,
            (match, instance_id, fetch_limit),
        ).fetchall()
    finally:
        connection.close()

    query_terms = set(meaningful_query_terms(query))
    procedural_query = bool(query_terms & _PROCEDURAL_QUERY_TERMS)
    required_overlap = minimum_overlap if minimum_overlap is not None else (1 if len(query_terms) == 1 else max(2, (len(query_terms) + 1) // 2))
    excluded_messages = set(exclude_message_ids)
    results = []
    for row in rows:
        passage = dict(row)
        if (
            exclude_conversation_id
            and passage["conversation_id"] == exclude_conversation_id
        ):
            continue
        if passage["message_id"] in excluded_messages:
            continue
        content_terms = set(_query_terms(passage["content"]))
        overlap = len(query_terms & content_terms)
        if overlap < required_overlap:
            continue
        if (
            passage["role"] == "assistant"
            and _looks_procedural(passage["content"])
            and not procedural_query
        ):
            continue
        passage["matched_terms"] = sorted(query_terms & content_terms)
        results.append(passage)
        if len(results) >= limit:
            break
    return results


def continuity_window(*, instance_id, conversation_id, message_id, before=2, after=2, path=INDEX_PATH):
    """Return a bounded neighbor window from rebuildable indexed history."""
    connection = _connect(path)
    try:
        rows = connection.execute(
            """SELECT instance_id, conversation_id, message_id, role, content,
                      created_at, source_archive_id, canonicalizer_version
               FROM canonical_message_projection
               WHERE instance_id = ? AND conversation_id = ? ORDER BY created_at""",
            (instance_id, conversation_id),
        ).fetchall()
    finally:
        connection.close()
    index = next((i for i, row in enumerate(rows) if row["message_id"] == message_id), None)
    if index is None: return []
    return [dict(row) for row in rows[max(0, index-before):index+after+1]]


def messages_between(*, instance_id, start_at, end_at, limit=20, path=INDEX_PATH):
    """Bounded timestamp lookup over derived history; never mutates Archive."""
    connection = _connect(path)
    try:
        rows = connection.execute(
            """SELECT instance_id, conversation_id, message_id, role, content,
                      created_at, source_archive_id, canonicalizer_version
               FROM canonical_message_projection
               WHERE instance_id = ? AND created_at BETWEEN ? AND ?
               ORDER BY created_at LIMIT ?""",
            (instance_id, start_at, end_at, max(0, int(limit))),
        ).fetchall()
    finally: connection.close()
    return [dict(row) for row in rows]


def recent_indexed_messages(*, instance_id, limit=80, path=INDEX_PATH):
    """Bounded semantic-candidate fallback ordered by recency."""
    connection = _connect(path)
    try:
        rows = connection.execute(
            """SELECT instance_id, conversation_id, message_id, role, content,
                      created_at, source_archive_id, canonicalizer_version
               FROM canonical_message_projection WHERE instance_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (instance_id, max(0, int(limit))),
        ).fetchall()
    finally: connection.close()
    return [dict(row) for row in rows]
