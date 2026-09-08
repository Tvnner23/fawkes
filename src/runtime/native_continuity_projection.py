"""Deterministic, read-only Phase 8 projection over eligible native Archive evidence."""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from calendar import monthrange
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.capabilities.core import CapabilityDefinition
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract
from src.runtime.retrieval_planner import contradiction_group_ids


PROCESSOR_ID = "native-continuity-projection"
PROCESSOR_VERSION = "1.0"
CAPABILITY_VERSION = "1.7"

NATIVE_CONTINUITY_PROJECTION_DEFINITION = CapabilityDefinition(
    name="continuity.native_projection", version=CAPABILITY_VERSION,
    display_name="Native Archive Continuity Projection",
    description="Derive stable, bounded temporal, neighbor, ambiguity, duplicate, and contradiction-preserving relationships over eligible native Archive evidence.",
    effect="read_only_rebuildable_native_archive_projection",
    modalities=MultimodalCapabilityContract(input_modalities=("text",), output_modalities=("text",)),
    authority=AuthorityContract(actions=("read", "analyze"), execution_boundary="internal", authorization_mode="pre_granted"),
    privacy_handling="eligible_native_archive_only_no_inherited_history_no_canonical_mutation",
    features=("stable_native_evidence_identity", "temporal_order", "neighbor_relationships",
              "conservative_entity_mentions", "explicit_ambiguity_sets", "duplicate_relationships",
              "contradiction_preservation", "stale_projection_detection",
              "query_aware_candidate_generation", "bounded_neighbor_expansion", "temporal_constraints",
              "request_time_binding", "rider_timezone_binding", "relative_time_windows", "reference_candidate_generation",
              "explicit_source_original_preference", "non_mutating_context_duplicate_suppression",
              "bounded_multi_hop_thread_navigation", "verified_native_reference_traversal",
              "rider_facing_ambiguity_clarification", "served_validated_choice_consumption",
              "representative_native_corpus_qualified"),
    appropriate_use=("annotate eligible native Archive evidence for bounded continuity planning",),
    inappropriate_use=("resolve identity", "merge canonical records", "choose truth", "retrieve inherited history"),
    limitations=("entity mentions are deterministic lexical observations, not resolved entities",
                 "near-duplicate relationships are conservative hints", "contradictions require explicit upstream relationship metadata"),
    dependencies=("eligible native Archive candidates", "canonical Archive projection"),
    provenance_requirements=("Phoenix instance", "conversation", "message", "source Archive", "processor version", "source frontier digest"),
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _normalized(text):
    return " ".join(re.findall(r"[a-z0-9]+", str(text).casefold()))


def _entity_mentions(text):
    # Deliberately conservative lexical mentions. These are not entity IDs.
    ignored = {"I", "The", "This", "That", "We", "You", "It", "What", "When", "Where", "Why", "How"}
    values = []
    for match in re.finditer(r"\b(?:[A-Z][a-z0-9'-]+(?:\s+[A-Z][a-z0-9'-]+){0,2})\b", str(text)):
        value = match.group(0).strip()
        if value not in ignored and value not in values:
            values.append(value)
    return tuple(values)


def stable_native_evidence_id(item):
    return "native-evidence-" + _digest({
        "instance_id": item.get("instance_id"), "conversation_id": item.get("conversation_id"),
        "message_id": item.get("message_id") or item.get("evidence_id"),
        "source_archive_id": item.get("source_archive_id") or
            (item.get("original_evidence_reference") or {}).get("archive_id"),
    })[:32]


_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_REFERENCE = re.compile(r"\b(?:that|those|the one|which one|earlier|previous(?:ly)?|before|last time)\b", re.I)
_QUERY_STOP = {"that", "those", "the", "one", "which", "earlier", "previously", "before",
               "after", "between", "on", "from", "during", "what", "when", "where", "was",
               "were", "did", "we", "i", "you", "it", "this", "about"}


def _month_shift(year, month, delta):
    ordinal = year * 12 + month - 1 + delta
    return divmod(ordinal, 12)[0], divmod(ordinal, 12)[1] + 1


def _local_day_window(local_date, zone):
    start = datetime(local_date.year, local_date.month, local_date.day, tzinfo=zone)
    return start, start + timedelta(days=1)


def _window(start, end, kind):
    return {"kind": kind, "start": start.astimezone(timezone.utc).isoformat(),
            "end": (end.astimezone(timezone.utc) - timedelta(microseconds=1)).isoformat()}


def interpret_native_continuity_query(query, *, request_timestamp=None, rider_timezone=None):
    """Conservative, provider-neutral interpretation; no entity resolution."""
    dates = _DATE.findall(str(query))
    lower = str(query).casefold()
    temporal = None; timestamp_status = "not_required"; zone_name = rider_timezone or "UTC"
    zone_source = "explicit_rider_timezone" if rider_timezone else "deterministic_utc_fallback"
    anchor = None
    try:
        zone = ZoneInfo(zone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC"); zone_name = "UTC"; zone_source = "invalid_timezone_utc_fallback"
    if request_timestamp is not None:
        try:
            parsed = datetime.fromisoformat(str(request_timestamp))
            if parsed.tzinfo is None: raise ValueError("request timestamp must include offset")
            anchor = parsed.astimezone(zone); timestamp_status = "bound"
        except ValueError:
            timestamp_status = "invalid"
    try:
        def date_start(value):
            parsed=datetime.strptime(value,"%Y-%m-%d")
            return datetime(parsed.year,parsed.month,parsed.day,tzinfo=zone)
        if "between" in lower and len(dates) >= 2:
            temporal = _window(date_start(dates[0]),date_start(dates[1])+timedelta(days=1),"between_dates")
        elif dates and re.search(r"\b(?:on|during)\b", lower):
            temporal = _window(date_start(dates[0]),date_start(dates[0])+timedelta(days=1),"on_date")
        elif dates and "after" in lower:
            temporal = {"kind": "after_date", "start": date_start(dates[0]).astimezone(timezone.utc).isoformat(), "end": None}
        elif dates and "before" in lower:
            temporal = {"kind": "before_date", "start": None, "end": date_start(dates[0]).astimezone(timezone.utc).isoformat()}
        if temporal:
            for value in (temporal.get("start"), temporal.get("end")):
                if value: datetime.fromisoformat(value)
    except ValueError:
        temporal = None
    if temporal is None and anchor is not None:
        if re.search(r"\byesterday\b", lower):
            start,end=_local_day_window((anchor-timedelta(days=1)).date(),zone); temporal=_window(start,end,"yesterday")
        elif re.search(r"\btoday\b", lower):
            start,end=_local_day_window(anchor.date(),zone); temporal=_window(start,end,"today")
        elif re.search(r"\btomorrow\b", lower):
            start,end=_local_day_window((anchor+timedelta(days=1)).date(),zone); temporal=_window(start,end,"tomorrow")
        elif re.search(r"\b(?:this|last) week\b", lower):
            delta=-7 if "last week" in lower else 0
            start_date=(anchor+timedelta(days=delta-anchor.weekday())).date()
            start,end=_local_day_window(start_date,zone); temporal=_window(start,start+timedelta(days=7),"last_week" if delta else "this_week")
        elif re.search(r"\b(?:this|last) month\b", lower):
            year,month=(anchor.year,anchor.month) if "this month" in lower else _month_shift(anchor.year,anchor.month,-1)
            start=datetime(year,month,1,tzinfo=zone); next_year,next_month=_month_shift(year,month,1)
            temporal=_window(start,datetime(next_year,next_month,1,tzinfo=zone),"last_month" if "last month" in lower else "this_month")
        else:
            ago=re.search(r"\b(\d{1,3})\s+(day|week|month)s?\s+ago\b",lower)
            if ago:
                count=int(ago.group(1)); unit=ago.group(2)
                if 1 <= count <= 120:
                    if unit=="day":
                        start,end=_local_day_window((anchor-timedelta(days=count)).date(),zone)
                    elif unit=="week":
                        target=anchor-timedelta(weeks=count); start_date=(target-timedelta(days=target.weekday())).date()
                        start,_=_local_day_window(start_date,zone); end=start+timedelta(days=7)
                    else:
                        year,month=_month_shift(anchor.year,anchor.month,-count); start=datetime(year,month,1,tzinfo=zone)
                        next_year,next_month=_month_shift(year,month,1); end=datetime(next_year,next_month,1,tzinfo=zone)
                    temporal=_window(start,end,f"{count}_{unit}s_ago")
            elif re.search(r"\brecently\b",lower):
                temporal={"kind":"recently_bounded_7_days","start":(anchor.astimezone(timezone.utc)-timedelta(days=7)).isoformat(),"end":anchor.astimezone(timezone.utc).isoformat()}
            elif re.search(r"\bearlier\b",lower):
                temporal={"kind":"earlier_bounded_30_days","start":(anchor.astimezone(timezone.utc)-timedelta(days=30)).isoformat(),"end":anchor.astimezone(timezone.utc).isoformat()}
    reference_kinds=[]
    patterns=(("conversation",r"\bthat conversation\b"),("discussed_thing",r"\b(?:the thing|what) we discussed\b"),
              ("professor",r"\bthat professor\b"),("course",r"\bthat course\b"),("project",r"\bthat project\b"),
              ("person",r"\bthat person\b"),("previous_message",r"\bprevious message\b"),
              ("next_message",r"\bnext message\b"),("nearby_context",r"\bnearby context\b"),
              ("earlier_in_conversation",r"\bearlier in (?:that|the) conversation\b"),
              ("later_in_conversation",r"\blater in (?:that|the) conversation\b"))
    for kind,pattern in patterns:
        if re.search(pattern,lower): reference_kinds.append(kind)
    terms = tuple(sorted({term for term in re.findall(r"[a-z0-9]+", lower)
                          if len(term) > 2 and term not in _QUERY_STOP and not re.fullmatch(r"20\d{2}|\d{2}", term)}))
    result = {"schema_version": 1, "interpreter_version": "native-continuity-query-v2",
              "reference_intent": bool(_REFERENCE.search(str(query)) or reference_kinds),
              "reference_kinds": reference_kinds,
              "query_terms_sha256": _digest(terms), "query_term_count": len(terms),
              "temporal_constraint": temporal,
              "request_timestamp": str(request_timestamp) if request_timestamp is not None else None,
              "request_timestamp_status": timestamp_status,
              "rider_timezone": zone_name, "timezone_source": zone_source,
              "request_local_timestamp": anchor.isoformat() if anchor else None}
    result["interpretation_id"] = "continuity-query-" + _digest(result)[:24]
    return result, terms


class NativeArchiveCandidateGenerator:
    """Generate references only from already independently eligible metadata."""

    version = "native-archive-candidate-generator-v4"
    reference_relationship_types = {
        "thread_previous", "thread_next", "thread_related", "reference_to",
    }

    def generate(self, *, query, eligible_metadata, request_timestamp=None, rider_timezone=None,
                 max_total=24, max_per_conversation=4,
                 neighbor_radius=1, max_thread_hops=2, max_relationship_expansions=8):
        interpretation, query_terms = interpret_native_continuity_query(
            query, request_timestamp=request_timestamp, rider_timezone=rider_timezone)
        pool = [dict(item) for item in eligible_metadata]
        by_id = {item["evidence_id"]: item for item in pool}
        by_reference = {(str((item.get("original_evidence_reference") or {}).get("archive_id", "")),
                         str((item.get("original_evidence_reference") or {}).get("message_id", ""))): item
                        for item in pool}
        generated = {}
        relationship_ambiguities = []

        temporal = interpretation.get("temporal_constraint")
        temporal_start = datetime.fromisoformat(temporal["start"]).astimezone(timezone.utc) if temporal and temporal["start"] else None
        temporal_end = datetime.fromisoformat(temporal["end"]).astimezone(timezone.utc) if temporal and temporal["end"] else None

        def inside_temporal_window(item):
            if temporal is None: return True
            created = item.get("created_at")
            if not isinstance(created, str): return False
            try:
                instant = datetime.fromisoformat(created)
                if instant.tzinfo is None: return False
                instant = instant.astimezone(timezone.utc)
            except ValueError:
                return False
            return ((temporal_start is None or instant >= temporal_start)
                    and (temporal_end is None or instant <= temporal_end))

        def add(item, reason, seed=None, *, hop_depth=None, relationship_type=None):
            entry = generated.setdefault(item["evidence_id"], {**item, "candidate_generation_reasons": []})
            detail = {"reason": reason, "relationship_id": "candidate-relation-" + _digest({
                "version": self.version, "evidence_id": item["evidence_id"], "reason": reason,
                "seed": seed, "hop_depth": hop_depth, "relationship_type": relationship_type,
                "interpretation_id": interpretation["interpretation_id"]})[:24]}
            if seed: detail["seed_evidence_id"] = seed
            if hop_depth is not None: detail["hop_depth"] = hop_depth
            if relationship_type is not None: detail["relationship_type"] = relationship_type
            if detail not in entry["candidate_generation_reasons"]:
                entry["candidate_generation_reasons"].append(detail)

        for item in pool:
            terms = set(item.get("local_lexical_terms", ()))
            if query_terms and terms.intersection(query_terms) and inside_temporal_window(item):
                add(item, "direct_lexical_metadata_match")

        generic_reference = bool(set(interpretation["reference_kinds"]) & {
            "conversation","discussed_thing","previous_message","next_message","nearby_context",
            "earlier_in_conversation","later_in_conversation"})
        if generic_reference and not generated and interpretation["request_timestamp_status"] == "bound":
            request_instant=datetime.fromisoformat(interpretation["request_timestamp"]).astimezone(timezone.utc)
            recent_by_conversation={}
            for item in pool:
                try: instant=datetime.fromisoformat(item["created_at"]).astimezone(timezone.utc)
                except (ValueError,TypeError): continue
                if instant <= request_instant and instant >= request_instant-timedelta(days=30):
                    current=recent_by_conversation.get(item.get("conversation_id"))
                    if current is None or (item["created_at"],item["evidence_id"]) > (current["created_at"],current["evidence_id"]):
                        recent_by_conversation[item.get("conversation_id")]=item
            for item in recent_by_conversation.values(): add(item,"reference_recent_conversation_anchor")

        if temporal:
            for item in pool:
                if inside_temporal_window(item):
                    add(item, "explicit_temporal_constraint")

        seeds = sorted(generated)
        by_conversation = {}
        for item in pool:
            by_conversation.setdefault(item.get("conversation_id"), []).append(item)
        for items in by_conversation.values():
            items.sort(key=lambda x: (str(x.get("created_at")), str(x.get("evidence_id"))))
            positions = {item["evidence_id"]: position for position, item in enumerate(items)}
            for seed in seeds:
                if seed not in positions: continue
                position = positions[seed]
                offsets=range(-neighbor_radius,neighbor_radius+1)
                if "previous_message" in interpretation["reference_kinds"] or "earlier_in_conversation" in interpretation["reference_kinds"]: offsets=range(-neighbor_radius,0)
                elif "next_message" in interpretation["reference_kinds"] or "later_in_conversation" in interpretation["reference_kinds"]: offsets=range(1,neighbor_radius+1)
                for offset in offsets:
                    if offset and 0 <= position + offset < len(items):
                        add(items[position + offset], "conversation_neighbor", seed=seed)

        navigation_reference = bool(set(interpretation["reference_kinds"]) & {
            "conversation", "discussed_thing", "previous_message", "next_message",
            "nearby_context", "earlier_in_conversation", "later_in_conversation",
        })
        if navigation_reference and max_thread_hops > 1:
            for seed in seeds:
                item = by_id.get(seed)
                if item is None: continue
                items = by_conversation.get(item.get("conversation_id"), ())
                positions = {candidate["evidence_id"]: position for position, candidate in enumerate(items)}
                position = positions.get(seed)
                if position is None: continue
                directions = (-1, 1)
                if set(interpretation["reference_kinds"]) & {"previous_message", "earlier_in_conversation"}:
                    directions = (-1,)
                elif set(interpretation["reference_kinds"]) & {"next_message", "later_in_conversation"}:
                    directions = (1,)
                for hop in range(2, max_thread_hops + 1):
                    for direction in directions:
                        target_position = position + direction * hop
                        if 0 <= target_position < len(items):
                            add(items[target_position], "conversation_thread_hop", seed=seed,
                                hop_depth=hop,
                                relationship_type="thread_previous" if direction < 0 else "thread_next")

        # Explicit reference traversal is body-free and can only resolve inside
        # the independently eligible pool supplied by the Phase 7 boundary.
        if interpretation["reference_intent"] and max_relationship_expansions > 0:
            frontier = [(seed, seed, 0) for seed in seeds]
            visited_edges = set()
            expansions = 0
            cursor = 0
            while cursor < len(frontier) and expansions < max_relationship_expansions:
                current_id, root_seed, depth = frontier[cursor]; cursor += 1
                current = by_id.get(current_id)
                if current is None or depth >= max_thread_hops: continue
                valid = []
                for edge in current.get("native_reference_relationships", ()):
                    if not isinstance(edge, dict): continue
                    relationship_type = edge.get("relationship")
                    target_ref = edge.get("target")
                    if (relationship_type not in self.reference_relationship_types
                            or edge.get("qualification_status") != "verified"
                            or not isinstance(target_ref, dict)):
                        continue
                    target = by_reference.get((str(target_ref.get("archive_id", "")),
                                               str(target_ref.get("message_id", ""))))
                    if target is not None:
                        valid.append((relationship_type, target))
                valid.sort(key=lambda value: (value[0], value[1]["evidence_id"]))
                if len({target["evidence_id"] for _, target in valid}) > 1:
                    ambiguity_id = "reference-ambiguity-" + _digest({
                        "version": self.version, "source": current_id,
                        "targets": sorted(target["evidence_id"] for _, target in valid)})[:24]
                    ambiguity = {"ambiguity_set_id": ambiguity_id,
                        "candidate_evidence_ids": sorted({target["evidence_id"] for _, target in valid}),
                        "basis": "multiple_verified_native_reference_targets",
                        "source_evidence_id": current_id}
                    if ambiguity not in relationship_ambiguities:
                        relationship_ambiguities.append(ambiguity)
                for relationship_type, target in valid:
                    edge_key = (current_id, relationship_type, target["evidence_id"])
                    if edge_key in visited_edges: continue
                    visited_edges.add(edge_key)
                    expansions += 1
                    add(target, "verified_native_reference", seed=root_seed,
                        hop_depth=depth + 1, relationship_type=relationship_type)
                    frontier.append((target["evidence_id"], root_seed, depth + 1))
                    if expansions >= max_relationship_expansions: break

        # Stable per-conversation caps plus rounds prevent one thread starvation.
        groups = {}
        for item in generated.values():
            groups.setdefault(str(item.get("conversation_id")), []).append(item)
        for items in groups.values():
            items.sort(key=lambda x: (str(x.get("created_at")), str(x.get("evidence_id"))))
        selected = []; cursor = 0
        while len(selected) < max_total and any(cursor < min(len(items), max_per_conversation) for items in groups.values()):
            for conversation_id in sorted(groups):
                items = groups[conversation_id]
                if cursor < min(len(items), max_per_conversation):
                    selected.append(items[cursor])
                    if len(selected) >= max_total: break
            cursor += 1
        reference_ambiguity_sets=list(relationship_ambiguities)
        selected_by_id = {item["evidence_id"]: item for item in selected}
        for ambiguity in relationship_ambiguities:
            for evidence_id in ambiguity["candidate_evidence_ids"]:
                if evidence_id in selected_by_id:
                    selected_by_id[evidence_id].setdefault(
                        "candidate_reference_ambiguity_set_ids", []).append(
                            ambiguity["ambiguity_set_id"])
        direct_reference_matches = [item for item in selected
            if interpretation["reference_intent"] and any(
                reason["reason"] == "direct_lexical_metadata_match"
                for reason in item["candidate_generation_reasons"])]
        if len({item.get("conversation_id") for item in direct_reference_matches}) > 1:
            ambiguity_id = "reference-ambiguity-" + _digest({
                "version": self.version,
                "direct_reference_matches": sorted(item["evidence_id"] for item in direct_reference_matches),
            })[:24]
            direct_ambiguity = {"ambiguity_set_id": ambiguity_id,
                "candidate_evidence_ids": sorted(item["evidence_id"] for item in direct_reference_matches),
                "basis": "multiple_direct_native_reference_matches"}
            reference_ambiguity_sets.append(direct_ambiguity)
            for item in direct_reference_matches:
                item.setdefault("candidate_reference_ambiguity_set_ids", []).append(ambiguity_id)
        reference_anchors=[item for item in selected if any(x["reason"]=="reference_recent_conversation_anchor" for x in item["candidate_generation_reasons"])]
        if len({item.get("conversation_id") for item in reference_anchors}) > 1:
            ambiguity_id="reference-ambiguity-"+_digest(sorted(item["evidence_id"] for item in reference_anchors))[:24]
            reference_ambiguity_sets.append({"ambiguity_set_id":ambiguity_id,
                "candidate_evidence_ids":sorted(item["evidence_id"] for item in reference_anchors),
                "basis":"multiple_recent_conversations_no_reference_resolution"})
            for item in reference_anchors: item.setdefault("candidate_reference_ambiguity_set_ids",[]).append(ambiguity_id)
        ambiguity_choice_descriptors=[]
        for ambiguity in reference_ambiguity_sets:
            choices=[]
            for evidence_id in ambiguity["candidate_evidence_ids"]:
                item=selected_by_id.get(evidence_id)
                if item is not None:
                    choices.append({"evidence_id":evidence_id,"created_at":item.get("created_at"),
                                    "conversation_scope_sha256":_digest(str(item.get("conversation_id")))})
            if len(choices)>1:
                ambiguity_choice_descriptors.append({"ambiguity_set_id":ambiguity["ambiguity_set_id"],
                                                     "choices":choices})
        audit = {"schema_version": 1, "record_type": "native_candidate_generation",
                 "generator_version": self.version, "interpretation": interpretation,
                 "eligible_metadata_count": len(pool), "generated_candidate_count": len(selected),
                 "deduplicated_generation_count": sum(len(x["candidate_generation_reasons"]) for x in selected) - len(selected),
                 "max_total": max_total, "max_per_conversation": max_per_conversation,
                 "neighbor_radius": neighbor_radius, "max_thread_hops": max_thread_hops,
                 "max_relationship_expansions": max_relationship_expansions,
                 "relationship_expansion_count": expansions if interpretation["reference_intent"] else 0,
                 "reason_counts": {reason: sum(any(x["reason"] == reason for x in item["candidate_generation_reasons"]) for item in selected)
                                   for reason in ("direct_lexical_metadata_match", "explicit_temporal_constraint", "reference_recent_conversation_anchor", "conversation_neighbor", "conversation_thread_hop", "verified_native_reference")},
                 "generated_evidence_ids": [item["evidence_id"] for item in selected],
                 "reference_ambiguity_sets":reference_ambiguity_sets,
                 "ambiguity_choice_descriptors":ambiguity_choice_descriptors,
                 "automatic_inherited_history": False, "sensitive_content_logged": False}
        audit["generation_sha256"] = _digest(audit)
        return selected, audit


class NativeSourceRepresentationPreference:
    """Prefer only explicitly verified originals; never infer duplicate truth."""

    version = "native-source-representation-preference-v1"
    relationship_types = {"duplicate_of", "derived_from"}
    strength = {"duplicate_copy": 1, "derived_copy": 2, "source_original": 3}

    def apply(self, *, generated_candidates, eligible_metadata):
        generated = [dict(item) for item in generated_candidates]
        eligible = {item["evidence_id"]: dict(item) for item in eligible_metadata}
        by_reference = {}
        for item in eligible.values():
            reference = item.get("original_evidence_reference") or {}
            by_reference[(reference.get("archive_id"), reference.get("message_id"))] = item
        selected = {item["evidence_id"]: item for item in generated}
        decisions = []

        def relationship(item):
            envelope = item.get("representation_provenance")
            if not isinstance(envelope, dict): return None, "provenance_insufficient"
            representation = envelope.get("representation_class")
            edges = envelope.get("relationships")
            if representation not in self.strength or not isinstance(edges, list):
                return None, "provenance_malformed"
            verified = [edge for edge in edges if isinstance(edge, dict)
                        and edge.get("relationship") in self.relationship_types
                        and edge.get("qualification_status") == "verified"
                        and isinstance(edge.get("target"), dict)]
            if len(verified) != 1: return None, "provenance_ambiguous" if verified else "provenance_insufficient"
            return verified[0], None

        def strongest_target(item):
            """Follow only a fully verified eligible chain; preserve on any uncertainty."""
            chain = []
            seen = {item["evidence_id"]}
            current = item
            while True:
                edge, failure = relationship(current)
                if edge is None:
                    if current is item:
                        return None, chain, failure
                    return current, chain, None
                target_ref = edge["target"]
                target = by_reference.get((target_ref.get("archive_id"), target_ref.get("message_id")))
                if target is None:
                    return None, chain, "qualified_target_not_independently_eligible"
                target_id = target["evidence_id"]
                chain.append({"relationship": edge["relationship"], "target_evidence_id": target_id})
                if target_id in seen:
                    return None, chain, "provenance_cycle_or_self_reference"
                seen.add(target_id)
                current = target
                envelope = current.get("representation_provenance") or {}
                if envelope.get("representation_class") == "source_original":
                    return current, chain, None

        for copy_id in sorted(tuple(selected)):
            copy = selected.get(copy_id)
            if copy is None: continue
            target, chain, failure = strongest_target(copy)
            if target is None:
                decisions.append({"evidence_id":copy_id,"decision":"preserve",
                                  "reason":failure,"provenance_chain":chain,
                                  "canonical_record_mutated":False})
                continue
            target_id = target["evidence_id"]
            target_envelope = target.get("representation_provenance") or {}
            copy_envelope = copy.get("representation_provenance") or {}
            target_strength = self.strength.get(target_envelope.get("representation_class"), 0)
            copy_strength = self.strength.get(copy_envelope.get("representation_class"), 0)
            chain_items = [copy] + [eligible[step["target_evidence_id"]] for step in chain]
            contradictions = any(item.get("contradiction_group_ids") or item.get("contradiction_group_id")
                                 for item in chain_items)
            if contradictions:
                decisions.append({"evidence_id":copy_id,"decision":"preserve",
                    "reason":"contradiction_relationship_preserved","target_evidence_id":target_id,
                    "provenance_chain":chain,
                    "canonical_record_mutated":False})
                continue
            if target_strength <= copy_strength:
                decisions.append({"evidence_id":copy_id,"decision":"preserve",
                    "reason":"target_not_stronger_qualified_representation","target_evidence_id":target_id,
                    "provenance_chain":chain,
                    "canonical_record_mutated":False})
                continue
            if target_id not in selected:
                selected[target_id] = {**target, "candidate_generation_reasons": [
                    {"reason":"qualified_source_original_for_copy",
                     "relationship_id":"representation-relation-"+_digest({"version":self.version,"copy":copy_id,"target":target_id})[:24],
                     "seed_evidence_id":copy_id}]}
            selected.pop(copy_id, None)
            decisions.append({"evidence_id":copy_id,"decision":"suppress_redundant_context_copy",
                "reason":"stronger_verified_source_original_eligible","preferred_evidence_id":target_id,
                "copy_eligibility_policy_version":(copy.get("eligibility") or {}).get("policy_version"),
                "preferred_eligibility_policy_version":(target.get("eligibility") or {}).get("policy_version"),
                "provenance_chain":chain,"canonical_record_mutated":False,
                "truth_resolution_performed":False})
        ordered = sorted(selected.values(), key=lambda item: (
            str(item.get("created_at")), str(item.get("conversation_id")), item["evidence_id"]))
        audit={"schema_version":1,"record_type":"native_source_representation_preference",
               "policy_version":self.version,"input_candidate_count":len(generated),
               "output_candidate_count":len(ordered),"context_redundancy_reduction":len(generated)-len(ordered),
               "decisions":decisions,"selected_evidence_ids":[item["evidence_id"] for item in ordered],
               "canonical_records_merged":False,"canonical_records_mutated":False,
               "truth_resolution_performed":False,"automatic_inherited_history":False,
               "sensitive_content_logged":False}
        audit["preference_sha256"]=_digest(audit)
        return ordered,audit


class NativeContinuityProjection:
    """Pure projection. Originals remain authoritative and all candidates survive."""

    def project(self, *, instance_id, query, candidates, metadata_catalog, built_from_frontier_sha256=None):
        candidates = [dict(item) for item in candidates]
        if any(item.get("instance_id") != instance_id or item.get("domain") != "native_archive"
               for item in candidates):
            raise PermissionError("native_continuity_scope_mismatch")
        catalog = [dict(item) for item in metadata_catalog
                   if item.get("instance_id") == instance_id and item.get("domain") == "native_archive"]
        frontier = _digest([{
            "conversation_id": item.get("conversation_id"), "evidence_id": item.get("evidence_id"),
            "created_at": item.get("created_at"), "reference": item.get("original_evidence_reference"),
        } for item in sorted(catalog, key=lambda x: (str(x.get("conversation_id")), str(x.get("created_at")), str(x.get("evidence_id"))))])
        built = built_from_frontier_sha256 or frontier
        projection_id = "native-continuity-" + _digest({
            "processor": PROCESSOR_ID, "version": PROCESSOR_VERSION,
            "instance_id": instance_id, "built_from_frontier_sha256": built,
        })[:32]
        if frontier != built:
            return candidates, {"schema_version": 1, "record_type": "native_continuity_projection",
                "projection_id": projection_id, "processor_id": PROCESSOR_ID,
                "processor_version": PROCESSOR_VERSION, "instance_id": instance_id,
                "source_frontier_sha256": frontier, "built_from_frontier_sha256": built,
                "status": "stale", "derived": True, "rebuildable": True,
                "originals_authoritative": True, "candidate_count": len(candidates),
                "neighbor_relation_count": 0, "ambiguity_set_ids": [],
                "duplicate_group_ids": [], "contradiction_group_ids": [],
                "canonical_records_merged": False, "truth_resolution_performed": False,
                "automatic_inherited_history": False, "sensitive_content_logged": False,
                "projection_applied": False}

        neighbor_by_id = {}
        by_conversation = {}
        for item in catalog:
            by_conversation.setdefault(item.get("conversation_id"), []).append(item)
        for conversation_id, items in by_conversation.items():
            ordered = sorted(items, key=lambda x: (str(x.get("created_at")), str(x.get("evidence_id"))))
            for position, item in enumerate(ordered):
                relations = []
                for relation, neighbor_index in (("previous", position - 1), ("next", position + 1)):
                    if 0 <= neighbor_index < len(ordered):
                        neighbor = ordered[neighbor_index]
                        relations.append({"relation": relation, "conversation_id": conversation_id,
                                          "evidence_id": neighbor.get("evidence_id"),
                                          "created_at": neighbor.get("created_at")})
                neighbor_by_id[item.get("evidence_id")] = relations

        normalized = {item["evidence_id"]: _normalized(item.get("text", item.get("content", ""))) for item in candidates}
        duplicate_groups = []
        remaining = set(normalized)
        while remaining:
            first = min(remaining); remaining.remove(first); group = [first]
            first_terms = set(normalized[first].split())
            for other in sorted(tuple(remaining)):
                other_terms = set(normalized[other].split())
                exact = normalized[first] and normalized[first] == normalized[other]
                union = first_terms | other_terms
                near = bool(union and len(first_terms & other_terms) / len(union) >= 0.85)
                if exact or near:
                    group.append(other); remaining.remove(other)
            if len(group) > 1:
                duplicate_groups.append(tuple(group))

        contradiction_groups = {}
        for item in candidates:
            for group_id in contradiction_group_ids(item):
                contradiction_groups.setdefault(group_id, []).append(item["evidence_id"])

        mentions = {item["evidence_id"]: _entity_mentions(item.get("text", item.get("content", "")))
                    for item in candidates}
        mention_locations = {}
        by_id = {item["evidence_id"]: item for item in candidates}
        for evidence_id, values in mentions.items():
            for value in values:
                mention_locations.setdefault(value.casefold(), []).append(evidence_id)
        reference_like = bool(re.search(r"\b(?:that|those|the one|which one|earlier|previous)\b", query, re.I))
        ambiguity_sets = []
        if reference_like:
            for label, ids in sorted(mention_locations.items()):
                conversations = {by_id[eid].get("conversation_id") for eid in ids}
                if len(ids) > 1 and len(conversations) > 1:
                    ambiguity_sets.append({"ambiguity_set_id": "ambiguity-" + _digest({"label": label, "ids": sorted(ids)})[:24],
                                           "candidate_evidence_ids": sorted(ids),
                                           "basis": "same_lexical_mention_across_conversations_no_entity_resolution"})

        enriched = []
        for temporal_position, item in enumerate(sorted(candidates, key=lambda x: (str(x.get("created_at")), str(x.get("conversation_id")), str(x.get("evidence_id"))))):
            evidence_id = item["evidence_id"]
            duplicate = next((group for group in duplicate_groups if evidence_id in group), None)
            ambiguity_ids = [group["ambiguity_set_id"] for group in ambiguity_sets
                             if evidence_id in group["candidate_evidence_ids"]]
            enriched.append({**item,
                "native_evidence_identity": stable_native_evidence_id(item),
                "continuity_projection_id": projection_id,
                "temporal_relationship": {"position": temporal_position,
                    "created_at": item.get("created_at"), "ordering": "recorded_archive_time_then_stable_id"},
                "neighbor_relationships": list(neighbor_by_id.get(evidence_id, ())),
                "entity_mentions": list(mentions[evidence_id]),
                "entity_resolution_status": "unresolved_lexical_mentions" if mentions[evidence_id] else "not_observed",
                "ambiguity_set_ids": ambiguity_ids,
                "duplicate_relationship": ({"group_id": "duplicate-" + _digest(sorted(duplicate))[:24],
                    "member_evidence_ids": list(duplicate), "canonical_records_merged": False}
                    if duplicate else None),
                "contradiction_group_ids": contradiction_group_ids(item),
                "truth_resolution_performed": False,
            })
        # Preserve the adapter's deterministic rank after projection annotation.
        rank = {item["evidence_id"]: position for position, item in enumerate(candidates)}
        enriched.sort(key=lambda item: rank[item["evidence_id"]])
        audit = {"schema_version": 1, "record_type": "native_continuity_projection",
                 "projection_id": projection_id, "processor_id": PROCESSOR_ID,
                 "processor_version": PROCESSOR_VERSION, "instance_id": instance_id,
                 "source_frontier_sha256": frontier, "built_from_frontier_sha256": built,
                 "status": "current" if frontier == built else "stale",
                 "derived": True, "rebuildable": True, "originals_authoritative": True,
                 "candidate_count": len(candidates), "neighbor_relation_count": sum(len(x["neighbor_relationships"]) for x in enriched),
                 "ambiguity_set_ids": [x["ambiguity_set_id"] for x in ambiguity_sets],
                 "duplicate_group_ids": ["duplicate-" + _digest(sorted(x))[:24] for x in duplicate_groups],
                 "contradiction_group_ids": sorted(contradiction_groups),
                 "canonical_records_merged": False, "truth_resolution_performed": False,
                 "automatic_inherited_history": False, "sensitive_content_logged": False}
        audit["projection_applied"] = True
        return enriched, audit
