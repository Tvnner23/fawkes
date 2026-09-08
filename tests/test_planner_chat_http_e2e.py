import json
import hashlib
import os
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch

from src.app.server import FawkesAppServer
from src.memory.archive_retrieval import index_canonical_message
from src.runtime.chat_service import FawkesChatService
from src.runtime.context_receipts import save_context_receipt as write_context_receipt
from src.runtime.native_retrieval_ambiguity import NativeRetrievalAmbiguityPolicy
from src.runtime.retrieval_replay import record_live_flight as write_live_flight


class PlannerChatHTTPAcceptanceTests(unittest.TestCase):
    class Response:
        output_text = "served planner answer"
        usage = None

    def test_authenticated_served_planner_uses_production_assembly_and_exact_permit(self):
        if os.getenv("FAWKES_HTTP_ACCEPTANCE") != "1":
            self.skipTest("set FAWKES_HTTP_ACCEPTANCE=1 where loopback sockets are permitted")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); instance_id = "planner-http-phoenix"
            index = root / "archive.sqlite3"; meta = root / "archive-meta"
            meta.mkdir()
            body = "HTTP PLANNER VERIFIED EVIDENCE"
            index_canonical_message(
                instance_id=instance_id, conversation_id="historical-conversation",
                message_id="historical-message", role="user", content=body,
                created_at="2026-01-01T00:00:00+00:00",
                source_archive_id="historical-archive", path=index,
            )
            index_canonical_message(
                instance_id=instance_id, conversation_id="current-conversation",
                message_id="current-working-message", role="assistant",
                content="CURRENT WORKING CONTEXT MUST NOT BE RETRIEVED",
                created_at="2026-08-30T00:00:00+00:00",
                source_archive_id="current-archive", path=index,
            )
            index_canonical_message(
                instance_id=instance_id, conversation_id="duplicate-conversation",
                message_id="duplicate-message", role="user", content=body,
                created_at="2026-01-02T00:00:00+00:00",
                source_archive_id="duplicate-archive", path=index,
            )
            (meta / "historical-archive.json").write_text(json.dumps({
                "schema_version": 2, "archive_id": "historical-archive",
                "instance_id": instance_id,
                "owner_principal_id": f"authenticated-rider:{instance_id}",
                "privacy": {"classification": "potentially_private"},
                "representation_provenance": {"schema_version": 1,
                    "representation_class": "source_original", "relationships": []},
            }))
            (meta / "current-archive.json").write_text(json.dumps({
                "schema_version": 2, "archive_id": "current-archive",
                "instance_id": instance_id,
                "owner_principal_id": f"authenticated-rider:{instance_id}",
                "privacy": {"classification": "potentially_private"},
            }))
            (meta / "duplicate-archive.json").write_text(json.dumps({
                "schema_version": 2, "archive_id": "duplicate-archive",
                "instance_id": instance_id,
                "owner_principal_id": f"authenticated-rider:{instance_id}",
                "privacy": {"classification": "potentially_private"},
                "representation_provenance": {"schema_version": 1,
                    "representation_class": "duplicate_copy",
                    "relationships": [{"relationship": "duplicate_of",
                        "qualification_status": "verified",
                        "target": {"archive_id": "historical-archive",
                                   "message_id": "historical-message"}}]},
            }))
            calls = []

            class Responses:
                def create(_self, **kwargs):
                    calls.append(kwargs)
                    return PlannerChatHTTPAcceptanceTests.Response()

            client = type("Client", (), {"responses": Responses()})()
            conversation = {"conversation_id": "current-conversation", "title": "Chat"}
            persisted = []

            def persist(**kwargs):
                persisted.append(kwargs)
                return {"archive_id": "live-" + kwargs["message_id"],
                        "created_at": "2026-08-31T00:00:00+00:00"}

            def served_context(*args, **kwargs):
                return tuple({"message_id":item["message_id"],"role":item["role"],
                              "content":item["text"],"created_at":"2026-08-31T00:00:00+00:00"}
                             for item in persisted[-kwargs.get("max_messages",20):])

            def save_receipt(**kwargs):
                return write_context_receipt(
                    path=root / "context-receipts" / f"{kwargs['response_message_id']}.json",
                    **kwargs,
                )

            def record_flight(**kwargs):
                return write_live_flight(root=root / "replay", **kwargs)

            env = {
                "FAWKES_CHAT_MODEL": "test-model",
                "FAWKES_WEB_RESEARCH_ENABLED": "0", "FAWKES_MEMORY_WORKER_ENABLED": "0",
            }
            working_context = ({"message_id": "current-working-message", "role": "assistant",
                                "content": "CURRENT WORKING CONTEXT MUST NOT BE RETRIEVED"},)
            with patch.dict(os.environ, env, clear=True), \
                 patch("src.runtime.chat.OpenAI", return_value=client), \
                 patch("src.runtime.production_planner_builder.build_archive_context", return_value=working_context), \
                 patch("src.runtime.chat_service.build_archive_context", side_effect=served_context), \
                 patch("src.runtime.chat_service.ensure_archive_index"), \
                 patch("src.runtime.chat_service.get_latest_conversation", return_value=conversation), \
                 patch("src.runtime.chat_service.persist_live_message", side_effect=persist), \
                 patch("src.runtime.chat_service.discover_candidate", return_value={"work_item_id": "work-1"}), \
                 patch("src.runtime.chat_service.update_work_item"), \
                 patch("src.runtime.chat_service.record_provider_transmission"), \
                 patch("src.memory.review_feedback.FEEDBACK_DIR", root / "development-feedback"), \
                 patch("src.runtime.chat_service.save_context_receipt", side_effect=save_receipt), \
                 patch("src.runtime.chat_service.load_context_receipt", side_effect=lambda message_id: json.loads(
                     (root / "context-receipts" / f"{message_id}.json").read_text())
                     if (root / "context-receipts" / f"{message_id}.json").exists() else None), \
                 patch("src.runtime.chat_service.load_flight", side_effect=lambda instance, message_id: json.loads(
                     (root / "replay" / instance / "flights" / f"{message_id}.json").read_text())
                     if (root / "replay" / instance / "flights" / f"{message_id}.json").exists() else None), \
                 patch("src.runtime.chat_service.record_live_flight", side_effect=record_flight), \
                 patch.object(FawkesChatService, "_retain_requested_media", side_effect=lambda x, **kw: x):
                service = FawkesChatService(
                    phoenix={"instance_id": instance_id, "name": "Fawkes"},
                    archive_index_path=index, archive_meta_dir=meta,
                    library_root=root / "library",
                )
                service.runtime.evidence_transmission_authorizer.root = root / "permits"
                self.assertEqual(service.runtime.retrieval_path, "planner")
                health = {item["name"]: item["availability"]
                          for item in service.runtime.capability_context()}
                for capability in ("retrieval.plan", "retrieval.evidence_eligibility",
                                   "retrieval.production_adapters", "retrieval.evidence_transmission"):
                    self.assertEqual(health[capability], "live")
                preflight = service.runtime.planner_context_builder(
                    instance_id=instance_id, user_message="verified evidence",
                    conversation_id="current-conversation", request_message_id="preflight-message",
                )
                self.assertEqual([x["message_id"] for x in preflight["selected_evidence"]],
                                 ["historical-message"])
                repeated = service.runtime.planner_context_builder(
                    instance_id=instance_id, user_message="verified evidence",
                    conversation_id="current-conversation", request_message_id="preflight-message",
                )
                self.assertEqual(preflight["deterministic_replay_input_sha256"],
                                 repeated["deterministic_replay_input_sha256"])
                self.assertTrue(any(x.get("reason") == "working_context_excluded"
                                    for x in preflight["exclusions"]))
                self.assertNotIn(body, json.dumps(preflight["retrieval_audit"]))
                self.assertFalse(preflight["automatic_inherited_history"])
                native_projection = preflight["continuity_projections"]["native_archive"]
                self.assertEqual(native_projection["status"], "current")
                self.assertTrue(native_projection["rebuildable"])
                generation = preflight["candidate_generation"]["native_archive"]
                self.assertEqual(generation["reason_counts"]["direct_lexical_metadata_match"], 2)
                self.assertEqual(len(generation["generated_evidence_ids"]), 2)
                self.assertTrue(all(x.startswith("native-evidence-") for x in generation["generated_evidence_ids"]))
                preference = preflight["representation_preference"]["native_archive"]
                self.assertEqual(preference["context_redundancy_reduction"], 1)
                token = "planner-http-token"
                server = FawkesAppServer(("127.0.0.1", 0), chat_service=service, app_token=token)
                thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
                try:
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{server.server_port}/api/chat/messages",
                        data=json.dumps({"message": "verified evidence", "conversation_id": "current-conversation"}).encode(),
                        method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    )
                    try:
                        response = json.load(urllib.request.urlopen(request, timeout=10))
                    except urllib.error.HTTPError as exc:
                        self.fail(exc.read().decode())
                    inspector_request = urllib.request.Request(
                        f"http://127.0.0.1:{server.server_port}/api/chat/messages/{response['message']['message_id']}/context-inspector",
                        headers={"Authorization": f"Bearer {token}"})
                    inspector = json.load(urllib.request.urlopen(inspector_request, timeout=10))
                    feedback_payload = {"feedback_type": "context_helped",
                        "context_receipt_id": inspector["context_receipt_id"],
                        "package_id": inspector["package_id"],
                        "allocation_decision_sha256": inspector["allocation"]["decision_sha256"],
                        "transmission_manifest_id": inspector["transmission"]["manifest_id"],
                        "replay_flight_id": inspector["replay"]["flight_id"]}
                    feedback_request = urllib.request.Request(
                        f"http://127.0.0.1:{server.server_port}/api/chat/messages/{response['message']['message_id']}/context-feedback",
                        data=json.dumps(feedback_payload).encode(), method="POST",
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                    feedback_response = json.load(urllib.request.urlopen(feedback_request, timeout=10))
                    normal_builder=service.runtime.planner_context_builder
                    selected_for_clarification=[]
                    def ambiguity_builder(**kwargs):
                        result=normal_builder(**kwargs)
                        if kwargs.get("clarification_consumption") is not None:
                            return result
                        generated=result["candidate_generation"]["native_archive"]["generated_evidence_ids"]
                        selected_id=result["selected_evidence"][0]["evidence_id"]
                        selected_for_clarification[:] = [selected_id]
                        other_id=next(item for item in generated if item!=selected_id)
                        scoped=NativeRetrievalAmbiguityPolicy().evaluate(
                            instance_id=instance_id,
                            rider_principal_id=f"authenticated-rider:{instance_id}",
                            request_message_id=kwargs["request_message_id"],
                            correlation_id=kwargs["request_message_id"],
                            candidate_generation={"native_archive":{"reference_ambiguity_sets":[{
                                "ambiguity_set_id":"http-ambiguity","candidate_evidence_ids":[selected_id,other_id],
                                "basis":"multiple_verified_native_reference_targets"}],
                                "ambiguity_choice_descriptors":[{"ambiguity_set_id":"http-ambiguity","choices":[
                                    {"evidence_id":selected_id,"created_at":"2026-08-28T10:00:00+00:00"},
                                    {"evidence_id":other_id,"created_at":"2026-08-29T10:00:00+00:00"}]}]}},
                            selected_evidence=[{"domain":"native_archive","evidence_id":selected_id,
                                "created_at":"2026-08-28T10:00:00+00:00"},{"domain":"native_archive",
                                "evidence_id":other_id,"created_at":"2026-08-29T10:00:00+00:00"}],
                            planner_version=result.get("policy_version"),
                            eligibility_policy_version=result.get("evidence_eligibility_policy_version"),
                            retrieval_plan_identity=result.get("deterministic_replay_input_sha256"),
                            query_sha256=hashlib.sha256(kwargs["user_message"].encode()).hexdigest())
                        result["ambiguity_decision"]=scoped
                        result["retrieval_audit"]["ambiguity_decision"]=scoped
                        return result
                    service.runtime.planner_context_builder=ambiguity_builder
                    ambiguity_request=urllib.request.Request(
                        f"http://127.0.0.1:{server.server_port}/api/chat/messages",
                        data=json.dumps({"message":"Verified evidence — select target","conversation_id":"current-conversation"}).encode(),
                        method="POST",headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"})
                    ambiguity_response=json.load(urllib.request.urlopen(ambiguity_request,timeout=10))
                    clarification=ambiguity_response["retrieval_clarification"]
                    chosen=next(item for item in clarification["ambiguity_sets"][0]["choices"]
                                if item["evidence_id"]==selected_for_clarification[0])
                    clarification_payload={"originating_response_message_id":ambiguity_response["message"]["message_id"],
                        "decision_id":clarification["decision_id"],
                        "retrieval_plan_identity":clarification["resulting_retrieval_plan_identity"],
                        "ambiguity_set_id":clarification["ambiguity_sets"][0]["ambiguity_set_id"],
                        "choice_id":chosen["choice_id"],"original_query":"Verified evidence — select target"}
                    stale_request=urllib.request.Request(
                        f"http://127.0.0.1:{server.server_port}/api/chat/messages",
                        data=json.dumps({"message":"That one","conversation_id":"current-conversation",
                            "retrieval_clarification":{**clarification_payload,
                                "retrieval_plan_identity":"stale-plan"}}).encode(),
                        method="POST",headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"})
                    with self.assertRaises(urllib.error.HTTPError) as stale_error:
                        urllib.request.urlopen(stale_request,timeout=10)
                    self.assertEqual(stale_error.exception.code,400)
                    stale_error.exception.read(); stale_error.exception.close()
                    consume_request=urllib.request.Request(
                        f"http://127.0.0.1:{server.server_port}/api/chat/messages",
                        data=json.dumps({"message":"That one","conversation_id":"current-conversation",
                            "retrieval_clarification":clarification_payload}).encode(),
                        method="POST",headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"})
                    try:
                        consumed_response=json.load(urllib.request.urlopen(consume_request,timeout=10))
                    except urllib.error.HTTPError as exc:
                        self.fail(exc.read().decode())
                    service.runtime.planner_context_builder = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("down"))
                    degraded_request = urllib.request.Request(
                        f"http://127.0.0.1:{server.server_port}/api/chat/messages",
                        data=json.dumps({"message": "verified evidence", "conversation_id": "current-conversation"}).encode(),
                        method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    )
                    degraded_response = json.load(urllib.request.urlopen(degraded_request, timeout=10))
                finally:
                    server.shutdown(); server.server_close(); thread.join(timeout=2)

            provider_calls = [call for call in calls if "Relevant persistent memories:" in str(call.get("input"))]
            self.assertEqual(response["message"]["content"], "served planner answer")
            self.assertTrue(response["message"]["context_inspector_available"])
            self.assertEqual(inspector["composition_status"], "retrieved_context_used")
            self.assertEqual(inspector["source_domains"], {"native_archive": 1})
            self.assertEqual(inspector["transmission"]["status"], "authorized")
            self.assertEqual(inspector["replay"]["flight_id"], response["message"]["message_id"])
            self.assertFalse(inspector["contains_source_bodies"])
            self.assertNotIn(body, json.dumps(inspector))
            self.assertEqual(feedback_response["feedback"]["feedback_type"], "context_helped")
            self.assertFalse(any(feedback_response["feedback"]["authority"].values()))
            feedback_files = list((root / "development-feedback").glob("*.json"))
            self.assertEqual(len(feedback_files), 1)
            self.assertNotIn(body, feedback_files[0].read_text())
            self.assertIn("Which one do you mean?",ambiguity_response["message"]["content"])
            self.assertTrue(ambiguity_response["retrieval_clarification"]["clarification_required"])
            self.assertEqual(consumed_response["message"]["content"],"served planner answer")
            self.assertTrue(provider_calls)
            self.assertGreaterEqual(len(provider_calls), 2)
            self.assertIn(body, str(provider_calls[0]["input"]))
            self.assertEqual(degraded_response["message"]["content"], "served planner answer")
            self.assertNotIn(body, str(provider_calls[-1]["input"]))
            manifests = list((root / "permits").rglob("evidence-manifest-*.json"))
            self.assertEqual(len(manifests), 2)
            manifest = json.loads(sorted(manifests,key=lambda item:item.stat().st_mtime)[-1].read_text())
            self.assertEqual(len(manifest["evidence"]), 1)
            self.assertTrue(manifest["evidence"][0]["evidence_id"].startswith("native-evidence-"))
            self.assertTrue(manifest["evidence"][0]["native_evidence_identity"].startswith("native-evidence-"))
            self.assertNotIn(body, manifests[0].read_text())
            receipts = [json.loads(path.read_text())
                        for path in (root / "context-receipts").rglob("*.json")]
            flights = [json.loads(path.read_text())
                       for path in (root / "replay").rglob("*.json")]
            audit_text = json.dumps([item.get("retrieval_audit") for item in receipts])
            flight_metadata = json.dumps([{key: item.get(key) for key in (
                "retrieval_plan", "candidates", "exclusions", "context_allocation",
                "transmission_authorization") } for item in flights])
            self.assertNotIn(body, audit_text + flight_metadata)
            self.assertIn(manifest["manifest_id"], audit_text + flight_metadata)
            self.assertIn('"purpose": "response_model_context"', audit_text)
            self.assertIn('"policy_version": "context-cross-source-allocation-v1"', audit_text)
            self.assertIn(manifest["evidence"][0]["evidence_id"], audit_text)
            self.assertIn("native-continuity-", audit_text + flight_metadata)
            self.assertIn('"request_timestamp": "2026-08-31T00:00:00+00:00"',
                          audit_text + flight_metadata)
            self.assertIn('"timezone_source": "deterministic_utc_fallback"',
                          audit_text + flight_metadata)

    def test_explicit_served_legacy_mode_remains_immediate_rollback(self):
        client = type("Client", (), {"responses": object()})()
        with patch.dict(os.environ, {"FAWKES_RETRIEVAL_PATH": "legacy"}), \
             patch("src.runtime.chat.OpenAI", return_value=client), \
             patch("src.runtime.chat_service.ensure_archive_index"):
            service = FawkesChatService(phoenix={"instance_id": "rollback-phoenix", "name": "Fawkes"})
        self.assertEqual(service.runtime.retrieval_path, "legacy")
        self.assertIsNone(service.runtime.planner_context_builder)


if __name__ == "__main__":
    unittest.main()
