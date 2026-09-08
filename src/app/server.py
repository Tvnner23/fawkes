"""Dependency-free authenticated HTTP home for Fawkes Chat."""

import argparse
import hmac
import json
import os
import socket
import hashlib
import secrets
import time
import re
import threading
import fcntl
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from src.runtime.chat_service import (
    ChatServiceError, FawkesChatService, sanitize_development_console_diff,
)
from src.runtime.autonomy_supervision import RiderActivityStore, console_timestamp
from src.runtime.console_observation import ordered_campaigns, primary_campaign_id
from src.runtime.windows_clipboard import ConsoleClipboardDelivery
from src.runtime.personal_recording import (
    EDITABLE_CATEGORIES, RecordingPolicyConflict, RecordingPolicyDurabilityError,
    RecordingPolicyError,
)


STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_BODY_BYTES = 22 * 1024 * 1024
SESSION_COOKIE = "fawkes_app_session"
SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
DEV_CONSOLE_MAX_CAMPAIGNS = 32
DEV_CONSOLE_MAX_ACTIVITY_ITEMS = 64
DEV_CONSOLE_MAX_ATTENTION_ITEMS = 16
DEV_CONSOLE_MAX_REPOSITORY_FILES = 32
DEV_CONSOLE_MAX_TEXT_BYTES = 2_048
# Complete G15 history after integration measured 300,321 UTF-8 bytes; a full
# 32-slot heavy-history projection measured 312,402 bytes. Keep bounded response
# headroom without dropping campaigns, clocks, recaps or roadmap evidence.
DEV_CONSOLE_MAX_RESPONSE_BYTES = 512_000
DEV_CONSOLE_MAX_UPDATES = 40
DEV_CONSOLE_MAX_UPDATE_BYTES = 96_000
DEV_CONSOLE_COMPONENTS = (
    "app_server", "development_coordinator", "discord_bridge", "reviewer_launcher",
    "stack", "worker_launcher",
)
DEV_CONSOLE_CONFIGURED_ONLY_COMPONENTS = {
    "development_coordinator", "reviewer_launcher", "worker_launcher",
}


def _console_text(value, field, *, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ValueError(f"developer console {field} must be text")
    if len(value.encode("utf-8")) > DEV_CONSOLE_MAX_TEXT_BYTES:
        raise ValueError(f"developer console {field} exceeds its byte limit")
    return value


def _console_worker(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("developer console worker projection is malformed")
    projected = {}
    for field in ("worker_id", "role", "functional_role", "environment_id"):
        if field in value:
            projected[field] = _console_text(value[field], field, optional=True)
    return projected


def _console_needs_tanner(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("developer console Tanner projection is malformed")
    projected = {}
    for field in ("attention_id", "reason", "decision_needed", "expires_at"):
        if field in value:
            projected[field] = _console_text(value[field], field, optional=True)
    return projected


def _console_recovery_references(value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("developer console recovery references are malformed")
    projected = []
    for reference in value[:16]:
        if not isinstance(reference, dict):
            raise ValueError("developer console recovery reference is malformed")
        item = {}
        for field in ("reference_type", "reference_id", "record_sha256"):
            if field in reference:
                item[field] = _console_text(reference[field], field, optional=True)
        projected.append(item)
    return projected


def _console_activity_summary(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("developer console activity summary is malformed")
    projected = {}
    for field in ("status", "task_scope_id", "return_report_id", "review_report_id",
                  "verification_status"):
        if field in value:
            projected[field] = _console_text(value[field], field, optional=True)
    failure = value.get("failure")
    if failure is not None:
        if not isinstance(failure, dict):
            raise ValueError("developer console failure summary is malformed")
        if "code" in failure:
            projected["failure_code"] = _console_text(
                failure["code"], "failure_code", optional=True)
    for source, target in (
        ("validation_evidence", "validation_evidence_count"),
        ("acceptance_condition_ids_satisfied", "satisfied_condition_count"),
        ("violated_acceptance_condition_ids", "violated_condition_count"),
        ("defects", "defect_count"),
    ):
        if source in value:
            if not isinstance(value[source], list):
                raise ValueError(f"developer console {source} must be a list")
            projected[target] = len(value[source])
    return projected


def _console_activity(value):
    if not isinstance(value, list):
        raise ValueError("developer console activity is malformed")
    projected = []
    for event in value[-DEV_CONSOLE_MAX_ACTIVITY_ITEMS:]:
        if not isinstance(event, dict):
            raise ValueError("developer console activity item is malformed")
        item = {
            "event_id": _console_text(event.get("event_id"), "event_id"),
            "kind": _console_text(event.get("kind"), "kind"),
            "created_at": _console_text(event.get("created_at"), "created_at"),
        }
        detail = event.get("detail")
        if detail is not None:
            if not isinstance(detail, dict):
                raise ValueError("developer console activity detail is malformed")
            iteration = detail.get("iteration")
            if iteration is not None:
                if not isinstance(iteration, int) or isinstance(iteration, bool):
                    raise ValueError("developer console activity iteration is malformed")
                item["iteration"] = iteration
        if "worker" in event:
            item["worker"] = _console_worker(event["worker"])
        if "summary" in event:
            item["summary"] = _console_activity_summary(event["summary"])
        projected.append(item)
    return projected


def _console_campaigns(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("campaigns"), list):
        raise ValueError("developer console campaign source is malformed")
    result = []
    for wrapper in payload["campaigns"][:DEV_CONSOLE_MAX_CAMPAIGNS]:
        if not isinstance(wrapper, dict) or not isinstance(wrapper.get("live_activity"), dict):
            raise ValueError("developer console campaign activity is malformed")
        activity = wrapper["live_activity"]
        iteration = activity.get("iteration")
        maximum = activity.get("maximum_iterations")
        if (not isinstance(iteration, int) or isinstance(iteration, bool)
                or not isinstance(maximum, int) or isinstance(maximum, bool)):
            raise ValueError("developer console campaign iteration is malformed")
        cancelled = activity.get("cancelled")
        if not isinstance(cancelled, bool):
            raise ValueError("developer console campaign cancellation state is malformed")
        observations = wrapper.get("operational_learning_observations") or {}
        if not isinstance(observations, dict):
            raise ValueError("developer console campaign observations are malformed")
        projected_observations = {}
        for field in (
            "builder_invocations", "logical_reviews", "review_transport_attempts",
            "reviewer_process_invocations", "correction_count", "reviewer_defect_count",
            "source_section_count",
        ):
            value = observations.get(field)
            if value is not None:
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError("developer console campaign observation is malformed")
                projected_observations[field] = value
        acceptance_satisfied = wrapper.get("acceptance_satisfied")
        if acceptance_satisfied is not None and not isinstance(acceptance_satisfied, list):
            raise ValueError("developer console campaign acceptance state is malformed")
        result.append({
            "campaign_id": _console_text(activity.get("campaign_id"), "campaign_id"),
            "objective": _console_text(activity.get("objective", wrapper.get("objective", "")),
                                       "objective", optional=True),
            "created_at": _console_text(wrapper.get("created_at"), "created_at", optional=True),
            "updated_at": _console_text(wrapper.get("updated_at"), "updated_at", optional=True),
            "satisfied_condition_count": (
                len(acceptance_satisfied) if acceptance_satisfied is not None else None),
            "operational_learning_observations": projected_observations,
            "status": _console_text(activity.get("status"), "status"),
            "current_stage": _console_text(activity.get("current_stage"), "current_stage"),
            "iteration": iteration,
            "maximum_iterations": maximum,
            "cancelled": cancelled,
            "builder": _console_worker(activity.get("builder")),
            "reviewer": _console_worker(activity.get("reviewer")),
            "needs_tanner": _console_needs_tanner(activity.get("needs_tanner")),
            "recovery_references": _console_recovery_references(
                activity.get("recovery_references")),
            "activity": _console_activity(activity.get("activity", [])),
            "managed_worker_activity": _console_managed_activity(wrapper.get("managed_worker_activity", [])),
            "console_reporting": _console_reporting(wrapper.get("console_reporting")),
        })
    return ordered_campaigns(result)


def _console_reporting(value):
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("creates_authority") is not False:
        raise ValueError("console reporting must be observational")
    result = {field: _console_text(value.get(field), field, optional=True) for field in (
        "record_sha256", "observed_at", "worker_status", "worker_task_scope_id", "review_status",
        "application_status", "git_status", "parent_campaign_id", "created_at", "updated_at")}
    result["facts"] = [_console_text(item, "job fact") for item in value.get("facts", [])[:12]]
    recap = value.get("return_recap")
    result["return_recap"] = ({key: _console_text(recap.get(key), key, optional=True)
        for key in ("accomplished", "gained", "next", "status", "report_id", "record_sha256", "reported_at")}
        if isinstance(recap, dict) else None)
    result["source_references"] = [_console_text(item, "source reference")
                                   for item in value.get("source_references", [])[:8]]
    result["intervals"] = []
    for item in value.get("intervals", [])[:24]:
        projected = {field: _console_text(item.get(field), field, optional=True)
                     for field in ("stage", "started_at", "ended_at", "state", "timing_basis")}
        for field in ("attempt", "duration_seconds"):
            number = item.get(field)
            if number is not None and (type(number) is not int or number < 0):
                raise ValueError("invalid console timing number")
            projected[field] = number
        projected["active_verified"] = item.get("active_verified") is True
        projected["active_time_excludes_attention"] = item.get("active_time_excludes_attention") is True
        projected["source_references"] = [_console_text(source, "interval source")
                                           for source in item.get("source_references", [])[:8]]
        result["intervals"].append(projected)
    result["turns"] = []
    for item in value.get("turns", [])[:32]:
        turn = {key: _console_text(item.get(key), key, optional=True) for key in (
            "turn_id", "thread_id", "invocation_id", "role", "state", "started_at", "ended_at", "observed_at")}
        if turn["role"] not in {"worker", "reviewer"}:
            raise ValueError("invalid execution role")
        for key in ("active_seconds", "waiting_seconds"):
            number = item.get(key)
            if number is not None and (type(number) is not int or number < 0):
                raise ValueError("invalid turn timing")
            turn[key] = number
        turn["active_verified"] = item.get("active_verified") is True
        turn["duration_incomplete"] = item.get("duration_incomplete") is True
        result["turns"].append(turn)
    result["timing_history_incomplete"] = value.get("timing_history_incomplete") is True
    roles = value.get("timing_incomplete_roles")
    if roles is None:
        roles = ["worker", "reviewer"] if result["timing_history_incomplete"] else []
    if not isinstance(roles, list) or len(roles) > 2 or any(not isinstance(role, str) or role not in {"worker", "reviewer"} for role in roles):
        raise ValueError("invalid incomplete timing roles")
    result["timing_incomplete_roles"] = sorted(set(roles))
    result["creates_authority"] = False
    return result


def _console_managed_activity(value):
    if not isinstance(value, list): raise ValueError("managed activity must be a list")
    result = []
    for item in value[:8]:
        if item.get("state") not in {"running", "waiting", "completed", "failed", "disconnected"}:
            raise ValueError("unknown managed Worker state")
        record = {key:_console_text(item.get(key), key) for key in
                  ("invocation_id", "worker_id", "updated_at", "state")}
        record["role"] = _console_text(item.get("role", "worker"), "role")
        record["verified_at"] = _console_text(item.get("verified_at"), "verified_at", optional=True)
        record["events"] = [{key:_console_text(event.get(key), key) for key in
            ("event_id", "created_at", "kind", "state", "public_message")}
            for event in item.get("events", [])[-64:]]
        result.append(record)
    return result


def _console_repository(payload):
    if not isinstance(payload, dict):
        raise ValueError("developer console repository source is malformed")
    if payload.get("creates_authority") is not False \
            or payload.get("creates_continuing_authority") is not False:
        raise ValueError("developer console repository authority is malformed")
    summary = payload.get("status_summary")
    if not isinstance(summary, dict):
        raise ValueError("developer console repository summary is malformed")
    projected_summary = {}
    for field in (
        "dirty_paths", "tracked_changes", "untracked_paths", "staged_paths",
        "deleted_paths",
    ):
        value = summary.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("developer console repository count is malformed")
        projected_summary[field] = value
    files = payload.get("files")
    if not isinstance(files, list) or len(files) > DEV_CONSOLE_MAX_REPOSITORY_FILES:
        raise ValueError("developer console repository files are malformed")
    projected_files = []
    for source in files:
        if not isinstance(source, dict):
            raise ValueError("developer console repository file is malformed")
        path = _console_text(source.get("path"), "repository path")
        parts = Path(path).parts
        if not path or Path(path).is_absolute() or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("developer console repository path is outside its scope")
        projected_file = {field: _console_text(source.get(field), field)
            for field in (
                "path", "mode", "object_type", "object_id", "head_change",
                "worktree_state", "revision", "review_status",
            )}
        projected_file["diff_excerpt"] = sanitize_development_console_diff(
            _console_text(source.get("diff_excerpt"), "diff_excerpt"))
        projected_files.append(projected_file)
    return {
        "branch": _console_text(payload.get("branch"), "repository branch"),
        "head": _console_text(payload.get("head"), "repository HEAD"),
        "comparison_base": _console_text(
            payload.get("comparison_base"), "repository comparison base"),
        "selection_basis": _console_text(
            payload.get("selection_basis"), "repository selection basis"),
        "status_summary": projected_summary,
        "files": projected_files,
        "creates_authority": False,
        "creates_continuing_authority": False,
    }


def _console_attention(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("attention"), list):
        raise ValueError("developer console Attention source is malformed")
    result = []
    fields = ("attention_id", "campaign_id", "invocation_id", "state", "blocked_action",
              "why_required", "expires_at", "consumer_state", "detail_url")
    for event in payload["attention"][:DEV_CONSOLE_MAX_ATTENTION_ITEMS]:
        if not isinstance(event, dict):
            raise ValueError("developer console Attention item is malformed")
        item = {field: _console_text(event.get(field), field,
                                     optional=field in {"expires_at", "detail_url"})
                for field in fields}
        if not isinstance(event.get("actionable"), bool):
            raise ValueError("developer console Attention actionability is malformed")
        item["actionable"] = event["actionable"]
        result.append(item)
    return result


def _console_components(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("components"), dict):
        raise ValueError("developer console component source is malformed")
    result = []
    for name in DEV_CONSOLE_COMPONENTS:
        if name not in payload["components"]:
            continue
        source = payload["components"][name]
        if not isinstance(source, dict):
            raise ValueError("developer console component state is malformed")
        state = _console_text(source.get("state"), "component state")
        # These entries are configured placeholders in the existing source;
        # they are not measured liveness and must not masquerade as it.
        if name in DEV_CONSOLE_CONFIGURED_ONLY_COMPONENTS:
            state = "unobserved_configured"
        result.append({"name": name, "state": state})
    return result


_ROADMAP_SUMMARIES = (
    "Protects identity, integrity, privacy and recovery so Fawkes can change without losing who he is.",
    "Lets Fawkes keep durable media and documents with clear ownership and provenance.",
    "Lets every processing attempt be tracked once, resumed safely and audited later.",
    "Lets Tanner stage exported conversations for controlled review before they affect Fawkes.",
    "Lets Fawkes search retained history and approved outside sources when asked.",
    "Tests historical imports and retrieval quality before old material influences current answers.",
    "Lets developers replay retrieval decisions and diagnose why a result was selected.",
    "Lets Fawkes plan one bounded search across Library, Archive and semantic projections.",
    "Lets Fawkes connect relevant knowledge across conversations while preserving source boundaries.",
    "Builds a verified context package so responses receive relevant, attributable information.",
    "Lets Fawkes propose and test scoped improvements without granting himself authority.",
    "Lets Fawkes distinguish what used to be true from what is true now.",
    "Lets Fawkes track claims, supporting evidence and when that evidence may have gone stale.",
    "Lets historical material enter current knowledge only through explicit controlled review.",
    "Lets Fawkes remember decisions, their reasons and what actually happened afterward.",
    "Lets Fawkes build a revisable understanding of relationships while respecting each person's privacy.",
    "Lets Fawkes develop a coherent personality and assess changes without pretending certainty.",
    "Lets Fawkes deliver bounded improvements through independent review and Tanner's permissions.",
    "Lets Fawkes route work among suitable models while enforcing durable spending limits.",
    "Lets Fawkes understand approved video content as time-based evidence rather than isolated frames.",
    "Lets Fawkes form a sourced, revisable view of his surroundings and their current state.",
    "Lets Fawkes understand dates, schedules and deadlines without inventing current facts.",
    "Lets authorized workflows continue across restarts while retaining explicit stop conditions.",
    "Lets Fawkes offer timely help from verified context without acting beyond Tanner's authority.",
    "Lets Fawkes rehearse consequential actions safely before any real-world effect occurs.",
    "Lets tools use scoped credential references without exposing secrets to ordinary reasoning.",
    "Keeps physical and environmental actions inside explicit safety and human-control boundaries.",
    "Lets Fawkes use supervised tools and actions with exact scope, evidence and recovery.",
    "Lets Fawkes express one continuous Phoenix identity through evolving visual forms.",
    "Lets the same Fawkes stay coordinated across console, computer, phone and supported forms.",
    "Lets Tanner read and learn with guided context, notes and progress that remain source-bound.",
    "Lets Tanner talk naturally with Fawkes, interrupt him and hear his replies.",
    "Lets meaningful Fawkes events have consistent, controllable sounds without turning noise into status.",
    "Lets approved devices, homes and vehicles expose narrowly scoped capabilities to Fawkes.",
    "Lets Fawkes carry verified continuity between supported installations without cloning hidden authority.",
    "Lets multiple individual Phoenixes coexist while preserving each identity and Rider relationship.",
    "Lets households share selected capabilities with consent, privacy and relationship compartments.",
    "Lets Phoenixes provide attributable testimony without making another Phoenix's claims automatically true.",
    "Lets Phoenixes communicate through authenticated, consent-aware channels with retained provenance.",
    "Lets a wider Phoenix ecosystem interoperate while keeping identity, consent and authority explicit.",
)

_ROADMAP_TRACKS = (
    ("track-presence", "Presence and expression", "Lets Fawkes communicate identity and state through a restrained in-app presence.", "presence", "canonical"),
    ("track-ghost-rider", "Ghost Rider evaluation", "Tests Fawkes with simulated Rider interactions before changes reach real users.", "assurance", "canonical"),
    ("track-multi-worker", "Multi-Worker coordination", "Lets specialized Workers collaborate through exact packages, budgets and independent assurance.", "development", "canonical"),
    ("track-public", "Public experience", "Lets visitors meet a deliberately limited public Fawkes without entering Tanner's private instance.", "clients", "canonical"),
    ("track-social", "Scoped social and messaging", "Lets approved messaging adapters communicate without becoming unrestricted publication authority.", "clients", "proposed"),
    ("track-approval", "Secure human approval", "Lets consequential requests pause for an exact authenticated human decision before continuing.", "attention", "canonical"),
    ("track-phone", "Phone companion", "Lets Tanner reach the same authenticated Fawkes from a supported phone companion.", "clients", "canonical"),
    ("track-embodiment", "Progressive physical bodies", "Lets one Fawkes gain increasingly capable physical forms without moving identity into hardware.", "embodiment", "canonical"),
    ("track-dedicated-home", "Dedicated home infrastructure", "Keeps Fawkes available when Tanner's personal computer is shut down.", "infrastructure", "recorded_requirement"),
    ("track-console-controls", "Console physical controls", "Adds a power and idle button, wheel, clicker and volume slider after hardware selection and installation.", "embodiment", "recorded_requirement"),
    ("track-console-audio", "Console sound and speakers", "Lets the console play supported alerts after speakers, safe output points and volume limits are verified.", "embodiment", "recorded_requirement"),
    ("track-console-enclosure", "Console cooling and enclosure", "Lets the console operate in a protected shell with verified cooling and service access.", "embodiment", "recorded_requirement"),
    ("track-recovery", "Recovery and portable continuity", "Lets Fawkes restore verified state after failures without rewriting history or authority.", "identity", "canonical"),
    ("track-realtime", "Realtime conversation", "Lets voice, interruption, device presence and status stay coordinated across supported surfaces.", "clients", "canonical"),
)

def _console_roadmap(repository, *, source_revision):
    roadmap = Path(repository) / "docs/phoenix/CANONICAL_ROADMAP.md"
    source = roadmap.read_bytes()
    text = source.decode("utf-8")
    addendum_path = "src/app/static/dev-console/roadmap-addendum.txt"
    # One packaged, noncanonical source, never an arbitrary filesystem path.
    with (Path(repository) / addendum_path).open("rb") as stream:
        addendum = stream.read(16_385)
    if not addendum or len(addendum) > 16_384:
        raise ValueError("retained roadmap addendum exceeds its source bound")
    addendum_text = addendum.decode("utf-8")
    canonical_binding = {"source_sha256": hashlib.sha256(source).hexdigest(),
        "source_bytes": len(source), "source_revision": source_revision,
        "source_excerpt": ""}
    addendum_binding = {"source_sha256": hashlib.sha256(addendum).hexdigest(),
        "source_bytes": len(addendum), "source_revision": source_revision,
        "source_excerpt": addendum_text}
    phases = []
    for number, summary in enumerate(_ROADMAP_SUMMARIES):
        match = re.search(rf"^## Phase {number} [—-] (.+)$", text, re.MULTILINE)
        if not match:
            raise ValueError(f"canonical roadmap Phase {number} is unavailable")
        raw_title = match.group(1).strip()
        title = raw_title.replace(" — COMPLETE", "")
        next_phase = re.search(r"^## Phase \d+ [—-] ", text[match.end():], re.MULTILINE)
        section = text[match.end():match.end() + next_phase.start()] if next_phase else text[match.end():]
        recorded_complete = (raw_title.endswith(" — COMPLETE") or bool(re.search(
            rf"^\*\*Phase {number} [—-] [^\n]+ is COMPLETE\.\*\*", section, re.MULTILINE)))
        maturity = "implemented" if recorded_complete else "planned"
        # A recorded completed milestone remains complete even where the
        # associated foundation has later planned extensions.
        if maturity != "implemented" and number in {0, 1, 2, 3, 4, 5, 6, 7, 8, 10}:
            maturity = "partial"
        phases.append({"id": f"phase-{number}", "kind": "phase", "number": number,
            "name": title, "summary": summary, "maturity": maturity,
            "source": "docs/phoenix/CANONICAL_ROADMAP.md", "source_status": "canonical",
            "group": ("Foundations and continuity" if number <= 9 else
                      "Knowledge and improvement" if number <= 18 else
                      "Agency and safety" if number <= 27 else
                      "Presence, devices and ecosystem"),
            # Phase numbering is an identity, not an invented dependency edge.
            "prerequisites": [],
            "runtime_state": "unknown", **canonical_binding})
    documented_prerequisites = {"track-presence": ["phase-0", "phase-1"]}
    tracks = [{"id": item[0], "kind": "track", "name": item[1], "summary": item[2],
        "maturity": "planned", "source": ("docs/phoenix/CANONICAL_ROADMAP.md" if item[4] == "canonical"
            else addendum_path), "source_status": item[4],
        "group": "Cross-cutting and product tracks", "mapped_component": item[3],
        "prerequisites": documented_prerequisites.get(item[0], []),
        "runtime_state": "unknown",
        **(canonical_binding if item[4] == "canonical" else addendum_binding)} for item in _ROADMAP_TRACKS]
    return {"schema_version": "fawkes.console.roadmap.v1", "source_path": str(roadmap.relative_to(repository)),
        "source_sha256": hashlib.sha256(source).hexdigest(), "source_bytes": len(source),
        "source_revision": _console_text(source_revision, "roadmap source revision"),
        "phases": phases, "tracks": tracks, "expected_phase_ids": [f"phase-{n}" for n in range(40)],
        "coverage_complete": len(phases) == 40, "creates_authority": False,
        "creates_continuing_authority": False}

def _console_jobs(campaigns, attention):
    actionable_campaigns = {item["campaign_id"] for item in attention
                            if item.get("actionable") is True}
    terminal_statuses = {"succeeded", "failed_safe", "denied", "expired", "cancelled"}
    jobs = []
    for campaign in campaigns:
        stamps = [event.get("created_at") for event in campaign.get("activity", [])]
        stamps.append(campaign.get("updated_at"))
        stamps.extend(item.get("updated_at") for item in campaign.get("managed_worker_activity", []))
        now = datetime.now(timezone.utc)
        valid_stamps = [(console_timestamp(stamp), stamp) for stamp in stamps
                        if console_timestamp(stamp) and console_timestamp(stamp) <= now]
        last = max(valid_stamps, default=(None, None))[1]
        status = campaign["status"]
        actionable = campaign["campaign_id"] in actionable_campaigns
        successful = status == "succeeded"
        historical = status in terminal_statuses
        if actionable or status == "tanner_escalation":
            state = "needs_you"
        elif successful:
            state = "done"
        elif historical:
            state = "failed" if status == "failed_safe" else "closed"
        elif status in {"historical_contract_unavailable", "integrity_unavailable"}:
            state = "unknown"
        else:
            state = "waiting"
        reporting = campaign.get("console_reporting") or {}
        if not historical and state == "waiting" and any(
                item.get("active_verified") for item in reporting.get("turns", [])):
            state = "working"
        objective = campaign.get("objective") or campaign["campaign_id"]
        facts = list(reporting.get("facts") or [])
        # Legacy presentations still expose exact run/review status in activity.
        if not facts:
            for event in campaign.get("activity", []):
                summary = event.get("summary") or {}
                if event.get("kind") in {"builder_return_retained", "builder_failed_safe"}:
                    facts.append(f"Worker attempt {event.get('iteration', '?')}: {summary.get('status') or 'unknown'}.")
                elif event.get("kind") == "independent_review_retained":
                    facts.append(f"Independent review: {summary.get('status') or 'unknown'}.")
        public_results = [event.get("public_message") for item in campaign.get("managed_worker_activity", [])
                          if item.get("state") == "completed"
                          and reporting.get("worker_task_scope_id")
                          and item.get("invocation_id") == reporting["worker_task_scope_id"] + "-appserver"
                          and item.get("worker_id") == (campaign.get("builder") or {}).get("worker_id")
                          for event in item.get("events", [])
                          if event.get("state") == "completed" and event.get("public_message")]
        current_step = {
            "awaiting_independent_review": "Candidate retained; independent review still required. Reviewer execution is unverified.",
            "builder_in_progress": ("Worker execution observed." if state == "working" else
                                    "Worker attempt open; current execution unverified."),
            "review_accepted_application_pending": "Independent review accepted; canonical application pending.",
            "reviewed_application_completed": "Canonical application recorded; Git integration pending.",
            "correction_pending": "Review requires correction; next Worker attempt pending.",
            "ready": "Campaign ready; Worker execution has not started.",
            "succeeded": "Campaign succeeded; application and Git facts are listed separately.",
            "failed_safe": "Campaign failed safely; retained attempts are not campaign success.",
            "tanner_escalation": "Campaign paused for Tanner.",
        }.get(status, status.replace("_", " "))
        if status == "awaiting_independent_review" and any(
                item.get("stage") == "review_queue" and item.get("state") == "dispatched"
                for item in reporting.get("intervals", [])):
            current_step = "Independent review dispatched; current Reviewer execution is unverified."
        if status == "awaiting_independent_review" and any(
                item.get("role") == "reviewer" and item.get("active_verified")
                for item in reporting.get("turns", [])):
            current_step = "Independent Reviewer execution observed on the exact candidate."
        next_step = {
            "awaiting_independent_review": "Independent review of the retained candidate.",
            "review_accepted_application_pending": "Canonical application of the accepted candidate.",
            "reviewed_application_completed": "Canonical Git integration of the applied candidate.",
            "correction_pending": "A bounded correction attempt for the recorded review defects.",
            "ready": "Start the authorized Worker attempt.",
        }.get(status, "Unknown; no follow-on is recorded in this projection.")
        if state == "needs_you":
            next_step = (campaign.get("needs_tanner") or {}).get("decision_needed") or "Open the exact canonical Attention request."
        recap = reporting.get("return_recap") or {}
        recorded_result = recap.get("accomplished") if recap.get("status") == "worker_reported_historical" else None
        recorded_gain = recap.get("gained") if recorded_result else None
        if successful:
            next_step = "This campaign is complete. See other open jobs for current work; no new task is authorized by this recap."
        accomplishment = ("Worker reported: " + recorded_result if recorded_result else
            (public_results[-1][:900] if public_results else "No detailed result was recorded."))
        accomplishment += " Current records: " + (" ".join(facts[-12:])[:800] or "No completed stage recorded.")
        jobs.append({"job_id": campaign["campaign_id"], "objective": objective,
            "state": state, "recorded_status": status, "current_step": current_step,
            "last_activity_at": last, "worker": campaign.get("builder"),
            "successful": successful, "historical": historical,
            "accomplished": accomplishment[:1800],
            "public_result": public_results[-1][:500] if public_results else None,
            "gained": (("Worker reported at return: " + recorded_gain[:900] + " Current deployment is not established here.")
                if recorded_gain else "No verified capability gain is recorded here; stage results are listed separately."),
            "return_recap": recap,
            "parent_campaign_id": reporting.get("parent_campaign_id"),
            "created_at": campaign.get("created_at"),
            "source_record_sha256": reporting.get("record_sha256"),
            "next": next_step,
            "creates_authority": False})
    ordered = [item["campaign_id"] for item in ordered_campaigns(campaigns)]
    primary = primary_campaign_id(campaigns)
    jobs.sort(key=lambda job: (job["job_id"] != primary, ordered.index(job["job_id"])))
    for job in jobs:
        job["is_current_objective"] = job["job_id"] == primary
    return jobs[:32]


def developer_console_projection(chat_service):
    """Build one bounded, body-free and non-authorizing console projection."""
    campaigns = chat_service.list_codex_development_campaigns()
    attention = chat_service.development_attention_projection(pending_only=True)
    components = chat_service.production_component_status()
    repository = chat_service.development_console_repository_projection()
    build = build_identity()
    projection = {
        "schema_version": "fawkes.dev_console.read_only.v1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "build": {field: build.get(field)
                  for field in ("mode", "release_id", "manifest_sha256")},
        "campaigns": _console_campaigns(campaigns),
        "attention": _console_attention(attention),
        "components": _console_components(components),
        "repository": _console_repository(repository),
        "roadmap": _console_roadmap(
            Path(os.getenv("FAWKES_DEVELOPMENT_ROOT", Path(__file__).resolve().parents[2])),
            source_revision=repository["head"],
        ),
        "creates_authority": False,
        "creates_continuing_authority": False,
    }
    projection["jobs"] = _console_jobs(projection["campaigns"], projection["attention"])
    projection["current_campaign_id"] = primary_campaign_id(projection["campaigns"])
    projection["selection_basis"] = "Latest recorded user objective by creation, not last historical state change; known parent retained."
    # Recent observation window only, never a budget or authority decision.
    # Bound activity independently so public progress cannot crowd out pending
    # Attention. Full retained sidecars remain with their canonical owner.
    managed = sorted((item for campaign in projection["campaigns"]
        for item in campaign.get("managed_worker_activity", [])),
        key=lambda item:item["updated_at"], reverse=True)
    omitted = sum(len(item["events"]) for item in managed[4:])
    # Limit public event bodies, not the status metadata needed to interpret
    # native clocks. Quiet current roles must survive newer historical activity.
    # Existing per-campaign counts, total32KiB window and response guard remain.
    for item in managed[4:]:
        item["events"] = []
    while len(json.dumps(managed, ensure_ascii=False).encode("utf-8")) > 32768:
        populated = [item for item in managed if item["events"]]
        if not populated: raise ValueError("managed activity metadata exceeds its window")
        oldest = min(populated, key=lambda item:item["events"][0]["created_at"])
        oldest["events"].pop(0); omitted += 1
    projection["managed_activity_window"] = {"omitted_events": omitted, "maximum_bytes": 32768}
    if len(json.dumps(projection, ensure_ascii=False).encode("utf-8")) > \
            DEV_CONSOLE_MAX_RESPONSE_BYTES:
        raise ValueError("developer console projection exceeds its byte limit")
    return projection


def _console_update_text(projection, *, created_at, snapshot_id):
    """Render one exact, public, bounded status handoff without raw event bodies."""
    if not isinstance(projection, dict) or projection.get("creates_authority") is not False:
        raise ValueError("console update projection is not observational")
    lines = [
        "FAWKES — COMPLETED + WORKING ON",
        f"Snapshot: {snapshot_id}",
        f"Created: {created_at}",
        f"Last source update: {projection.get('observed_at') or 'Unknown'}",
        "Observation: authenticated developer-console projection; current truth depends on its freshness",
        "",
        "REQUESTED JOBS",
    ]
    lines.insert(4, f"Current objective campaign: {projection.get('current_campaign_id') or 'Unknown'}")
    lines.insert(5, f"Selected campaign: {projection.get('selected_campaign_id') or projection.get('current_campaign_id') or 'Unknown'}")
    jobs = projection.get("jobs") if isinstance(projection.get("jobs"), list) else []
    if not jobs:
        lines.append("- No campaign/job records are available to this preview; this is not an all-history claim.")
    for job in jobs[:32]:
        state = str(job.get("state") or "unknown").replace("_", " ").upper()
        objective = str(job.get("objective") or job.get("job_id") or "Unnamed job")
        lines.extend([
            f"- {state}: {objective}",
            f"  Worker/job: {(job.get('worker') or {}).get('worker_id') or 'Not projected'} / {job.get('job_id') or 'Unknown'}",
            f"  Current step: {job.get('current_step') or 'Unknown'}",
            f"  Last activity: {job.get('last_activity_at') or 'Unknown'}",
        ])
        if job.get("accomplished"):
            lines.append(f"  Accomplished: {job['accomplished']}")
        if job.get("gained"):
            lines.append(f"  Gained: {job['gained']}")
        if job.get("next"):
            lines.append(f"  Next: {job['next']}")
        if job.get("public_result"):
            lines.append(f"  Public Worker result: {job['public_result']}")
        lines.append(f"  Parent job: {job.get('parent_campaign_id') or 'Not recorded; no parent completion inferred'}")
        lines.append(f"  Source record: {job.get('source_record_sha256') or 'Unknown'}")
    attention = [item for item in projection.get("attention", [])
                 if isinstance(item, dict) and item.get("actionable")]
    lines.extend(["", "BLOCKERS / DECISIONS"])
    if not attention:
        lines.append("- No presently actionable canonical Attention request is projected.")
    for item in attention:
        lines.append(f"- Campaign / request: {item.get('campaign_id') or 'Unknown'} / {item.get('attention_id') or 'Unknown'}")
        lines.append(f"- {item.get('blocked_action') or 'Decision required'}")
        lines.append(f"  Why: {item.get('why_required') or 'Canonical owner requires Tanner'}")
        lines.append(f"  Expires: {item.get('expires_at') or 'Unknown'}")
    repository = projection.get("repository") or {}
    build = projection.get("build") or {}
    lines.extend([
        "",
        "COMPACT EVIDENCE",
        f"- Repository: {repository.get('branch') or 'Unknown'} @ {repository.get('head') or 'Unknown'}",
        f"- Working-tree paths observed: {(repository.get('status_summary') or {}).get('dirty_paths', 'Unknown')}",
        f"- Console build: {build.get('release_id') or 'Unknown'} ({build.get('mode') or 'Unknown'})",
        "- Review/application/deployment: consult each job's recorded state; this export grants no authority.",
        "",
        "STEERING QUESTION",
        "What should Fawkes do next after any listed Needs You item and the current authorized job are resolved?",
    ])
    content = "\n".join(lines) + "\n"
    if len(content.encode("utf-8")) > DEV_CONSOLE_MAX_UPDATE_BYTES:
        raise ValueError("console update exceeds its byte limit")
    return content


class ConsoleUpdateStore:
    """Append-only, authenticated console-to-PC status snapshots."""
    _ID = re.compile(r"^console-update-[a-f0-9]{64}$")
    _KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{15,127}$")

    def __init__(self, root):
        self.root = Path(root)
        self._lock = threading.RLock()

    @staticmethod
    def _canonical(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")

    def _prepare(self):
        root_existed = self.root.exists()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        if not root_existed:
            self._fsync_directory(self.root.parent)
        for name in ("records", "idempotency"):
            path = self.root / name
            existed = path.exists()
            path.mkdir(exist_ok=True, mode=0o700)
            path.chmod(0o700)
            if not existed:
                self._fsync_directory(self.root)

    @staticmethod
    def _fsync_directory(path):
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _write_atomic(path, body):
        temporary = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
        try:
            with temporary.open("xb") as handle:
                os.chmod(temporary, 0o600)
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            ConsoleUpdateStore._fsync_directory(path.parent)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def _read(self, snapshot_id, *, expected_idempotency_sha256=None):
        if not self._ID.fullmatch(str(snapshot_id or "")):
            raise KeyError("console update not found")
        path = self.root / "records" / f"{snapshot_id}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            content = value["content"]
            if (value.get("schema_version") != "fawkes.console_update.v1"
                    or value.get("snapshot_id") != snapshot_id
                    or not isinstance(content, str)
                    or len(content.encode("utf-8")) > DEV_CONSOLE_MAX_UPDATE_BYTES
                    or hashlib.sha256(content.encode("utf-8")).hexdigest()
                    != value.get("content_sha256")):
                raise ValueError("console update integrity check failed")
            retained_key = value.get("idempotency_sha256")
            if (expected_idempotency_sha256 is not None
                    and retained_key is not None
                    and retained_key != expected_idempotency_sha256):
                raise ValueError("console update idempotency binding failed")
            if "campaign_id" in value:
                expected = hashlib.sha256(self._canonical({k:v for k,v in value.items()
                    if k != "record_sha256"})).hexdigest()
                if value.get("record_sha256") != expected:
                    raise ValueError("console update campaign/record binding failed")
            return value
        except FileNotFoundError as exc:
            raise KeyError("console update not found") from exc

    def save(self, *, idempotency_key, projection, campaign_id=None, final_message=None):
        if not self._KEY.fullmatch(str(idempotency_key or "")):
            raise ValueError("console update idempotency key is malformed")
        if campaign_id is not None and (not isinstance(campaign_id, str)
                or not any(c.get("campaign_id") == campaign_id for c in projection.get("campaigns", []))):
            raise ValueError("selected campaign is not in the authenticated observation")
        projection = dict(projection, selected_campaign_id=campaign_id or projection.get("current_campaign_id"))
        message_binding = None
        if final_message is not None:
            if (not isinstance(final_message, dict) or final_message.get('role') != 'worker'
                    or final_message.get('phase') != 'final_answer'
                    or not isinstance(final_message.get('text'), str)):
                raise ValueError('an actual final Worker message is required')
            body = final_message['text'].encode('utf-8')
            if not body or len(body) > DEV_CONSOLE_MAX_UPDATE_BYTES or '\0' in final_message['text']:
                raise ValueError('complete final message exceeds clipboard capacity; it was not truncated')
            if hashlib.sha256(body).hexdigest() != final_message.get('content_sha256'):
                raise ValueError('final Worker message digest mismatch')
            message_binding = {key: final_message.get(key) for key in
                               ('thread_id', 'turn_id', 'message_id', 'content_sha256')}
            if any(not isinstance(value, str) or not value or len(value) > 200 for value in message_binding.values()):
                raise ValueError('final Worker message identity unavailable')
        def bound(record):
            if campaign_id is not None and record.get("campaign_id") != campaign_id:
                raise ValueError("retry key is already bound to a different campaign snapshot")
            if record.get('worker_message') != message_binding:
                raise ValueError('retry key is already bound to a different message or update kind')
            return record
        with self._lock:
            self._prepare()
            key_digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
            key_path = self.root / "idempotency" / f"{key_digest}.txt"
            lock_path = self.root / "idempotency" / f"{key_digest}.lock"
            with lock_path.open("a+b") as descriptor:
                os.chmod(lock_path, 0o600)
                fcntl.flock(descriptor.fileno(), fcntl.LOCK_EX)
                try:
                    if key_path.exists():
                        return bound(self._read(
                            key_path.read_text(encoding="ascii").strip(),
                            expected_idempotency_sha256=key_digest,
                        ))
                    seed = {"schema_version": "fawkes.console_update.identity.v2",
                            "idempotency_sha256": key_digest}
                    snapshot_id = "console-update-" + hashlib.sha256(
                        self._canonical(seed)).hexdigest()
                    record_path = self.root / "records" / f"{snapshot_id}.json"
                    if record_path.exists():
                        record = bound(self._read(
                            snapshot_id, expected_idempotency_sha256=key_digest))
                    else:
                        created_at = datetime.now(timezone.utc).isoformat()
                        content = (final_message['text'] if final_message is not None else
                                   _console_update_text(projection, created_at=created_at, snapshot_id=snapshot_id))
                        record = {"schema_version": "fawkes.console_update.v1",
                                  "snapshot_id": snapshot_id, "created_at": created_at,
                                  "projection_observed_at": projection.get("observed_at"),
                                  "campaign_id": projection.get("selected_campaign_id"),
                                  "idempotency_sha256": key_digest,
                                  "content_sha256": hashlib.sha256(
                                      content.encode("utf-8")).hexdigest(),
                                  "content": content, "creates_authority": False,
                                  "creates_continuing_authority": False}
                        if message_binding is not None:
                            record['worker_message'] = message_binding
                        record["record_sha256"] = hashlib.sha256(self._canonical(record)).hexdigest()
                        self._write_atomic(record_path, self._canonical(record))
                    self._write_atomic(key_path, (snapshot_id + "\n").encode("ascii"))
                    return record
                finally:
                    fcntl.flock(descriptor.fileno(), fcntl.LOCK_UN)

    def get(self, snapshot_id):
        with self._lock:
            self._prepare()
            return self._read(snapshot_id)

    def list(self):
        with self._lock:
            self._prepare()
            records = []
            for path in (self.root / "records").glob("console-update-*.json"):
                try:
                    record = self._read(path.stem)
                except (KeyError, OSError, ValueError, json.JSONDecodeError):
                    continue
                records.append({key: record[key] for key in (
                    "snapshot_id", "created_at", "projection_observed_at", "content_sha256")})
            records.sort(key=lambda item: item["created_at"], reverse=True)
            records = records[:DEV_CONSOLE_MAX_UPDATES]
            return {"schema_version": "fawkes.console_updates.v1", "updates": records,
                    "creates_authority": False, "creates_continuing_authority": False}


class BrowserSessionStore:
    """Protected revocable browser sessions; only token digests reach disk."""
    def __init__(self, root):
        self.root = Path(root)

    def create(self):
        return self.create_bound()[0]

    def create_bound(self):
        token = secrets.token_urlsafe(32)
        csrf_token = self._session_csrf(token)
        digest = hashlib.sha256(token.encode()).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        path = self.root / f"{digest}.json"
        temporary = self.root / f".{digest}.{secrets.token_hex(8)}.tmp"
        temporary.write_text(json.dumps({"schema_version": 1,
            "expires_epoch": int(time.time()) + SESSION_MAX_AGE_SECONDS,
            "rider_id": "tanner",
            "csrf_sha256": hashlib.sha256(csrf_token.encode()).hexdigest()}), encoding="utf-8")
        temporary.chmod(0o600); temporary.replace(path)
        path.chmod(0o600)
        return token, csrf_token

    @staticmethod
    def _session_csrf(token):
        return hmac.new(token.encode(), b"fawkes-browser-session-csrf-v1", hashlib.sha256).hexdigest()

    def console_csrf(self, token):
        """Recover only the current session's existing CSRF value, without writes.

        Older random-CSRF sessions require fresh login. This neither extends a
        session nor changes its stored digest or any Attention record.
        """
        csrf = self._session_csrf(token)
        if not self.valid_csrf(token, csrf):
            raise PermissionError("Sign in again to enable decisions in this browser session.")
        return csrf

    def valid(self, token):
        if not token:
            return False
        path = self.root / f"{hashlib.sha256(token.encode()).hexdigest()}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value.get("schema_version") == 1 and int(value["expires_epoch"]) > int(time.time())
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return False

    def valid_csrf(self, token, csrf_token, *, rider_id="tanner"):
        if not token or not csrf_token or rider_id != "tanner":
            return False
        path = self.root / f"{hashlib.sha256(token.encode()).hexdigest()}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            expected = value.get("csrf_sha256", "")
            supplied = hashlib.sha256(csrf_token.encode()).hexdigest()
            return (value.get("schema_version") == 1
                    and value.get("rider_id") == rider_id
                    and int(value["expires_epoch"]) > int(time.time())
                    and bool(expected) and hmac.compare_digest(supplied, expected))
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return False

    def revoke(self, token):
        """Durably revoke one browser session without retaining its bearer value."""
        if not token:
            return False
        path = self.root / f"{hashlib.sha256(token.encode()).hexdigest()}.json"
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False


def build_identity():
    release = next((parent / "release.json" for parent in Path(__file__).resolve().parents
                    if (parent / "release.json").is_file()), None)
    if release:
        value = json.loads(release.read_text(encoding="utf-8"))
        return {"mode": "approved_release", "release_id": value.get("release_id"),
                "manifest_sha256": value.get("manifest_sha256")}
    files = [Path(__file__), STATIC_DIR / "index.html", STATIC_DIR / "app.js",
             STATIC_DIR / "app.css", STATIC_DIR / "dev-console" / "index.html",
             STATIC_DIR / "dev-console" / "console.js",
             STATIC_DIR / "dev-console" / "worker.js",
             STATIC_DIR / "dev-console" / "console.css"]
    digest = hashlib.sha256()
    for item in files: digest.update(item.read_bytes())
    return {"mode": "development_checkout", "release_id": "development-" + digest.hexdigest(),
            "manifest_sha256": None}


def default_bind_host(*, app_token, configured_host=None):
    """Expose the app only when authentication has been configured."""
    return configured_host or ("0.0.0.0" if app_token else "127.0.0.1")


def bind_requires_token(host):
    return host not in {"127.0.0.1", "localhost", "::1"}


class FawkesAppHandler(BaseHTTPRequestHandler):
    server_version = "FawkesApp/1"

    def log_message(self, format, *args):
        return

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _text(self, status, body, *, filename=None):
        body = body.encode("utf-8") if isinstance(body, str) else bytes(body)
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        expected = self.server.app_token
        if not expected:
            return True
        supplied = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if supplied.startswith(prefix) and hmac.compare_digest(supplied[len(prefix):], expected):
            return True
        cookies = {}
        for part in self.headers.get("Cookie", "").split(";"):
            name, separator, value = part.strip().partition("=")
            if separator: cookies[name] = value
        return self.server.app_session_store.valid(cookies.get(SESSION_COOKIE, ""))

    def _session_token(self):
        for part in self.headers.get("Cookie", "").split(";"):
            name, separator, value = part.strip().partition("=")
            if separator and name == SESSION_COOKIE:
                return value
        return ""

    def _establish_session(self):
        value, csrf_token = self.server.app_session_store.create_bound()
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto", "").lower() == "https" else ""
        body = json.dumps({"authenticated_rider": "tanner", "csrf_token": csrf_token}).encode("utf-8")
        self.send_response(200)
        self.send_header("Set-Cookie", f"{SESSION_COOKIE}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_MAX_AGE_SECONDS}{secure}")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _require_attention_decision_auth(self):
        session = self._session_token()
        csrf_token = self.headers.get("X-Fawkes-CSRF-Token", "")
        if self.server.app_session_store.valid_csrf(session, csrf_token, rider_id="tanner"):
            return True
        self._json(403, {"error": {"code": "attention_decision_auth_required",
            "message": "A current Tanner browser session and session-bound CSRF token are required."}})
        return False

    def _require_recording_settings_auth(self):
        if not self._require_auth(record_rider_activity=False):
            return False
        origin = self.headers.get("Origin")
        parsed = urlparse(origin) if origin else None
        if (parsed and (parsed.scheme not in {"http", "https"}
                or parsed.netloc.lower() != self.headers.get("Host", "").lower())):
            self._json(403, {"error": {"code": "recording_settings_auth_required",
                "message": "Recording settings require this app's authenticated browser session."}})
            return False
        if self.server.app_session_store.valid_csrf(
                self._session_token(), self.headers.get("X-Fawkes-CSRF-Token", ""),
                rider_id="tanner"):
            return True
        self._json(403, {"error": {"code": "recording_settings_auth_required",
            "message": "A current browser session and session-bound CSRF token are required to change recording."}})
        return False

    def _attention_decision_failure(self, status, code, message, attention_id):
        """Return an exact body-free lifecycle with a decision failure.

        Failure projection never creates or repairs a decision. It lets the
        browser replace a stale actionable card with the server-owned state for
        the exact URL identity.
        """
        payload = {"error": {"code": code, "message": str(message)},
                   "creates_authority": False,
                   "creates_continuing_authority": False}
        try:
            lifecycle = self.server.chat_service.development_attention_event(
                unquote(attention_id))
            attention = lifecycle.get("attention") if isinstance(lifecycle, dict) else None
            if (isinstance(attention, dict)
                    and attention.get("attention_id") == unquote(attention_id)):
                payload.update({"attention": attention,
                                "decision": lifecycle.get("decision")})
        except (KeyError, ValueError, RuntimeError):
            pass
        self._json(status, payload)

    def _require_auth(self, *, record_rider_activity=True):
        if self._authorized():
            instance_id = getattr(self.server.chat_service, "instance_id", None)
            if record_rider_activity and instance_id:
                RiderActivityStore(
                    instance_id,
                    root=Path(os.environ.get("FAWKES_RUNTIME_STATE_ROOT") or Path(__file__).resolve().parents[2]) / "database" / "rider_activity",
                ).touch(authenticated_rider=True)
            return True
        self._json(401, {"error": {"code": "unauthorized", "message": "Access token required."}})
        return False

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ChatServiceError("Invalid request.", code="invalid_request") from exc
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ChatServiceError("Invalid request size.", code="invalid_request")
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ChatServiceError("Invalid request.", code="invalid_request") from exc
        if not isinstance(value, dict):
            raise ChatServiceError("Invalid request.", code="invalid_request")
        return value

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        reply_match = re.fullmatch(r'/api/development/worker/replies/([0-9a-f-]{36})', path)
        if path == '/api/development/worker' or reply_match:
            if not self._require_auth(record_rider_activity=False): return
            try:
                worker = getattr(self.server, 'worker_conversation', None)
                if worker is None:
                    raise RuntimeError('The same-session Worker connection is not configured.')
                query = parse_qs(parsed.query, keep_blank_values=True)
                if set(query) - {'cursor'} or any(len(v) != 1 for v in query.values()):
                    raise ValueError('invalid Worker page query')
                value = worker.reply_status(reply_match.group(1)) if reply_match else worker.projection(query.get('cursor', [None])[0])
                self._json(200, value)
            except (ValueError, FileNotFoundError) as exc:
                self._json(400, {'error': {'code': 'invalid_worker_request', 'message': str(exc)}})
            except Exception:
                self._json(503, {'error': {'code': 'worker_not_connected', 'message':
                    'This Worker conversation is not available through its supported shared connection. Retained text is last known; no reply is confirmed.'}})
            return
        if path == "/api/status":
            self._json(200, {"service": "fawkes", "state": "ready", "build": build_identity()})
            return

        if path == "/api/chat":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.history())
            except ChatServiceError as exc:
                self._json(400, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "chat_unavailable", "message": "Fawkes is unavailable right now."}})
            return
        inspector_prefix = "/api/chat/messages/"
        inspector_suffix = "/context-inspector"
        if path.startswith(inspector_prefix) and path.endswith(inspector_suffix):
            if not self._require_auth():
                return
            message_id = path[len(inspector_prefix):-len(inspector_suffix)].strip("/")
            try:
                self._json(200, self.server.chat_service.context_inspector(message_id))
            except ChatServiceError as exc:
                status = 404 if exc.code == "context_inspection_not_found" else 409 if exc.code == "context_inspection_invalid" else 400
                self._json(status, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "context_inspection_unavailable", "message": "Context inspection is unavailable right now."}})
            return
        if path == "/api/capabilities":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.capabilities())
            except Exception:
                self._json(503, {"error": {"code": "capabilities_unavailable", "message": "Capability discovery is unavailable right now."}})
            return
        if path == "/api/preferences/recording":
            if not self._require_auth(record_rider_activity=False):
                return
            try:
                self._json(200, self.server.chat_service.get_recording_policy())
            except Exception:
                self._json(503, {"error": {"code": "recording_policy_unavailable",
                    "message": "Recording settings could not be read. No recording mode has been assumed."}})
            return
        if path == "/api/preferences/sounds":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.sound_settings())
            except Exception:
                self._json(503, {"error": {"code": "sound_preferences_unavailable", "message": "Sound settings are unavailable right now."}})
            return
        if path == "/api/presence":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.presence_profile())
            except Exception:
                self._json(503, {"error": {"code": "presence_unavailable", "message": "Phoenix Presence is unavailable right now; Chat remains available."}})
            return
        if path == "/api/library":
            if not self._require_auth(): return
            try: self._json(200, self.server.chat_service.library_catalog())
            except Exception: self._json(503, {"error": {"code": "library_unavailable", "message": "Library is unavailable right now."}})
            return
        history_evidence_prefix = "/api/history/evidence/"
        if path.startswith(history_evidence_prefix):
            if not self._require_auth(): return
            parts = path[len(history_evidence_prefix):].strip("/").split("/", 1)
            if len(parts) != 2:
                self._json(400, {"error": {"code": "invalid_history_evidence", "message": "History evidence domain and identity are required."}}); return
            try: self._json(200, self.server.chat_service.historical_evidence(unquote(parts[0]), unquote(parts[1])))
            except ChatServiceError as exc:
                self._json(404 if exc.code == "history_evidence_not_found" else 400,
                           {"error": {"code": exc.code, "message": str(exc)}})
            except Exception: self._json(503, {"error": {"code": "history_unavailable", "message": "Historical evidence is unavailable right now."}})
            return
        if path == "/api/development/observations":
            if not self._require_auth():
                return
            query = parse_qs(parsed.query)
            try:
                self._json(200, {"observations": self.server.chat_service.list_observations(
                    category=query.get("category", [None])[0],
                    status=query.get("status", [None])[0],
                )})
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Development observations are unavailable right now."}})
            return
        if path == "/api/development/dashboard":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.development_dashboard())
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Development information is unavailable right now."}})
            return
        if path == "/api/development/dev-console":
            if not self._require_auth(record_rider_activity=False):
                return
            try:
                self._json(200, developer_console_projection(self.server.chat_service))
            except Exception:
                self._json(503, {"error": {"code": "dev_console_projection_unavailable",
                    "message": "The read-only developer-console projection is unavailable right now."}})
            return
        if path == "/api/development/console-updates":
            if not self._require_auth(record_rider_activity=False):
                return
            try:
                payload = self.server.console_update_store.list()
                delivery = getattr(self.server, 'console_clipboard_delivery', None)
                if delivery is not None:
                    for item in payload['updates']:
                        item['windows_clipboard'] = delivery.status(item)
                self._json(200, payload)
            except Exception:
                self._json(503, {"error": {"code": "console_updates_unavailable",
                    "message": "Prepared console updates are unavailable right now."}})
            return
        update_match = re.fullmatch(
            r"/api/development/console-updates/(console-update-[a-f0-9]{64})(\.txt)?", path)
        if update_match:
            if not self._require_auth(record_rider_activity=False):
                return
            try:
                update = self.server.console_update_store.get(update_match.group(1))
                if update_match.group(2):
                    self._text(200, update["content"],
                               filename=f"{update['snapshot_id']}.txt")
                else:
                    delivery = getattr(self.server, 'console_clipboard_delivery', None)
                    if delivery is not None:
                        update = {**update, 'windows_clipboard': delivery.status(update)}
                    self._json(200, update)
            except KeyError:
                self._json(404, {"error": {"code": "console_update_not_found",
                    "message": "That prepared console update is not available."}})
            except Exception:
                self._json(503, {"error": {"code": "console_updates_unavailable",
                    "message": "Prepared console updates are unavailable right now."}})
            return
        if path == "/api/development/codex-campaigns":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.list_codex_development_campaigns())
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Campaign activity is unavailable right now."}})
            return
        campaign_prefix = "/api/development/codex-campaigns/"
        if path.startswith(campaign_prefix) and path.count("/") == 4:
            if not self._require_auth():
                return
            campaign_id = unquote(path[len(campaign_prefix):])
            try:
                self._json(200, self.server.chat_service.codex_development_campaign(campaign_id))
            except KeyError:
                self._json(404, {"error": {"code": "campaign_not_found", "message": "Development campaign not found."}})
            except (ValueError, PermissionError) as exc:
                self._json(400, {"error": {"code": "invalid_campaign", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Development campaign status is unavailable right now."}})
            return
        if path.startswith(campaign_prefix) and path.endswith("/evidence"):
            if not self._require_auth():
                return
            campaign_id = unquote(path[len(campaign_prefix):-len("/evidence")].strip("/"))
            try:
                self._json(200, self.server.chat_service.codex_development_campaign_evidence(campaign_id))
            except KeyError:
                self._json(404, {"error": {"code": "campaign_not_found", "message": "Development campaign not found."}})
            except Exception:
                self._json(503, {"error": {"code": "campaign_evidence_unavailable", "message": "Exact campaign evidence is unavailable right now."}})
            return
        if path == "/api/development/runtime-status":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.production_component_status())
            except Exception:
                self._json(503, {"error": {"code": "runtime_status_unavailable", "message": "Fawkes component status is unavailable right now."}})
            return
        if path == "/api/development/attention":
            if not self._require_auth():
                return
            try:
                query = parse_qs(parsed.query)
                owner = (self.server.chat_service.development_attention_projection
                    if query.get("observation", ["false"])[0].lower() == "true"
                    else self.server.chat_service.development_attention)
                self._json(200, owner(
                    pending_only=query.get("pending", ["false"])[0].lower() == "true"))
            except Exception:
                self._json(503, {"error": {"code": "attention_unavailable", "message": "Development attention state is unavailable right now."}})
            return
        attention_prefix = "/api/development/attention/"
        if path.startswith(attention_prefix) and path.count("/") == 4:
            if not self._require_auth():
                return
            attention_id = unquote(path[len(attention_prefix):])
            try:
                self._json(200, self.server.chat_service.development_attention_event(attention_id))
            except KeyError:
                self._json(404, {"error": {"code": "attention_not_found", "message": "That Tanner attention request does not exist in this Fawkes build."}})
            except Exception:
                self._json(503, {"error": {"code": "attention_unavailable", "message": "Development attention state is unavailable right now."}})
            return
        if path == "/api/development/test-center":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.acceptance_center().snapshot())
            except Exception:
                self._json(503, {"error": {"code": "test_center_unavailable", "message": "The Capability Test Center is unavailable right now."}})
            return
        prefix = "/api/development/observations/"
        if path.startswith(prefix) and path.count("/") == 4:
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.inspect_observation(path[len(prefix):]))
            except ChatServiceError as exc:
                self._json(404, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Development observations are unavailable right now."}})
            return
        self._serve_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        if path in {'/api/development/worker/replies', '/api/development/worker/clipboard'}:
            if not self._require_auth(record_rider_activity=False): return
            if not self._require_attention_decision_auth(): return
            try:
                from src.runtime.worker_conversation import unique
                length = int(self.headers.get('Content-Length', '0'))
                if length <= 0 or length > 100_000: raise ValueError('Worker input exceeds its bound')
                request = json.loads(self.rfile.read(length), object_pairs_hook=unique)
                if not isinstance(request, dict): raise ValueError('Worker request must be an object')
                worker = getattr(self.server, 'worker_conversation', None)
                if worker is None: raise RuntimeError('Worker connection is not configured')
                if path.endswith('/replies'):
                    if set(request) != {'thread_id', 'reply_id', 'text'}:
                        raise ValueError('only reply text and exact identities are accepted')
                    value = worker.send_reply(**request)
                else:
                    if set(request) != {'thread_id', 'message_id', 'content_sha256', 'idempotency_key'}:
                        raise ValueError('only the displayed final message identity is accepted')
                    final = worker.exact_final(**{k:v for k,v in request.items() if k != 'idempotency_key'})
                    projection = developer_console_projection(self.server.chat_service)
                    value = self.server.console_clipboard_delivery.send(
                        idempotency_key=request['idempotency_key'], projection=projection,
                        campaign_id=projection.get('current_campaign_id'), final_message=final)
                self._json(201, value)
            except (ValueError, ChatServiceError) as exc:
                self._json(400, {'error': {'code': 'invalid_worker_request', 'message': str(exc)}})
            except Exception:
                self._json(503, {'error': {'code': 'worker_delivery_unconfirmed', 'message':
                    'Delivery is not confirmed. Preserve this request identity; do not send a duplicate. Saved updates and replies remain available.'}})
            return
        if path == "/api/session":
            try:
                credential = self._read_json().get("credential", "")
            except ChatServiceError:
                self._json(400, {"error": {"code": "invalid_session_request", "message": "A Fawkes app credential is required."}})
                return
            if not self.server.app_token or not hmac.compare_digest(str(credential), self.server.app_token):
                self._json(401, {"error": {"code": "unauthorized", "message": "That Fawkes app credential was not accepted."}})
                return
            self._establish_session()
            return
        if path == "/api/session/logout":
            session = self._session_token()
            csrf_token = self.headers.get("X-Fawkes-CSRF-Token", "")
            if not self.server.app_session_store.valid_csrf(
                    session, csrf_token, rider_id="tanner"):
                self._json(403, {"error": {"code": "session_logout_auth_required",
                    "message": "A current Tanner session and session-bound CSRF token are required."}})
                return
            self.server.app_session_store.revoke(session)
            body = json.dumps({"authenticated_rider": None}).encode("utf-8")
            self.send_response(200)
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/development/console-updates":
            if not self._require_auth(record_rider_activity=False):
                return
            if not self._require_attention_decision_auth():
                return
            try:
                request = self._read_json()
                if set(request) not in ({"idempotency_key"}, {"idempotency_key", "campaign_id"}):
                    raise ValueError("only an idempotency key and optional campaign identity are accepted")
                projection = developer_console_projection(self.server.chat_service)
                delivery = getattr(self.server, 'console_clipboard_delivery', None)
                save = delivery.send if delivery is not None else self.server.console_update_store.save
                update = save(
                    idempotency_key=request["idempotency_key"], projection=projection,
                    campaign_id=request.get("campaign_id"))
                self._json(201, update)
            except (ValueError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_console_update",
                    "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "console_update_failed",
                    "message": "Windows delivery was not confirmed. The snapshot may already be saved; retry checks the same request. Previous updates are preserved."}})
            return
        observation_prefix = "/api/development/observations/"
        proposal_prefix = "/api/development/proposals/"
        test_prefix = "/api/development/test-center/tests/"
        run_prefix = "/api/development/test-center/runs/"
        feedback_prefix = "/api/chat/messages/"
        feedback_suffix = "/context-feedback"
        if path == "/api/development/codex-handoffs":
            if not self._require_auth():
                return
            try:
                self._json(201, self.server.chat_service.codex_development_handoff(
                    self._read_json(), authenticated_rider=True))
            except PermissionError as exc:
                self._json(403, {"error": {"code": "codex_handoff_denied", "message": str(exc)}})
            except (ValueError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_codex_handoff", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "codex_handoff_unavailable",
                    "message": "The Codex Development handoff is unavailable right now."}})
            return
        if path == "/api/development/runtime-control":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.control_production_component(
                    self._read_json(), authenticated_rider=True))
            except PermissionError as exc:
                self._json(403, {"error": {"code": "runtime_control_denied", "message": str(exc)}})
            except (ValueError, RuntimeError) as exc:
                self._json(400, {"error": {"code": "runtime_control_failed", "message": str(exc)}})
            return
        if path == "/api/development/codex-campaigns":
            if not self._require_auth():
                return
            try:
                self._json(201, self.server.chat_service.create_codex_development_campaign(
                    self._read_json(), authenticated_rider=True))
            except PermissionError as exc:
                self._json(403, {"error": {"code": "campaign_denied", "message": str(exc)}})
            except (ValueError, RuntimeError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_campaign", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "campaign_unavailable",
                    "message": "The bounded Codex Development campaign is unavailable right now."}})
            return
        campaign_prefix = "/api/development/codex-campaigns/"
        if path.startswith(campaign_prefix) and path.endswith("/cancel"):
            if not self._require_auth():
                return
            campaign_id = unquote(path[len(campaign_prefix):-len("/cancel")].strip("/"))
            try:
                self._read_json()
                self._json(200, self.server.chat_service.cancel_codex_development_campaign(
                    campaign_id, authenticated_rider=True))
            except PermissionError as exc:
                self._json(403, {"error": {"code": "campaign_cancel_denied", "message": str(exc)}})
            except (KeyError, ValueError, RuntimeError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_campaign_cancel", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "campaign_unavailable",
                    "message": "The bounded Codex Development campaign is unavailable right now."}})
            return
        if path.startswith(campaign_prefix) and path.endswith("/review"):
            if not self._require_auth():
                return
            campaign_id = unquote(path[len(campaign_prefix):-len("/review")].strip("/"))
            try:
                self._read_json()
                self._json(200, self.server.chat_service.review_codex_development_campaign(
                    campaign_id, authenticated_rider=True))
            except PermissionError as exc:
                self._json(403, {"error": {"code": "campaign_review_denied", "message": str(exc)}})
            except (KeyError, ValueError, RuntimeError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_campaign_review", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "campaign_review_unavailable",
                    "message": "The formal campaign review is unavailable right now."}})
            return
        if path.startswith(campaign_prefix) and "/attention/" in path and path.endswith("/decision"):
            if not self._require_attention_decision_auth():
                return
            remainder = path[len(campaign_prefix):-len("/decision")].strip("/")
            campaign_id, marker, attention_id = remainder.partition("/attention/")
            if not marker:
                self._json(400, {"error": {"code": "invalid_attention_decision", "message": "Attention identity is required."}}); return
            try:
                payload = self._read_json()
                if not isinstance(payload.get("identity"), dict):
                    raise ValueError("complete immutable attention identity is required")
                self._json(200, self.server.chat_service.decide_development_attention(
                    unquote(campaign_id), unquote(attention_id), payload.get("choice"),
                    authenticated_rider=True, expected_identity=payload.get("identity")))
            except PermissionError as exc:
                self._attention_decision_failure(
                    403, "attention_decision_denied", exc, attention_id)
            except Exception as exc:
                from src.runtime.development_attention import AttentionConsumerUnavailable
                if isinstance(exc, AttentionConsumerUnavailable):
                    self._attention_decision_failure(
                        409, exc.code, exc, attention_id)
                    return
                if isinstance(exc, (KeyError, ValueError, RuntimeError)):
                    self._attention_decision_failure(
                        400, "invalid_attention_decision", exc, attention_id)
                    return
                raise
            return
        if path.startswith(feedback_prefix) and path.endswith(feedback_suffix):
            if not self._require_auth():
                return
            message_id = path[len(feedback_prefix):-len(feedback_suffix)].strip("/")
            try:
                self._json(201, {"feedback": self.server.chat_service.context_feedback(
                    message_id, self._read_json())})
            except ChatServiceError as exc:
                status = 404 if exc.code == "context_inspection_not_found" else 409 if exc.code == "context_inspection_invalid" else 400
                self._json(status, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "context_feedback_unavailable",
                    "message": "Context feedback could not be recorded right now."}})
            return
        if path == "/api/preferences/presence":
            if not self._require_auth(): return
            try: self._json(200, self.server.chat_service.update_presence_preferences(self._read_json()))
            except (ValueError, ChatServiceError) as exc: self._json(400, {"error": {"code": "invalid_presence_preferences", "message": str(exc)}})
            except Exception: self._json(503, {"error": {"code": "presence_unavailable", "message": "Phoenix Presence settings are unavailable right now."}})
            return
        if path == "/api/preferences/recording":
            if not self._require_recording_settings_auth():
                return
            try:
                if int(self.headers.get("Content-Length", "0")) > 16384:
                    raise ValueError("Recording settings request is too large.")
                payload = self._read_json()
                if set(payload) != {"changes", "expected_revision"}:
                    raise ValueError("Changes and the current revision are required.")
                revision = payload["expected_revision"]
                changes = payload["changes"]
                if type(revision) is not int or revision < 0:
                    raise ValueError("The current recording revision is required.")
                if not isinstance(changes, dict) or set(changes) - {"mode", "categories"}:
                    raise ValueError("Unknown recording setting.")
                if "mode" in changes and changes["mode"] not in ("private", "retained"):
                    raise ValueError("Recording mode must be private or retained.")
                categories = changes.get("categories", {})
                if (not isinstance(categories, dict)
                        or set(categories) - set(EDITABLE_CATEGORIES)
                        or any(type(value) is not bool for value in categories.values())):
                    raise ValueError("Unknown, unavailable or invalid recording category.")
                self._json(200, self.server.chat_service.update_recording_policy(
                    changes, expected_revision=revision))
            except RecordingPolicyConflict:
                self._json(409, {"error": {"code": "recording_policy_conflict",
                    "message": "Recording settings changed elsewhere. Reload them before making another change."}})
            except RecordingPolicyDurabilityError:
                self._json(503, {"error": {"code": "recording_policy_commit_unconfirmed",
                    "message": "The settings replacement may be visible, but durable saving was not confirmed. Reload the current settings; do not repeat the write automatically."}})
            except RecordingPolicyError:
                self._json(503, {"error": {"code": "recording_policy_unavailable",
                    "message": "Recording settings could not be safely updated. Reload the current settings before making another change."}})
            except (ValueError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_recording_settings", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "recording_policy_unavailable",
                    "message": "Saving recording settings was not confirmed. Reload the current settings before making another change."}})
            return
        if path == "/api/preferences/sounds":
            if not self._require_auth():
                return
            try:
                self._json(200, self.server.chat_service.update_sound_settings(self._read_json()))
            except (ValueError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_sound_preferences", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "sound_preferences_unavailable", "message": "Sound settings are unavailable right now."}})
            return
        if path == "/api/library/search":
            if not self._require_auth(): return
            try:
                payload = self._read_json(); self._json(200, self.server.chat_service.library_search(payload.get("query")))
            except (ValueError, ChatServiceError) as exc: self._json(400, {"error": {"code": "invalid_library_query", "message": str(exc)}})
            except Exception: self._json(503, {"error": {"code": "library_unavailable", "message": "Library search is unavailable right now."}})
            return
        if path == "/api/history/search":
            if not self._require_auth(): return
            try: self._json(200, self.server.chat_service.historical_search(self._read_json()))
            except ChatServiceError as exc: self._json(400, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception: self._json(503, {"error": {"code": "history_unavailable", "message": "Historical search is unavailable right now."}})
            return
        if path == "/api/history/validate":
            if not self._require_auth(): return
            try: self._json(200, self.server.chat_service.historical_corpus_validation(self._read_json()))
            except ChatServiceError as exc: self._json(400, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception: self._json(503, {"error": {"code": "history_validation_unavailable", "message": "Historical corpus validation is unavailable right now."}})
            return
        library_extract_prefix = "/api/library/sources/"
        if path.startswith(library_extract_prefix) and path.endswith("/extract"):
            if not self._require_auth(): return
            source_id = unquote(path[len(library_extract_prefix):-len("/extract")].strip("/"))
            try:
                self._read_json()
                self._json(200, self.server.chat_service.library_extract(source_id))
            except ChatServiceError as exc:
                status = 404 if exc.code == "library_source_not_found" else 400
                self._json(status, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "library_extraction_unavailable", "message": "Library extraction is unavailable right now."}})
            return
        if path == "/api/development/test-center/run-all":
            if not self._require_auth():
                return
            try:
                payload = self._read_json()
                self._json(202, self.server.chat_service.acceptance_center().start_all(platform=payload.get("platform")))
            except (ValueError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_acceptance_request", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "test_center_unavailable", "message": "The Capability Test Center is unavailable right now."}})
            return
        if path.startswith(test_prefix) and path.endswith("/run"):
            if not self._require_auth():
                return
            test_id = path[len(test_prefix):-len("/run")].strip("/")
            try:
                payload = self._read_json()
                self._json(202, self.server.chat_service.acceptance_center().start(test_id, platform=payload.get("platform")))
            except (ValueError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_acceptance_request", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "test_center_unavailable", "message": "The Capability Test Center is unavailable right now."}})
            return
        if path.startswith(run_prefix) and path.endswith("/complete"):
            if not self._require_auth():
                return
            run_id = path[len(run_prefix):-len("/complete")].strip("/")
            try:
                payload = self._read_json()
                result = self.server.chat_service.acceptance_center().complete(
                    run_id, result=payload.get("result"), actual=payload.get("actual", ""),
                    duration_ms=payload.get("duration_ms", 0), failure_stage=payload.get("failure_stage"),
                    technical=payload.get("technical_details"), source="client",
                )
                self._json(200, result)
            except (ValueError, ChatServiceError) as exc:
                self._json(400, {"error": {"code": "invalid_acceptance_result", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "test_center_unavailable", "message": "The Capability Test Center is unavailable right now."}})
            return
        if path.startswith(proposal_prefix) and path.endswith("/review"):
            if not self._require_auth():
                return
            proposal_id = path[len(proposal_prefix):-len("/review")].strip("/")
            try:
                self._json(200, {"proposal": self.server.chat_service.review_development_proposal(proposal_id, self._read_json())})
            except (ChatServiceError, ValueError) as exc:
                self._json(400, {"error": {"code": "invalid_review", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Development review is unavailable right now."}})
            return
        if path == "/api/research":
            if not self._require_auth():
                return
            try:
                self._json(201, self.server.chat_service.research(self._read_json()))
            except ChatServiceError as exc:
                status = 400 if exc.code.startswith("invalid_") else 503
                self._json(status, {"error": {"code": exc.code, "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "research_unavailable", "message": "Web research is unavailable right now."}})
            return
        if path == "/api/development/observations":
            if not self._require_auth():
                return
            try:
                self._json(201, {"observation": self.server.chat_service.create_observation(self._read_json())})
            except (ChatServiceError, ValueError) as exc:
                self._json(400, {"error": {"code": "invalid_observation", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Development observations are unavailable right now."}})
            return
        if path.startswith(observation_prefix) and path.endswith("/evidence"):
            if not self._require_auth():
                return
            observation_id = path[len(observation_prefix):-len("/evidence")].strip("/")
            try:
                self._json(200, {"observation": self.server.chat_service.add_observation_evidence(observation_id, self._read_json())})
            except (ChatServiceError, ValueError) as exc:
                self._json(400, {"error": {"code": "invalid_observation_evidence", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Development observations are unavailable right now."}})
            return
        if path.startswith(observation_prefix) and path.endswith("/revisions"):
            if not self._require_auth():
                return
            observation_id = path[len(observation_prefix):-len("/revisions")].strip("/")
            try:
                self._json(200, {"observation": self.server.chat_service.revise_observation(observation_id, self._read_json())})
            except (ChatServiceError, ValueError) as exc:
                self._json(400, {"error": {"code": "invalid_observation_revision", "message": str(exc)}})
            except Exception:
                self._json(503, {"error": {"code": "development_unavailable", "message": "Development observations are unavailable right now."}})
            return
        if path != "/api/chat/messages":
            self._json(404, {"error": {"code": "not_found", "message": "Not found."}})
            return
        if not self._require_auth():
            return
        try:
            payload = self._read_json()
            if "recording_mode" in payload and payload["recording_mode"] not in (None, "private", "retained"):
                raise ChatServiceError("Recording mode must be private or retained.", code="invalid_recording_mode")
            result = self.server.chat_service.send(
                payload.get("message"),
                conversation_id=payload.get("conversation_id"),
                attachments=payload.get("attachments"),
                retrieval_clarification=payload.get("retrieval_clarification"),
                **({"recording_mode": payload["recording_mode"]} if "recording_mode" in payload else {}),
            )
            self._json(201, result)
        except ChatServiceError as exc:
            status = 400 if exc.code.startswith("invalid_") else 503
            self._json(status, {"error": {"code": exc.code, "message": str(exc)}})
        except Exception:
            self._json(503, {"error": {"code": "chat_unavailable", "message": "Fawkes is unavailable right now."}})

    def _serve_static(self, path):
        names = {
            "/console-login": ("console-login.html", "text/html; charset=utf-8"),
            "/preview-login.js": ("preview-login.js", "text/javascript; charset=utf-8"),
            "/attention-binding.js": ("attention-binding.js", "text/javascript; charset=utf-8"),
            "/native-attention.js": ("native-attention.js", "text/javascript; charset=utf-8"),
            "/native-attention.css": ("native-attention.css", "text/css; charset=utf-8"),
            "/": ("index.html", "text/html; charset=utf-8"),
            "/app.css": ("app.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/presence-contract.js": ("presence-contract.js", "text/javascript; charset=utf-8"),
            "/presence-controller.js": ("presence-controller.js", "text/javascript; charset=utf-8"),
            "/presence-renderer-three.js": ("presence-renderer-three.js", "text/javascript; charset=utf-8"),
            "/presence-fallback.js": ("presence-fallback.js", "text/javascript; charset=utf-8"),
            "/presence-bootstrap.js": ("presence-bootstrap.js", "text/javascript; charset=utf-8"),
            "/presence-three.bundle.js": ("presence-three.bundle.js", "text/javascript; charset=utf-8"),
            "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
            "/dev-console": ("dev-console/index.html", "text/html; charset=utf-8"),
            "/dev-console/": ("dev-console/index.html", "text/html; charset=utf-8"),
            "/dev-console/index.html": ("dev-console/index.html", "text/html; charset=utf-8"),
            "/dev-console/console.js": ("dev-console/console.js", "text/javascript; charset=utf-8"),
            "/dev-console/console.css": ("dev-console/console.css", "text/css; charset=utf-8"),
            "/dev-console/worker.js": ("dev-console/worker.js", "text/javascript; charset=utf-8"),
        }
        if path.startswith("/assets/presence/"):
            filename = path.removeprefix("/assets/presence/")
            try:
                target = self.server.chat_service.presence_asset_path(filename)
                if target is not None:
                    body = target.read_bytes(); self.send_response(200)
                    self.send_header("Content-Type", "model/gltf-binary")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "public, max-age=3600")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers(); self.wfile.write(body); return
            except Exception:
                pass
            self._json(404, {"error": {"code": "presence_asset_unavailable", "message": "That Phoenix embodiment asset is not installed."}}); return
        if path.startswith("/assets/sounds/"):
            filename = path.removeprefix("/assets/sounds/")
            from src.capabilities.event_audio import SOUND_EVENTS, ASSET_ROOT
            allowed = {item.asset_filename for item in SOUND_EVENTS if item.asset_filename}
            if filename in allowed and (ASSET_ROOT / filename).is_file():
                body = (ASSET_ROOT / filename).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers(); self.wfile.write(body); return
            self._json(404, {"error": {"code": "sound_asset_unavailable", "message": "That approved sound asset is not installed."}}); return
        item = names.get(path)
        if item is None:
            self._json(404, {"error": {"code": "not_found", "message": "Not found."}})
            return
        body = (STATIC_DIR / item[0]).read_bytes()
        identity = build_identity()["release_id"]
        if item[0].endswith("index.html"):
            body = body.replace(b"__FAWKES_BUILD_ID__", identity.encode("ascii"))
        if item[0] == "dev-console/index.html":
            console_context = os.getenv("FAWKES_DEV_CONSOLE_CONTEXT", "")
            if (len(console_context) > 100 or any(
                    character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-"
                    for character in console_context)):
                console_context = ""
            body = body.replace(
                b"__FAWKES_CONSOLE_CONTEXT__", console_context.encode("ascii"))
        asset_sha256 = hashlib.sha256(body).hexdigest()
        self.send_response(200)
        self.send_header("Content-Type", item[1])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Fawkes-Build-ID", identity)
        self.send_header("X-Fawkes-Asset-SHA256", asset_sha256)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:")
        self.end_headers()
        self.wfile.write(body)


class FawkesConsoleApprovalHandler(FawkesAppHandler):
    """Explicit minimal console surface; not the broad Chat/runtime controller.

    Its injected service is bound to one campaign/Attention owner and root.
    The running read-only preview does not select this handler.
    """
    def _same_origin(self):
        origin = self.headers.get("Origin")
        expected = ("https" if isinstance(self.connection, __import__('ssl').SSLSocket) else "http") + "://" + self.headers.get("Host", "")
        if origin != expected:
            self._json(403, {"error": {"code": "same_origin_required", "message": "A same-origin browser request is required."}})
            return False
        return True

    def _require_auth(self, *, record_rider_activity=True):
        # Passive console reads must not fabricate Rider activity.
        return super()._require_auth(record_rider_activity=False)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self._serve_static("/console-login")
        if path == "/preview-login.js":
            return self._serve_static(path)
        allowed = {"/dev-console", "/dev-console/", "/dev-console/console.js",
            "/dev-console/console.css", "/attention-binding.js", "/native-attention.js",
            "/native-attention.css", "/api/status", "/api/development/dev-console",
            "/api/development/console-updates", "/api/development/worker", "/dev-console/worker.js"}
        exact = path.startswith("/api/development/attention/") and path.count("/") == 4
        # The console history uses the passive owner only. Never expose the
        # collection's lifecycle-maintenance branch through this narrow surface.
        history = (path == "/api/development/attention" and
            parse_qs(urlparse(self.path).query, keep_blank_values=True) == {"observation": ["true"]})
        update = bool(re.fullmatch(
            r"/api/development/console-updates/console-update-[a-f0-9]{64}(?:\.txt)?", path))
        worker_reply = bool(re.fullmatch(r'/api/development/worker/replies/[0-9a-f-]{36}', path))
        if path in allowed or exact or update or history or worker_reply:
            return super().do_GET()
        self._json(404, {"error": {"code": "unavailable_in_console"}})

    def do_POST(self):
        path = urlparse(self.path).path
        if not self._same_origin():
            return
        if path == "/api/session/console-csrf":
            try:
                csrf = self.server.app_session_store.console_csrf(self._session_token())
            except PermissionError as exc:
                self._json(401, {"error": {"code": "console_login_required", "message": str(exc)}})
                return
            self._json(200, {"authenticated_rider": "tanner", "csrf_token": csrf})
            return
        decision = (path.startswith("/api/development/codex-campaigns/")
                    and "/attention/" in path and path.endswith("/decision")
                    and path.count("/") == 7)
        if path in {"/api/session", "/api/session/logout",
                    "/api/development/console-updates", "/api/development/worker/replies",
                    "/api/development/worker/clipboard"} or decision:
            return super().do_POST()
        self._json(405, {"error": {"code": "unavailable_in_console"},
                         "creates_authority": False, "creates_continuing_authority": False})


class FawkesAppServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, *, chat_service, app_token, app_session_store=None,
                 console_update_store=None, console_clipboard_writer=None, worker_conversation=None):
        super().__init__(address, FawkesAppHandler)
        self.chat_service = chat_service
        self.app_token = app_token
        self.worker_conversation = worker_conversation
        state_root = Path(os.environ.get("FAWKES_DEVELOPMENT_ROOT", Path.cwd()))
        self.app_session_store = app_session_store or BrowserSessionStore(
            os.environ.get("FAWKES_APP_SESSION_ROOT", state_root / "database" / "app_sessions"))
        self.console_update_store = console_update_store or ConsoleUpdateStore(
            os.environ.get("FAWKES_CONSOLE_UPDATE_ROOT",
                           state_root / "database" / "console_updates"))
        # Only the explicitly configured PC launcher enables Windows execution.
        # No browser request can supply an executable, script, account or writer.
        self.console_clipboard_delivery = ConsoleClipboardDelivery(
            self.console_update_store, console_clipboard_writer)


def main():
    parser = argparse.ArgumentParser(description="Serve the Fawkes mobile Chat app")
    token = os.getenv("FAWKES_APP_TOKEN", "")
    default_host = default_bind_host(
        app_token=token,
        configured_host=os.getenv("FAWKES_APP_HOST"),
    )
    parser.add_argument("--host", default=default_host)
    parser.add_argument("--port", type=int, default=int(os.getenv("FAWKES_APP_PORT", "8787")))
    args = parser.parse_args()
    if bind_requires_token(args.host) and not token:
        parser.error("FAWKES_APP_TOKEN is required when binding beyond this computer")
    service = FawkesChatService()
    server = FawkesAppServer((args.host, args.port), chat_service=service, app_token=token)
    if args.host in {"127.0.0.1", "localhost", "::1"}:
        print(f"Fawkes Chat is local-only at http://127.0.0.1:{args.port}")
        print("Set FAWKES_APP_TOKEN and bind --host 0.0.0.0 for phone access.")
    else:
        print(f"Fawkes Chat is listening on all interfaces at port {args.port}.")
        addresses = set()
        try:
            for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                address = item[4][0]
                if not address.startswith("127."):
                    addresses.add(address)
        except OSError:
            pass
        for address in sorted(addresses):
            print(f"Candidate phone URL: http://{address}:{args.port}")
        print("A WSL/container address may require host forwarding and a firewall rule.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
