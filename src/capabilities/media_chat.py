"""Validated, ephemeral Chat media inputs for provider-neutral reasoning."""

import base64
import binascii
import hashlib
import io
import os
import re

from src.capabilities.core import CapabilityDefinition
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract
from src.library.artifacts import source_artifact_envelope


MAX_MEDIA_ITEMS = 4
MAX_MEDIA_ITEM_BYTES = 16 * 1024 * 1024
MAX_MEDIA_TOTAL_BYTES = 16 * 1024 * 1024
ALLOWED_MEDIA = {
    "image/jpeg": ("image", b"\xff\xd8\xff"),
    "image/png": ("image", b"\x89PNG\r\n\x1a\n"),
    "image/webp": ("image", b"RIFF"),
    "image/gif": ("image", b"GIF8"),
    "application/pdf": ("pdf", b"%PDF-"),
    "audio/mpeg": ("audio", (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")),
    "audio/wav": ("audio", b"RIFF"),
    "audio/x-wav": ("audio", b"RIFF"),
    "audio/flac": ("audio", b"fLaC"),
    "audio/ogg": ("audio", b"OggS"),
    "audio/webm": ("audio", b"\x1aE\xdf\xa3"),
    "audio/mp4": ("audio", b"\x00\x00\x00"),
    "audio/x-m4a": ("audio", b"\x00\x00\x00"),
}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")

MEDIA_CHAT_DEFINITION = CapabilityDefinition(
    name="media.chat_analyze", version="1.0",
    description="Analyze rider-attached images, screenshots, and PDFs ephemerally in Chat.",
    permissions=("rider_media.external_analyze",), effect="ephemeral_evidence",
    modalities=MultimodalCapabilityContract(
        input_modalities=("text", "image", "screenshot", "pdf", "audio"),
        output_modalities=("text", "diagram", "chart"),
    ),
    authority=AuthorityContract(
        actions=("read", "analyze", "create"), execution_boundary="external_read",
        authorization_mode="task_request",
    ),
    privacy_handling="rider_visible_ephemeral_external_processing_not_library",
    features=("image_analysis", "screenshot_analysis", "pdf_analysis", "cross_modal_reasoning", "temporary_artifact_lifecycle", "provider_transmission_receipt"),
    display_name="Temporary media analysis",
    appropriate_use=("rider attaches an image, screenshot, or PDF for analysis", "combine supplied media with text or authorized research"),
    inappropriate_use=("no media was supplied", "silently retaining casual media as Library material"),
    limitations=("supported allowlisted formats only", "maximum four files and 16 MB total", "temporary external-provider analysis"),
    presentation_options=("text", "table", "diagram", "chart"),
    dependencies=("rider attachment", "configured multimodal provider support"),
    provenance_requirements=("media digest", "filename and MIME type", "page or image-region locator when practical", "untrusted-content boundary"),
)

AUDIO_TRANSCRIPTION_DEFINITION = CapabilityDefinition(
    name="media.audio_transcribe", version="1.0",
    description="Transcribe rider-attached lecture or conversational audio for reasoning with timestamped evidence.",
    permissions=("rider_media.external_analyze",), effect="ephemeral_evidence",
    modalities=MultimodalCapabilityContract(
        input_modalities=("audio",), output_modalities=("text",),
    ),
    authority=AuthorityContract(
        actions=("read", "analyze", "create"), execution_boundary="external_read",
        authorization_mode="task_request",
    ),
    privacy_handling="rider_visible_ephemeral_external_transcription_not_library",
    features=("transcription", "timestamped_evidence", "audio_question_answering"),
    display_name="Audio transcription and reasoning",
    appropriate_use=("rider attaches supported audio", "lecture summary", "timestamped question answering"),
    inappropriate_use=("no audio was supplied", "claiming speaker identification when unsupported"),
    limitations=("transcription quality depends on source audio", "speaker diarization is not currently guaranteed", "audio remains temporary"),
    dependencies=("configured transcription provider", "supported audio attachment"),
    provenance_requirements=("audio digest", "timestamp segments", "transcription derivation", "untrusted-content boundary"),
)


def validate_chat_media(items, *, instance_id="ephemeral-session", owner_principal_id="authenticated-rider"):
    """Decode allowlisted media without writing it to disk or Library."""
    if items is None:
        return ()
    if not isinstance(items, list) or len(items) > MAX_MEDIA_ITEMS:
        raise ValueError(f"Attach no more than {MAX_MEDIA_ITEMS} files.")
    result, total = [], 0
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("Invalid attachment.")
        mime = raw.get("mime_type")
        if mime not in ALLOWED_MEDIA:
            raise ValueError("Only supported image, PDF, and audio attachments are accepted.")
        encoded = raw.get("data")
        if not isinstance(encoded, str):
            raise ValueError("Attachment data is missing.")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Attachment data is invalid.") from exc
        if not data or len(data) > MAX_MEDIA_ITEM_BYTES:
            raise ValueError("Each attachment must be 16 MB or smaller.")
        total += len(data)
        if total > MAX_MEDIA_TOTAL_BYTES:
            raise ValueError("Attachments must total 16 MB or less.")
        modality, signature = ALLOWED_MEDIA[mime]
        signatures = signature if isinstance(signature, tuple) else (signature,)
        if not any(data.startswith(item) for item in signatures):
            raise ValueError("Attachment content does not match its declared type.")
        if mime == "image/webp" and data[8:12] != b"WEBP":
            raise ValueError("Attachment content is not a valid WebP image.")
        if mime in {"audio/wav", "audio/x-wav"} and data[8:12] != b"WAVE":
            raise ValueError("Attachment content is not a valid WAV file.")
        if mime in {"audio/mp4", "audio/x-m4a"} and b"ftyp" not in data[:32]:
            raise ValueError("Attachment content is not a valid M4A audio file.")
        name = _SAFE_NAME.sub("_", str(raw.get("name") or "attachment"))[:120]
        digest = hashlib.sha256(data).hexdigest()
        privacy = raw.get("privacy", "potentially_private")
        if privacy not in {"standard", "potentially_private", "highly_private"}:
            raise ValueError("Attachment privacy classification is invalid.")
        source_id = f"media:{digest}"
        keep_in_library = raw.get("keep_in_library", False)
        if not isinstance(keep_in_library, bool):
            raise ValueError("Keep in Library must be true or false.")
        retention_title = str(raw.get("retention_title") or name).strip()[:200]
        if keep_in_library and not retention_title:
            raise ValueError("A title is required to keep an attachment in Library.")
        retention = {
            "decision": "temporary_only", "policy": "chat_ephemeral",
            "eligible_for_library": True, "requires_explicit_keep": True,
            "automatic_library_retention": False,
        }
        artifact = source_artifact_envelope(
            artifact_id=source_id, instance_id=instance_id,
            owner_principal_id=owner_principal_id, artifact_kind="temporary_media",
            source_domain="rider_chat_attachment", evidence_era="native_phoenix_history",
            sha256=digest, media_type=mime, storage_reference=None,
            lifecycle_state="validated_temporary",
            privacy={"classification": privacy, "assigned_by": "rider",
                     "rider_visible": True, "revisable": True},
            trust="untrusted_user_content", retention=retention,
            actor={"actor_type": "rider", "principal_id": owner_principal_id},
            resource={"size_bytes": len(data), "quota_class": "chat_ephemeral"},
            identifiers={"session_id": None, "correlation_id": None, "causation_id": None,
                         "environment_id": None, "device_id": None, "sensor_id": None,
                         "actuator_id": None, "embodiment_id": None,
                         "sandbox_branch_id": None},
        )
        result.append({
            "source_id": source_id, "name": name, "mime_type": mime,
            "modality": modality, "bytes": data, "sha256": digest,
            "retention": "ephemeral_not_retained", "trust": "untrusted_user_content",
            "privacy": {
                "classification": privacy,
                "assigned_by": "rider", "rider_visible": True, "revisable": True,
            },
            "keep_in_library": keep_in_library,
            "retention_title": retention_title,
            "artifact": artifact,
        })
    return tuple(result)


def provider_content_blocks(text, attachments):
    """Build Responses input blocks; provider details stop at this adapter."""
    blocks = [{"type": "input_text", "text": text}]
    for item in attachments:
        if item["modality"] == "audio":
            continue
        encoded = base64.b64encode(item["bytes"]).decode("ascii")
        data_url = f"data:{item['mime_type']};base64,{encoded}"
        if item["modality"] == "image":
            blocks.append({"type": "input_image", "image_url": data_url, "detail": "auto"})
        else:
            blocks.append({"type": "input_file", "filename": item["name"], "file_data": data_url})
    return blocks


class OpenAIAudioTranscriber:
    """Provider adapter producing an ephemeral transcript with time locators."""

    def __init__(self, *, client, model=None):
        self.client = client
        self.model = model or os.getenv("FAWKES_TRANSCRIPTION_MODEL", "whisper-1")

    def transcribe(self, item):
        stream = io.BytesIO(item["bytes"])
        stream.name = item["name"]
        result = self.client.audio.transcriptions.create(
            model=self.model,
            file=stream,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
            timeout=float(os.getenv("FAWKES_MEDIA_CALL_TIMEOUT", "120")),
        )
        text = getattr(result, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Audio provider returned an empty transcript")
        segments = []
        for segment in getattr(result, "segments", ()) or ():
            start = getattr(segment, "start", None)
            end = getattr(segment, "end", None)
            segment_text = getattr(segment, "text", None)
            if start is None or end is None or not segment_text:
                continue
            segments.append({
                "start_seconds": float(start), "end_seconds": float(end),
                "text": str(segment_text).strip(),
            })
        return {"text": text.strip(), "segments": segments, "model": self.model}


def attach_audio_transcripts(attachments, *, transcriber):
    """Return new in-memory records; never write audio or transcripts locally."""
    enriched = []
    for item in attachments:
        copy = dict(item)
        if item["modality"] == "audio":
            copy["transcript"] = transcriber.transcribe(item)
        enriched.append(copy)
    return tuple(enriched)


def media_reasoning_context(attachments):
    sections = []
    for item in attachments:
        transcript = item.get("transcript")
        if not transcript:
            continue
        timed = "\n".join(
            f"[{part['start_seconds']:.1f}s–{part['end_seconds']:.1f}s] {part['text']}"
            for part in transcript["segments"]
        )
        sections.append(
            f"Untrusted rider audio: {item['name']} ({item['source_id']})\n"
            f"Transcript:\n{timed or transcript['text']}"
        )
    return "\n\n".join(sections)


def public_media_references(attachments):
    references = [{k: item[k] for k in (
        "source_id", "name", "mime_type", "modality", "sha256", "retention", "trust", "privacy", "artifact"
    )} for item in attachments]
    for reference, item in zip(references, attachments):
        if item.get("capability_receipt_id"):
            reference["capability_receipt_id"] = item["capability_receipt_id"]
        if item.get("library_retention"):
            reference["library_retention"] = dict(item["library_retention"])
        transcript = item.get("transcript")
        if transcript:
            reference["derivation"] = "external_audio_transcription"
            reference["transcription_model"] = transcript["model"]
            reference["locators"] = [
                {"kind": "audio_segment", "start_seconds": part["start_seconds"], "end_seconds": part["end_seconds"]}
                for part in transcript["segments"]
            ]
            reference["transcript_retention"] = "ephemeral_not_retained"
    return references
