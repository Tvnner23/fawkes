"""Real Chat layers, synthetic Archive, fake provider, disposable source copies.

No application modules are imported in the parent test process. Each scenario
binds runtime state before importing the copied source, and denies network and
subprocess activity in the child. This tests recording integration, not general
relocation of older checkout-relative runtime owners.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
import uuid


class FakeResponses:
    def __init__(self):
        self.calls = []
        self.answer = "Synthetic response."
        self.fail_response = False
        self.correction = False

    def create(self, **kwargs):
        system = kwargs["input"][0]["content"]
        assert not kwargs.get("tools"), "Unexpected research/provider tool request"
        if "is_correction, confidence, reasoning" in system:
            stage = "correction"
            text = json.dumps({"is_correction": self.correction, "confidence": 0.99,
                               "reasoning": "Synthetic classification."})
        elif "developmental evaluator for Fawkes" in system:
            stage = "development"
            text = json.dumps({"should_propose": True, "category": "workflow",
                # A provider may quote the experience it was given. This makes
                # incorrect context eligibility observable at the real writer.
                "observation": "Synthetic supplied experience: " + kwargs["input"][1]["content"],
                "proposed_change": "Consider clearer explanations.",
                "rationale": "Synthetic non-applied proposal.", "confidence": 0.99})
        elif "semantic memory evaluator for Fawkes" in system:
            stage = "memory"
            text = json.dumps({"should_remember": False, "memory_type": None,
                "meaning": None, "confidence": 0.99, "importance": 0.0,
                "reasoning": "Synthetic evaluation rejects this candidate.",
                "supporting_message_ids": [], "supporting_archive_ids": []})
        elif "You are Fawkes" in system:
            stage = "response"
            text = self.answer
        else:
            raise AssertionError("Unexpected fake-provider request shape")
        self.calls.append({"stage": stage, "request": kwargs})
        if stage == "response" and self.fail_response:
            raise RuntimeError("synthetic provider failure")
        return SimpleNamespace(output_text=text, usage=None)


def _runtime_files(root):
    for name in ("archive", "memory", "database", "library", "conversations", "instances"):
        directory = root / name
        if directory.exists():
            yield from (path for path in directory.rglob("*") if path.is_file())


def _assert_absent(root, *sentinels):
    for path in _runtime_files(root):
        body = path.read_bytes()
        for sentinel in sentinels:
            assert sentinel.encode() not in body, "Non-retained content persisted in " + str(path.relative_to(root))


def _run_scenario(name):
    root = Path(os.environ["FAWKES_RUNTIME_STATE_ROOT"])
    assert root == Path.cwd() and (root / "src/runtime/chat.py").is_file()
    def deny_external(event, args):
        if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "subprocess.Popen"}:
            raise AssertionError("External activity forbidden in recording E2E: " + event)
    sys.addaudithook(deny_external)

    from src.capture.canonical import canonical_messages
    from src.memory import archive_retrieval, worker
    from src.memory.archive_context import build_archive_context
    from src.memory.ledger import list_work_items
    from src.memory.semantic_provider import ModelSemanticMemoryEvaluator
    from src.runtime.chat import FawkesChatRuntime
    from src.runtime.chat_service import ChatServiceError, FawkesChatService
    from src.runtime.context_receipts import load_context_receipt
    from src.runtime.evidence_transmission import ProviderRoute
    from src.runtime.personal_recording import RecordingPolicyStore
    from src.runtime.production_planner_builder import ServedProductionPlannerBuilder
    from src.runtime.retrieval_replay import load_flight

    instance = "recording-e2e"
    policy = RecordingPolicyStore(instance, root=root)
    responses = FakeResponses()
    route = ProviderRoute("private-chat-policy", "openai-compatible", "synthetic-e2e-model")
    planner = ServedProductionPlannerBuilder(
        instance_id=instance, provider_route=route.public(),
        archive_index_path=archive_retrieval.INDEX_PATH,
        archive_meta_dir=root / "archive/meta", library_root=root / "library")
    runtime = FawkesChatRuntime(
        client=SimpleNamespace(responses=responses), model=route.model,
        instance_id=instance, retrieval_path="planner", planner_context_builder=planner,
        evidence_transmission_root=root / "database/evidence_transmissions",
        library_root=root / "library", research_enabled=True)
    service = FawkesChatService(
        phoenix={"instance_id": instance, "name": "Fawkes"}, runtime=runtime,
        recording_policy_store=policy, library_root=root / "library",
        provider_receipt_dir=root / "database/provider_transmission_receipts",
        archive_index_path=archive_retrieval.INDEX_PATH,
        archive_meta_dir=root / "archive/meta", archive_raw_dir=root / "archive/raw")
    assert isinstance(service.runtime, FawkesChatRuntime)
    assert not service._memory_worker_enabled

    def configure(changes):
        return policy.update(changes, expected_revision=policy.load().revision)

    private_text = "private-payload-" + uuid.uuid4().hex
    private_reply = "private-reply-" + uuid.uuid4().hex
    denied_text = "learning-disabled-" + uuid.uuid4().hex

    if name == "private_retained":
        configure({"mode": "private"})
        responses.answer = private_reply
        first = service.send(private_text + " current weather")
        assert first["recording"]["mode"] == "private"
        assert [item["stage"] for item in responses.calls] == ["response"]
        assert first["message"]["context_inspector_available"] is False
        assert list_work_items(instance_id=instance) == []
        assert len(service.history()["messages"]) == 2
        _assert_absent(root, private_text, private_reply)
        followup = service.send("Continue privately.", conversation_id=first["conversation_id"])
        assert private_text in responses.calls[-1]["request"]["input"][1]["content"]
        assert followup["conversation_id"] == first["conversation_id"]
        _assert_absent(root, private_text, private_reply)
        assert list((root / "database/evidence_transmissions").rglob("*.json"))
        assert list((root / "database/provider_transmission_receipts").rglob("*.json"))
        configure({"mode": "retained"})
        responses.answer = "Retained reply."
        retained = service.send("Hello again.", recording_mode="retained")
        assert retained["recording"]["mode"] == "retained"
        assert not retained["conversation_id"].startswith("private-")
        assert private_text not in responses.calls[-1]["request"]["input"][1]["content"]
        messages = canonical_messages(retained["conversation_id"], instance_id=instance)
        assert len(messages) == 2 and all(item["memory_learning_eligible"] for item in messages)
        receipt = load_context_receipt(retained["message"]["message_id"])
        flight = load_flight(instance, retained["message"]["message_id"])
        assert receipt and flight, "Retained mode must exercise actual diagnostic writers"
        assert len(list_work_items(instance_id=instance)) == 1
        _assert_absent(root, private_text, private_reply)
    elif name in {"memory_off", "memory_off_correction"}:
        configure({"categories": {"memory_learning": False}})
        denied = service.send(denied_text)
        messages = canonical_messages(denied["conversation_id"], instance_id=instance)
        assert len(messages) == 2 and all(not item["memory_learning_eligible"] for item in messages)
        assert list_work_items(instance_id=instance) == []
        configure({"categories": {"memory_learning": True}})
        responses.correction = name == "memory_off_correction"
        allowed = service.send("Please correct your wording." if responses.correction else "Hello again.")
        rows = list_work_items(instance_id=instance)
        assert [item["message_id"] for item in rows] == [allowed["user_message_id"]]
        worker.discover_history(instance_id=instance)
        rows = list_work_items(instance_id=instance)
        assert [item["message_id"] for item in rows] == [allowed["user_message_id"]], "Disabled turn was rediscovered"
        context = build_archive_context(allowed["conversation_id"], instance_id=instance,
                                        memory_learning_only=True)
        assert denied_text not in str(context)
        evaluated = worker.evaluate_next(instance_id=instance,
            evaluator=ModelSemanticMemoryEvaluator(runtime.semantic_retriever.provider))
        assert evaluated is not None
        memory_calls = [item for item in responses.calls if item["stage"] == "memory"]
        assert memory_calls and denied_text not in str(memory_calls)
        if responses.correction:
            development_calls = [item for item in responses.calls if item["stage"] == "development"]
            assert development_calls, "The correction-derived writer must be exercised"
            assert list((root / "memory/development").glob("*.json")), "No real correction proposal was written"
            leaked_paths = [str(path.relative_to(root)) for path in (root / "memory").rglob("*")
                            if path.is_file() and denied_text.encode() in path.read_bytes()]
            assert denied_text not in str(development_calls), (
                "Memory-disabled history entered correction-derived learning; durable sinks=" + str(leaked_paths))
            assert not leaked_paths, "Memory-disabled history entered durable learning: " + str(leaked_paths)
    elif name == "private_failure":
        configure({"mode": "private"})
        responses.fail_response = True
        try:
            service.send(private_text)
        except ChatServiceError as exc:
            assert "not recorded" in str(exc) and "preserved" not in str(exc)
        else:
            raise AssertionError("Synthetic provider failure did not reach the service")
        assert list_work_items(instance_id=instance) == []
        _assert_absent(root, private_text)
        receipts = [json.loads(path.read_text()) for path in
                    (root / "database/provider_transmission_receipts").rglob("*.json")]
        assert {item["status"] for item in receipts} == {"authorized", "failed"}
    else:
        raise AssertionError("Unknown synthetic E2E scenario")
    print(json.dumps({"scenario": name, "passed": True,
                      "fake_provider_calls": len(responses.calls), "real_provider_calls": 0}))


class RecordingEndToEndTests(unittest.TestCase):
    def run_scenario(self, name):
        source_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="fawkes-recording-e2e-") as temporary:
            root = Path(temporary)
            shutil.copytree(source_root / "src", root / "src",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            environment = {key: value for key, value in os.environ.items()
                           if not key.startswith("FAWKES_")
                           and not any(word in key.upper() for word in
                                       ("TOKEN", "SECRET", "API_KEY", "PASSWORD", "CREDENTIAL"))
                           and key not in {"OPENAI_BASE_URL", "ANTHROPIC_BASE_URL"}}
            environment.update(FAWKES_RUNTIME_STATE_ROOT=str(root), PYTHONPATH=str(root),
                PYTHONDONTWRITEBYTECODE="1", FAWKES_MEMORY_WORKER_ENABLED="0",
                FAWKES_ESTIMATED_CHAT_COST="0", FAWKES_ESTIMATED_RESEARCH_COST="0",
                FAWKES_RETRIEVAL_PATH="planner", FAWKES_CHAT_MODEL="synthetic-e2e-model")
            result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()),
                                     "--scenario", name], cwd=root, env=environment,
                                    capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            outcome = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertTrue(outcome["passed"])
            self.assertEqual(outcome["real_provider_calls"], 0)

    def test_private_then_retained_uses_real_archive_without_private_sentinels(self):
        self.run_scenario("private_retained")

    def test_retained_learning_off_stays_excluded_after_enable_and_real_discovery(self):
        self.run_scenario("memory_off")

    def test_learning_off_history_cannot_feed_later_correction_learning(self):
        self.run_scenario("memory_off_correction")

    def test_real_runtime_private_provider_failure_has_only_body_free_receipts(self):
        self.run_scenario("private_failure")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--scenario":
        _run_scenario(sys.argv[2])
    else:
        unittest.main()
