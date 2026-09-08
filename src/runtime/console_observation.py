"""Bounded, observational console identity and execution clocks. No authority writes."""
from datetime import datetime, timezone


def stamp(value):
    from src.runtime.autonomy_supervision import console_timestamp
    return console_timestamp(value)


def campaign_created(campaign):
    value = stamp(campaign.get("created_at"))
    if value:
        return value
    for event in campaign.get("activity", campaign.get("events", [])):
        if event.get("kind") == "campaign_created" and stamp(event.get("created_at")):
            return stamp(event["created_at"])
    return datetime.min.replace(tzinfo=timezone.utc)


def ordered_campaigns(campaigns):
    # A later failure/expiry in an old job is not a new user objective.
    return sorted(campaigns, key=lambda c: (campaign_created(c), c.get("campaign_id", "")), reverse=True)


def primary_campaign_id(campaigns):
    values = ordered_campaigns(campaigns)
    if not values:
        return None
    by_id = {c["campaign_id"]: c for c in values}
    chosen = values[0]
    seen = set()
    while chosen["campaign_id"] not in seen:
        seen.add(chosen["campaign_id"])
        parent = (chosen.get("console_reporting") or {}).get("parent_campaign_id")
        if not parent or parent not in by_id or parent in seen:
            break
        chosen = by_id[parent]
    return chosen["campaign_id"]


def unobserved_attention_transition(campaign, observation):
    """Cross-check observation freshness against existing canonical transitions.

    Process identity proves liveness, not that a failed pause/resume publication
    never happened. This read-only check also survives loss of transport memory.
    It does not invent the missing native timestamp or rewrite retained events.
    """
    if observation.get("state") not in {"running", "waiting"}:
        return False, None
    needs = campaign.get("needs_tanner") or {}
    invocation = observation.get("invocation_id")
    worker = observation.get("worker_id")
    pending = (campaign.get("status") == "tanner_escalation"
               and needs.get("invocation_id") == invocation
               and needs.get("worker_id") == worker)
    hint = "waiting" if pending else "unknown"
    if campaign.get("cancelled"):
        return True, hint
    events = campaign.get("events", [])
    if not isinstance(events, list):
        return True, hint
    binding = observation.get("campaign_observation_binding")
    if binding is None:
        # Legacy observations have no cross-stream ordering proof. Completed
        # turns remain readable; an open native wait/resume cannot be ordered
        # by wall timestamps, especially after an adjustment to the system clock.
        relevant = any(event.get("kind") == "tanner_attention_required"
            and (event.get("detail") or {}).get("invocation_id") == invocation
            and (event.get("detail") or {}).get("worker_id") == worker
            for event in events[-128:])
        return bool(relevant or pending or len(events)>128
                    or (campaign.get("status") and observation.get("state")=="waiting")), hint
    from src.runtime.worker_exchange import _digest
    if (not isinstance(binding, dict)
            or set(binding) != {"state_revision", "record_sha256", "event_count", "event_tail_sha256"}
            or type(binding.get("state_revision")) is not int
            or type(binding.get("event_count")) is not int
            or type(campaign.get("state_revision")) is not int
            or not 1 <= binding["state_revision"] <= campaign["state_revision"]
            or not 0 <= binding["event_count"] <= len(events)
            or any(not isinstance(binding.get(key), str) or len(binding[key])!=64
                   for key in ("record_sha256", "event_tail_sha256"))):
        return True, hint
    count=binding["event_count"]
    if (binding["event_tail_sha256"] != _digest(events[count-1] if count else None)
            or (binding["state_revision"] == campaign["state_revision"]
                and binding["record_sha256"] != campaign.get("record_sha256"))
            or len(events)-count > 128):
        return True, hint
    attention_ids = set()
    # At most128 earlier entries to correlate IDs and128 later transitions.
    for index in range(max(0,count-128),len(events)):
        event=events[index]
        detail = event.get("detail") or {}
        same = (detail.get("invocation_id") == invocation
                and detail.get("worker_id") == worker)
        if event.get("kind") == "tanner_attention_required" and same:
            attention_ids.add(detail.get("attention_id"))
            if index >= count and observation.get("state") != "waiting":
                return True, hint
        elif (index >= count and event.get("kind") in {
                "tanner_attention_approve_once", "tanner_attention_deny", "tanner_attention_failed_safe"}):
            if detail.get("attention_id") in attention_ids or count>128:
                # If the matching requirement fell outside the bounded window,
                # do not assert that its decision is unrelated.
                return True, hint
    # Even if transition history is absent, an exact current canonical wait
    # contradicts a retained running observation. Empty history is not proof.
    return bool(pending != (observation.get("state") == "waiting")), hint


def execution_turns(observations, *, observed_at):
    """Turn IDs and transition times come from the actual same app-server stream.

    Elapsed active time excludes permission waits. A lost process freezes at the
    last verified sync, not the time a browser opens. Missing beginnings remain
    unknown. No elapsed value changes an execution or accounting limit.
    """
    now = stamp(observed_at)
    result = []
    history_incomplete = len(observations) > 16 or any(
        item.get("timing_history_incomplete") for item in observations)
    for observation in observations[:16]:
        role = observation.get("role", "worker")
        if role not in {"worker", "reviewer"}:
            continue
        events = observation.get("timing_events", [])
        if not isinstance(events, list) or len(events) > 256:
            history_incomplete = True
            continue
        # Validate the retained sequence before filtering by observation time.
        # Otherwise a future-dated pause can disappear and falsely join two
        # running intervals after a backward wall-clock adjustment.
        previous, unusable, gaps, uncertain, checked = {}, set(), set(), set(), set()
        for event in events:
            key=event.get("event_id");identity=(event.get("thread_id"),event.get("turn_id"))
            if not key or key in checked:continue
            checked.add(key)
            if not all(identity):
                history_incomplete=True
                continue
            when=stamp(event.get("created_at"))
            if not when or not now or when>now:
                unusable.add(key);uncertain.add(identity)
            earlier=previous.get(identity)
            if when and earlier and when<earlier[1]:
                unusable.add(earlier[0]);gaps.add(key);uncertain.add(identity)
            if when:previous[identity]=(key,when)
        turns, seen = {}, set()
        for event in events:
            key = event.get("event_id")
            when = stamp(event.get("created_at"))
            turn = event.get("turn_id")
            thread = event.get("thread_id")
            if not key or key in seen:
                continue
            seen.add(key)
            if not turn or not thread:
                continue
            identity = (thread, turn)
            kind = event.get("kind")
            if key in unusable:
                item=turns.get(identity)
                if item:
                    item["state"]="unknown" if not item["ended_at"] else item["state"]
                    item["reliable"]=False;item["duration_incomplete"]=True
                    item["source_event_ids"].append(key)
                continue
            if kind == "turn_started":
                if identity in turns:
                    continue
                turns[identity] = {"turn_id": turn, "thread_id": thread, "role": role,
                    "invocation_id": observation["invocation_id"], "started_at": event["created_at"],
                    "ended_at": None, "state": "running", "active_seconds": 0,
                    "waiting_seconds": 0, "segments": [], "cursor": when,
                    "source_event_ids": [key], "reliable": True, "connection_lost": False,
                    "duration_incomplete": False}
                continue
            item = turns.get(identity)
            if not item:
                if not event.get("timing_gap_before") and kind not in {"permission_wait", "permission_result", "transport_closed", "final_result"}:
                    continue
                # The stream identifies a turn but its beginning was not retained.
                # Preserve that missing evidence, including in otherwise complete
                # role totals. An observed transition cannot invent a start time.
                history_incomplete = True
                item = turns[identity] = {"turn_id": turn, "thread_id": thread, "role": role,
                    "invocation_id": observation["invocation_id"], "started_at": None,
                    "first_observed_at": event["created_at"], "ended_at": None,
                    "state": "unknown", "active_seconds": 0, "waiting_seconds": 0,
                    "segments": [], "cursor": when, "source_event_ids": [],
                    "reliable": False, "connection_lost": False, "duration_incomplete": False}
            if item["ended_at"]:
                continue
            if when < item["cursor"]:
                item["reliable"] = False
                item["duration_incomplete"] = True
                item["state"] = "unknown"
                item["cursor"] = when
                item["source_event_ids"].append(key)
                continue
            if event.get("timing_gap_before") is True or key in gaps:
                # No duration bridges a missing pause/resume. Keep earlier
                # supported segments and, after a new observed transition,
                # retain later supported segments without inventing a total.
                item["reliable"] = False
                item["duration_incomplete"] = True
                item["state"] = "unknown"
                item["cursor"] = when
                item["source_event_ids"].append(key)
            if kind == "permission_wait":
                state = "waiting"
            elif kind == "permission_result":
                # Denial resolves this action's wait, not the native turn.
                state = "running"
            elif kind == "transport_closed":
                # Detection time is not an execution boundary. Retain earlier
                # observed segments but never accrue through an unobserved loss.
                item["connection_lost"] = True
                item["state"] = "disconnected"
                item["source_event_ids"].append(key)
                continue
            elif kind == "final_result":
                state = event.get("state", "disconnected")
            else:
                continue
            if state == item["state"]:
                continue
            seconds = (when - item["cursor"]).total_seconds()
            if item["state"] in {"running", "waiting"}:
                item["segments"].append({"state": item["state"], "started_at": item["cursor"].isoformat(),
                    "ended_at": when.isoformat(), "seconds": seconds})
                item["active_seconds" if item["state"] == "running" else "waiting_seconds"] += seconds
            item["cursor"] = when; item["state"] = state
            if key not in item["source_event_ids"]: item["source_event_ids"].append(key)
            if kind == "final_result" and state in {"completed", "failed"}:
                item["ended_at"] = when.isoformat()
        for identity in uncertain:
            if identity not in turns:
                # A bound turn with no usable timestamps is unknown, not an
                # omitted zero-duration turn in a supposedly complete total.
                turns[identity]={"thread_id":identity[0],"turn_id":identity[1],"role":role,
                    "invocation_id":observation["invocation_id"],"started_at":None,
                    "first_observed_at":None,"ended_at":None,"state":"unknown",
                    "active_seconds":None,"waiting_seconds":None,"segments":[],
                    "cursor":now or datetime.min.replace(tzinfo=timezone.utc),"source_event_ids":[],
                    "reliable":False,"connection_lost":False,"duration_incomplete":True}
            turns[identity]["reliable"]=False;turns[identity]["duration_incomplete"]=True
        verified = stamp(observation.get("verified_at"))
        for item in turns.values():
            if not item["ended_at"] and observation.get("timing_state_unverified") is True:
                item["reliable"] = False
                item["duration_incomplete"] = True
                item["state"] = ("waiting" if observation.get("timing_state_hint") == "waiting"
                                 else "unknown")
            live = bool(not item["ended_at"] and not item["connection_lost"]
                        and verified and now
                        and item["cursor"] <= verified <= now
                        and (now - verified).total_seconds() <= 30
                        and observation.get("state") in {"running", "waiting"})
            if not item["ended_at"]:
                if live and item["reliable"] and item["state"] in {"running", "waiting"}:
                    seconds = (verified - item["cursor"]).total_seconds()
                    item["active_seconds" if item["state"] == "running" else "waiting_seconds"] += seconds
                elif not live:
                    item["state"] = "disconnected"
                    # A dead process provides no exact final execution boundary.
                    # Do not replace an observed live total with a smaller guess.
                    # Completed transition segments remain separately available.
                    item["active_seconds"] = None
                    item["waiting_seconds"] = None
            item["active_verified"] = live and item["reliable"] and item["state"] == "running"
            item["observed_at"] = verified.isoformat() if live else observation.get("last_verified_at")
            item.pop("cursor")
            reliable, connection_lost = item.pop("reliable"), item.pop("connection_lost")
            if not reliable or connection_lost:
                item["active_seconds"] = None; item["waiting_seconds"] = None; item["active_verified"] = False
            for field in ("active_seconds", "waiting_seconds"):
                if item[field] is not None: item[field] = int(item[field])
            result.append(item)
    result.sort(key=lambda item: (item["started_at"] or item.get("first_observed_at") or "", item["invocation_id"], item["turn_id"]))
    history_incomplete = history_incomplete or len(result) > 32
    for item in result:
        item["history_incomplete"] = history_incomplete or item["duration_incomplete"]
    return result[-32:]
