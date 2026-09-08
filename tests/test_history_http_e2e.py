import hashlib
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from src.app.server import FawkesAppServer
from src.history_staging import ChatGPTExportAdapter, InheritedHistoryStore
from src.memory.archive_retrieval import index_canonical_message
from src.runtime.chat_service import FawkesChatService


class HistoryHTTPAcceptanceTests(unittest.TestCase):
    def test_authenticated_manual_search_and_exact_navigation(self):
        if os.getenv("FAWKES_HTTP_ACCEPTANCE") != "1":
            self.skipTest("set FAWKES_HTTP_ACCEPTANCE=1 where loopback sockets are permitted")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); owner = "history-http-phoenix"; index = root / "native.sqlite3"
            raw = json.dumps({"message_id": "native-message", "role": "user", "text": "HTTP shared history phrase native"}).encode()
            (root / "archive/raw").mkdir(parents=True); (root / "archive/meta").mkdir(parents=True)
            (root / "archive/raw/native-archive.json").write_bytes(raw)
            (root / "archive/meta/native-archive.json").write_text(json.dumps({
                "archive_id": "native-archive", "instance_id": owner, "raw_file": "native-archive.json",
                "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw), "encoding": "utf-8"}))
            index_canonical_message(instance_id=owner, conversation_id="native-conversation", message_id="native-message",
                role="user", content="HTTP shared history phrase native", created_at="2026-01-01T00:00:00+00:00",
                source_archive_id="native-archive", path=index)
            payload = [{"id": "inherited-conversation", "mapping": {"node": {"parent": None, "children": [], "message": {
                "id": "inherited-message", "author": {"role": "user"},
                "content": {"content_type": "text", "parts": ["HTTP shared history phrase inherited"]}}}}}]
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive: archive.writestr("conversations.json", json.dumps(payload))
            inherited_root = root / "inherited"
            principal = f"rider:{owner}"
            InheritedHistoryStore(owner, root=inherited_root, processing_root=root / "processing").stage(
                buffer.getvalue(), adapter=ChatGPTExportAdapter(), actor_principal=principal,
                authorization={"authorization_id": "authorization:history-http", "mode": "explicit_confirmation",
                    "scope": "stage_inherited_history_export", "instance_id": owner, "principal_id": principal})
            runtime = Mock(); runtime.capability_context.return_value = []
            with patch("src.runtime.chat_service.ensure_archive_index"):
                service = FawkesChatService(phoenix={"instance_id": owner, "name": "Fawkes"}, runtime=runtime,
                    inherited_history_root=inherited_root, archive_index_path=index,
                    archive_meta_dir=root / "archive/meta", archive_raw_dir=root / "archive/raw",
                    capability_receipt_dir=root / "receipts")
            token = "history-http-token"
            server = FawkesAppServer(("127.0.0.1", 0), chat_service=service, app_token=token)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/api/history/search",
                    data=json.dumps({"query": "HTTP shared history phrase"}).encode(), method="POST",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
                result = json.load(urllib.request.urlopen(request, timeout=10))
                inherited = next(item for item in result["results"] if item["domain"] == "inherited_history")
                ref = inherited["evidence_reference"]
                evidence_request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/history/evidence/{ref['domain']}/{ref['evidence_id']}",
                    headers={"Authorization": f"Bearer {token}"})
                evidence = json.load(urllib.request.urlopen(evidence_request, timeout=10))
                runtime_root = Path(os.environ['FAWKES_RUNTIME_STATE_ROOT'])
                self.assertTrue((runtime_root / 'database/rider_activity' / owner / 'rider-activity.json').is_file())
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)
        self.assertEqual({item["domain"] for item in result["results"]}, {"native_archive", "inherited_history"})
        self.assertFalse(result["automatic_chat_context"])
        self.assertEqual(evidence["exact_original_text"], "HTTP shared history phrase inherited")
        self.assertEqual(evidence["identity_attribution"], "unassessed")


if __name__ == "__main__": unittest.main()
