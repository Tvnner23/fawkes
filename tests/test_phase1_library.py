import base64
import io
import json
import multiprocessing
import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from src.capabilities.media_chat import validate_chat_media
from src.capabilities.awareness import CapabilityAwareness
from src.library.extraction import ExtractionResult, PypdfDocumentExtractor, _publish_result
from src.library.store import list_extractions, list_sources, search_extractions
from src.runtime.chat_service import FawkesChatService
from src.runtime.chat import FawkesChatRuntime


def text_pdf(*pages):
    writer = PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})
        })
        stream = DecodedStreamObject()
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class FixtureExtractor:
    extractor_id = "fixture-page-extractor"
    extractor_version = "1"

    def extract(self, raw_bytes, *, media_type):
        if media_type != "application/pdf":
            raise ValueError("PDF only")
        return ExtractionResult(({
            "segment_id": "page-142",
            "text": "Subnetting divides an IP network into smaller networks.",
            "location": {"page_number": 142, "page_label": "142",
                         "source_locator": "pdf:page=142"},
        },), {"physical_page_count": 200, "extracted_page_count": 1,
              "coverage": "partial", "original_remains_authoritative": True})


class FailingExtractor(FixtureExtractor):
    def extract(self, raw_bytes, *, media_type):
        raise ValueError("synthetic extraction failure")


def partial_result_worker(raw_bytes, output):
    """A real spawned writer stalls after publishing only a partial body."""
    view = memoryview(output).cast('B')
    struct.pack_into('!Q', view, 0, 1024)
    view[8:9] = b'{'
    time.sleep(20)


class PhaseOneLibraryTests(unittest.TestCase):
    def _service(self, root, extractor):
        runtime = Mock()
        runtime.model = "test-model"
        runtime.capability_catalog = Mock()
        with patch("src.runtime.chat_service.ensure_archive_index"):
            return FawkesChatService(
                phoenix={"instance_id": "fawkes-one", "name": "Fawkes"},
                runtime=runtime, library_root=root,
                provider_receipt_dir=Path(root) / "provider-receipts",
                capability_receipt_dir=Path(root) / "capability-receipts",
                document_extractor=extractor,
            )

    def _attachment(self, *, keep):
        payload = text_pdf("Subnetting chapter")
        return validate_chat_media([{
            "name": "networking.pdf", "mime_type": "application/pdf",
            "data": base64.b64encode(payload).decode("ascii"),
            "privacy": "potentially_private", "keep_in_library": keep,
            "retention_title": "Networking textbook",
        }], instance_id="fawkes-one", owner_principal_id="authenticated-rider:fawkes-one")

    def test_real_local_extractor_returns_physical_page_provenance(self):
        result = PypdfDocumentExtractor().extract(
            text_pdf("First page", "Subnetting appears on the second page"),
            media_type="application/pdf",
        )
        self.assertEqual(result.metadata["physical_page_count"], 2)
        self.assertEqual(result.segments[1]["location"]["page_number"], 2)
        self.assertEqual(result.segments[1]["location"]["source_locator"], "pdf:page=2")
        self.assertIn("Subnetting", result.segments[1]["text"])

    def test_result_larger_than_pipe_buffer_completes_without_framed_pipe(self):
        payload = text_pdf("Source-backed local fixture text. " * 2500)
        with patch("src.library.extraction.EXTRACTION_TIMEOUT_SECONDS", 5):
            result = PypdfDocumentExtractor().extract(payload, media_type="application/pdf")
        self.assertGreater(len(result.segments[0]["text"]), 64000)
        self.assertEqual("pdf:page=1", result.segments[0]["location"]["source_locator"])
        self.assertTrue(result.metadata["original_remains_authoritative"])

    def result_context(self, envelope=None):
        context = Mock(); process = context.Process.return_value
        process.is_alive.return_value = False; process.exitcode = 0
        output = bytearray(4096)
        context.RawArray.return_value = output
        if envelope is not None:
            _publish_result(output, envelope)
        return context, process, output

    def test_completed_shared_result_and_failed_exit_are_distinct(self):
        context, process, _ = self.result_context({'ok': True, 'result': {'segments': [], 'metadata': {}}})
        with patch("src.library.extraction.multiprocessing.get_context", return_value=context):
            PypdfDocumentExtractor().extract(b"synthetic", media_type="application/pdf")
        process.join.assert_called_once(); process.close.assert_called_once()
        context.Queue.assert_not_called()
        process.exitcode = 1
        with patch("src.library.extraction.multiprocessing.get_context", return_value=context):
            with self.assertRaisesRegex(RuntimeError, "unsuccessfully"):
                PypdfDocumentExtractor().extract(b"synthetic", media_type="application/pdf")

    def test_missing_result_start_failure_and_timeout_close_owned_resources(self):
        context, process, _ = self.result_context()
        with patch("src.library.extraction.multiprocessing.get_context", return_value=context):
            with self.assertRaisesRegex(RuntimeError, "without a complete bounded result"):
                PypdfDocumentExtractor().extract(b"synthetic", media_type="application/pdf")
        process.close.assert_called_once()
        context.reset_mock(); process.start.side_effect = OSError("synthetic process start failure")
        with patch("src.library.extraction.multiprocessing.get_context", return_value=context):
            with self.assertRaises(OSError):
                PypdfDocumentExtractor().extract(b"synthetic", media_type="application/pdf")
        process.close.assert_called_once()
        context.reset_mock(); process.start.side_effect = None
        process.is_alive.side_effect = [True, True, True, False]
        with patch("src.library.extraction.multiprocessing.get_context", return_value=context), \
                patch("src.library.extraction.EXTRACTION_TIMEOUT_SECONDS", 0):
            with self.assertRaises(TimeoutError):
                PypdfDocumentExtractor().extract(b"synthetic", media_type="application/pdf")
        process.terminate.assert_called_once(); process.kill.assert_called_once(); process.close.assert_called_once()

    def test_real_partial_transfer_deadline_terminates_owned_writer(self):
        real = multiprocessing.get_context('spawn')
        context = Mock()
        output = real.RawArray('B', 4096)
        context.RawArray.return_value = output
        owned = []
        def process_factory(**kwargs):
            kwargs['target'] = partial_result_worker
            process = real.Process(**kwargs)
            owned.append(process)
            return process
        context.Process.side_effect = process_factory
        began = time.monotonic()
        with patch('src.library.extraction.multiprocessing.get_context', return_value=context), \
                patch('src.library.extraction.EXTRACTION_TIMEOUT_SECONDS', 2):
            with self.assertRaises(TimeoutError):
                PypdfDocumentExtractor().extract(b'synthetic', media_type='application/pdf')
        self.assertLess(time.monotonic() - began, 5)
        self.assertEqual(struct.unpack_from('!Q', memoryview(output).cast('B'))[0], 1024)
        self.assertTrue(owned[0]._closed)

    def test_late_completion_and_late_decode_are_not_success(self):
        for clock in ((0, 0, 2), (0, 0, 0, 2)):
            with self.subTest(clock=clock):
                context, process, _ = self.result_context({'ok': True, 'result': {'segments': [], 'metadata': {}}})
                with patch('src.library.extraction.multiprocessing.get_context', return_value=context), \
                        patch('src.library.extraction.EXTRACTION_TIMEOUT_SECONDS', 1), \
                        patch('src.library.extraction.time.monotonic', side_effect=clock):
                    with self.assertRaises(TimeoutError):
                        PypdfDocumentExtractor().extract(b'synthetic', media_type='application/pdf')
                process.close.assert_called_once()

    def test_missing_oversized_malformed_and_error_results_never_succeed(self):
        for kind in ('oversized', 'malformed-json', 'wrong-envelope', 'wrong-result', 'worker-error'):
            with self.subTest(kind=kind):
                context, process, output = self.result_context()
                expected = RuntimeError
                if kind == 'oversized':
                    struct.pack_into('!Q', output, 0, 2**63)
                elif kind == 'malformed-json':
                    struct.pack_into('!Q', output, 0, 1); output[8:9] = b'{'
                    expected = ValueError
                elif kind == 'wrong-envelope':
                    _publish_result(output, {'ok': 'true'})
                elif kind == 'wrong-result':
                    _publish_result(output, {'ok': True, 'result': []})
                else:
                    _publish_result(output, {'ok': False, 'error': 'fixture failure'})
                    expected = ValueError
                with patch('src.library.extraction.multiprocessing.get_context', return_value=context):
                    with self.assertRaises(expected):
                        PypdfDocumentExtractor().extract(b'synthetic', media_type='application/pdf')
                process.close.assert_called_once()
        with self.assertRaisesRegex(ValueError, 'transfer limit'):
            _publish_result(bytearray(16), {'ok': True, 'result': 'too long'})

    def test_temporary_attachment_is_not_written_without_explicit_keep(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp, FixtureExtractor())
            result = service._retain_requested_media(
                self._attachment(keep=False), conversation_id="conversation-1",
                request_message_id="message-1",
            )
            self.assertEqual(result[0]["library_retention"]["status"], "temporary_not_retained")
            self.assertEqual(list_sources(instance_id="fawkes-one", library_root=tmp), ())

    def test_explicit_keep_registers_extracts_and_retrieves_page_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp, FixtureExtractor())
            result = service._retain_requested_media(
                self._attachment(keep=True), conversation_id="conversation-1",
                request_message_id="message-1",
            )
            retention = result[0]["library_retention"]
            self.assertEqual(retention["status"], "retained")
            self.assertEqual(retention["extraction"]["status"], "searchable")
            sources = list_sources(instance_id="fawkes-one", library_root=tmp)
            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0]["artifact"]["owner_principal_id"],
                             "authenticated-rider:fawkes-one")
            self.assertEqual(sources[0]["artifact"]["provenance"][0]["target_kind"],
                             "temporary_media")
            match = search_extractions("subnetting", instance_id="fawkes-one", library_root=tmp)[0]
            self.assertEqual(match["location"]["page_number"], 142)
            self.assertEqual(list_sources(instance_id="fawkes-two", library_root=tmp), ())
            self.assertGreaterEqual(len(list(Path(tmp).glob("capability-receipts/fawkes-one/*.json"))), 2)

    def test_extraction_failure_preserves_original_and_retry_recovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp, FailingExtractor())
            result = service._retain_requested_media(
                self._attachment(keep=True), conversation_id="conversation-1",
                request_message_id="message-1",
            )
            retention = result[0]["library_retention"]
            self.assertEqual(retention["status"], "retained")
            self.assertEqual(retention["extraction"]["status"], "failed")
            self.assertEqual(len(list_sources(instance_id="fawkes-one", library_root=tmp)), 1)
            self.assertEqual(list_extractions(instance_id="fawkes-one", library_root=tmp), ())
            events = [json.loads(path.read_text()) for path in
                      Path(tmp, "instances", "fawkes-one", "events").glob("*.json")]
            failure = next(item for item in events if item["event_type"] == "library.extraction.failed")
            self.assertTrue(failure["details"]["original_preserved"])
            self.assertTrue(failure["details"]["retryable"])
            service._document_extractor = FixtureExtractor()
            recovered = service.library_extract(retention["source_id"])
            self.assertEqual(recovered["extraction"]["segment_count"], 1)
            self.assertEqual(len(search_extractions(
                "subnetting", instance_id="fawkes-one", library_root=tmp)), 1)

    def test_capability_awareness_selects_live_library_without_granting_write(self):
        awareness = CapabilityAwareness(({
            "name": "library.search", "availability": "live",
            "authorization_mode": "pre_granted", "effects": "read_only",
        }, {
            "name": "library.retain", "availability": "live",
            "authorization_mode": "explicit_confirmation",
            "effects": "durable_library_write",
        }))
        selected = awareness.select(
            "Find the subnetting section in my textbook and explain it.",
            library_evidence=({"source_id": "source-1"},),
        )
        self.assertEqual([item.capability_id for item in selected], ["library.search"])
        self.assertNotIn("library.retain", [item.capability_id for item in selected])

    def test_runtime_consults_the_same_instance_scoped_library_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp, FixtureExtractor())
            service._retain_requested_media(
                self._attachment(keep=True), conversation_id="conversation-1",
                request_message_id="message-1",
            )
            with patch("src.runtime.chat.list_sources", wraps=list_sources), \
                 patch("src.memory.store.list_memories", return_value=()), \
                 patch("src.runtime.chat.build_archive_context", return_value=()), \
                 patch("src.runtime.chat.retrieve_archive_passages", return_value=[]):
                runtime = FawkesChatRuntime(
                    client=Mock(), model="test-model", instance_id="fawkes-one",
                    research_enabled=False, library_root=tmp,
                    presentation_planner=Mock(),
                )
                runtime.semantic_retriever = Mock()
                runtime.semantic_retriever.rank.return_value = []
                context = runtime.build_context(
                    conversation_id="conversation-1", user_message="Teach me subnetting"
                )
            self.assertEqual(len(context["library_passages"]), 1)
            self.assertEqual(context["library_passages"][0]["location"]["page_number"], 142)


if __name__ == "__main__":
    unittest.main()
