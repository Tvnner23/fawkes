"""Versioned local document extraction adapters for retained Library sources.

Original Library blobs remain authoritative.  Extraction output is rebuildable,
page-located derived evidence and never becomes Memory or canonical Archive.
"""

from dataclasses import dataclass
import io
import multiprocessing
import json
import struct
import time


EXTRACTOR_ID = "pypdf-page-text"
EXTRACTOR_VERSION = "1.0"
MAX_PDF_PAGES = 2000
MAX_EXTRACTED_CHARACTERS = 10_000_000
EXTRACTION_TIMEOUT_SECONDS = 90
WORKER_MEMORY_BYTES = 768 * 1024 * 1024
MAX_RESULT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class ExtractionResult:
    segments: tuple[dict, ...]
    metadata: dict


def _extract_pdf(raw_bytes):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw_bytes), strict=False)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs must be unlocked before Library extraction.")
    page_count = len(reader.pages)
    if page_count > MAX_PDF_PAGES:
        raise ValueError(f"PDF has {page_count} pages; the current limit is {MAX_PDF_PAGES}.")
    labels = list(getattr(reader, "page_labels", ()) or ())
    segments, total, empty_pages = [], 0, []
    for index, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if not text:
            empty_pages.append(index + 1)
            continue
        total += len(text)
        if total > MAX_EXTRACTED_CHARACTERS:
            raise ValueError("Extracted PDF text exceeds the current safe processing limit.")
        physical = index + 1
        segments.append({
            "segment_id": f"page-{physical}",
            "text": text,
            "location": {
                "page_number": physical,
                "page_label": labels[index] if index < len(labels) else str(physical),
                "chapter": None,
                "section": None,
                "subsection": None,
                "source_locator": f"pdf:page={physical}",
            },
        })
    if not segments:
        raise ValueError(
            "This PDF has no extractable text. It may be scanned; OCR is not active yet."
        )
    return {
        "segments": segments,
        "metadata": {
            "physical_page_count": page_count,
            "extracted_page_count": len(segments),
            "empty_or_image_only_pages": empty_pages,
            "coverage": "complete" if not empty_pages else "partial",
            "page_label_source": "pdf_page_labels_or_physical_fallback",
            "original_remains_authoritative": True,
        },
    }


def _publish_result(output, envelope):
    encoded = json.dumps(envelope, ensure_ascii=False).encode('utf-8')
    if len(encoded) > len(output) - 8:
        raise ValueError('PDF extraction result exceeds the bounded transfer limit.')
    view = memoryview(output).cast('B')
    view[8:8+len(encoded)] = encoded
    # Publish length last. The parent also requires a successful child exit,
    # so partial writes never constitute a completed result.
    struct.pack_into('!Q', view, 0, len(encoded))


def _worker(raw_bytes, output):
    try:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (WORKER_MEMORY_BYTES, WORKER_MEMORY_BYTES))
        except (ImportError, OSError, ValueError):
            # The adapter contract remains portable; operating systems without
            # RLIMIT_AS still retain page/count/output bounds and a timeout.
            pass
        _publish_result(output, {"ok": True, "result": _extract_pdf(raw_bytes)})
    except BaseException as exc:
        _publish_result(output, {"ok": False, "error": str(exc)[:2048], "error_type": type(exc).__name__})


class PypdfDocumentExtractor:
    """Local, page-aware PDF extraction behind a provider-neutral interface."""

    extractor_id = EXTRACTOR_ID
    extractor_version = EXTRACTOR_VERSION

    def extract(self, raw_bytes, *, media_type):
        if media_type != "application/pdf":
            raise ValueError("Page-aware extraction currently supports PDF sources only.")
        context = multiprocessing.get_context("spawn")
        # Anonymous shared memory, not a disk temporary or blocking framed pipe.
        # Queue.get(timeout) cannot bound a partly received frame. Waiting only
        # on the process exit lets the existing deadline govern the full write.
        output = context.RawArray('B', MAX_RESULT_BYTES + 8)
        process = context.Process(target=_worker, args=(raw_bytes, output), daemon=True)
        started = False
        deadline = time.monotonic() + EXTRACTION_TIMEOUT_SECONDS
        try:
            process.start()
            started = True
            process.join(max(0, deadline - time.monotonic()))
            if process.is_alive() or time.monotonic() >= deadline:
                raise TimeoutError("PDF extraction exceeded the safe processing time limit.")
            if process.exitcode != 0:
                raise RuntimeError("PDF extraction worker exited unsuccessfully.")
            view = memoryview(output).cast('B')
            length = struct.unpack_from('!Q', view)[0]
            if not 0 < length <= MAX_RESULT_BYTES or length > len(view) - 8:
                raise RuntimeError("PDF extraction worker exited without a complete bounded result.")
            envelope = json.loads(bytes(view[8:8+length]))
            if time.monotonic() >= deadline:
                raise TimeoutError("PDF extraction exceeded the safe processing time limit.")
        finally:
            if started and process.is_alive():
                process.terminate()
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join(5)
            if not started or not process.is_alive():
                process.close()
        if not isinstance(envelope, dict) or type(envelope.get('ok')) is not bool:
            raise RuntimeError('PDF extraction worker returned a malformed result.')
        if not envelope['ok']:
            raise ValueError(envelope.get("error") or "PDF extraction failed.")
        result = envelope.get("result")
        if (not isinstance(result, dict) or not isinstance(result.get('segments'), list)
                or not isinstance(result.get('metadata'), dict)):
            raise RuntimeError('PDF extraction worker returned a malformed result.')
        return ExtractionResult(tuple(result["segments"]), dict(result["metadata"]))


def extractor_available():
    try:
        import pypdf  # noqa: F401
        return True
    except ImportError:
        return False
