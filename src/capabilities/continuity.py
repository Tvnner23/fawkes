"""Bounded, provider-neutral retrieval of referential interaction history."""

from datetime import datetime, timedelta, timezone
import os
import re
from zoneinfo import ZoneInfo

from src.capabilities.core import CapabilityDefinition
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract
from src.memory.archive_retrieval import (
    continuity_window, messages_between, recent_indexed_messages, retrieve_archive_passages,
)


CONTINUITY_RETRIEVAL_DEFINITION = CapabilityDefinition(
    name="continuity.retrieve", version="1.0", display_name="Conversation continuity retrieval",
    description="Retrieve bounded relevant evidence from this Phoenix's indexed canonical interaction history.",
    effect="read_only_evidence",
    modalities=MultimodalCapabilityContract(input_modalities=("text",), output_modalities=("text",)),
    authority=AuthorityContract(actions=("read", "analyze"), execution_boundary="internal", authorization_mode="pre_granted"),
    privacy_handling="instance_scoped_rider_visible",
    features=("same_conversation_history", "cross_conversation_history", "semantic_reranking", "timestamp_lookup", "neighbor_context", "ambiguity_reporting"),
    appropriate_use=("natural reference to a prior person, course, project, decision, result, problem, or reason", "rider asks what was discussed earlier", "a timestamp identifies prior interaction evidence"),
    inappropriate_use=("casual self-contained conversation", "dumping full history into working context", "claiming absence from a failed search", "using history from another Phoenix"),
    limitations=("bounded candidate retrieval can miss weakly connected references", "semantic reranking depends on the configured model", "a failed lookup does not prove a message was never stored", "ambiguous candidates require clarification"),
    platform_support=("server", "web", "future_native_clients"),
    presentation_options=("text",), dependencies=("canonical Archive derived index",),
    provenance_requirements=("conversation id", "message id", "source Archive id", "captured timestamp", "retrieval status"),
)

_REFERENCE = re.compile(
    r"\b(?:the one|that (?!is\b|was\b|sounds?\b|means?\b|would\b|could\b|should\b)|"
    r"those |we (?:discussed|talked about|decided|found|researched)|i (?:told|mentioned|said)|"
    r"earlier|previously|before|last time|first message|at \d{1,2}:\d{2})",
    re.I,
)
_CLOCK = re.compile(r"\b(?:at\s+)?(\d{1,2}):(\d{2})\s*(a\.?m\.?|p\.?m\.?)?\b", re.I)


def is_continuity_reference(text):
    return bool(_REFERENCE.search(str(text or "")))


def timestamp_bounds(text, *, now=None, timezone_name=None):
    match = _CLOCK.search(str(text or ""))
    if not match: return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if minute > 59 or hour > 23 or hour == 0 and match.group(3): return None
    marker = (match.group(3) or "").lower().replace(".", "")
    if marker:
        if hour > 12: return None
        if marker == "pm" and hour != 12: hour += 12
        if marker == "am" and hour == 12: hour = 0
    zone = ZoneInfo(timezone_name or os.getenv("FAWKES_TIMEZONE", "America/Chicago"))
    current = now or datetime.now(zone)
    if current.tzinfo is None: current = current.replace(tzinfo=zone)
    local = current.astimezone(zone).replace(hour=hour, minute=minute, second=0, microsecond=0)
    start = (local - timedelta(minutes=5)).astimezone(timezone.utc).isoformat()
    end = (local + timedelta(minutes=5)).astimezone(timezone.utc).isoformat()
    return start, end, local.astimezone(timezone.utc).isoformat()


class ContinuityRetriever:
    def __init__(self, *, instance_id, semantic_provider=None, index_path=None):
        self.instance_id = instance_id
        self.semantic_provider = semantic_provider
        self.index_path = index_path

    def retrieve(self, query, *, exclude_message_ids=(), limit=8, now=None):
        kwargs = {"instance_id": self.instance_id, "limit": 40, "exclude_message_ids": exclude_message_ids, "minimum_overlap": 1}
        if self.index_path is not None: kwargs["path"] = self.index_path
        candidates = retrieve_archive_passages(query, **kwargs)
        bounds = timestamp_bounds(query, now=now)
        timestamp_hits = []
        if bounds:
            time_kwargs = {"instance_id": self.instance_id, "start_at": bounds[0], "end_at": bounds[1], "limit": 50}
            if self.index_path is not None: time_kwargs["path"] = self.index_path
            timestamp_hits = messages_between(**time_kwargs)
            target = datetime.fromisoformat(bounds[2])
            timestamp_hits.sort(key=lambda item: (
                item.get("role") != "user",
                abs((datetime.fromisoformat(item["created_at"]) - target).total_seconds()),
            ))
        excluded = set(exclude_message_ids)
        if self.semantic_provider is not None and len(candidates) < 20:
            recent_kwargs = {"instance_id": self.instance_id, "limit": 80}
            if self.index_path is not None: recent_kwargs["path"] = self.index_path
            candidates.extend(recent_indexed_messages(**recent_kwargs))
        by_id = {item["message_id"]: item for item in (*timestamp_hits, *candidates) if item["message_id"] not in excluded}
        candidates = list(by_id.values())
        if not candidates:
            return {"attempted": True, "status": "no_match", "passages": [], "candidate_count": 0,
                    "limitations": "No bounded indexed candidate matched; this does not prove the interaction was never stored."}

        anchors = list(timestamp_hits)
        ranking = "timestamp" if anchors else "lexical_fallback"
        if not anchors and self.semantic_provider is not None:
            mapped = [{**item, "memory_id": item["message_id"], "memory_type": "historical_interaction",
                       "importance": 0.5, "confidence": 1.0} for item in candidates]
            try:
                anchors = self.semantic_provider.rank_memories(query=query, memories=tuple(mapped))[:3]
                ranking = "semantic" if anchors else "semantic_no_match"
            except Exception:
                anchors = candidates[:3]
                ranking = "lexical_fallback"
        elif not anchors:
            anchors = candidates[:3]
        if not anchors:
            return {"attempted": True, "status": "no_match", "passages": [], "candidate_count": len(candidates),
                    "limitations": "Candidates existed, but semantic relevance was not established."}

        passages = []
        seen = set(excluded)
        for anchor in anchors[:3]:
            window_kwargs = {"instance_id": self.instance_id, "conversation_id": anchor["conversation_id"], "message_id": anchor["message_id"], "before": 1, "after": 1}
            if self.index_path is not None: window_kwargs["path"] = self.index_path
            for item in continuity_window(**window_kwargs):
                if item["message_id"] in seen: continue
                seen.add(item["message_id"]); item["retrieval_role"] = "anchor" if item["message_id"] == anchor["message_id"] else "neighbor"; passages.append(item)
                if len(passages) >= limit: break
            if len(passages) >= limit: break
        return {"attempted": True, "status": "found", "passages": passages,
                "candidate_count": len(candidates), "anchor_count": len(anchors), "ranking": ranking,
                "ambiguous": len(anchors) > 1 and ranking != "timestamp"}
