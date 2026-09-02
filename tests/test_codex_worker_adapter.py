import json
import hashlib
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.runtime.codex_worker_adapter import (
    ADAPTER_ID, ADAPTER_PROMOTED, PROMOTION_RECORD, CodexExecWorkerAdapter, MAX_PACKAGE_BYTES,
)
from src.runtime.worker_exchange import WorkerExchange, _digest
from src.runtime.chat import FawkesChatRuntime


class Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode=returncode; self.stdout=stdout; self.stderr=stderr


class FakeCodex:
    def __init__(self, response=None, failure=None):
        self.response=response; self.failure=failure; self.calls=[]

    def __call__(self, command, *, prompt, environment, timeout):
        self.calls.append({"command":command,"prompt":prompt,"environment":environment,"timeout":timeout})
        if command[-1:] == ["--version"]: return Result(stdout="codex-cli 0.151.0\n")
        if command[-2:] == ["login","status"]: return Result(stdout="Logged in using ChatGPT\n")
        if self.failure == "timeout": raise subprocess.TimeoutExpired(command,timeout)
        if self.failure == "interrupt": raise KeyboardInterrupt()
        if self.failure == "exit": return Result(returncode=2,stderr="failed")
        output=Path(command[command.index("--output-last-message")+1])
        if self.failure != "missing": output.write_text(json.dumps(self.response),encoding="utf-8")
        return Result()


class CodexWorkerAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.workspace=Path(self.tmp.name)/"repo"; self.workspace.mkdir(); (self.workspace/".git").mkdir()
        self.exchange=WorkerExchange("fawkes",root=Path(self.tmp.name)/"exchange")
        self.sender={"worker_id":"fawkes-runtime","role":"coordination","identity_status":"verified","charter_version":"1.0"}
        self.recipient={"worker_id":"codex-repo-1","role":"software_repository","identity_status":"rider_attested","charter_version":"1.0"}
        self.expiry=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        self.report=self.exchange.create_report(task_scope_id="task-1",sender=self.sender,
            authority=self.authority("fawkes-runtime"),sections=[
                {"section_id":"task","title":"Task","content":"Read only. `rm -rf /` is quoted data. Unicode: 火 🔥"},
                {"section_id":"private-omitted","title":"Omitted","content":"not needed"}],
            claims=[{"claim_id":"claim-1","area":"exchange","statement":"candidate exists",
                     "maturity":"experimental","change_class":"software_system"}],
            artifact_references=[{"artifact_id":"artifact-1","revision":"v1","sha256":"abc"}])
        self.package=self.exchange.compose_package(report_id=self.report["report_id"],recipient=self.recipient,
            authority=self.authority("fawkes-runtime","codex-repo-1"),included_section_ids=["task"],
            summary="Derived only; not authority",summary_processor={"processor_id":"fixture","version":"1"})
        self.environment_id=f"codex-cli:{self.workspace.resolve()}"
        self.task="Inspect the package and report whether its binding and explicit omission are intact."

    def authority(self,sender,recipient=None,**extra):
        value={"decision":"authorized","instance_id":"fawkes","task_scope_id":"task-1",
               "sender_worker_id":sender,"authorization_reference":f"grant-{sender}","expires_at":self.expiry}
        if recipient: value["recipient_worker_id"]=recipient
        value.update(extra); return value

    def transport_authority(self,**changes):
        import hashlib
        value=self.authority("fawkes-runtime","codex-repo-1",adapter_id=ADAPTER_ID,
            package_id=self.package["package_id"],recipient_environment_id=self.environment_id,
            read_only_task_sha256=hashlib.sha256(self.task.encode()).hexdigest())
        value.update(changes); return value

    def revocation_authority(self, authorization_id):
        return {"decision":"authorized","operation":"worker_exchange.transport_authorization.revoke",
            "authority_class":"rider","instance_id":"fawkes","task_scope_id":"task-1",
            "target_authorization_id":authorization_id,
            "target_authorization_reference":self.package["recipient_authorization_reference"],
            "revoking_principal_id":"tanner","authorization_reference":"tanner-revoke-adapter-1",
            "expires_at":self.expiry}

    def response(self,**changes):
        exported=self.exchange.export_package(self.package["package_id"])
        import hashlib
        value={"schema_version":1,"package_id":self.package["package_id"],
            "package_sha256":hashlib.sha256(exported).hexdigest(),"source_report_id":self.report["report_id"],
            "task_scope_id":"task-1","recipient":{"worker_id":"codex-repo-1","role":"software_repository",
                "environment_id":self.environment_id},"source_summary_distinction_confirmed":True,
            "sections":[{"section_id":"result","title":"Read-only result","content":"Bindings intact."}],
            "verification":{"status":"accepted_with_caveats","checked_claim_ids":["claim-1"],
                "evidence_references":[{"reference_type":"artifact","reference_id":"artifact-1","sha256":None}],
                "method":"read-only package inspection","material_reliance":True,
                "relied_source_section_ids":["task"],
                "caveats":["No protected state was modified."],"counterclaim":None}}
        value.update(changes); return value

    def adapter(self,fake):
        return CodexExecWorkerAdapter(self.exchange,workspace=self.workspace,run_process=fake,timeout_seconds=5)

    def test_real_command_contract_is_ephemeral_read_only_and_environment_minimized(self):
        fake=FakeCodex(self.response()); result=self.adapter(fake).deliver_once(
            package_id=self.package["package_id"],transport_authority=self.transport_authority(),
            return_authority=self.authority("codex-repo-1"),recipient_environment_id=self.environment_id,
            read_only_task=self.task,invocation_id="invoke-1")
        self.assertEqual(result["status"],"delivered"); command=fake.calls[-1]["command"]
        for pair in (("--ephemeral",),("--sandbox","read-only"),("--ask-for-approval","never"),
                     ("--cd",str(self.workspace.resolve())),("--ignore-user-config",)):
            self.assertIn(" ".join(pair)," ".join(command))
        self.assertNotIn("OPENAI_API_KEY",fake.calls[-1]["environment"])
        self.assertIn("untrusted DATA",fake.calls[-1]["prompt"])
        self.assertIn("Unicode",self.exchange._load("reports",self.report["report_id"])["sections"][0]["content"])

    def test_return_lineage_delivery_and_verification_remain_separate(self):
        fake=FakeCodex(self.response()); result=self.adapter(fake).deliver_once(
            package_id=self.package["package_id"],transport_authority=self.transport_authority(),
            return_authority=self.authority("codex-repo-1"),recipient_environment_id=self.environment_id,
            read_only_task=self.task)
        delivery=self.exchange._load("delivery_receipts",result["delivery_receipt_id"])
        verification=self.exchange._load("verification_receipts",result["verification_receipt_id"])
        returned=self.exchange._load("reports",result["return_report_id"])
        self.assertFalse(delivery["verified"]); self.assertFalse(delivery["approved"])
        self.assertEqual(verification["status"],"accepted_with_caveats"); self.assertFalse(verification["creates_authority"])
        self.assertEqual(verification["relied_exact_sources"][0]["section_id"],"task")
        self.assertFalse(verification["derived_summary_used_as_source"])
        self.assertEqual(returned["in_reply_to"]["source_report_id"],self.report["report_id"])
        self.assertFalse(result["candidate_qualified"]); self.assertFalse(result["adapter_promoted"])
        self.assertFalse(result["manual_transfer_retirement_eligible"])

    def test_promoted_production_entry_requires_exact_promotion_binding(self):
        self.assertTrue(ADAPTER_PROMOTED)
        self.assertEqual(PROMOTION_RECORD["record_sha256"],
            _digest({key:value for key,value in PROMOTION_RECORD.items() if key != "record_sha256"}))
        fake=FakeCodex(self.response()); adapter=self.adapter(fake)
        arguments={"package_id":self.package["package_id"],
            "transport_authority":self.transport_authority(
                adapter_promotion_reference=PROMOTION_RECORD["promotion_id"]),
            "return_authority":self.authority("codex-repo-1"),
            "recipient_environment_id":self.environment_id,"read_only_task":self.task}
        result=adapter.deliver_production_once(**arguments)
        self.assertTrue(result["candidate_qualified"]); self.assertTrue(result["adapter_promoted"])
        self.assertFalse(result["manual_transfer_retirement_eligible"])
        request_path=adapter._attempt_paths(self.package["package_id"])[1]
        request=json.loads(request_path.read_text())
        self.assertTrue(request["production_use"])
        self.assertEqual(request["adapter_promotion_reference"],PROMOTION_RECORD["promotion_id"])
        result_path=adapter._attempt_paths(self.package["package_id"])[3]
        historical=result_path.read_bytes()
        valid=self.exchange.validate_transport_authorization(
            package_id=self.package["package_id"],authority=arguments["transport_authority"])
        self.exchange.revoke_transport_authorization(package_id=self.package["package_id"],
            target_authorization=arguments["transport_authority"],
            revocation_authority=self.revocation_authority(valid["authorization_id"]))
        with self.assertRaisesRegex(PermissionError,"revoked"):
            adapter.deliver_production_once(**arguments)
        self.assertEqual(result_path.read_bytes(),historical)

        other=Path(self.tmp.name)/"missing-promotion"; other.mkdir(); (other/".git").mkdir()
        other_exchange=WorkerExchange("fawkes",root=Path(self.tmp.name)/"missing-promotion-exchange")
        report=other_exchange.create_report(task_scope_id="task-1",sender=self.sender,
            authority=self.authority("fawkes-runtime"),sections=[{"section_id":"task","title":"Task","content":"x"}])
        package=other_exchange.compose_package(report_id=report["report_id"],recipient=self.recipient,
            authority=self.authority("fawkes-runtime","codex-repo-1"),included_section_ids=["task"])
        environment_id=f"codex-cli:{other.resolve()}"
        transport=self.authority("fawkes-runtime","codex-repo-1",adapter_id=ADAPTER_ID,
            package_id=package["package_id"],recipient_environment_id=environment_id,
            read_only_task_sha256=hashlib.sha256(self.task.encode()).hexdigest())
        with self.assertRaisesRegex(PermissionError,"bind"):
            CodexExecWorkerAdapter(other_exchange,workspace=other,run_process=FakeCodex(self.response())).deliver_production_once(
                package_id=package["package_id"],transport_authority=transport,
                return_authority=self.authority("codex-repo-1"),recipient_environment_id=environment_id,
                read_only_task=self.task)

    def test_runtime_capability_truthfully_advertises_promoted_adapter_live(self):
        runtime=FawkesChatRuntime(client=object(),model="fixture",instance_id="fawkes",retrieval_path="legacy")
        manifest=next(item for item in runtime.capability_context() if item["name"] == "worker.exchange.codex")
        self.assertEqual(manifest["availability"],"live")
        self.assertIn("Tanner-promoted",manifest["availability_reason"])
        self.assertIn("manual fallback",manifest["availability_reason"])

    def test_wrong_workspace_phoenix_task_recipient_and_request_binding_fail_before_invocation(self):
        fake=FakeCodex(self.response()); adapter=self.adapter(fake)
        cases=[{"recipient_environment_id":"codex-cli:/wrong"},
               {"transport_authority":self.transport_authority(instance_id="foreign")},
               {"transport_authority":self.transport_authority(task_scope_id="wrong")},
               {"transport_authority":self.transport_authority(recipient_worker_id="wrong")},
               {"transport_authority":self.transport_authority(read_only_task_sha256="0"*64)}]
        for case in cases:
            args={"package_id":self.package["package_id"],"transport_authority":self.transport_authority(),
                  "return_authority":self.authority("codex-repo-1"),"recipient_environment_id":self.environment_id,
                  "read_only_task":self.task}; args.update(case)
            with self.assertRaises(PermissionError): adapter.deliver_once(**args)
        self.assertEqual(fake.calls,[])

    def test_malformed_or_lineage_changed_response_fails_closed(self):
        changed=self.response(package_id="wrong"); fake=FakeCodex(changed)
        result=self.adapter(fake).deliver_once(package_id=self.package["package_id"],
            transport_authority=self.transport_authority(),return_authority=self.authority("codex-repo-1"),
            recipient_environment_id=self.environment_id,read_only_task=self.task)
        self.assertEqual(result["status"],"failed"); self.assertEqual(result["failure_reason"],"malformed_or_unbound_response")
        self.assertFalse(result["delivered"]); self.assertFalse(result["verified"])

    def test_uncontracted_return_fields_fail_closed_even_if_client_schema_is_bypassed(self):
        changed=self.response(); changed["self_approval"]="promoted"
        result=self.adapter(FakeCodex(changed)).deliver_once(package_id=self.package["package_id"],
            transport_authority=self.transport_authority(),return_authority=self.authority("codex-repo-1"),
            recipient_environment_id=self.environment_id,read_only_task=self.task)
        self.assertEqual(result["status"],"failed")
        self.assertEqual(result["failure_reason"],"malformed_or_unbound_response")
        self.assertFalse(result["delivered"]); self.assertFalse(result["verified"])

    def test_timeout_exit_and_missing_output_fail_honestly(self):
        for failure,reason in (("timeout","timeout"),("interrupt","interrupted"),
                               ("exit","client_failure"),("missing","missing_return_report")):
            with self.subTest(failure=failure):
                separate=Path(self.tmp.name)/failure; separate.mkdir(); (separate/".git").mkdir()
                exchange=WorkerExchange("fawkes",root=Path(self.tmp.name)/f"exchange-{failure}")
                # Rebuild equivalent records in the isolated attempt root.
                report=exchange.create_report(task_scope_id="task-1",sender=self.sender,
                    authority=self.authority("fawkes-runtime"),sections=[{"section_id":"task","title":"Task","content":"x"}])
                package=exchange.compose_package(report_id=report["report_id"],recipient=self.recipient,
                    authority=self.authority("fawkes-runtime","codex-repo-1"),included_section_ids=["task"])
                environment_id=f"codex-cli:{separate.resolve()}"
                import hashlib
                auth=self.authority("fawkes-runtime","codex-repo-1",adapter_id=ADAPTER_ID,
                    package_id=package["package_id"],recipient_environment_id=environment_id,
                    read_only_task_sha256=hashlib.sha256(self.task.encode()).hexdigest())
                result=CodexExecWorkerAdapter(exchange,workspace=separate,run_process=FakeCodex(failure=failure),timeout_seconds=1).deliver_once(
                    package_id=package["package_id"],transport_authority=auth,
                    return_authority=self.authority("codex-repo-1"),recipient_environment_id=environment_id,
                    read_only_task=self.task)
                self.assertEqual(result["failure_reason"],reason); self.assertFalse(result["delivered"])

    def test_duplicate_delivery_is_idempotent_and_does_not_reinvoke(self):
        fake=FakeCodex(self.response()); adapter=self.adapter(fake); args={
            "package_id":self.package["package_id"],"transport_authority":self.transport_authority(),
            "return_authority":self.authority("codex-repo-1"),"recipient_environment_id":self.environment_id,
            "read_only_task":self.task}
        first=adapter.deliver_once(**args); call_count=len(fake.calls); second=adapter.deliver_once(**args)
        self.assertEqual(first["record_sha256"],second["record_sha256"])
        self.assertTrue(second["idempotent_replay"]); self.assertEqual(len(fake.calls),call_count)

    def test_corrupt_or_resealed_elevated_cached_result_fails_closed(self):
        for mutation in ("digest", "state"):
            with self.subTest(mutation=mutation):
                workspace=Path(self.tmp.name)/f"cached-{mutation}"; workspace.mkdir(); (workspace/".git").mkdir()
                exchange=WorkerExchange("fawkes",root=Path(self.tmp.name)/f"cached-exchange-{mutation}")
                report=exchange.create_report(task_scope_id="task-1",sender=self.sender,
                    authority=self.authority("fawkes-runtime"),sections=[{"section_id":"task","title":"Task","content":"x"}])
                package=exchange.compose_package(report_id=report["report_id"],recipient=self.recipient,
                    authority=self.authority("fawkes-runtime","codex-repo-1"),included_section_ids=["task"])
                environment_id=f"codex-cli:{workspace.resolve()}"
                task_sha256=hashlib.sha256(self.task.encode()).hexdigest()
                transport=self.authority("fawkes-runtime","codex-repo-1",adapter_id=ADAPTER_ID,
                    package_id=package["package_id"],recipient_environment_id=environment_id,
                    read_only_task_sha256=task_sha256)
                adapter=CodexExecWorkerAdapter(exchange,workspace=workspace,run_process=FakeCodex(self.response()))
                args={"package_id":package["package_id"],"transport_authority":transport,
                    "return_authority":self.authority("codex-repo-1"),
                    "recipient_environment_id":environment_id,"read_only_task":self.task}
                adapter.deliver_once(**args)
                _,_,_,result_path=adapter._attempt_paths(package["package_id"])
                cached=json.loads(result_path.read_text())
                cached["candidate_qualified"]=True
                if mutation == "state":
                    cached["record_sha256"]=_digest({key:value for key,value in cached.items() if key != "record_sha256"})
                result_path.write_text(json.dumps(cached))
                with self.assertRaisesRegex(ValueError,"cached Codex result"):
                    adapter.deliver_once(**args)

    def test_revocation_blocks_new_use_and_replay_without_rewriting_completed_result(self):
        fake=FakeCodex(self.response()); adapter=self.adapter(fake); transport=self.transport_authority(); args={
            "package_id":self.package["package_id"],"transport_authority":transport,
            "return_authority":self.authority("codex-repo-1"),"recipient_environment_id":self.environment_id,
            "read_only_task":self.task}
        first=adapter.deliver_once(**args); before=json.dumps(first,sort_keys=True)
        valid=self.exchange.validate_transport_authorization(package_id=self.package["package_id"],authority=transport)
        self.exchange.revoke_transport_authorization(package_id=self.package["package_id"],
            target_authorization=transport,revocation_authority=self.revocation_authority(valid["authorization_id"]))
        with self.assertRaisesRegex(PermissionError,"revoked"):
            adapter.deliver_once(**args)
        directory,_,_,result_path=adapter._attempt_paths(self.package["package_id"])
        self.assertTrue(directory.exists())
        self.assertEqual(json.dumps(json.loads(result_path.read_text()),sort_keys=True),before)

    def test_expired_package_and_oversize_package_fail_before_real_client(self):
        fake=FakeCodex(self.response()); adapter=self.adapter(fake)
        path=self.exchange._path("packages",self.package["package_id"]); package=json.loads(path.read_text())
        package["authority_expires_at"]="2000-01-01T00:00:00+00:00"
        package["record_sha256"]="invalid"
        path.write_text(json.dumps(package))
        with self.assertRaises(ValueError):
            adapter.deliver_once(package_id=self.package["package_id"],transport_authority=self.transport_authority(),
                return_authority=self.authority("codex-repo-1"),recipient_environment_id=self.environment_id,
                read_only_task=self.task)
        self.assertEqual(fake.calls,[])

        exchange=WorkerExchange("fawkes",root=Path(self.tmp.name)/"exchange-large")
        report=exchange.create_report(task_scope_id="task-1",sender=self.sender,
            authority=self.authority("fawkes-runtime"),
            sections=[{"section_id":"large","title":"Large","content":"x"*(MAX_PACKAGE_BYTES+1)}])
        package=exchange.compose_package(report_id=report["report_id"],recipient=self.recipient,
            authority=self.authority("fawkes-runtime","codex-repo-1"),included_section_ids=["large"])
        import hashlib
        auth=self.authority("fawkes-runtime","codex-repo-1",adapter_id=ADAPTER_ID,
            package_id=package["package_id"],recipient_environment_id=self.environment_id,
            read_only_task_sha256=hashlib.sha256(self.task.encode()).hexdigest())
        with self.assertRaisesRegex(ValueError,"byte limit"):
            CodexExecWorkerAdapter(exchange,workspace=self.workspace,run_process=fake).deliver_once(
                package_id=package["package_id"],transport_authority=auth,
                return_authority=self.authority("codex-repo-1"),recipient_environment_id=self.environment_id,
                read_only_task=self.task)
        self.assertEqual(fake.calls,[])

    def test_supported_login_preflight_fails_without_claiming_identity(self):
        def logged_out(command, *, prompt, environment, timeout):
            if command[-1:] == ["--version"]: return Result(stdout="codex-cli 0.151.0\n")
            return Result(returncode=1,stderr="Not logged in\n")
        with self.assertRaises(PermissionError): self.adapter(logged_out).preflight()


if __name__ == "__main__": unittest.main()
