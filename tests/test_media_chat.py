import base64
import unittest

from src.capabilities.media_chat import (
    AUDIO_TRANSCRIPTION_DEFINITION,
    MEDIA_CHAT_DEFINITION,
    attach_audio_transcripts,
    media_reasoning_context,
    provider_content_blocks,
    public_media_references,
    validate_chat_media,
)


class ChatMediaTests(unittest.TestCase):
    def test_image_is_validated_and_ephemeral(self):
        payload = base64.b64encode(b"\x89PNG\r\n\x1a\ncontent").decode()
        media = validate_chat_media([{
            "name": "diagram.png", "mime_type": "image/png", "data": payload,
            "privacy": "potentially_private",
        }])
        self.assertEqual(media[0]["modality"], "image")
        self.assertEqual(media[0]["retention"], "ephemeral_not_retained")
        self.assertEqual(media[0]["artifact"]["lifecycle"]["state"], "validated_temporary")
        self.assertTrue(media[0]["artifact"]["retention"]["requires_explicit_keep"])
        self.assertNotIn("bytes", public_media_references(media)[0])
        blocks = provider_content_blocks("Explain this", media)
        self.assertEqual(blocks[1]["type"], "input_image")
        self.assertTrue(blocks[1]["image_url"].startswith("data:image/png;base64,"))

    def test_pdf_uses_file_input_without_local_persistence(self):
        payload = base64.b64encode(b"%PDF-1.7\nexample").decode()
        media = validate_chat_media([{
            "name": "chapter.pdf", "mime_type": "application/pdf", "data": payload,
        }])
        block = provider_content_blocks("Teach me", media)[1]
        self.assertEqual(block["type"], "input_file")
        self.assertEqual(block["filename"], "chapter.pdf")

    def test_type_spoof_and_oversized_item_count_are_rejected(self):
        bad = base64.b64encode(b"not a png").decode()
        with self.assertRaises(ValueError):
            validate_chat_media([{"mime_type": "image/png", "data": bad}])
        with self.assertRaises(ValueError):
            validate_chat_media([{}] * 5)

    def test_manifest_discloses_external_task_authorized_boundary(self):
        manifest = MEDIA_CHAT_DEFINITION.public_manifest()
        self.assertEqual(manifest["authorization_mode"], "task_request")
        self.assertEqual(manifest["execution_boundary"], "external_read")
        self.assertIn("image", manifest["input_modalities"])
        self.assertIn("audio", manifest["input_modalities"])
        self.assertEqual(
            AUDIO_TRANSCRIPTION_DEFINITION.public_manifest()["authorization_mode"],
            "task_request",
        )

    def test_audio_transcript_is_reasoning_evidence_but_not_retained_in_receipt(self):
        wav = b"RIFF" + (32).to_bytes(4, "little") + b"WAVE" + b"audio"
        media = validate_chat_media([{
            "name": "lecture.wav", "mime_type": "audio/wav",
            "data": base64.b64encode(wav).decode(),
        }])

        class Transcriber:
            def transcribe(self, item):
                return {
                    "text": "Subnetting starts here.", "model": "fake-transcriber",
                    "segments": [{
                        "start_seconds": 12.0, "end_seconds": 18.5,
                        "text": "Subnetting starts here.",
                    }],
                }

        enriched = attach_audio_transcripts(media, transcriber=Transcriber())
        self.assertIn("[12.0s–18.5s]", media_reasoning_context(enriched))
        reference = public_media_references(enriched)[0]
        self.assertEqual(reference["locators"][0]["kind"], "audio_segment")
        self.assertEqual(reference["transcript_retention"], "ephemeral_not_retained")
        self.assertNotIn("transcript", reference)
        self.assertNotIn("bytes", reference)


if __name__ == "__main__":
    unittest.main()
