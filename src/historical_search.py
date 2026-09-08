"""Explicit, read-only federation over distinct historical evidence domains.

This module is not imported by the normal Chat context builder. Search results
are navigation projections; only the referenced immutable source is authority.
"""

from abc import ABC, abstractmethod
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import stat

from src.capabilities.core import CapabilityDefinition
from src.capture.storage import read_metadata
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract
from src.history_staging import InheritedHistoryStore
from src.library.artifacts import require_id
from src.memory.archive_retrieval import INDEX_PATH, retrieve_archive_passages


ROOT = Path(__file__).resolve().parent.parent
STATE_ROOT = Path(os.environ.get("FAWKES_RUNTIME_STATE_ROOT") or ROOT)
ARCHIVE_META = STATE_ROOT / "archive" / "meta"
ARCHIVE_RAW = STATE_ROOT / "archive" / "raw"
DOMAINS = ("native_archive", "inherited_history")

MANUAL_HISTORY_SEARCH_DEFINITION = CapabilityDefinition(
    name="history.search_manual", version="1.0",
    display_name="Manual historical search",
    description="Explicitly search native canonical history and inert inherited history while preserving their distinct provenance and authority.",
    permissions=("history.search_manual",), effect="read_only_historical_inspection",
    modalities=MultimodalCapabilityContract(input_modalities=("text",), output_modalities=("text",)),
    authority=AuthorityContract(actions=("read",), execution_boundary="internal", authorization_mode="task_request"),
    privacy_handling="authenticated_instance_scoped_local_history_inspection",
    features=("federated_domain_search", "deterministic_navigation_snippets", "exact_source_navigation", "domain_availability"),
    appropriate_use=("rider explicitly opens History and searches", "rider manually inspects exact historical evidence"),
    inappropriate_use=("automatic Chat context", "Memory absorption", "identity classification", "native-boundary inference"),
    limitations=("lexical search only in this phase", "snippets are navigation aids", "inherited history remains unavailable to ordinary Chat"),
    platform_support=("server", "web", "future_native_clients"),
    presentation_options=("search_results", "exact_original_text"),
    dependencies=("canonical Archive index and/or inherited-history staging", "authenticated rider request"),
    provenance_requirements=("source domain", "history era", "source identity", "message identity", "immutable evidence reference", "native-boundary status"),
)


def _result_id(domain, instance_id, evidence_id):
    digest = hashlib.sha256(f"{domain}\x1f{instance_id}\x1f{evidence_id}".encode()).hexdigest()
    return f"history-result-{digest[:32]}"


def _snippet(text, query, limit=280):
    """Deterministic navigation excerpt, explicitly not a summary of truth."""
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    position = value.casefold().find(str(query).strip().casefold())
    start = max(0, position - limit // 3) if position >= 0 else 0
    end = min(len(value), start + limit)
    return ("…" if start else "") + value[start:end] + ("…" if end < len(value) else "")


class HistoricalSearchDomain(ABC):
    domain_id = None

    @abstractmethod
    def search(self, query, *, limit):
        """Return domain-native results or raise an availability error."""

    @abstractmethod
    def evidence(self, evidence_id):
        """Resolve a result back to authoritative source evidence."""


class NativeArchiveDomain(HistoricalSearchDomain):
    domain_id = "native_archive"

    def __init__(self, instance_id, *, index_path=None, meta_dir=None, raw_dir=None):
        self.instance_id = require_id(instance_id, "instance_id")
        self.index_path = Path(index_path) if index_path is not None else INDEX_PATH
        self.meta_dir = Path(meta_dir) if meta_dir is not None else ARCHIVE_META
        self.raw_dir = Path(raw_dir) if raw_dir is not None else ARCHIVE_RAW

    def _metadata(self, archive_id):
        require_id(archive_id, "archive_id")
        path = self.meta_dir / f"{archive_id}.json"
        try: record = read_metadata(path)
        except FileNotFoundError as exc: raise LookupError("native source evidence is unavailable") from exc
        except (OSError, ValueError) as exc: raise ValueError("native source metadata is malformed") from exc
        if record.get("archive_id") != archive_id or record.get("instance_id") != self.instance_id:
            raise PermissionError("native source evidence does not belong to this Phoenix")
        digest = record.get("sha256")
        if (not isinstance(digest, str) or len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)
                or type(record.get("size_bytes")) is not int or record["size_bytes"] < 0):
            raise ValueError("native source metadata lacks verifiable retained byte identity")
        return record

    def search(self, query, *, limit):
        if not self.index_path.is_file():
            raise FileNotFoundError("native Archive search projection is unavailable")
        try:
            passages = retrieve_archive_passages(query, instance_id=self.instance_id,
                                                  limit=limit, path=self.index_path, minimum_overlap=1)
        except sqlite3.DatabaseError as exc:
            raise ValueError("native Archive search projection is malformed") from exc
        results = []
        for position, item in enumerate(passages, 1):
            archive_id = item["source_archive_id"]
            # A projection row without owned source evidence is not safe to
            # present as navigable historical truth.
            metadata = self._metadata(archive_id)
            evidence_reference = {"domain": self.domain_id, "evidence_id": archive_id,
                                  "archive_id": archive_id, "sha256": metadata.get("sha256")}
            results.append({
                "schema_version": 1, "record_type": "historical_search_result",
                "result_id": _result_id(self.domain_id, self.instance_id, archive_id),
                "instance_id": self.instance_id, "domain": self.domain_id,
                "source_domain": "canonical_archive", "history_era": "native_phoenix_history",
                "authority_class": "immutable_original_source_evidence",
                "relationship_provenance": "native_runtime_interaction",
                "identity_attribution": "not_inferred_by_search",
                "native_boundary_status": metadata.get("native_boundary_status", "boundary_unknown"),
                "provider_source": {"provider": "phoenix_canonical_archive", "archive_id": archive_id},
                "conversation_id": item["conversation_id"], "message_id": item["message_id"],
                "source_message_id": item["message_id"], "role": item["role"],
                "created_at": item["created_at"], "navigation_snippet": _snippet(item["content"], query),
                "snippet_role": "navigation_only", "snippet_authoritative": False,
                "evidence_reference": evidence_reference, "domain_position": position,
                "rank_basis": "lexical_match_within_native_archive_only",
            })
        return results

    def evidence(self, evidence_id):
        metadata = self._metadata(evidence_id)
        raw_file = metadata.get("raw_file")
        if (not isinstance(raw_file, str) or not raw_file or raw_file in {".", ".."}
                or Path(raw_file).name != raw_file or "/" in raw_file or "\\" in raw_file):
            raise ValueError("native source raw-file reference is unsafe")
        raw_path = self.raw_dir / raw_file
        if raw_path.is_symlink() or raw_path.resolve().parent != self.raw_dir.resolve():
            raise ValueError("native source raw-file reference escapes selected Archive storage")
        try:
            fd = os.open(raw_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("native original evidence is not a regular file")
                raw = stream.read()
        except OSError as exc: raise LookupError("native original evidence is unavailable") from exc
        digest = hashlib.sha256(raw).hexdigest()
        if metadata["sha256"] != digest or metadata["size_bytes"] != len(raw):
            raise ValueError("native original evidence failed integrity verification")
        try: decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError): decoded = None
        exact_text = decoded.get("text") if isinstance(decoded, dict) else raw.decode(metadata.get("encoding") or "utf-8", errors="replace")
        return {"schema_version": 1, "record_type": "historical_source_evidence",
                "instance_id": self.instance_id, "domain": self.domain_id,
                "history_era": "native_phoenix_history", "native_boundary_status": metadata.get("native_boundary_status", "boundary_unknown"),
                "authority_class": "immutable_original_source_evidence", "archive_metadata": metadata,
                "evidence_reference": {"domain": self.domain_id, "evidence_id": evidence_id,
                                       "archive_id": evidence_id, "sha256": digest},
                "exact_original_text": exact_text, "original_record": decoded,
                "navigation_projection_authoritative": False}


class InheritedHistoryDomain(HistoricalSearchDomain):
    domain_id = "inherited_history"

    def __init__(self, instance_id, *, root=None):
        self.instance_id = require_id(instance_id, "instance_id")
        self.store = InheritedHistoryStore(instance_id, root=root)

    def search(self, query, *, limit):
        if not self.store.index_path.is_file():
            raise FileNotFoundError("inherited-history staging projection is unavailable")
        try: messages = self.store.search(query, limit=limit)
        except sqlite3.DatabaseError as exc: raise ValueError("inherited-history staging projection is malformed") from exc
        results = []
        for position, item in enumerate(messages, 1):
            evidence_id = item["message_id"]
            results.append({
                "schema_version": 1, "record_type": "historical_search_result",
                "result_id": _result_id(self.domain_id, self.instance_id, evidence_id),
                "instance_id": self.instance_id, "domain": self.domain_id,
                "source_domain": "inherited_history_staging", "history_era": item["history_era"],
                "authority_class": "immutable_imported_source_evidence",
                "relationship_provenance": item["relationship_provenance"],
                "identity_attribution": item["identity_attribution"],
                "native_boundary_status": item["native_boundary_status"],
                "provider_source": item["history_origin"], "export_id": item["export_id"],
                "conversation_id": item["conversation_id"], "message_id": item["message_id"],
                "source_conversation_id": item["source_conversation_id"],
                "source_message_id": item["source_message_id"], "source_node_id": item["source_node_id"],
                "role": item["role"], "created_at": item["created_at"],
                "navigation_snippet": _snippet(item["text"], query),
                "snippet_role": "navigation_only", "snippet_authoritative": False,
                "evidence_reference": {"domain": self.domain_id, "evidence_id": evidence_id,
                    "original_evidence_reference": item["original_evidence_reference"],
                    "export_id": item["export_id"], "original_digest": item["history_origin"]["original_digest"]},
                "domain_position": position, "rank_basis": "lexical_match_within_inherited_history_only",
            })
        return results

    def evidence(self, evidence_id):
        return self.store.original_message(evidence_id)


class FederatedHistoricalSearch:
    """Federate distinct domains without assigning cross-domain truth scores."""

    def __init__(self, instance_id, *, domains):
        self.instance_id = require_id(instance_id, "instance_id")
        self.domains = {domain.domain_id: domain for domain in domains}
        if set(self.domains) - set(DOMAINS):
            raise ValueError("unsupported historical search domain")

    def search(self, query, *, requested_domains=DOMAINS, limit=20):
        if not isinstance(query, str) or not query.strip(): raise ValueError("historical search query is required")
        if not isinstance(limit, int) or not 1 <= limit <= 100: raise ValueError("limit must be 1 to 100")
        requested = tuple(dict.fromkeys(requested_domains))
        if not requested or any(item not in DOMAINS for item in requested): raise ValueError("invalid historical search domain")
        per_domain = max(1, min(limit, (limit + len(requested) - 1) // len(requested)))
        found, statuses = {}, {}
        for domain_id in requested:
            adapter = self.domains.get(domain_id)
            if adapter is None:
                statuses[domain_id] = {"status": "unavailable", "reason": "domain adapter is not configured"}
                found[domain_id] = []
                continue
            try:
                found[domain_id] = adapter.search(query, limit=per_domain)
                statuses[domain_id] = {"status": "available", "reason": "bounded lexical projection searched"}
            except FileNotFoundError as exc:
                found[domain_id] = []; statuses[domain_id] = {"status": "unavailable", "reason": str(exc)}
            except (ValueError, PermissionError, LookupError) as exc:
                found[domain_id] = []; statuses[domain_id] = {"status": "degraded", "reason": str(exc)}
        # Round-robin preserves domain positions and prevents a score from one
        # projection masquerading as comparable authority in another domain.
        results = []
        for position in range(per_domain):
            for domain_id in requested:
                items = found[domain_id]
                if position < len(items) and len(results) < limit: results.append(items[position])
        return {"schema_version": 1, "record_type": "federated_historical_search",
                "instance_id": self.instance_id, "query": query, "requested_domains": list(requested),
                "domain_status": statuses, "results": results,
                "ranking_policy": "round_robin_domain_neutral_no_cross_domain_authority_score",
                "summary_policy": "deterministic_snippets_for_navigation_only",
                "source_policy": "original_evidence_is_authoritative", "automatic_chat_context": False}

    def evidence(self, domain_id, evidence_id):
        if domain_id not in DOMAINS: raise ValueError("invalid historical evidence domain")
        adapter = self.domains.get(domain_id)
        if adapter is None: raise LookupError("historical evidence domain is unavailable")
        return adapter.evidence(evidence_id)
