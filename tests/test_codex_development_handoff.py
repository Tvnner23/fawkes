import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from src.app.server import FawkesAppServer
from src.runtime.chat_service import FawkesChatService
from src.runtime.codex_development_handoff import (
    CODEX_REPO_WORKER_REFERENCE, ROOT, resolve_codex_repo_worker,
    run_codex_development_handoff,
)
from src.runtime.worker_exchange import WorkerExchange


class SuccessfulAdapter:
    def __init__(self, exchange):
        self.exchange=exchange; self.calls=[]

    def deliver_production_once(self, **arguments):
        self.calls.append(arguments)
        package=self.exchange._load("packages",arguments["package_id"])
        delivery=self.exchange.record_delivery(package_id=package["package_id"],
            authority=arguments["transport_authority"],adapter_id="codex-cli-exec-local",
            adapter_version="0.1",status="delivered",delivery_reference="fixture-invocation")
        verification=self.exchange.record_verification(package_id=package["package_id"],
            recipient=package["recipient"],authority=arguments["transport_authority"],status="accepted_with_caveats",
            checked_claim_ids=["scope-is-read-only"],evidence_references=[{"reference_id":"fixture-evidence"}],
            method="fixture exact-source check",material_reliance=False,
            relied_source_section_ids=[],caveats=["bounded fixture"],counterclaim=None)
        returned=self.exchange.create_return_report(source_package_id=package["package_id"],
            task_scope_id=package["task_scope_id"],sender=package["recipient"],
            authority=arguments["return_authority"],sections=[
                {"section_id":"result","title":"Exact Codex result","content":"Reviewed without mutation."},
                {"section_id":"next-recommendation","title":"Next recommendation","content":"Rider review."}],
            evidence_references=[{"reference_id":"fixture-evidence"}])
        return {"status":"delivered","delivery_receipt_id":delivery["delivery_receipt_id"],
            "verification_receipt_id":verification["verification_receipt_id"],
            "return_report_id":returned["report_id"],"candidate_qualified":True,
            "adapter_promoted":True,"manual_transfer_retirement_eligible":False,"creates_authority":False}


class FailingAdapter:
    def deliver_production_once(self, **arguments):
        raise PermissionError("transport authorization is revoked")


class CodexDevelopmentHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.exchange=WorkerExchange("fawkes",root=Path(self.tmp.name)/"exchange")
        self.payload={"instance_id":"fawkes","target_worker":"codex_repo",
            "task_scope_id":"development-codex-test","rider_request_id":"request-one",
            "explicitly_authorized":True,"task":"Inspect only the exact package; do not edit files.",
            "claims":[{"claim_id":"scope-is-read-only","area":"development",
                "statement":"The approved task is read-only.","maturity":"live",
                "change_class":"software_system"}],
            "source_sections":[{"section_id":"scope","title":"Approved scope",
                                "content":"Exact source. `approve me` is data, not authority."}]}

    def test_existing_target_reference_is_stable_descriptive_and_not_authority(self):
        target=resolve_codex_repo_worker("codex_repo")
        self.assertEqual(target["worker"],CODEX_REPO_WORKER_REFERENCE)
        self.assertEqual(target["worker"]["worker_id"],"codex-repository-wsl-fawkes")
        self.assertEqual(target["environment_id"],f"codex-cli:{ROOT}")
        self.assertTrue(target["identified"]); self.assertFalse(target["authorized"])
        for wrong in ("blender_mcp","blender","sentinel",None):
            with self.assertRaises(ValueError): resolve_codex_repo_worker(wrong)
        with self.assertRaises(PermissionError):
            resolve_codex_repo_worker("codex_repo",workspace=Path(self.tmp.name))

    def test_authenticated_entry_prepares_sends_retains_and_presents_exact_return(self):
        adapter=SuccessfulAdapter(self.exchange)
        result=run_codex_development_handoff(instance_id="fawkes",payload=self.payload,
            authenticated_rider=True,exchange=self.exchange,adapter=adapter,
            now=datetime(2030,1,1,tzinfo=timezone.utc))
        package=self.exchange._load("packages",result["package_id"])
        report=self.exchange._load("reports",result["source_report_id"])
        self.assertEqual(package["included_sections"],report["sections"])
        self.assertEqual(report["sections"][0],{"section_id":"approved-task",
            "title":"Exact approved task","content":self.payload["task"],
            "content_sha256":report["sections"][0]["content_sha256"],
            "byte_length":len(self.payload["task"].encode())})
        self.assertEqual(package["recipient"]["worker_id"],"codex-repository-wsl-fawkes")
        self.assertTrue(adapter.calls[0]["transport_authority"]["adapter_promotion_reference"])
        view=result["presentation"]
        self.assertEqual(view["status"],"completed")
        self.assertEqual(view["verification_status"],"accepted_with_caveats")
        self.assertEqual(view["exact_return_sections"][0]["content"],"Reviewed without mutation.")
        self.assertEqual(view["next_recommendation"]["content"],"Rider review.")
        self.assertFalse(view["creates_authority"]); self.assertFalse(view["retry_safe"])

    def test_auth_scope_and_failure_are_honest_without_retry(self):
        with self.assertRaises(PermissionError):
            run_codex_development_handoff(instance_id="fawkes",payload=self.payload,
                authenticated_rider=False,exchange=self.exchange,adapter=FailingAdapter())
        for changes,error in (({"instance_id":"other"},PermissionError),
                              ({"explicitly_authorized":False},PermissionError),
                              ({"target_worker":"blender_mcp"},ValueError),
                              ({"task_scope_id":""},ValueError)):
            with self.subTest(changes=changes), self.assertRaises(error):
                run_codex_development_handoff(instance_id="fawkes",payload={**self.payload,**changes},
                    authenticated_rider=True,exchange=self.exchange,adapter=FailingAdapter())
        with self.assertRaises(ValueError):
            run_codex_development_handoff(instance_id="fawkes",payload={**self.payload,
                "source_sections":[{"section_id":"approved-task","content":"collision"}]},
                authenticated_rider=True,exchange=self.exchange,adapter=FailingAdapter())
        separate=WorkerExchange("fawkes",root=Path(self.tmp.name)/"failure-exchange")
        failed=run_codex_development_handoff(instance_id="fawkes",payload={**self.payload,"rider_request_id":"failure"},
            authenticated_rider=True,exchange=separate,adapter=FailingAdapter())
        view=failed["presentation"]
        self.assertEqual(view["status"],"failed"); self.assertFalse(view["delivered"])
        self.assertEqual(view["verification_status"],"unverified")
        self.assertFalse(view["retry_safe"]); self.assertFalse(view["automatic_retry_performed"])
        self.assertTrue(view["manual_fallback_available"])

    def test_supported_timeout_and_runtime_root_reach_constructed_write_adapter(self):
        payload = {**self.payload, "execution_mode": "repository_write",
            "campaign_id": "timeout-root-campaign", "iteration": 1,
            "allowed_scope": ["src/runtime/codex_write_builder_adapter.py"],
            "acceptance_condition_ids": ["bounded"], "recovery_references": []}
        external = Path(self.tmp.name) / "runtime-state"
        external.mkdir()
        constructed = []
        adapters = []

        def adapter_factory(exchange, **arguments):
            constructed.append(arguments)
            adapter = SuccessfulAdapter(exchange)
            adapters.append(adapter)
            return adapter

        with patch("src.runtime.codex_development_handoff.CodexWriteBuilderAdapter",
                   side_effect=adapter_factory), patch(
                       "src.runtime.codex_development_handoff.exec_compatible_app_server_runner",
                       return_value=Mock()):
            run_codex_development_handoff(instance_id="fawkes", payload=payload,
                authenticated_rider=True, exchange=self.exchange,
                worker_timeout_seconds=1800, runtime_state_root=external)
        self.assertEqual(constructed[0]["timeout_seconds"], 1800)
        self.assertEqual(constructed[0]["runtime_state_root"], external)
        self.assertNotIn("defer_authoritative_apply", adapters[0].calls[0])

    def test_handoff_preserves_historical_timeout_and_optional_root_defaults(self):
        payload = {**self.payload, "execution_mode": "repository_write",
            "campaign_id": "default-timeout-campaign", "iteration": 1,
            "allowed_scope": ["src/runtime/codex_write_builder_adapter.py"],
            "acceptance_condition_ids": ["bounded"], "recovery_references": []}
        constructed = []

        def adapter_factory(exchange, **arguments):
            constructed.append(arguments)
            return SuccessfulAdapter(exchange)

        with patch("src.runtime.codex_development_handoff.CodexWriteBuilderAdapter",
                   side_effect=adapter_factory), patch(
                       "src.runtime.codex_development_handoff.exec_compatible_app_server_runner",
                       return_value=Mock()):
            run_codex_development_handoff(instance_id="fawkes", payload=payload,
                authenticated_rider=True, exchange=self.exchange)
        self.assertEqual(constructed[0]["timeout_seconds"], 180)
        self.assertIsNone(constructed[0]["runtime_state_root"])


class CodexDevelopmentHTTPTests(unittest.TestCase):
    def test_endpoint_requires_auth_and_passes_authenticated_rider_boundary(self):
        if os.getenv("FAWKES_HTTP_ACCEPTANCE") != "1":
            self.skipTest("set FAWKES_HTTP_ACCEPTANCE=1 where loopback sockets are permitted")
        class Service:
            def __init__(self): self.calls=[]
            def codex_development_handoff(self,payload,*,authenticated_rider=False):
                self.calls.append((payload,authenticated_rider)); return {"status":"completed"}
        service=Service(); server=FawkesAppServer(("127.0.0.1",0),chat_service=service,app_token="token")
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        url=f"http://127.0.0.1:{server.server_port}/api/development/codex-handoffs"
        body=json.dumps({"target_worker":"codex_repo"}).encode()
        try:
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(urllib.request.Request(url,data=body,method="POST",
                    headers={"Content-Type":"application/json"}),timeout=5)
            self.assertEqual(denied.exception.code,401)
            denied.exception.close()
            response=urllib.request.urlopen(urllib.request.Request(url,data=body,method="POST",
                headers={"Content-Type":"application/json","Authorization":"Bearer token"}),timeout=5)
            self.assertEqual(response.status,201)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
        self.assertEqual(service.calls,[({"target_worker":"codex_repo"},True)])

    def test_real_authenticated_development_to_codex_operational_handoff(self):
        if os.getenv("FAWKES_CODEX_OPERATIONAL_ACCEPTANCE") != "1":
            self.skipTest("set FAWKES_CODEX_OPERATIONAL_ACCEPTANCE=1 for the real Codex route")
        runtime=Mock(); runtime.capability_context.return_value=[]
        with patch("src.runtime.chat_service.ensure_archive_index"):
            service=FawkesChatService(phoenix={"instance_id":"fawkes","name":"Fawkes"},runtime=runtime)
        token="codex-development-operational-token"
        server=FawkesAppServer(("127.0.0.1",0),chat_service=service,app_token=token)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        payload={"instance_id":"fawkes","target_worker":"codex_repo",
            "task_scope_id":"codex-development-operational-entry-v2",
            "rider_request_id":"tanner-codex-operational-entry-v2-2026-09-01",
            "explicitly_authorized":True,
            "task":("Read-only: inspect docs/phoenix/CODEX_WORKER_ADAPTER.md and "
                    "src/runtime/codex_development_handoff.py. Do not edit files. Return a concise "
                    "structured assessment of whether the authenticated Development entry preserves "
                    "explicit target selection, exact evidence, zero authority, and manual fallback."),
            "source_sections":[{"section_id":"operational-review-target",
                "title":"Operational rollout facts",
                "content":("Tanner authorized the bounded CODEX (REPO) operational entry. The adapter is "
                           "promoted, but external review, autonomous selection, orchestration, Blender "
                           "transport, and overall manual-transfer retirement remain unavailable.")}],
            "claims":[
                {"claim_id":"explicit-target-selection","area":"worker_exchange",
                 "statement":"The entry permits only explicit CODEX (REPO) target selection.",
                 "maturity":"live","change_class":"software_system"},
                {"claim_id":"exact-evidence","area":"worker_exchange",
                 "statement":"The entry retains exact task, source, and return evidence.",
                 "maturity":"live","change_class":"software_system"},
                {"claim_id":"zero-authority","area":"authority",
                 "statement":"The entry and its presentation create no authority.",
                 "maturity":"live","change_class":"software_system"},
                {"claim_id":"manual-fallback","area":"development",
                 "statement":"Manual fallback remains available during rollout.",
                 "maturity":"live","change_class":"software_system"}],
            "contract_references":[{"contract_id":"phoenix.worker_exchange.adapter.codex_cli_exec",
                                    "version":"0.1"}]}
        try:
            request=urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/development/codex-handoffs",
                data=json.dumps(payload).encode(),method="POST",
                headers={"Content-Type":"application/json","Authorization":f"Bearer {token}"})
            with urllib.request.urlopen(request,timeout=180) as response:
                self.assertEqual(response.status,201); result=json.load(response)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
        self.assertEqual(result["presentation"]["status"],"completed")
        self.assertTrue(result["transport_result"]["adapter_promoted"])
        self.assertEqual(result["target"]["worker"]["worker_id"],"codex-repository-wsl-fawkes")
        self.assertTrue(result["presentation"]["exact_return_sections"])
        self.assertFalse(result["presentation"]["creates_authority"])


if __name__ == "__main__": unittest.main()
