"""Deterministic, read-only qualification of staged inherited-history corpora.

This validator compares an inspection projection to its immutable original. It
does not classify identity, create Memory, establish continuity, or expose the
corpus to ordinary Chat.
"""

import hashlib
import json

from src.capabilities.core import CapabilityDefinition
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract
from src.history_staging import ChatGPTExportAdapter, InheritedHistoryStore
from src.library.artifacts import require_id


VALIDATOR_VERSION = "1.0"
INVARIANT_PROVENANCE = {
    "history_era": "inherited_history",
    "relationship_provenance": "founding_developmental",
    "identity_attribution": "unassessed",
    "native_boundary_status": "boundary_unknown",
}

HISTORICAL_CORPUS_VALIDATION_DEFINITION = CapabilityDefinition(
    name="history.validate_corpus", version=VALIDATOR_VERSION,
    display_name="Historical corpus validation",
    description="Explicitly compare staged inherited history with its immutable original and known navigation queries without granting cognitive authority.",
    permissions=("history.validate_corpus",), effect="read_only_historical_validation",
    modalities=MultimodalCapabilityContract(input_modalities=("document", "text"), output_modalities=("text",)),
    authority=AuthorityContract(actions=("read", "analyze"), execution_boundary="internal", authorization_mode="task_request"),
    privacy_handling="authenticated_instance_scoped_local_validation_no_provider_transmission",
    features=("original_digest_verification", "structural_reconciliation", "exact_text_reconciliation", "provenance_invariants", "known_query_checks"),
    appropriate_use=("rider explicitly validates an already staged inherited-history export",),
    inappropriate_use=("automatic Chat retrieval", "Memory absorption", "identity classification", "native-boundary inference"),
    limitations=("deterministic structural and lexical validation only", "real-corpus qualification requires a rider-authorized staged export"),
    platform_support=("server", "provider_neutral"), presentation_options=("validation_report",),
    dependencies=("history.import_stage", "history.search_manual", "immutable inherited-history original"),
    provenance_requirements=("export identity", "original digest", "processor version", "staged record identities", "native-boundary status"),
)


def _key(conversation_index, conversation_id, node_id, message_id=None):
    values = (conversation_index, str(conversation_id), str(node_id))
    return values if message_id is None else values + (str(message_id),)


def _validation_id(export_id, known_queries):
    digest = hashlib.sha256(
        f"{export_id}\x1f{VALIDATOR_VERSION}\x1f{json.dumps(known_queries, sort_keys=True)}".encode("utf-8")
    ).hexdigest()
    return f"history-validation-{digest[:32]}"


class HistoricalCorpusValidator:
    """Provider-adapter-aware validator with no durable or cognitive writes."""

    def __init__(self, store, *, adapters=None):
        if not isinstance(store, InheritedHistoryStore):
            raise TypeError("inherited-history store is required")
        self.store = store
        adapters = adapters or (ChatGPTExportAdapter(),)
        self.adapters = {(item.provider_id, item.format_id): item for item in adapters}

    def validate(self, export_id, *, known_queries=()):
        export_id = require_id(export_id, "export_id")
        if not isinstance(known_queries, (list, tuple)):
            raise ValueError("known_queries must be a bounded list or tuple")
        if len(known_queries) > 50:
            raise ValueError("known_queries exceeds the validation limit")
        snapshot = self.store.inspection_snapshot(export_id)
        manifest = snapshot["manifest"]
        origin = manifest.get("history_origin") or {}
        adapter = self.adapters.get((origin.get("provider"), origin.get("format")))
        if adapter is None:
            raise ValueError("no validation adapter is registered for this inherited-history source")
        original = self.store.root / manifest["original_evidence_reference"]
        try:
            raw = original.read_bytes()
        except OSError as exc:
            raise LookupError("immutable inherited-history original is unavailable") from exc
        actual_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        checks = []

        def check(name, passed, actual, expected):
            checks.append({"check": name, "status": "pass" if passed else "fail",
                           "actual": actual, "expected": expected})

        check("original_digest", actual_digest == origin.get("original_digest"),
              actual_digest, origin.get("original_digest"))
        source_conversations, source_warnings = adapter.parse(raw)
        source_nodes = {}
        source_messages = {}
        for conversation in source_conversations:
            prefix = (conversation["source_conversation_index"], conversation["source_conversation_id"])
            for node in conversation["branch_nodes"]:
                source_nodes[_key(*prefix, node["source_node_id"])] = node
            for message in conversation["messages"]:
                source_messages[_key(*prefix, message["source_node_id"], message["source_message_id"])] = message

        staged_conversations = {(item["source_conversation_index"], item["source_conversation_id"]): item
                                for item in snapshot["conversations"]}
        staged_nodes = {_key(item["source_conversation_index"], item["source_conversation_id"], item["source_node_id"]): item
                        for item in snapshot["nodes"]}
        staged_messages = {_key(item["source_conversation_index"], item["source_conversation_id"],
                                item["source_node_id"], item["source_message_id"]): item
                           for item in snapshot["messages"]}
        source_conversation_keys = {(item["source_conversation_index"], item["source_conversation_id"])
                                    for item in source_conversations}
        check("conversation_identity", set(staged_conversations) == source_conversation_keys,
              len(staged_conversations), len(source_conversation_keys))
        check("node_identity", set(staged_nodes) == set(source_nodes), len(staged_nodes), len(source_nodes))
        check("message_identity", set(staged_messages) == set(source_messages), len(staged_messages), len(source_messages))
        check("manifest_counts", manifest.get("conversation_count") == len(source_conversations)
              and manifest.get("message_count") == len(source_messages),
              [manifest.get("conversation_count"), manifest.get("message_count")],
              [len(source_conversations), len(source_messages)])
        check("parser_warnings", manifest.get("warnings") == source_warnings,
              manifest.get("warnings"), source_warnings)

        conversation_exact = all(
            staged_conversations.get((item["source_conversation_index"], item["source_conversation_id"]), {}).get(field) == item[field]
            for item in source_conversations for field in ("title", "created_at", "updated_at", "current_node")
        )
        check("conversation_fields", conversation_exact, conversation_exact, True)
        node_exact = all(
            staged_nodes.get(key, {}).get(field) == source.get(field)
            for key, source in source_nodes.items()
            for field in ("source_parent_node_id", "source_child_node_ids", "source_message_id")
        )
        check("branch_structure", node_exact, node_exact, True)
        message_exact = all(
            staged_messages.get(key, {}).get(field) == source.get(field)
            for key, source in source_messages.items()
            for field in ("role", "author_name", "created_at", "updated_at", "content_type", "text",
                          "source_parent_node_id", "source_child_node_ids")
        )
        check("message_fields_and_exact_text", message_exact, message_exact, True)

        records = [manifest, *snapshot["conversations"], *snapshot["nodes"], *snapshot["messages"]]
        provenance_exact = all(all(record.get(field) == expected for field, expected in INVARIANT_PROVENANCE.items())
                               for record in records)
        check("inherited_provenance", provenance_exact, provenance_exact, True)
        no_native_promotion = all(record.get("native_boundary_status") != "proven_native" for record in records)
        check("no_native_promotion", no_native_promotion, no_native_promotion, True)

        query_reports = []
        for specification in known_queries:
            if isinstance(specification, str):
                query, minimum = specification, 1
            elif isinstance(specification, dict):
                query, minimum = specification.get("query"), specification.get("minimum_results", 1)
            else:
                raise ValueError("known queries must be strings or query specifications")
            if (not isinstance(query, str) or not query.strip() or len(query) > 500
                    or not isinstance(minimum, int) or minimum < 0 or minimum > 100):
                raise ValueError("known query specification is invalid")
            hits = self.store.search(query, limit=100, export_id=export_id)
            navigable = True
            for hit in hits:
                evidence = self.store.original_message(hit["message_id"])
                if evidence["exact_original_text"] != hit["text"]:
                    navigable = False
            passed = len(hits) >= minimum and navigable
            query_reports.append({"query": query, "minimum_results": minimum,
                                  "actual_results": len(hits), "exact_navigation": navigable,
                                  "status": "pass" if passed else "fail"})
        check("known_queries", all(item["status"] == "pass" for item in query_reports),
              [item["status"] for item in query_reports], ["pass"] * len(query_reports))

        failed = [item["check"] for item in checks if item["status"] == "fail"]
        validation_id = _validation_id(export_id, known_queries)
        return {
            "schema_version": 1, "record_type": "historical_corpus_validation_report",
            "validation_id": validation_id, "validator_version": VALIDATOR_VERSION,
            "instance_id": self.store.instance_id, "export_id": export_id,
            "status": "failed" if failed else ("qualified_with_source_warnings" if source_warnings else "qualified"),
            "checks": checks, "failed_checks": failed, "source_warnings": source_warnings,
            "known_queries": query_reports, "read_only": True,
            "source_evidence_authority": "immutable_original",
            "navigation_projection_authoritative": False,
            "automatic_chat_context": False, "memory_promotion": "prohibited",
            **INVARIANT_PROVENANCE,
        }
