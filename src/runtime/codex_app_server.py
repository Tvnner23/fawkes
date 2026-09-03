"""Bounded Codex app-server client with typed, one-request approvals.

This is a process transport only.  Development remains the authority owner;
the disposable Worker and frozen Reviewer remain the filesystem boundaries.
"""

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import os
import queue
import re
import subprocess
import threading
import time


PROTOCOL_VERSION = "codex-app-server-0.151.0"
SUPPORTED_CLI_VERSION = "codex-cli 0.151.0"
SHELL_ENVIRONMENT_POLICY_OVERRIDE = "shell_environment_policy.inherit=all"
PROTOCOL_SCHEMA_SHA256 = {
    "item/commandExecution/requestApproval": "c9728280b8f3204fd729d0fb3d1ca7bb05b1150de26b3653f7163e6a9bd941e7",
    "item/fileChange/requestApproval": "13848b26814c286ad6425a20d01c1691c86790e1f9e2529399677a8a22fe0d18",
    "item/permissions/requestApproval": "c6d165e1b0c65d5dcf1e099b4c226c7e4dad79fe2b88b03621a1fc6c1d3c86c2",
    "applyPatchApproval": "179d91081c3c84d0f79fc544a3d6d423f280c0f9d93512cdd0344c80e09b99a3",
    "execCommandApproval": "653116614df1aa5011c3cc399cf79bae6b9eb28c1d527df27275abf61ceb1365",
}
TYPED_APPROVAL_METHODS = frozenset({
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
    "item/permissions/requestApproval",
    "applyPatchApproval",
    "execCommandApproval",
})
WRITE_APPROVAL_METHODS = frozenset({
    "item/fileChange/requestApproval", "applyPatchApproval",
})
_SECRET = re.compile(
    r"(?i)(authorization|token|api[_ -]?key|webhook|password|secret)\s*[:=]\s*\S+"
)


class CodexAppServerError(OSError):
    def __init__(self, stage, category, safe_message, *, provider_code=None):
        super().__init__(safe_message)
        self.stage = stage
        self.category = category
        self.provider_code = provider_code


def _safe(value, maximum=2_000):
    text = "".join(c for c in str(value or "")[:maximum] if c.isprintable())
    text = re.sub(r"(?:https?|wss?)://\S+", "<redacted-endpoint>", text)
    return _SECRET.sub(lambda m: m.group(1) + "=<redacted>", text)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def extend_deadline_for_attention(deadline, wait_started, wait_finished):
    """Exclude the durable Tanner pause from the bounded execution budget."""
    if wait_finished < wait_started:
        raise ValueError("attention wait clock moved backwards")
    return deadline + (wait_finished - wait_started)


def _available_decisions(params):
    values = params.get("availableDecisions")
    if not isinstance(values, list):
        return set()
    return {value for value in values if isinstance(value, str)}


def approval_response(method, choice, params):
    """Return only a documented exact response; never persist broader policy."""
    if method == "item/permissions/requestApproval":
        raise CodexAppServerError("approval", "unsupported_bounded_permission",
                                  "permission profile cannot be granted for one action")
    modern = method in {
        "item/commandExecution/requestApproval", "item/fileChange/requestApproval"
    }
    if choice == "approve_once":
        decision = "accept" if modern else "approved"
        available = _available_decisions(params)
        if available and decision not in available:
            raise CodexAppServerError("approval", "unsupported_decision",
                                      "one-action approval is unavailable")
        return {"decision": decision}
    if choice == "deny":
        if modern:
            available = _available_decisions(params)
            decision = "decline" if "decline" in available else "cancel"
            if available and decision not in available:
                raise CodexAppServerError("approval", "unsupported_decision",
                                          "bounded denial is unavailable")
            return {"decision": decision}
        return {"decision": {"denied": {"rejection": "Denied by authenticated Rider"}}}
    if choice == "cancel_campaign":
        return {"decision": "cancel" if modern else "abort"}
    raise CodexAppServerError("approval", "invalid_decision", "invalid Tanner decision")


def typed_approval(method, params, *, campaign_id, invocation_id, worker, process_id,
                   active_thread_id=None, active_turn_id=None):
    if method not in TYPED_APPROVAL_METHODS or not isinstance(params, dict):
        raise CodexAppServerError("approval", "approval_mapping_failure",
                                  "unsupported typed approval request")
    legacy = method in {"applyPatchApproval", "execCommandApproval"}
    thread_id = params.get("conversationId") if legacy else params.get("threadId")
    turn_id = active_turn_id if legacy else params.get("turnId")
    item_id = params.get("callId") if legacy else params.get("itemId")
    if legacy and active_thread_id != thread_id:
        raise CodexAppServerError("approval", "approval_mapping_failure",
                                  "legacy approval conversation mismatches active thread")
    if not all(isinstance(v, str) and v for v in (thread_id, turn_id, item_id)):
        raise CodexAppServerError("approval", "approval_mapping_failure",
                                  "typed approval request lacks exact lineage")
    raw_action = (params.get("command") or params.get("changes") or params.get("fileChanges")
                  or params.get("permissions") or params.get("reason"))
    action = (params.get("commandActions") or params.get("parsedCmd") or raw_action)
    authority = {
        "method": method, "thread_id": thread_id, "turn_id": turn_id,
        "item_id": item_id, "action": action, "cwd": params.get("cwd"),
    }
    action_identity = {"method": method, "action": action, "cwd": params.get("cwd")}
    return {
        "campaign_id": campaign_id, "invocation_id": invocation_id,
        "worker": worker, "kind": "native_codex_approval_required",
        "blocked_action": _safe(action),
        "why_required": _safe(params.get("reason") or "Codex requested native approval"),
        "requested_authority": _safe(json.dumps(authority, sort_keys=True)),
        "resources": [_safe(params.get("cwd"))] if params.get("cwd") else [],
        "reversible": None, "provider_code": method,
        "protocol": {"version": PROTOCOL_VERSION, "method": method, "process_id": process_id,
                     "thread_id": thread_id, "turn_id": turn_id,
                     "item_id": item_id, "blocked_action_sha256": _digest(authority),
                     "approved_action_sha256": _digest(action_identity)},
        "exact_action": action_identity,
    }


@dataclass
class AppServerResult:
    returncode: int
    stdout: str
    stderr: str
    lifecycle: list
    thread_id: str | None = None
    turn_id: str | None = None


class CodexAppServerTransport:
    """One fresh stdio app-server process for one bounded turn."""

    def __init__(self, *, codex_binary="codex", timeout_seconds=420,
                 decision_timeout_seconds=3600, popen=subprocess.Popen):
        self.codex_binary = str(codex_binary)
        self.timeout_seconds = int(timeout_seconds)
        self.decision_timeout_seconds = int(decision_timeout_seconds)
        self.popen = popen

    def qualify(self, environment):
        completed = subprocess.run([self.codex_binary, "--version"], text=True,
                                   capture_output=True, env=environment, timeout=30, check=False)
        # The CLI may emit a harmless PATH-alias warning on stderr in a
        # read-only home.  Only its dedicated stdout version line is identity.
        version = completed.stdout.strip()
        if completed.returncode or version != SUPPORTED_CLI_VERSION:
            raise CodexAppServerError("qualification", "unsupported_protocol_version",
                                      f"expected {SUPPORTED_CLI_VERSION}; received {_safe(version)}")
        return {"protocol_version": PROTOCOL_VERSION, "cli_version": version,
                "typed_approval_methods": sorted(TYPED_APPROVAL_METHODS),
                "request_schema_sha256": dict(PROTOCOL_SCHEMA_SHA256)}

    def run(self, *, cwd, prompt, output_schema, output_path, sandbox,
            campaign_id, invocation_id, worker, environment, approval_handler=None,
            allow_detached_continuation=True):
        qualification = self.qualify(environment)
        process = self.popen([self.codex_binary, "-c", SHELL_ENVIRONMENT_POLICY_OVERRIDE,
                              "app-server", "--listen", "stdio://"],
            cwd=str(cwd), env=environment, text=True, bufsize=1,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        inbox, stderr_lines = queue.Queue(), []
        threading.Thread(target=lambda: [inbox.put(line) for line in process.stdout], daemon=True).start()
        threading.Thread(target=lambda: [stderr_lines.append(_safe(line)) for line in process.stderr], daemon=True).start()
        next_id, pending, lifecycle = 1, {}, [{"stage": "launched", **qualification}]
        thread_id = turn_id = None
        last_agent_text = None
        pending_grant = None
        deadline = time.monotonic() + self.timeout_seconds

        def send(value):
            process.stdin.write(json.dumps(value, separators=(",", ":")) + "\n")
            process.stdin.flush()

        def request(method, params):
            nonlocal next_id
            request_id = next_id; next_id += 1
            send({"id": request_id, "method": method, "params": params})
            return request_id

        init_id = request("initialize", {"clientInfo": {"name": "fawkes-development", "version": "0.1"},
            "capabilities": {"experimentalApi": True}})
        pending[init_id] = "initialize"
        try:
            while True:
                if time.monotonic() >= deadline:
                    raise CodexAppServerError("turn", "timeout", "bounded app-server turn timed out")
                try: line = inbox.get(timeout=min(1.0, max(0.01, deadline-time.monotonic())))
                except queue.Empty:
                    if process.poll() is None:
                        try: process.wait(timeout=0.15)
                        except subprocess.TimeoutExpired: pass
                    if process.poll() is not None:
                        if pending_grant is not None and allow_detached_continuation:
                            return self._continue_detached(cwd=cwd, original_prompt=prompt,
                                output_schema=output_schema, output_path=output_path, sandbox=sandbox,
                                campaign_id=campaign_id, invocation_id=invocation_id, worker=worker,
                                environment=environment, approval_handler=approval_handler,
                                original_approval=pending_grant["approval"],
                                decision=pending_grant["decision"])
                        time.sleep(0.05)
                        detail = "".join(stderr_lines).strip()
                        raise CodexAppServerError("process", "unexpected_exit",
                            f"app-server exited with code {process.returncode}"
                            + (f": {detail}" if detail else ""))
                    continue
                try: message = json.loads(line)
                except json.JSONDecodeError:
                    raise CodexAppServerError("protocol", "malformed_frame", "app-server emitted malformed JSON")
                if "id" in message and "method" not in message:
                    stage = pending.pop(message["id"], None)
                    if "error" in message:
                        raise CodexAppServerError(stage or "protocol", "protocol_error",
                                                  _safe(message["error"]))
                    if stage == "initialize":
                        send({"method": "initialized"})
                        rid = request("thread/start", {"cwd": str(Path(cwd).resolve()),
                            "approvalPolicy": "on-request", "approvalsReviewer": "user",
                            "sandbox": sandbox, "ephemeral": True, "experimentalRawEvents": False})
                        pending[rid] = "thread/start"; lifecycle.append({"stage": "initialized"})
                    elif stage == "thread/start":
                        thread_id = message["result"]["thread"]["id"]
                        rid = request("turn/start", {"threadId": thread_id,
                            "input": [{"type": "text", "text": prompt}],
                            "approvalPolicy": "on-request", "outputSchema": output_schema})
                        pending[rid] = "turn/start"; lifecycle.append({"stage": "thread_started", "thread_id": thread_id})
                    elif stage == "turn/start":
                        turn_id = message["result"]["turn"]["id"]
                        lifecycle.append({"stage": "turn_started", "turn_id": turn_id})
                    continue
                method = message.get("method")
                if method in TYPED_APPROVAL_METHODS and "id" in message:
                    approval = typed_approval(method, message.get("params"), campaign_id=campaign_id,
                        invocation_id=invocation_id, worker=worker, process_id=process.pid,
                        active_thread_id=thread_id, active_turn_id=turn_id)
                    if approval["protocol"]["thread_id"] != thread_id or approval["protocol"]["turn_id"] != turn_id:
                        raise CodexAppServerError("approval", "lineage_mismatch", "approval request mismatches active turn")
                    decision = {"choice": "deny"}
                    if sandbox == "read-only" and method in WRITE_APPROVAL_METHODS:
                        response = approval_response(method, "deny", message["params"])
                        lifecycle.append({"stage": "reviewer_write_denied", **approval["protocol"]})
                    else:
                        if approval_handler is None:
                            raise CodexAppServerError("approval", "attention_handler_unavailable",
                                                      "typed approval requires Tanner")
                        approval_wait_started = time.monotonic()
                        decision = approval_handler(approval,
                            timeout_seconds=self.decision_timeout_seconds,
                            process_alive=lambda: process.poll() is None)
                        # Tanner's explicitly displayed decision window is a paused
                        # lifecycle, not Worker execution time. Preserve the entire
                        # remaining turn budget after the exact decision returns.
                        deadline = extend_deadline_for_attention(
                            deadline, approval_wait_started, time.monotonic())
                        response = approval_response(method, decision["choice"], message["params"])
                        lifecycle.append({"stage": "approval_decided", "choice": decision["choice"],
                                          **approval["protocol"]})
                    if process.poll() is not None:
                        if decision.get("choice") == "approve_once" and allow_detached_continuation:
                            return self._continue_detached(cwd=cwd, original_prompt=prompt,
                                output_schema=output_schema, output_path=output_path, sandbox=sandbox,
                                campaign_id=campaign_id, invocation_id=invocation_id, worker=worker,
                                environment=environment, approval_handler=approval_handler,
                                original_approval=approval, decision=decision)
                        raise CodexAppServerError("approval", "stale_app_server_process",
                                                  "approval process is no longer alive")
                    send({"id": message["id"], "result": response})
                    if decision.get("choice") == "approve_once" and callable(decision.get("claim")):
                        pending_grant = {"approval": approval, "decision": decision}
                    if response.get("decision") in {"cancel", "abort"} and decision.get("choice") == "cancel_campaign":
                        raise CodexAppServerError("approval", "campaign_cancelled", "campaign cancelled by Tanner")
                    continue
                if method == "serverRequest/resolved" and pending_grant is not None:
                    pending_grant["decision"]["claim"]()
                    pending_grant["claimed"] = True
                    lifecycle.append({"stage": "approval_claim_consumed"})
                    continue
                if method == "turn/completed":
                    params = message.get("params") or {}
                    status = (params.get("turn") or {}).get("status")
                    lifecycle.append({"stage": "turn_completed", "status": status})
                    if status != "completed":
                        error = (params.get("turn") or {}).get("error")
                        raise CodexAppServerError("turn", "turn_not_completed",
                            f"turn ended with status {_safe(status)}"
                            + (f": {_safe(error)}" if error else ""))
                    if last_agent_text is None:
                        raise CodexAppServerError("turn", "missing_structured_return",
                                                  "turn completed without a final agent message")
                    output_path = Path(output_path)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(last_agent_text, encoding="utf-8")
                    break
                if method == "item/completed":
                    item = (message.get("params") or {}).get("item") or {}
                    if item.get("type") == "agentMessage" and isinstance(item.get("text"), str):
                        last_agent_text = item["text"]
                    if (pending_grant is not None and pending_grant.get("claimed")
                            and item.get("id") == pending_grant["approval"]["protocol"]["item_id"]
                            and item.get("type") in {"commandExecution", "fileChange"}):
                        complete = pending_grant["decision"].get("complete")
                        if callable(complete):
                            complete("completed" if item.get("status") in {None, "completed"} else "failed")
                        pending_grant = None
                if method in {"item/commandExecution/outputDelta", "item/commandExecution/completed",
                              "item/fileChange/completed"}:
                    lifecycle.append({"stage": method, "item_id": _safe((message.get("params") or {}).get("itemId"))})
                    if (method.endswith("/completed") and pending_grant is not None
                            and pending_grant.get("claimed")
                            and (message.get("params") or {}).get("itemId") ==
                                pending_grant["approval"]["protocol"]["item_id"]):
                        complete = pending_grant["decision"].get("complete")
                        if callable(complete):
                            status = (message.get("params") or {}).get("status")
                            complete("completed" if status in {None, "completed"} else "failed")
                        pending_grant = None
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                try: stream.close()
                except (AttributeError, OSError): pass
        return AppServerResult(0, json.dumps(lifecycle),
                               "".join(stderr_lines), lifecycle, thread_id, turn_id)

    def _continue_detached(self, *, cwd, original_prompt, output_schema, output_path,
                           sandbox, campaign_id, invocation_id, worker, environment,
                           approval_handler, original_approval, decision):
        if original_approval["provider_code"] not in {
                "item/commandExecution/requestApproval", "execCommandApproval"}:
            raise CodexAppServerError("continuation", "action_not_reconstructable",
                                      "detached approval action cannot be reconstructed safely")
        for name in ("reserve", "claim", "finish"):
            if not callable(decision.get(name)):
                raise CodexAppServerError("continuation", "continuation_store_unavailable",
                                          "durable continuation claim is unavailable")
        action_sha = original_approval["protocol"]["approved_action_sha256"]
        continuation_id = f"{invocation_id}-continuation-{action_sha[:16]}"
        decision["reserve"](continuation_id)
        claimed = False

        def continuation_handler(request, *, timeout_seconds, process_alive=None):
            nonlocal claimed
            if (claimed or request["campaign_id"] != campaign_id
                    or request["worker"]["worker_id"] != worker["worker_id"]
                    or request["protocol"]["approved_action_sha256"] != action_sha):
                raise CodexAppServerError("continuation", "approved_action_mismatch",
                    "fresh continuation requested a different action: expected "
                    f"{_safe(original_approval['exact_action'])}; received {_safe(request['exact_action'])}")
            claimed = True
            return {"choice": "approve_once",
                    "claim": lambda: decision["claim"](continuation_id)}

        exact_action = json.dumps(original_approval["exact_action"], ensure_ascii=False,
                                  sort_keys=True)
        continuation_prompt = (
            "This is one restart-safe bounded continuation. First request and perform ONLY the exact "
            f"previously Rider-approved action represented by this JSON: {exact_action}. "
            "Do not substitute a different command, cwd, file, or resource. After that exact action "
            "succeeds, continue the original authorized task without repeating completed mutations.\n\n"
            "ORIGINAL AUTHORIZED TASK:\n" + original_prompt)
        try:
            result = self.run(cwd=cwd, prompt=continuation_prompt,
                output_schema=output_schema, output_path=output_path, sandbox=sandbox,
                campaign_id=campaign_id, invocation_id=continuation_id, worker=worker,
                environment=environment, approval_handler=continuation_handler,
                allow_detached_continuation=False)
            if not claimed:
                raise CodexAppServerError("continuation", "approved_action_not_claimed",
                                          "fresh continuation did not claim the exact action")
            decision["finish"](continuation_id, "completed")
            result.lifecycle.insert(0, {"stage": "detached_continuation",
                "continuation_id": continuation_id,
                "original_invocation_id": invocation_id,
                "approved_action_sha256": action_sha})
            result.stdout = json.dumps(result.lifecycle)
            return result
        except Exception:
            decision["finish"](continuation_id, "failed")
            raise


def exec_compatible_app_server_runner(*, campaign_id, invocation_id, worker,
                                      approval_handler, codex_binary="codex"):
    """Adapt the existing adapter's process seam without changing its owner."""
    def run(command, *, prompt, environment, timeout):
        if "--output-schema" not in command:
            return subprocess.run(command, input=prompt, text=True, capture_output=True,
                                  env=environment, timeout=timeout, check=False)
        def value_after(flag):
            try: return command[command.index(flag) + 1]
            except (ValueError, IndexError) as exc:
                raise CodexAppServerError("invocation", "malformed_adapter_command",
                                          f"missing required {flag}") from exc
        schema_path = Path(value_after("--output-schema"))
        try:
            return CodexAppServerTransport(codex_binary=codex_binary,
                timeout_seconds=timeout).run(cwd=value_after("--cd"), prompt=prompt,
                    output_schema=json.loads(schema_path.read_text(encoding="utf-8")),
                    output_path=value_after("--output-last-message"),
                    sandbox=value_after("--sandbox"), campaign_id=campaign_id,
                    invocation_id=invocation_id, worker=worker, environment=environment,
                    approval_handler=approval_handler)
        except CodexAppServerError as exc:
            from src.runtime.component_supervision import ComponentReceiptStore
            component = ("reviewer" if "review" in str(worker.get("role", ""))
                         else "worker")
            ComponentReceiptStore().failure(component=component, stage=exc.stage,
                category=exc.category, provider_code=exc.provider_code,
                exception=exc, service_state="needs_tanner", notify=True)
            raise
    return run
