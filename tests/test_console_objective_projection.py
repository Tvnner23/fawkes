"""Regression: valid canonical objectives must not disable the compact console."""
import copy
import hashlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from src.app.server import (
    FawkesConsoleApprovalHandler, _console_campaigns, _console_jobs, _console_objective,
    _console_update_text, developer_console_projection, developer_console_objective,
    DEV_CONSOLE_MAX_TEXT_BYTES, DEV_CONSOLE_MAX_RESPONSE_BYTES,
)
from tests.test_dev_console_projection import _repository_fixture

def wrapper(objective, campaign_id="campaign-real-length", created="2026-09-14T05:00:00+00:00"):
    return {"created_at":created, "live_activity":{"campaign_id":campaign_id,
        "objective":objective,"status":"succeeded","current_stage":"succeeded",
        "iteration":1,"maximum_iterations":1,"cancelled":False,"activity":[]}}

class ObjectiveTests(unittest.TestCase):
    def service(self, values):
        service=Mock()
        service.list_codex_development_campaigns.return_value={"campaigns":values}
        service.development_attention_projection.return_value={"attention":[]}
        service.production_component_status.return_value={"components":{}}
        service.development_console_repository_projection.return_value=_repository_fixture()
        return service

    def request(self, service, path, authorized=True):
        handler=object.__new__(FawkesConsoleApprovalHandler)
        handler.server=SimpleNamespace(chat_service=service)
        handler.path=path
        handler._require_auth=Mock(return_value=authorized)
        handler._json=Mock()
        handler.do_GET()
        return handler

    def route(self, text, campaign_id="campaign-real-length"):
        return "/api/development/dev-console/objectives/"+campaign_id+"/"+hashlib.sha256(text.encode()).hexdigest()

    def test_reproduced_11073_byte_objective_summary_and_exact_detail(self):
        text="Finish accepted console. "+("a"*11048)
        self.assertEqual(len(text.encode()),11073)
        records=[wrapper(text)]; before=copy.deepcopy(records);service=self.service(records)
        projection=developer_console_projection(service)
        job=projection["jobs"][0];campaign=projection["campaigns"][0]
        self.assertEqual(projection["current_campaign_id"],campaign["campaign_id"])
        self.assertEqual(job["objective"],campaign["objective"])
        self.assertEqual(job["objective_source"],campaign["objective_source"])
        self.assertIn("objective excerpt",job["objective"])
        self.assertLessEqual(len(job["objective"].encode()),DEV_CONSOLE_MAX_TEXT_BYTES)
        self.assertLessEqual(len(json.dumps(projection,ensure_ascii=False).encode()),DEV_CONSOLE_MAX_RESPONSE_BYTES)
        handler=self.request(service,self.route(text))
        status,full=handler._json.call_args.args
        self.assertEqual(status,200);self.assertEqual(full["objective"],text)
        self.assertFalse(full["creates_authority"])
        self.assertEqual(records,before)
        self.assertEqual(full["sha256"],job["objective_source"]["sha256"])

    def test_unicode_boundaries_and_full_source_bytes(self):
        for text in ["x"*2048, "é"*1024, "a"*2047+"🔥", "🔥"*8000]:
            with self.subTest(length=len(text.encode())):
                view,source=_console_objective(text,"campaign-unicode")
                self.assertLessEqual(len(view.encode()),2048)
                view.encode().decode()
                if len(text.encode())<=2048:
                    self.assertEqual(view,text);self.assertIsNone(source)
                else:
                    self.assertEqual(source["byte_length"],len(text.encode()))
                    self.assertEqual(source["sha256"],hashlib.sha256(text.encode()).hexdigest())

    def test_wrong_type_and_beyond_canonical_bound_remain_rejected(self):
        for value in [{}, [], True, 1, "x"*32001]:
            with self.subTest(value_type=type(value).__name__),self.assertRaises(ValueError):
                _console_objective(value,"campaign-invalid")
        self.assertEqual(_console_objective(None,"campaign-optional"),(None,None))

    def test_32_heavy_objectives_retain_all_ids_with_complete_retrieval(self):
        records=[wrapper(("z"*31996)+str(i).zfill(4),"campaign-"+str(i)) for i in range(32)]
        service=self.service(records);before=copy.deepcopy(records)
        projection=developer_console_projection(service)
        self.assertEqual(len(projection["campaigns"]),32);self.assertEqual(len(projection["jobs"]),32)
        self.assertLess(len(json.dumps(projection,ensure_ascii=False).encode()),512000)
        for item in records:
            activity=item["live_activity"];text=activity["objective"]
            handler=self.request(service,self.route(text,activity["campaign_id"]))
            self.assertEqual(handler._json.call_args.args[1]["objective"],text)
        self.assertEqual(records,before)

    def test_export_labels_excerpt_and_retains_exact_reference(self):
        text="Purpose. "+"é"*5000
        projection=developer_console_projection(self.service([wrapper(text)]))
        exported=_console_update_text(projection,created_at="2026-09-14T05:00:00+00:00",snapshot_id="fixture")
        self.assertIn("Objective excerpt;",exported)
        self.assertIn(hashlib.sha256(text.encode()).hexdigest(),exported)
        self.assertIn("campaign-real-length",exported)
        self.assertIn(str(len(text.encode())),exported)

    def test_detail_requires_authentication_and_no_rider_activity(self):
        service=self.service([wrapper("x"*2200)])
        handler=self.request(service,self.route("x"*2200),authorized=False)
        service.list_codex_development_campaigns.assert_not_called()
        handler._require_auth.assert_called_once_with(record_rider_activity=False)
        handler._json.assert_not_called()

    def test_wrong_digest_or_duplicate_campaign_fails_closed(self):
        text="x"*2200;service=self.service([wrapper(text)])
        handler=self.request(service,self.route("y"*2200))
        self.assertEqual(handler._json.call_args.args[0],409)
        service.list_codex_development_campaigns.return_value={"campaigns":[wrapper(text),wrapper(text)]}
        handler=self.request(service,self.route(text))
        self.assertEqual(handler._json.call_args.args[0],409)

    def test_exact_path_no_traversal_or_other_campaign_fallback(self):
        text="x"*2200;service=self.service([wrapper(text)])
        self.assertEqual(self.request(service,self.route(text,"campaign-other"))._json.call_args.args[0],404)
        service.reset_mock()
        handler=self.request(service,self.route(text,"..%2Fprivate"))
        self.assertEqual(handler._json.call_args.args[0],404)
        service.list_codex_development_campaigns.assert_not_called()

    def test_missing_or_unavailable_source_does_not_return_another_objective(self):
        text="x"*2200;service=self.service([])
        self.assertEqual(self.request(service,self.route(text))._json.call_args.args[0],404)
        service.list_codex_development_campaigns.side_effect=OSError("fixture unavailable")
        self.assertEqual(self.request(service,self.route(text))._json.call_args.args[0],503)

    def test_old_trial_does_not_replace_latest_objective_after_completion(self):
        values=[wrapper("old trial","campaign-old","2026-09-01T01:00:00+00:00"),wrapper("x"*11073)]
        service=self.service(values)
        for _ in range(2):
            projection=developer_console_projection(service)
            self.assertEqual(projection["current_campaign_id"],"campaign-real-length")
            self.assertEqual(projection["jobs"][0]["job_id"],"campaign-real-length")

    def test_global_summary_guard_unchanged(self):
        service=self.service([wrapper("x"*11073)])
        with patch("src.app.server.DEV_CONSOLE_MAX_RESPONSE_BYTES",1),self.assertRaises(ValueError):
            developer_console_projection(service)

    def test_escaping_heavy_32_campaign_reproduction_and_exact_retrieval(self):
        for text in ["x"+"\0"*31998+"y", "x"+"\x01"*1998+"y",
                     "x"+(chr(92)+chr(34)+chr(10)+chr(9))*7000+"y",
                     "é🔥"+"\b\r"*5000]:
            with self.subTest(raw_bytes=len(text.encode())):
                records=[wrapper(text,"campaign-escaped-"+str(i)) for i in range(32)]
                before=copy.deepcopy(records);service=self.service(records)
                handler=self.request(service,"/api/development/dev-console")
                status,projection=handler._json.call_args.args
                self.assertEqual(status,200)
                self.assertLessEqual(len(json.dumps(projection,ensure_ascii=False).encode()),512000)
                self.assertEqual(len(projection["campaigns"]),32)
                self.assertEqual(len(projection["jobs"]),32)
                for campaign,job in zip(projection["campaigns"],projection["jobs"]):
                    self.assertEqual(campaign["objective"],job["objective"])
                    self.assertLessEqual(len(json.dumps(campaign["objective"],ensure_ascii=False).encode())-2,2048)
                    self.assertLessEqual(len(campaign["objective"].encode()),2048)
                    full=self.request(service,self.route(text,campaign["campaign_id"]))
                    self.assertEqual(full._json.call_args.args[1]["objective"],text)
                self.assertEqual(records,before)

    def test_short_raw_but_escaping_heavy_source_is_explicit_excerpt_and_export(self):
        text="x"+"\0"*1998+"y"
        self.assertLessEqual(len(text.encode()),2048)
        projection=developer_console_projection(self.service([wrapper(text)]))
        source=projection["jobs"][0]["objective_source"]
        self.assertEqual(source["byte_length"],2000)
        self.assertTrue(source["excerpt"])
        exported=_console_update_text(projection,created_at="fixture",snapshot_id="fixture")
        self.assertIn(source["sha256"],exported)
        self.assertIn("Objective excerpt;",exported)

if __name__=="__main__":unittest.main()
