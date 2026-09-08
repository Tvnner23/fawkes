"""Offline first-start/default-path regressions, using no real history or provider."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AlphaStartupTests(unittest.TestCase):
    def run_isolated(self, body):
        with tempfile.TemporaryDirectory(prefix="fawkes-alpha-startup-") as temporary:
            env = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL")}
            env.update(FAWKES_RUNTIME_STATE_ROOT=temporary,
                       FAWKES_MEMORY_WORKER_ENABLED="0", PYTHONDONTWRITEBYTECODE="1")
            prelude = '''
import hashlib, io, json, os, socket, sqlite3, subprocess, sys, zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
state = Path(os.environ['FAWKES_RUNTIME_STATE_ROOT'])
def forbidden(*args, **kwargs):
    raise AssertionError('External operation forbidden in offline startup test')
socket.socket.connect = forbidden
socket.create_connection = forbidden
subprocess.Popen = forbidden
patch('openai.OpenAI', side_effect=forbidden).start()
from src.runtime.chat_service import FawkesChatService
from src.instances import get_or_create_default_instance
from src.conversations import create_conversation
from src.ingest import ingest_bytes, RAW_DIR, META_DIR
from src.memory.archive_retrieval import INDEX_PATH
phoenix = get_or_create_default_instance(name='Synthetic Alpha fixture')
owner = phoenix['instance_id']
conversation = create_conversation('Synthetic first start', instance_id=owner)
payload = json.dumps({'schema_version': 1, 'message_id': 'synthetic-message',
    'conversation_id': conversation['conversation_id'], 'role': 'user',
    'text': 'Synthetic Alpha source sentinel'}).encode()
metadata = ingest_bytes(payload, 'Synthetic fixture', source='offline-test',
    capture_type='message_state', encoding='utf-8', instance_id=owner,
    conversation_id=conversation['conversation_id'], capture_event_id='synthetic-event',
    emit_receipt=False)
assert not INDEX_PATH.exists()
originals = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
    for directory in (RAW_DIR, META_DIR) for p in directory.iterdir()
    if p.is_file() and not p.name.startswith('.')}
service = FawkesChatService(phoenix=phoenix,
    runtime=SimpleNamespace(model='offline-fixture', context_messages=20))
assert not service._memory_worker_enabled
'''
            result = subprocess.run([sys.executable, "-I", "-B", "-c", prelude + body, str(ROOT)],
                                    cwd=temporary, env=env, capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_nonempty_first_start_rebuilds_and_preserves_originals(self):
        self.run_isolated('''
with sqlite3.connect(INDEX_PATH) as connection:
    rows = connection.execute('SELECT content FROM canonical_message_projection WHERE instance_id=?', (owner,)).fetchall()
assert rows == [('Synthetic Alpha source sentinel',)], rows
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest for p, digest in originals.items())
''')

    def test_history_defaults_follow_configured_state_and_resolve_exact_evidence(self):
        self.run_isolated('''
from src.historical_search import NativeArchiveDomain, InheritedHistoryDomain
from src.history_staging import InheritedHistoryStore, ChatGPTExportAdapter
from src.runtime.processing_ledger import PROCESSING_ROOT
from src.capabilities.core import RECEIPTS_DIR
native = NativeArchiveDomain(owner)
store = InheritedHistoryStore(owner)
assert native.raw_dir == state / 'archive/raw', native.raw_dir
assert native.meta_dir == state / 'archive/meta', native.meta_dir
assert store.base_root == state / 'database/inherited_history', store.base_root
assert PROCESSING_ROOT == state / 'database/processing', PROCESSING_ROOT
assert RECEIPTS_DIR == state / 'database/capability_receipts', RECEIPTS_DIR
rows = native.search('source sentinel', limit=10)
assert len(rows) == 1, rows
assert native.evidence(metadata['archive_id'])['exact_original_text'] == 'Synthetic Alpha source sentinel'
export = [{'id': 'inherited-conversation', 'title': 'Synthetic founding', 'mapping': {
    'node-1': {'id': 'node-1', 'parent': None, 'children': [], 'message': {
        'id': 'inherited-message', 'author': {'role': 'user'}, 'create_time': 10,
        'content': {'content_type': 'text', 'parts': ['Synthetic inherited sentinel']}}}}}]
buffer = io.BytesIO()
with zipfile.ZipFile(buffer, 'w') as archive:
    archive.writestr('conversations.json', json.dumps(export))
principal = 'rider:' + owner
store.stage(buffer.getvalue(), adapter=ChatGPTExportAdapter(), actor_principal=principal,
    authorization={'authorization_id': 'synthetic-authorization', 'mode': 'explicit_confirmation',
        'scope': 'stage_inherited_history_export', 'instance_id': owner, 'principal_id': principal})
inherited = InheritedHistoryDomain(owner)
rows = inherited.search('inherited sentinel', limit=10)
assert len(rows) == 1, rows
assert inherited.evidence(rows[0]['evidence_reference']['evidence_id'])['exact_original_text'] == 'Synthetic inherited sentinel'
result = service.historical_search({'query': 'sentinel'})
assert {row['domain'] for row in result['results']} == {'native_archive', 'inherited_history'}, result
assert service.historical_evidence('native_archive', metadata['archive_id'])['exact_original_text'] == 'Synthetic Alpha source sentinel'
assert (PROCESSING_ROOT / owner / 'ledger.sqlite3').is_file()
assert list((RECEIPTS_DIR / owner).glob('*.json'))
assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest for p, digest in originals.items())
''')


if __name__ == "__main__":
    unittest.main()
