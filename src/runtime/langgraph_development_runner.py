"""Bounded LangGraph coordination over canonical Phoenix campaign owners.

LangGraph persists graph position and body-free projections only. The
canonical Development campaign owns provider reservations, review acceptance,
application, Git, Attention, budgets, cancellation, and terminal authority.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import TypedDict
import fcntl
import hashlib
import json
import math
import os
import re
import time

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from src.runtime.codex_development_campaign import (
    CodexDevelopmentCampaign,
    stepwise_campaign_budget_limits,
    stepwise_campaign_status_disposition,
)
from src.runtime.wsl_codex_reviewer import WslCodexReviewAdapter


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode()


def _digest(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def _canonical_campaign_binding(record):
    """Project only immutable identity from a canonical campaign record."""
    budget = record.get("execution_budget_v01")
    if not isinstance(budget, dict):
        raise PermissionError("runner requires a canonical stepwise campaign budget")
    stepwise_campaign_budget_limits(record)
    fields = {
        "campaign_id": record.get("campaign_id"),
        "instance_id": record.get("instance_id"),
        "objective_sha256": record.get("objective_sha256"),
        "objective_mode": record.get("objective_mode"),
        "acceptance_condition_ids": record.get("acceptance_condition_ids"),
        "acceptance_conditions_sha256": _digest(record.get("acceptance_conditions")),
        "allowed_scope_sha256": _digest(record.get("allowed_scope")),
        "source_sections_sha256": _digest(record.get("source_sections")),
        "validation_commands_sha256": _digest(record.get("validation_commands")),
        "validation_policy": record.get("validation_policy"),
        "validation_declaration_sha256": _digest(record.get("validation_declaration")),
        "rider_authorization_reference": record.get("rider_authorization_reference"),
        "recovery_references_sha256": _digest(record.get("recovery_references")),
        "stepwise_v01": record.get("stepwise_v01"),
        "budget_sha256": budget.get("budget_sha256"),
        "maximum_iterations": record.get("maximum_iterations"),
    }
    if (fields["campaign_id"] is None or fields["instance_id"] is None
            or fields["objective_sha256"] is None
            or fields["rider_authorization_reference"] is None
            or fields["stepwise_v01"] is not True):
        raise PermissionError("runner campaign immutable identity is incomplete")
    return fields


def freeze_runner_plan(repository, task, *, campaign_id, limits, campaign_record):
    """Bind coordination to one already-authorized canonical campaign."""
    repository = Path(repository).resolve()
    required_limits = {"seconds", "batches", "provider_turns", "correction_cycles",
                       "cost_units", "iterations", "files"}
    if set(limits) != required_limits or any(type(value) is not int or value <= 0
                                              for value in limits.values()):
        raise ValueError("exact positive runner limits are required")
    if (limits["batches"] != 1 or limits["correction_cycles"] > 2
            or limits["correction_cycles"] >= limits["iterations"]):
        raise ValueError("runner plan exceeds the bounded pilot contract")
    if set(task) != {"task_id", "payload"}:
        raise ValueError("exactly one predeclared task is required")
    payload = task["payload"]
    if payload.get("campaign_id") != campaign_id:
        raise ValueError("task and runner campaign identities differ")
    if "execution_budget_v01" in payload:
        raise ValueError("campaign budget is derived once from the immutable runner plan")
    scope = payload.get("allowed_scope")
    if not isinstance(scope, list) or not scope or len(scope) > limits["files"]:
        raise ValueError("a nonempty fixed path scope within the file limit is required")
    for raw in scope:
        path = PurePosixPath(raw)
        if path.is_absolute() or ".." in path.parts:
            raise PermissionError("runner scope escapes the repository")
    if (not isinstance(campaign_record, dict)
            or campaign_record.get("record_sha256") != _digest({
                key: value for key, value in campaign_record.items()
                if key != "record_sha256"})
            or campaign_record.get("status") != "ready"
            or campaign_record.get("campaign_id") != campaign_id
            or campaign_record.get("instance_id") != payload.get("instance_id")
            or campaign_record.get("objective") != payload.get("objective")
            or campaign_record.get("objective_mode") != payload.get("objective_mode")
            or campaign_record.get("acceptance_condition_ids") !=
                payload.get("acceptance_condition_ids")
            or campaign_record.get("acceptance_conditions") !=
                payload.get("acceptance_conditions")
            or campaign_record.get("allowed_scope") != scope
            or campaign_record.get("source_sections") != payload.get("source_sections")
            or campaign_record.get("validation_commands") !=
                payload.get("validation_commands", [])
            or campaign_record.get("validation_policy") !=
                payload.get("validation_policy")
            or campaign_record.get("rider_authorization_reference") !=
                payload.get("rider_authorization_reference")
            or campaign_record.get("recovery_references") !=
                payload.get("recovery_references")):
        raise PermissionError("runner plan is not bound to the exact canonical campaign genesis")
    campaign_binding = _canonical_campaign_binding(campaign_record)
    requested_budget_limits = {
        key: limits[key] for key in (
            "seconds", "provider_turns", "correction_cycles",
            "cost_units", "iterations")
    }
    if stepwise_campaign_budget_limits(campaign_record) != requested_budget_limits:
        raise PermissionError(
            "runner limits differ from the canonical campaign budget")
    plan = {
        "schema_version": 2,
        "record_type": "bounded_langgraph_runner_plan",
        "campaign_id": campaign_id,
        "task": json.loads(json.dumps(task)),
        "repository_root": str(repository),
        "limits": dict(limits),
        "canonical_campaign_initial_record_sha256": campaign_record["record_sha256"],
        "canonical_campaign_initial_revision": campaign_record["state_revision"],
        "canonical_campaign_binding": campaign_binding,
        "canonical_campaign_binding_sha256": _digest(campaign_binding),
        "classification": "synthetic_pre_genesis",
        "canonical_memory": False,
        "creates_authority": False,
        "creates_continuing_authority": False,
    }
    plan["plan_sha256"] = _digest(plan)
    return plan


class RunnerState(TypedDict, total=False):
    plan_sha256: str
    stage: str
    started_at: float
    campaign_record_sha256: str
    campaign_state_revision: int
    canonical_campaign_status: str
    provider_turns_consumed: int
    cost_units_consumed: int
    correction_cycles_consumed: int
    iterations_consumed: int
    provider_action_status: str | None
    application_operation_id: str | None
    application_receipt_sha256: str | None
    commit_operation_id: str | None
    commit_receipt_sha256: str | None
    needs_tanner_reason: str | None
    paused: bool
    terminal: bool
    terminal_status: str | None
    creates_authority: bool
    creates_continuing_authority: bool


class BoundedLangGraphDevelopmentRunner:
    """Ask the canonical campaign for one transition per graph node."""

    _STATE_KEYS = set(RunnerState.__annotations__)

    def __init__(self, *, repository, runtime_root, plan, instance_id="fawkes",
                 clock=time.time):
        self.repository = Path(repository).resolve()
        self.runtime_root = Path(runtime_root).resolve()
        tracing_values = (os.environ.get("LANGCHAIN_TRACING_V2", ""),
                          os.environ.get("LANGSMITH_TRACING", ""))
        if (any(value.strip().lower() not in {"", "0", "false", "off"}
                for value in tracing_values) or os.environ.get("LANGGRAPH_API_URL")):
            raise PermissionError("hosted tracing or LangGraph control planes are prohibited")
        if self.runtime_root == self.repository or self.repository in self.runtime_root.parents:
            raise PermissionError("runner runtime state must remain outside the repository")
        self.runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.runtime_root, 0o700)
        self.plan = json.loads(json.dumps(plan))
        self.clock = clock
        self._check_plan_integrity()
        self.campaign = CodexDevelopmentCampaign(
            instance_id, root=self.runtime_root / "campaigns",
            runtime_state_root=self.runtime_root / "component-runtime",
            worker_timeout_seconds=max(
                1, plan["limits"]["seconds"] // plan["limits"]["provider_turns"]))
        self.reviewer = WslCodexReviewAdapter(
            self.campaign.exchange,
            timeout_seconds=max(
                1, plan["limits"]["seconds"] // plan["limits"]["provider_turns"]))
        try:
            initial_campaign = self.campaign.store.load(self.plan["campaign_id"])
        except KeyError as exc:
            raise PermissionError(
                "runner requires an already-authorized canonical campaign") from exc
        self._assert_campaign_binding(initial_campaign)
        self._lock_stream = (self.runtime_root / "active-session.lock").open("a+b")
        try:
            fcntl.flock(self._lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._lock_stream.close()
            raise RuntimeError("another runner owns the active session") from exc
        self._connection = None
        try:
            self._connection = __import__("sqlite3").connect(
                self.runtime_root / "langgraph.sqlite", check_same_thread=False)
            self._saver = SqliteSaver(self._connection)
            graph = StateGraph(RunnerState)
            for node in ("bind", "campaign", "validate", "close"):
                graph.add_node(node, getattr(self, "_" + node))
            graph.add_edge(START, "bind")
            graph.add_edge("bind", "campaign")
            graph.add_conditional_edges(
                "campaign", self._route_after_campaign,
                {"continue": "campaign", "pause": END, "success": "validate",
                 "terminal": "close"})
            graph.add_edge("validate", "close")
            graph.add_edge("close", END)
            self.graph = graph.compile(checkpointer=self._saver)
        except BaseException:
            if self._connection is not None:
                self._connection.close()
            fcntl.flock(self._lock_stream.fileno(), fcntl.LOCK_UN)
            self._lock_stream.close()
            raise

    def _config(self):
        return {"configurable": {"thread_id": self.plan["campaign_id"]},
                "recursion_limit": 64}

    def _check_plan_integrity(self):
        claimed = self.plan.get("plan_sha256")
        if claimed != _digest({key: value for key, value in self.plan.items()
                               if key != "plan_sha256"}):
            raise PermissionError("runner plan changed")
        if self.plan.get("canonical_memory") is not False or self.plan.get(
                "creates_authority") is not False or self.plan.get(
                "creates_continuing_authority") is not False:
            raise PermissionError("runner plan attempts to create authority or Memory")
        binding = self.plan.get("canonical_campaign_binding")
        if (not isinstance(binding, dict)
                or self.plan.get("canonical_campaign_binding_sha256") != _digest(binding)):
            raise PermissionError("runner canonical campaign binding changed")

    def _assert_campaign_binding(self, record):
        if (not isinstance(record, dict)
                or record.get("record_sha256") != _digest({
                    key: value for key, value in record.items()
                    if key != "record_sha256"})
                or _canonical_campaign_binding(record) !=
                    self.plan["canonical_campaign_binding"]
                or stepwise_campaign_budget_limits(record) != {
                    key: self.plan["limits"][key] for key in (
                        "seconds", "provider_turns", "correction_cycles",
                        "cost_units", "iterations")
                }):
            raise PermissionError("canonical campaign differs from the frozen runner plan")

    def _validate_checkpoint_state(self, state):
        if not isinstance(state, dict) or set(state) - self._STATE_KEYS:
            raise PermissionError("runner checkpoint contains non-coordination state")
        if len(_bytes(state)) > 8_192:
            raise PermissionError("runner checkpoint exceeds the body-free size bound")
        if state.get("plan_sha256") != self.plan["plan_sha256"]:
            raise PermissionError("checkpoint belongs to a neighboring plan")
        if state.get("creates_authority") is not False or state.get(
                "creates_continuing_authority") is not False:
            raise PermissionError("runner checkpoint attempts to retain authority")
        string_fields = {
            "stage", "canonical_campaign_status", "provider_action_status",
            "application_operation_id", "commit_operation_id", "needs_tanner_reason",
            "terminal_status",
        }
        digest_fields = {
            "plan_sha256", "campaign_record_sha256",
            "application_receipt_sha256", "commit_receipt_sha256",
        }
        counter_fields = {
            "campaign_state_revision", "provider_turns_consumed", "cost_units_consumed",
            "correction_cycles_consumed", "iterations_consumed",
        }
        for key in string_fields:
            value = state.get(key)
            if value is not None and (not isinstance(value, str) or not value
                                      or len(value.encode()) > 256
                                      or re.fullmatch(r"[A-Za-z0-9_.:/-]+", value) is None):
                raise PermissionError("runner checkpoint string is malformed")
        for key in digest_fields:
            value = state.get(key)
            if value is not None and (not isinstance(value, str)
                                      or re.fullmatch(r"[0-9a-f]{64}", value) is None):
                raise PermissionError("runner checkpoint digest is malformed")
        for key in counter_fields:
            value = state.get(key)
            if value is not None and (type(value) is not int or value < 0):
                raise PermissionError("runner checkpoint counter is malformed")
        if "started_at" in state and (type(state["started_at"]) not in {int, float}
                                      or not math.isfinite(state["started_at"])
                                      or state["started_at"] < 0):
            raise PermissionError("runner checkpoint start time is malformed")
        for key in ("paused", "terminal"):
            if key in state and type(state[key]) is not bool:
                raise PermissionError("runner checkpoint Boolean is malformed")
        status = state.get("canonical_campaign_status")
        if status is not None:
            stepwise_campaign_status_disposition(status)
        if (state.get("terminal") and
                stepwise_campaign_status_disposition(
                    state.get("terminal_status")) != "terminal"):
            raise PermissionError("runner terminal checkpoint is inconsistent")
        if state.get("terminal"):
            record = self.campaign.store.load(self.plan["campaign_id"])
            self._assert_campaign_binding(record)
            if (record.get("record_sha256") != state.get("campaign_record_sha256")
                    or record.get("status") != state.get("terminal_status")):
                raise PermissionError("terminal checkpoint is not canonically supported")

    def _project_record(self, state, record):
        self._assert_campaign_binding(record)
        status = record["status"]
        disposition = stepwise_campaign_status_disposition(status)
        budget = record["execution_budget_v01"]
        for key in ("consumed_provider_turns", "consumed_cost_units",
                    "consumed_correction_cycles"):
            if type(budget.get(key)) is not int or budget[key] < 0:
                raise PermissionError("canonical campaign projection is malformed")
        action = budget.get("provider_action")
        application = record.get("application_evidence") or {}
        committed = record.get("git_commit_evidence") or {}
        reason = (record.get("needs_tanner") or {}).get("reason")
        paused = disposition == "paused"
        terminal = disposition == "terminal"
        return {
            **state,
            "stage": "campaign:" + status,
            "campaign_record_sha256": record["record_sha256"],
            "campaign_state_revision": record["state_revision"],
            "canonical_campaign_status": status,
            "provider_turns_consumed": budget["consumed_provider_turns"],
            "cost_units_consumed": budget["consumed_cost_units"],
            "correction_cycles_consumed": budget["consumed_correction_cycles"],
            "iterations_consumed": record["iteration"],
            "provider_action_status": action.get("status") if isinstance(action, dict) else None,
            "application_operation_id": application.get("operation_id"),
            "application_receipt_sha256": application.get("record_sha256"),
            "commit_operation_id": committed.get("operation_id"),
            "commit_receipt_sha256": committed.get("record_sha256"),
            "needs_tanner_reason": reason,
            "paused": paused,
            "terminal": terminal,
            "terminal_status": status if terminal else None,
            "creates_authority": False,
            "creates_continuing_authority": False,
        }

    def _route_after_campaign(self, state):
        if state.get("paused"):
            return "pause"
        if state.get("terminal_status") == "succeeded":
            return "success"
        if state.get("terminal"):
            return "terminal"
        return "continue"

    def run_or_resume(self):
        self._check_plan_integrity()
        prior = self.graph.get_state(self._config())
        if prior.values:
            state = dict(prior.values)
            self._validate_checkpoint_state(state)
            if state.get("terminal"):
                return state
            if state.get("paused"):
                record = self.campaign.store.load(self.plan["campaign_id"])
                refreshed = self._project_record(state, record)
                if refreshed["paused"] or refreshed["terminal"]:
                    return refreshed
                self.graph.update_state(self._config(), refreshed, as_node="bind")
            return self.graph.invoke(None, self._config())
        initial = {
            "plan_sha256": self.plan["plan_sha256"],
            "stage": "created",
            "started_at": self.clock(),
            "provider_turns_consumed": 0,
            "cost_units_consumed": 0,
            "correction_cycles_consumed": 0,
            "iterations_consumed": 0,
            "paused": False,
            "terminal": False,
            "terminal_status": None,
            "needs_tanner_reason": None,
            "creates_authority": False,
            "creates_continuing_authority": False,
        }
        return self.graph.invoke(initial, self._config())

    def _bind(self, state):
        self._check_plan_integrity()
        if self.repository != Path(self.plan["repository_root"]):
            raise PermissionError("runner repository binding changed")
        self._assert_campaign_binding(
            self.campaign.store.load(self.plan["campaign_id"]))
        return {**state, "stage": "bound"}

    def _campaign(self, state):
        """Request exactly one transition from an existing canonical campaign."""
        self._check_plan_integrity()
        campaign_id = self.plan["campaign_id"]
        try:
            record = self.campaign.store.load(campaign_id)
        except KeyError as exc:
            raise PermissionError(
                "runner cannot create or authorize a missing campaign") from exc
        # The runner validates only immutable campaign identity. Eligibility,
        # budgets, expiry, repository state, and recovery are canonical-owner
        # decisions made inside this one requested transition.
        self._assert_campaign_binding(record)
        if stepwise_campaign_status_disposition(record["status"]) == "active":
            record = self.campaign.advance_once(
                campaign_id, reviewer_adapter=self.reviewer)
        return self._project_record(state, record)

    def _validate(self, state):
        """Confirm canonical terminal status; do not reinterpret its receipts."""
        record = self.campaign.store.load(self.plan["campaign_id"])
        if (record.get("status") != "succeeded"
                or record.get("record_sha256") != state.get("campaign_record_sha256")):
            raise PermissionError("validation cannot precede canonical campaign success")
        return {**state, "stage": "validated"}

    def _close(self, state):
        return {**state, "stage": "closed", "paused": False,
                "creates_authority": False,
                "creates_continuing_authority": False}

    def progress_projection(self):
        """Return a body-free display projection sourced from canonical state."""
        try:
            record = self.campaign.store.load(self.plan["campaign_id"])
        except KeyError:
            return {
                "campaign_id": self.plan["campaign_id"], "status": "not_started",
                "plan_sha256": self.plan["plan_sha256"], "needs_tanner": None,
                "creates_authority": False, "creates_continuing_authority": False,
            }
        projected = self._project_record({"plan_sha256": self.plan["plan_sha256"]}, record)
        result = {key: projected.get(key) for key in (
            "plan_sha256", "campaign_record_sha256", "campaign_state_revision",
            "canonical_campaign_status", "provider_turns_consumed", "cost_units_consumed",
            "correction_cycles_consumed", "iterations_consumed", "provider_action_status",
            "needs_tanner_reason", "terminal", "terminal_status", "creates_authority",
            "creates_continuing_authority")}
        result["summary"] = (
            "Tanner decision required: " + result["needs_tanner_reason"]
            if result["needs_tanner_reason"] else
            "Canonical campaign state: " + result["canonical_campaign_status"])
        return result

    def cancel(self, *, authenticated_rider):
        record = self.campaign.cancel(
            self.plan["campaign_id"], authenticated_rider=authenticated_rider)
        return self._project_record({"plan_sha256": self.plan["plan_sha256"]}, record)

    def end_campaign(self, *, authenticated_rider):
        return self.cancel(authenticated_rider=authenticated_rider)

    def close(self):
        self._connection.close()
        fcntl.flock(self._lock_stream.fileno(), fcntl.LOCK_UN)
        self._lock_stream.close()
