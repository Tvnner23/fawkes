"""Real authenticated loopback + actual Workshop/Exchange, synthetic roots only."""
import json
import hashlib
import os
from pathlib import Path
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from src.app.server import BrowserSessionStore, FawkesAppServer
from src.memory.workshop import WorkshopStore
from src.runtime.personal_recording import RecordingPolicyStore
from tests import test_workshop as fixtures


class WorkshopHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.WorkshopTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.env = patch.dict(os.environ, {
            "FAWKES_RUNTIME_STATE_ROOT": str(self.root),
            "FAWKES_DEVELOPMENT_ROOT": str(self.root),
            "FAWKES_CONSOLE_UPDATE_ROOT": str(self.root / "unused-console"),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        # No runtime/model client is constructed. Any unexpected service path fails.
        class InertService:
            instance_id = "fixture-phoenix"
        self.service = InertService()
        self.service._recording_policy_store = self.fixture.policy
        self.sessions = BrowserSessionStore(self.root / "sessions")
        self.server = FawkesAppServer(("127.0.0.1", 0), chat_service=self.service,
            app_token="synthetic-workshop-token", app_session_store=self.sessions)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.origin = "http://127.0.0.1:" + str(self.server.server_port)
        self.cookie, self.csrf = self.sessions.create_bound()
        self.record = None

    def test_http_uses_existing_development_and_exchange_outside_policy_root(self):
        from src.memory import development_store
        from src.runtime import worker_exchange
        source=self.fixture.legacy_proposal()
        evidence=self.fixture.report()
        self.service._recording_policy_store=RecordingPolicyStore('fixture-phoenix',root=self.root/'other-runtime')
        status,value,_=self.request('/development-source/'+source['proposal_id'])
        self.assertEqual(status,200,value)
        self.assertEqual(value['development_source']['source_record'],source)
        status,value,_=self.request(payload={'classification':'ui_defect','observation':'Synthetic separate-root case',
            'interpretation':'Test owner binding','uncertainty':'Synthetic only','evidence':[self.fixture.ref(evidence)]})
        self.assertEqual(status,201,value)
        self.assertTrue((self.root/'other-runtime'/'memory'/'development'/'workshop').exists())
        self.assertFalse((self.root/'other-runtime'/'database').exists())

    def test_http_exchange_import_uses_existing_bus_with_separate_policy_root(self):
        evidence=self.fixture.report()
        self.service._recording_policy_store=RecordingPolicyStore('fixture-phoenix',root=self.root/'separate-policy')
        status,value,_=self.request(payload={'classification':'ui_defect','observation':'Synthetic Exchange binding',
            'interpretation':'Existing bus must remain visible','uncertainty':'Synthetic only','evidence':[self.fixture.ref(evidence)]})
        self.assertEqual(status,201,value)
        self.assertEqual(value['proposal']['evidence'][0],self.fixture.ref(evidence))
        self.assertFalse((self.root/'separate-policy'/'database').exists())

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, suffix="", payload=None, *, auth=True, csrf=True,
                bearer=False, origin=True, raw=None):
        headers = {}
        if auth:
            headers["Authorization" if bearer else "Cookie"] = (
                "Bearer synthetic-workshop-token" if bearer else "fawkes_app_session=" + self.cookie)
        if csrf:
            headers["X-Fawkes-CSRF-Token"] = self.csrf
        if origin:
            headers["Origin"] = self.origin if origin is True else origin
        body = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
        request = urllib.request.Request(self.origin + "/api/development/workshop" + suffix,
            data=body, headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.load(response), response.headers

    def create(self):
        status, value, _ = self.request(payload={"classification": "ui_defect",
            "observation": "Synthetic UI fixture failed.", "interpretation": "Maybe a label defect.",
            "uncertainty": "No real rider result asserted.", "evidence": []})
        self.assertEqual(status, 201, value)
        self.record = value["proposal"]
        return self.record

    def action(self, action, payload):
        status, value, _ = self.request("/" + self.record["proposal_id"] + "/actions", {
            "expected_revision": self.record["revision"], "action": action, "payload": payload})
        self.assertEqual(status, 200, value)
        self.record = value["proposal"]
        return self.record

    def declared(self):
        self.create()
        self.action("investigate", self.fixture.investigation())
        self.action("design", {"proposed_change": "Detached fixture label change.",
            "affected_systems": ["synthetic UI"], "permissions": [], "risks": ["Not real use."],
            "rollback": "Discard fixture."})
        self.action("declare_acceptance", self.fixture.contract(tier=2))
        self.fixture.record = self.record

    def test_reads_are_authenticated_and_writes_require_same_origin_session_csrf(self):
        self.assertEqual(self.request(auth=False)[0], 401)
        self.assertEqual(self.request(payload={}, auth=False)[0], 401)
        for options in ({"csrf": False}, {"bearer": True}, {"origin": False},
                        {"origin": "https://foreign.invalid"}):
            self.assertEqual(self.request(payload={}, **options)[0], 403)
        status, value, headers = self.request(bearer=True)
        self.assertEqual(status, 200)
        self.assertEqual(value["proposals"], [])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertFalse((self.root / "memory").exists())

    def test_round_trip_is_attributed_versioned_and_has_no_execution_path(self):
        self.declared()
        payload = self.fixture.evaluation_payload(verdict="fail")
        source = self.fixture.ref(self.fixture.report("workshop-evaluation-v1", payload))
        self.action("record_evaluation", {"report_reference": source})
        self.assertEqual(self.record["verdict"], "fail")
        self.action("submit", {})
        status, value, _ = self.request("/" + self.record["proposal_id"] + "/review", {
            "expected_revision": self.record["revision"], "decision": "approve",
            "note": "Only a future separately authorized correction; failure remains visible."})
        self.assertEqual(status, 200, value)
        reviewed = value["proposal"]
        self.assertEqual(reviewed["verdict"], "fail")
        self.assertEqual(reviewed["builder"]["role"], "rider_submission")
        self.assertEqual(reviewed["evaluations"][0]["producer"]["worker_id"], fixtures.BUILDER["worker_id"])
        self.assertEqual(reviewed["reviews"][0]["effect"], "recorded_only_no_automatic_application")
        self.assertEqual(reviewed["status"], "approved_for_future_action")
        self.assertIsNone(reviewed["applied_revision"])
        self.assertEqual(reviewed["outcome"], "not_applied")
        self.assertFalse(value["creates_authority"])
        self.assertFalse(value["execution_allowed"])
        status, old, _ = self.request("/" + self.record["proposal_id"] + "?revision=1")
        self.assertEqual(status, 200)
        self.assertEqual(old["proposal"]["revision"], 1)
        self.assertEqual(old["proposal"]["investigations"], [])
        self.assertEqual(len(old["history"]), reviewed["revision"])
        self.assertEqual({path.name for path in (self.root / "memory").iterdir()}, {"development"})
        self.assertEqual({path.name for path in (self.root / "database").iterdir()}, {"worker_exchange"})
        for operation in ("run", "apply", "export", "campaign", "provider"):
            self.assertEqual(self.request("/" + self.record["proposal_id"] + "/" + operation, {})[0], 404)

    def test_cas_conflict_does_not_retry_or_accept_caller_owned_identity(self):
        self.create()
        old = dict(self.record)
        self.action("investigate", self.fixture.investigation())
        status, value, _ = self.request("/" + old["proposal_id"] + "/actions", {
            "expected_revision": old["revision"], "action": "investigate", "payload": self.fixture.investigation()})
        self.assertEqual(status, 409)
        self.assertEqual(value["error"]["code"], "workshop_revision_conflict")
        for addition in ({"instance_id": "another-phoenix"}, {"actor": fixtures.VERIFIER}, {"authority": {"decision": "authorized"}}):
            status, _, _ = self.request("/" + old["proposal_id"] + "/actions", {
                "expected_revision": self.record["revision"], "action": "submit", "payload": {}, **addition})
            self.assertEqual(status, 400)
        self.assertEqual(self.fixture.store.get(old["proposal_id"])["revision"], 2)

    def test_cross_instance_source_and_query_are_denied(self):
        sibling = WorkshopStore("sibling-phoenix", root=self.root).create({"classification": "memory_issue",
            "observation": "Sibling secret fixture.", "interpretation": "Fixture only.", "uncertainty": "Unknown.",
            "evidence": []}, actor=fixtures.BUILDER)
        status, value, _ = self.request("/" + sibling["proposal_id"])
        self.assertEqual(status, 404)
        self.assertNotIn("Sibling secret", json.dumps(value))
        self.assertEqual(self.request("?instance_id=sibling-phoenix")[0], 400)
        self.assertEqual(self.request()[1]["proposals"], [])

    def test_disabled_recording_blocks_new_content_but_retained_reads_survive(self):
        self.create()
        self.fixture.policy.update({"categories": {"personal_diagnostics": False}}, expected_revision=0)
        status, _, _ = self.request("/" + self.record["proposal_id"] + "/actions", {
            "expected_revision": 1, "action": "investigate", "payload": self.fixture.investigation()})
        self.assertEqual(status, 403)
        self.assertEqual(self.request()[1]["proposals"][0]["revision"], 1)
        self.fixture.policy.update({"mode": "private", "categories": {"personal_diagnostics": True}}, expected_revision=1)
        self.assertEqual(self.request(payload={})[0], 403)
        self.assertEqual(self.request("/" + self.record["proposal_id"])[0], 200)

    def test_duplicate_nonfinite_invalid_fields_and_unknown_actions_fail_closed(self):
        for raw in (b'{"observation":"a","observation":"b"}', b'{"cost":NaN}', b'[]'):
            self.assertEqual(self.request(raw=raw)[0], 400)
        self.create()
        for revision in (True, "1", 0):
            self.assertEqual(self.request("/" + self.record["proposal_id"] + "/actions", {
                "expected_revision": revision, "action": "investigate", "payload": self.fixture.investigation()})[0], 400)
        self.assertEqual(self.request("/" + self.record["proposal_id"] + "/actions", {
            "expected_revision": 1, "action": "apply", "payload": {}})[0], 400)
        self.assertEqual(self.request("/" + self.record["proposal_id"] + "?revision=1&revision=2")[0], 400)
        self.assertEqual(self.fixture.store.get(self.record["proposal_id"])["revision"], 1)

    def test_no_evaluation_is_not_completed_and_fake_report_cannot_be_imported(self):
        self.create()
        self.assertEqual(self.record["verdict"], "inconclusive")
        self.assertEqual(self.request("/" + self.record["proposal_id"] + "/actions", {
            "expected_revision": 1, "action": "submit", "payload": {}})[0], 400)
        self.assertEqual(self.request("/" + self.record["proposal_id"] + "/actions", {
            "expected_revision": 1, "action": "record_evaluation", "payload": {"verdict": "pass"}})[0], 400)

    def test_ambiguous_durability_returns_no_success_and_no_retry(self):
        self.create()
        publish = WorkshopStore._publish
        def uncertain(store, *args, **kwargs):
            publish(store, *args, **kwargs)
            raise OSError("synthetic post-publication uncertainty")
        with patch.object(WorkshopStore, "_publish", uncertain):
            status, value, _ = self.request("/" + self.record["proposal_id"] + "/actions", {
                "expected_revision": 1, "action": "investigate", "payload": self.fixture.investigation()})
        self.assertEqual(status, 503)
        self.assertNotIn("proposal", value)
        self.assertEqual(self.fixture.store.get(self.record["proposal_id"])["revision"], 2)

    def test_corrupt_preferences_do_not_assume_recording_enabled(self):
        self.fixture.policy.update({"mode": "private"}, expected_revision=0)
        self.fixture.policy.path.write_text("{broken", encoding="utf-8")
        status, value, _ = self.request(payload={})
        self.assertEqual(status, 503)
        self.assertEqual(value["error"]["code"], "workshop_recording_unavailable")
        self.assertFalse((self.root / "memory").exists())

    def test_existing_development_intake_binds_exact_source_without_rewriting_it(self):
        source = self.fixture.legacy_proposal()
        path = self.root / "memory" / "development" / (source["proposal_id"] + ".json")
        before = path.read_bytes()
        status, value, _ = self.request("/development-source/" + source["proposal_id"])
        self.assertEqual(status, 200, value)
        reference = value["development_source"]
        self.assertEqual(reference["expected_source_sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(reference["producer_identity"], "not_recorded_by_legacy_owner")
        payload = {key: reference[key] for key in ("source_proposal_id", "expected_source_sha256")}
        payload["classification"] = "development_observation"
        self.assertEqual(self.request("/intake-development", payload, csrf=False)[0], 403)
        self.assertEqual(self.request("/intake-development", {**payload, "source_record": source})[0], 400)
        self.assertEqual(self.request("/intake-development", {**payload, "expected_source_sha256": "0" * 64})[0], 409)
        status, value, _ = self.request("/intake-development", payload)
        self.assertEqual(status, 201, value)
        intake = value["proposal"]
        self.assertEqual(intake["origin"]["source_record"], source)
        self.assertEqual(intake["builder"]["role"], "rider_submission")
        self.assertEqual(intake["evaluations"], [])
        self.assertEqual(intake["investigations"], [])
        self.assertEqual(intake["verdict"], "inconclusive")
        self.assertEqual(path.read_bytes(), before)
        self.fixture.policy.update({"mode": "private"}, expected_revision=0)
        self.assertEqual(self.request("/intake-development", payload)[0], 403)
        self.assertEqual(path.read_bytes(), before)

    def test_existing_development_source_never_projects_foreign_or_unscoped_body(self):
        source = self.fixture.legacy_proposal()
        path = self.root / "memory" / "development" / (source["proposal_id"] + ".json")
        for owner in (None, "sibling-phoenix"):
            source["instance_id"] = owner
            source["observation"] = "FOREIGN_WORKSHOP_HTTP_SENTINEL"
            path.write_text(json.dumps(source), encoding="utf-8")
            status, value, _ = self.request("/development-source/" + source["proposal_id"])
            self.assertIn(status, (400, 403, 404))
            self.assertNotIn("FOREIGN_WORKSHOP_HTTP_SENTINEL", json.dumps(value))


if __name__ == "__main__":
    unittest.main()
