"""Complete response byte boundaries, independently of per-field schema tests."""
from io import BytesIO
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from src.app import server
from tests.test_dev_console_projection import _repository_fixture

class ProjectionCapacityTests(unittest.TestCase):
    def service(self):
        service=Mock()
        service.list_codex_development_campaigns.return_value={'campaigns':[]}
        service.development_attention_projection.return_value={'attention':[]}
        service.production_component_status.return_value={'components':{}}
        service.development_console_repository_projection.return_value=_repository_fixture()
        return service

    def project(self, filler):
        # Synthetic aggregate content isolates the final guard; per-field and
        # real roadmap contracts retain their existing separate tests.
        with patch.object(server,'_console_roadmap',return_value={'payload':filler}):
            return server.developer_console_projection(self.service())

    @staticmethod
    def body(value):return json.dumps(value,ensure_ascii=False).encode('utf-8')

    def test_exact_byte_limit_and_one_byte_over(self):
        empty=self.project('')
        available=server.DEV_CONSOLE_MAX_RESPONSE_BYTES-len(self.body(empty))
        exact=self.project('x'*available)
        self.assertEqual(len(self.body(exact)),server.DEV_CONSOLE_MAX_RESPONSE_BYTES)
        with self.assertRaisesRegex(ValueError,'exceeds its byte limit'):
            self.project('x'*(available+1))

    def test_unicode_bound_is_utf8_bytes_not_characters(self):
        available=server.DEV_CONSOLE_MAX_RESPONSE_BYTES-len(self.body(self.project('')))
        fill='😀'*(available//4)+'x'*(available%4)
        self.assertEqual(len(self.body(self.project(fill))),server.DEV_CONSOLE_MAX_RESPONSE_BYTES)
        with self.assertRaisesRegex(ValueError,'exceeds its byte limit'):
            self.project(fill+'x')

    def test_large_complete_content_survives_actual_json_writer(self):
        text=('history ⚙ \"exact\"\r\n'*16000)
        value=self.project(text)
        self.assertGreater(len(self.body(value)),256000)
        handler=object.__new__(server.FawkesAppHandler)
        handler.wfile=BytesIO();handler.send_response=Mock();handler.send_header=Mock();handler.end_headers=Mock()
        server.FawkesAppHandler._json(handler,200,value)
        body=handler.wfile.getvalue()
        self.assertEqual(body,self.body(value))
        self.assertEqual(json.loads(body)['roadmap']['payload'],text)
        handler.send_header.assert_any_call('Content-Length',str(len(body)))

    def test_existing_independent_limits_unchanged(self):
        self.assertEqual(server.DEV_CONSOLE_MAX_CAMPAIGNS,32)
        self.assertEqual(server.DEV_CONSOLE_MAX_TEXT_BYTES,2048)
        self.assertEqual(server.DEV_CONSOLE_MAX_UPDATE_BYTES,96000)
        self.assertEqual(server.DEV_CONSOLE_MAX_RESPONSE_BYTES,512000)
        with self.assertRaises(ValueError):server._console_text('x'*2049,'test')

    def test_authentication_still_precedes_projection(self):
        handler=object.__new__(server.FawkesAppHandler)
        handler.path='/api/development/dev-console';handler.headers={}
        handler.server=SimpleNamespace(chat_service=self.service())
        handler._require_auth=Mock(return_value=False);handler._json=Mock()
        handler.do_GET()
        handler.server.chat_service.list_codex_development_campaigns.assert_not_called()
        handler._json.assert_not_called()

if __name__=='__main__':unittest.main()
