"""Shared application boundary for every Fawkes chat interface."""

import os
from pathlib import Path
import threading
import time
import uuid

from src.conversations import create_conversation, get_latest_conversation
from src.instances import get_or_create_default_instance
from src.memory.archive_context import build_archive_context
from src.memory.archive_retrieval import ensure_archive_index
from src.memory.ledger import discover_candidate, update_work_item
from src.memory.worker import evaluate_batch, apply_accepted_batch
from src.memory.semantic_provider import ModelSemanticMemoryEvaluator
from src.memory.development_observations import (
    add_observation_evidence,
    create_development_observation,
    get_development_observation,
    list_development_observations,
    observation_history,
    revise_observation,
)
from src.memory.development_dashboard import build_development_dashboard
from src.memory.development_store import review_development_proposal
from src.memory.review_feedback import record_context_retrieval_feedback
from src.runtime.chat import FawkesChatRuntime
from src.runtime.evidence_transmission import ProviderRoute
from src.runtime.production_planner_builder import ServedProductionPlannerBuilder
from src.runtime.context_receipts import build_context_inspector, load_context_receipt, save_context_receipt
from src.runtime.retrieval_replay import load_flight, record_live_flight
from src.runtime.codex_development_handoff import run_codex_development_handoff
from src.runtime.codex_development_campaign import CodexDevelopmentCampaign
from src.runtime.persistence import persist_live_message
from src.capabilities.media_chat import (
    AUDIO_TRANSCRIPTION_DEFINITION, MEDIA_CHAT_DEFINITION,
    OpenAIAudioTranscriber,
    validate_chat_media, public_media_references,
)
from src.capabilities.core import (
    CapabilityExecutor, CapabilityRegistry, CapabilityRequest,
    enforce_capability_authority,
)
from src.capabilities.provider_privacy import record_provider_transmission
from src.capabilities.provider_privacy import ephemeral_provider_artifact
from src.capabilities.library import LIBRARY_RETAIN_DEFINITION, LIBRARY_EXTRACT_DEFINITION
from src.library.artifacts import require_id


class ChatServiceError(RuntimeError):
    """A safe, user-facing failure at the chat application boundary."""

    def __init__(self, message, *, code="chat_unavailable"):
        super().__init__(message)
        self.code = code


class FawkesChatService:
    """Coordinate durable turns while delegating cognition to the runtime.

    This class owns no conversation, memory, or Phoenix data. It only composes
    the existing instance, Archive, Memory ledger, runtime, and receipt APIs.
    """

    def __init__(
        self, *, phoenix=None, runtime=None, title="Fawkes Chat", research_capability=None,
        audio_transcriber=None,
        provider_receipt_dir=None,
        capability_receipt_dir=None,
        library_root=None,
        document_extractor=None,
        inherited_history_root=None,
        archive_index_path=None,
        archive_meta_dir=None,
        archive_raw_dir=None,
    ):
        self.phoenix = phoenix or get_or_create_default_instance()
        self.instance_id = self.phoenix["instance_id"]
        if runtime is None:
            retrieval_path = os.getenv("FAWKES_RETRIEVAL_PATH", "planner")
            model = os.getenv("FAWKES_CHAT_MODEL", "gpt-5.6-luna")
            planner_builder = None
            if retrieval_path == "planner":
                route = ProviderRoute(
                    os.getenv("FAWKES_CHAT_PROVIDER_POLICY", "private-chat-policy"),
                    os.getenv("FAWKES_CHAT_PROVIDER_CLASS", "openai-compatible"),
                    model, os.getenv("FAWKES_CHAT_ROUTE_VERSION", "1"),
                )
                planner_builder = ServedProductionPlannerBuilder(
                    instance_id=self.instance_id, provider_route=route.public(),
                    archive_index_path=archive_index_path,
                    archive_meta_dir=archive_meta_dir, library_root=library_root,
                )
            runtime = FawkesChatRuntime(
                instance_id=self.instance_id,
                include_unscoped_memories=True,
                library_root=library_root,
                retrieval_path=retrieval_path,
                planner_context_builder=planner_builder,
            )
        self.runtime = runtime
        self.title = title
        self._research_capability = research_capability
        self._audio_transcriber = audio_transcriber
        self._provider_receipt_dir = provider_receipt_dir
        self._capability_receipt_dir = (
            capability_receipt_dir
            if capability_receipt_dir is not None
            else (Path(provider_receipt_dir).parent / "capability_receipts"
                  if provider_receipt_dir is not None else None)
        )
        self._library_root = library_root
        self._document_extractor = document_extractor
        self._inherited_history_root = inherited_history_root
        self._archive_index_path = archive_index_path
        self._archive_meta_dir = archive_meta_dir
        self._archive_raw_dir = archive_raw_dir
        self._turn_lock = threading.Lock()
        self._memory_worker_lock = threading.Lock()
        self._memory_worker_enabled = os.getenv(
            "FAWKES_MEMORY_WORKER_ENABLED", "1"
        ).lower() not in {"0", "false", "no", "off"}
        ensure_archive_index(instance_id=self.instance_id, include_unscoped=True)

    def _process_memory_queue(self):
        """Advance durable candidates without delaying Chat or hiding failures."""
        if not self._memory_worker_lock.acquire(blocking=False):
            return
        try:
            retriever = getattr(self.runtime, "semantic_retriever", None)
            provider = getattr(retriever, "provider", None)
            if provider is None:
                return
            from src.memory.ledger import list_work_items
            candidates = [item for item in list_work_items(instance_id=self.instance_id)
                          if item.get("status") in {"discovered", "queued", "failed_retryable",
                                                    "failed_evaluation_retryable", "failed_consolidation_retryable"}]
            if not candidates:
                return
            batch_content = "\n".join(
                f"{item.get('work_item_id')}:{item.get('candidate_content') or ''}"
                for item in candidates
            )
            artifact = ephemeral_provider_artifact(
                instance_id=self.instance_id, content=batch_content,
                artifact_kind="memory_triage_batch",
                source_domain="native_phoenix_conversation_candidates",
            )
            receipt_args = dict(
                instance_id=self.instance_id, artifact=artifact,
                capability_id="memory.triage",
                provider_class="configured_semantic_memory_adapter",
                purpose="configured_background_memory_candidate_triage",
                authorization_source={"mode": "pre_granted_runtime_policy",
                                      "policy": "FAWKES_MEMORY_WORKER_ENABLED"},
                transformations=("candidate_assessment", "evidence_reconciliation"),
                correlation_id=f"memory-batch:{candidates[0]['work_item_id']}",
                receipt_dir=self._provider_receipt_dir,
            )
            record_provider_transmission(status="authorized", **receipt_args)
            limit = max(1, min(10, int(os.getenv("FAWKES_MEMORY_WORKER_BATCH", "3"))))
            try:
                evaluate_batch(
                    instance_id=self.instance_id,
                    evaluator=ModelSemanticMemoryEvaluator(provider),
                    limit=limit,
                )
                apply_accepted_batch(
                    instance_id=self.instance_id,
                    limit=limit,
                    matcher=provider,
                    semantic_retriever=retriever,
                    include_unscoped=self.runtime.include_unscoped_memories,
                )
            except Exception as exc:
                record_provider_transmission(
                    status="failed", failure_code=type(exc).__name__, **receipt_args
                )
                raise
            record_provider_transmission(status="completed", **receipt_args)
        finally:
            self._memory_worker_lock.release()

    def _schedule_memory_queue(self):
        if not self._memory_worker_enabled:
            return
        retriever = getattr(self.runtime, "semantic_retriever", None)
        if getattr(retriever, "provider", None) is None:
            return
        threading.Thread(
            target=self._process_memory_queue,
            name="fawkes-memory-triage",
            daemon=True,
        ).start()

    def _transcribe_audio(self, attachments, *, conversation_id, request_message_id):
        transcriber = self._audio_transcriber or OpenAIAudioTranscriber(
            client=self.runtime.client
        )
        enriched = []
        for item in attachments:
            copy = dict(item)
            if item["modality"] == "audio":
                def transcribe_with_receipt(request, source=item):
                    receipt_args = dict(
                        instance_id=self.instance_id, artifact=source["artifact"],
                        capability_id=AUDIO_TRANSCRIPTION_DEFINITION.name,
                        provider_class="configured_audio_transcription_adapter",
                        purpose="rider_requested_audio_transcription",
                        authorization_source={"mode": "task_request", "request_message_id": request_message_id},
                        correlation_id=request_message_id,
                        receipt_dir=self._provider_receipt_dir,
                    )
                    record_provider_transmission(status="authorized", **receipt_args)
                    try:
                        transcript = transcriber.transcribe(source)
                    except Exception as exc:
                        record_provider_transmission(
                            status="failed", failure_code=type(exc).__name__,
                            **receipt_args,
                        )
                        raise
                    receipt = record_provider_transmission(
                        status="completed", **receipt_args,
                    )
                    return {"transcript": transcript,
                            "result_references": [source["source_id"], receipt["transmission_id"]]}
                registry = CapabilityRegistry()
                registry.register(
                    AUDIO_TRANSCRIPTION_DEFINITION,
                    transcribe_with_receipt,
                )
                result = CapabilityExecutor(
                    registry, receipt_dir=self._capability_receipt_dir
                ).execute(
                    CapabilityRequest(
                        instance_id=self.instance_id,
                        capability=AUDIO_TRANSCRIPTION_DEFINITION.name,
                        arguments={"source_id": item["source_id"]},
                        requested_by="rider", conversation_id=conversation_id,
                        request_message_id=request_message_id, task_authorized=True,
                    ),
                    granted_permissions=("rider_media.external_analyze",),
                )
                copy["transcript"] = result["transcript"]
                copy["capability_receipt_id"] = result["capability_receipt_id"]
            enriched.append(copy)
        return tuple(enriched)

    def _retain_requested_media(self, attachments, *, conversation_id, request_message_id):
        """Promote only rider-confirmed attachments into Library.

        Retention and extraction are separate receipts. A successful immutable
        retention remains truthful even when rebuildable extraction fails.
        """
        from src.library.artifacts import lineage_edge, retention_intent
        from src.library.extraction import PypdfDocumentExtractor
        from src.library.store import (
            instance_library_paths, record_extraction_failure, register_source,
            save_extraction,
        )

        paths = instance_library_paths(self.instance_id, library_root=self._library_root)
        extractor = self._document_extractor or PypdfDocumentExtractor()
        enriched = []
        for source in attachments:
            item = dict(source)
            if not item.get("keep_in_library"):
                item["library_retention"] = {
                    "status": "temporary_not_retained",
                    "policy": "not_durably_stored_released_after_request_not_securely_zeroized",
                    "requires_explicit_keep": True,
                }
                enriched.append(item)
                continue
            principal = f"authenticated-rider:{self.instance_id}"
            registry = CapabilityRegistry()

            def retain(_request, media=item):
                retained = register_source(
                    media["bytes"], title=media["retention_title"],
                    media_type=media["mime_type"], original_filename=media["name"],
                    instance_id=self.instance_id,
                    retention_intent=retention_intent(
                        actor_type="rider", principal_id=principal
                    ),
                    privacy=media["privacy"]["classification"],
                    source_domain="rider_chat_attachment",
                    provenance=(lineage_edge("derived_from", media["source_id"], target_kind="temporary_media"),),
                    correlation_id=request_message_id,
                    originals_dir=paths["originals"], sources_dir=paths["sources"],
                    events_dir=paths["events"],
                )
                return {"retained": retained, "result_references": [retained["source_id"]]}

            registry.register(LIBRARY_RETAIN_DEFINITION, retain)
            try:
                retained_result = CapabilityExecutor(
                    registry, receipt_dir=self._capability_receipt_dir
                ).execute(
                    CapabilityRequest(
                        instance_id=self.instance_id,
                        capability=LIBRARY_RETAIN_DEFINITION.name,
                        arguments={"temporary_source_id": item["source_id"],
                                   "sha256": item["sha256"], "title": item["retention_title"]},
                        requested_by="rider", conversation_id=conversation_id,
                        request_message_id=request_message_id,
                        task_authorized=True, explicitly_confirmed=True,
                    ),
                    granted_permissions=("library.retain",),
                )
                retained = retained_result["retained"]
                try:
                    self.runtime.capability_catalog.set_health(
                        LIBRARY_RETAIN_DEFINITION.name, "live",
                        reason="most recent explicit rider retention completed",
                    )
                except (AttributeError, ValueError):
                    pass
                retention = {
                    "status": "retained",
                    "source_id": retained["source_id"],
                    "title": retained["title"],
                    "retention_work_id": retained["retention_work_id"],
                    "retention_capability_receipt_id": retained_result["capability_receipt_id"],
                    "replayed": retained.get("_replayed", False),
                    "extraction": {"status": "not_applicable"},
                }
                if item["mime_type"] == "application/pdf":
                    extraction_registry = CapabilityRegistry()

                    def extract(_request):
                        result = extractor.extract(item["bytes"], media_type=item["mime_type"])
                        record = save_extraction(
                            retained["source_id"], result.segments,
                            extractor=extractor.extractor_id,
                            extractor_version=extractor.extractor_version,
                            instance_id=self.instance_id, sources_dir=paths["sources"],
                            extractions_dir=paths["extractions"], events_dir=paths["events"],
                            metadata=result.metadata,
                        )
                        return {"extraction": record,
                                "result_references": [record["extraction_id"], retained["source_id"]]}

                    extraction_registry.register(LIBRARY_EXTRACT_DEFINITION, extract)
                    try:
                        extracted_result = CapabilityExecutor(
                            extraction_registry, receipt_dir=self._capability_receipt_dir
                        ).execute(
                            CapabilityRequest(
                                instance_id=self.instance_id,
                                capability=LIBRARY_EXTRACT_DEFINITION.name,
                                arguments={"source_id": retained["source_id"],
                                           "source_sha256": retained["sha256"]},
                                requested_by="runtime", conversation_id=conversation_id,
                                request_message_id=request_message_id, task_authorized=True,
                            ),
                            granted_permissions=("library.extract",),
                        )
                        extraction = extracted_result["extraction"]
                        try:
                            self.runtime.capability_catalog.set_health(
                                LIBRARY_EXTRACT_DEFINITION.name, "live",
                                reason="most recent retained PDF extraction completed",
                            )
                        except (AttributeError, ValueError):
                            pass
                        retention["extraction"] = {
                            "status": "searchable",
                            "extraction_id": extraction["extraction_id"],
                            "extractor": extraction["extractor"],
                            "extractor_version": extraction["extractor_version"],
                            "segment_count": len(extraction["segments"]),
                            "metadata": extraction.get("metadata", {}),
                            "capability_receipt_id": extracted_result["capability_receipt_id"],
                        }
                    except Exception as exc:
                        record_extraction_failure(
                            retained["source_id"], extractor=extractor.extractor_id,
                            extractor_version=extractor.extractor_version,
                            error_code=(type(exc.__cause__).__name__ if exc.__cause__ else type(exc).__name__),
                            instance_id=self.instance_id, events_dir=paths["events"],
                            correlation_id=request_message_id,
                        )
                        retention["extraction"] = {
                            "status": "failed",
                            "error_code": type(exc).__name__,
                            "message": str(exc),
                            "retryable": True,
                        }
                        try:
                            self.runtime.capability_catalog.set_health(
                                LIBRARY_EXTRACT_DEFINITION.name, "degraded",
                                reason="most recent retained PDF extraction failed; original is preserved for retry",
                                failure_code=(type(exc.__cause__).__name__ if exc.__cause__ else type(exc).__name__),
                            )
                        except (AttributeError, ValueError):
                            pass
                item["library_retention"] = retention
            except Exception as exc:
                try:
                    self.runtime.capability_catalog.set_health(
                        LIBRARY_RETAIN_DEFINITION.name, "degraded",
                        reason="most recent explicit rider retention failed",
                        failure_code=(type(exc.__cause__).__name__ if exc.__cause__ else type(exc).__name__),
                    )
                except (AttributeError, ValueError):
                    pass
                item["library_retention"] = {
                    "status": "failed", "error_code": type(exc).__name__,
                    "message": str(exc), "retryable": True,
                }
            enriched.append(item)
        return tuple(enriched)

    def research(self, payload):
        """Run authenticated, instance-scoped research outside Memory/Archive."""
        if self._research_capability is None:
            from src.capabilities.web_research import WebResearchCapability

            self._research_capability = WebResearchCapability()
        try:
            return self._research_capability.run(
                instance_id=self.instance_id,
                query=payload.get("query"),
                requested_by="rider",
                conversation_id=payload.get("conversation_id"),
                request_message_id=payload.get("request_message_id"),
                allowed_domains=payload.get("allowed_domains", ()),
                task_authorized=True,
            )
        except ValueError as exc:
            raise ChatServiceError(str(exc), code="invalid_research_request") from exc
        except PermissionError as exc:
            raise ChatServiceError(str(exc), code="capability_not_permitted") from exc
        except Exception as exc:
            raise ChatServiceError(
                "Web research is unavailable right now.", code="research_unavailable"
            ) from exc

    def capabilities(self):
        """Provider-neutral runtime discovery for web and future native clients."""
        return {
            "instance_id": self.instance_id,
            "capabilities": self.runtime.capability_context(),
            "presentation": {
                "envelope_versions": [1, 2],
                "fallback": "canonical_text",
            },
        }

    def sound_settings(self):
        from src.capabilities.event_audio import public_sound_settings
        return public_sound_settings(self.instance_id)

    def presence_profile(self):
        from src.capabilities.phoenix_presence import PresenceProfileStore
        return PresenceProfileStore(self.instance_id, phoenix_name=self.phoenix["name"]).public()

    def presence_asset_path(self, filename):
        """Resolve only this Phoenix's currently registered, digest-validated asset."""
        from src.capabilities.phoenix_presence import PresenceProfileStore, validate_asset
        store = PresenceProfileStore(self.instance_id, phoenix_name=self.phoenix["name"])
        profile = store.load()
        asset = profile.get("asset")
        if not asset or filename != asset.get("filename") or Path(filename).name != filename:
            return None
        validate_asset(asset, asset_root=store.asset_root)
        target = store.asset_root / filename
        return target if target.is_file() else None

    def update_presence_preferences(self, payload):
        from src.capabilities.phoenix_presence import PresenceProfileStore
        profile = PresenceProfileStore(
            self.instance_id, phoenix_name=self.phoenix["name"]
        ).update_preferences(
            payload, actor_principal_id=f"authenticated-rider:{self.instance_id}"
        )
        health = PresenceProfileStore(
            self.instance_id, phoenix_name=self.phoenix["name"]
        ).public()["health"]
        try:
            self.runtime.capability_catalog.set_health(
                "presentation.phoenix_presence", health["status"],
                reason=health["reason"], failure_code=health.get("failure_code"),
            )
        except (AttributeError, ValueError):
            pass
        return self.presence_profile()

    def library_catalog(self):
        from src.library.store import list_extractions, list_sources
        sources = list_sources(instance_id=self.instance_id, library_root=self._library_root)
        return {"instance_id": self.instance_id, "sources": [{key: item.get(key) for key in (
            "source_id", "title", "media_type", "original_filename", "created_at", "sha256", "size_bytes", "immutability", "retention_work_id", "artifact"
        )} | {"extractions": [{"extraction_id": extraction.get("extraction_id"),
                                "extractor": extraction.get("extractor"),
                                "extractor_version": extraction.get("extractor_version"),
                                "status": extraction.get("status"),
                                "segment_count": len(extraction.get("segments", ())),
                                "metadata": extraction.get("metadata", {})}
                               for extraction in list_extractions(
                                   instance_id=self.instance_id,
                                   source_id=item.get("source_id"),
                                   library_root=self._library_root)]}
        for item in sources]}

    def library_search(self, query):
        from src.library.store import search_extractions
        try: results = search_extractions(query, instance_id=self.instance_id, limit=20, library_root=self._library_root)
        except ValueError as exc: raise ChatServiceError(str(exc), code="invalid_library_query") from exc
        return {"instance_id": self.instance_id, "query": query, "results": results}

    def _historical_search_service(self):
        from src.historical_search import (
            FederatedHistoricalSearch, InheritedHistoryDomain, NativeArchiveDomain,
        )
        return FederatedHistoricalSearch(self.instance_id, domains=(
            NativeArchiveDomain(self.instance_id, index_path=self._archive_index_path,
                                meta_dir=self._archive_meta_dir, raw_dir=self._archive_raw_dir),
            InheritedHistoryDomain(self.instance_id, root=self._inherited_history_root),
        ))

    def historical_search(self, payload):
        """Authenticated rider-requested inspection, never normal Chat context."""
        from src.historical_search import MANUAL_HISTORY_SEARCH_DEFINITION
        registry = CapabilityRegistry()
        registry.register(MANUAL_HISTORY_SEARCH_DEFINITION, lambda request: {
            "search": self._historical_search_service().search(
                request.arguments.get("query"),
                requested_domains=request.arguments.get("domains") or ("native_archive", "inherited_history"),
                limit=request.arguments.get("limit", 20),
            ),
            "result_references": [],
        })
        try:
            result = CapabilityExecutor(registry, receipt_dir=self._capability_receipt_dir).execute(
                CapabilityRequest(instance_id=self.instance_id,
                    capability=MANUAL_HISTORY_SEARCH_DEFINITION.name,
                    arguments={"query": payload.get("query"), "domains": payload.get("domains"),
                               "limit": payload.get("limit", 20)},
                    requested_by="rider", task_authorized=True),
                granted_permissions=("history.search_manual",),
            )
        except (ValueError, PermissionError) as exc:
            raise ChatServiceError(str(exc), code="invalid_history_search") from exc
        return result["search"]

    def historical_evidence(self, domain, evidence_id):
        try: return self._historical_search_service().evidence(domain, evidence_id)
        except (ValueError, PermissionError) as exc:
            raise ChatServiceError(str(exc), code="invalid_history_evidence") from exc
        except LookupError as exc:
            raise ChatServiceError(str(exc), code="history_evidence_not_found") from exc

    def historical_corpus_validation(self, payload):
        """Run explicit read-only qualification of one already staged export."""
        from src.history_staging import InheritedHistoryStore
        from src.history_validation import (
            HISTORICAL_CORPUS_VALIDATION_DEFINITION, HistoricalCorpusValidator,
        )
        registry = CapabilityRegistry()

        def validate(request):
            store = InheritedHistoryStore(self.instance_id, root=self._inherited_history_root)
            report = HistoricalCorpusValidator(store).validate(
                request.arguments.get("export_id"),
                known_queries=payload.get("known_queries") or (),
            )
            return {"validation": report, "result_references": [report["validation_id"], report["export_id"]]}

        registry.register(HISTORICAL_CORPUS_VALIDATION_DEFINITION, validate)
        try:
            result = CapabilityExecutor(registry, receipt_dir=self._capability_receipt_dir).execute(
                CapabilityRequest(instance_id=self.instance_id,
                    capability=HISTORICAL_CORPUS_VALIDATION_DEFINITION.name,
                    arguments={"export_id": payload.get("export_id"),
                               "known_query_count": len(payload.get("known_queries") or ())},
                    requested_by="rider", task_authorized=True),
                granted_permissions=("history.validate_corpus",),
            )
        except (ValueError, PermissionError, LookupError) as exc:
            raise ChatServiceError(str(exc), code="invalid_history_validation") from exc
        return result["validation"]

    def library_extract(self, source_id):
        """Retry a rebuildable local extraction without changing the original."""
        from src.library.extraction import PypdfDocumentExtractor
        from src.library.storage import LocalImmutableBlobStore
        from src.library.store import (
            instance_library_paths, list_sources, record_extraction_failure,
            save_extraction,
        )

        sources = {item["source_id"]: item for item in list_sources(
            instance_id=self.instance_id, library_root=self._library_root
        )}
        source = sources.get(source_id)
        if source is None:
            raise ChatServiceError("That Library source was not found.", code="library_source_not_found")
        if source.get("media_type") != "application/pdf":
            raise ChatServiceError("Page-aware extraction currently supports PDF sources only.", code="library_extraction_unsupported")
        paths = instance_library_paths(self.instance_id, library_root=self._library_root)
        raw = LocalImmutableBlobStore(paths["originals"]).open_bytes(
            source["original_blob"], source["sha256"]
        )
        extractor = self._document_extractor or PypdfDocumentExtractor()
        registry = CapabilityRegistry()

        def extract(_request):
            result = extractor.extract(raw, media_type=source["media_type"])
            record = save_extraction(
                source_id, result.segments, extractor=extractor.extractor_id,
                extractor_version=extractor.extractor_version,
                instance_id=self.instance_id, sources_dir=paths["sources"],
                extractions_dir=paths["extractions"], events_dir=paths["events"],
                metadata=result.metadata,
            )
            return {"extraction": record, "result_references": [record["extraction_id"], source_id]}

        registry.register(LIBRARY_EXTRACT_DEFINITION, extract)
        try:
            result = CapabilityExecutor(registry, receipt_dir=self._capability_receipt_dir).execute(
                CapabilityRequest(
                    instance_id=self.instance_id, capability=LIBRARY_EXTRACT_DEFINITION.name,
                    arguments={"source_id": source_id, "source_sha256": source["sha256"]},
                    requested_by="rider", task_authorized=True,
                ), granted_permissions=("library.extract",),
            )
        except Exception as exc:
            record_extraction_failure(
                source_id, extractor=extractor.extractor_id,
                extractor_version=extractor.extractor_version,
                error_code=(type(exc.__cause__).__name__ if exc.__cause__ else type(exc).__name__),
                instance_id=self.instance_id, events_dir=paths["events"],
            )
            try:
                self.runtime.capability_catalog.set_health(
                    LIBRARY_EXTRACT_DEFINITION.name, "degraded",
                    reason="most recent retained PDF extraction retry failed; original is preserved",
                    failure_code=(type(exc.__cause__).__name__ if exc.__cause__ else type(exc).__name__),
                )
            except (AttributeError, ValueError):
                pass
            raise ChatServiceError(str(exc), code="library_extraction_failed") from exc
        record = result["extraction"]
        try:
            self.runtime.capability_catalog.set_health(
                LIBRARY_EXTRACT_DEFINITION.name, "live",
                reason="most recent retained PDF extraction retry completed",
            )
        except (AttributeError, ValueError):
            pass
        return {"instance_id": self.instance_id, "source_id": source_id,
                "extraction": {"extraction_id": record["extraction_id"],
                               "extractor": record["extractor"],
                               "extractor_version": record["extractor_version"],
                               "segment_count": len(record["segments"]),
                               "metadata": record.get("metadata", {}),
                               "capability_receipt_id": result["capability_receipt_id"]}}

    def phase0_integrity_audit(self):
        from src.runtime.phase0_integrity import audit_phoenix_state
        return audit_phoenix_state(self.instance_id)

    def update_sound_settings(self, payload):
        from src.capabilities.event_audio import SoundPreferenceStore, public_sound_settings
        SoundPreferenceStore(self.instance_id).update(payload)
        return public_sound_settings(self.instance_id)

    def acceptance_center(self):
        """Development-only rider acceptance projection; never conversation state."""
        from src.capabilities.acceptance import AcceptanceCenter
        center = getattr(self, "_acceptance_center", None)
        if center is None:
            center = self._acceptance_center = AcceptanceCenter(self)
        return center

    def resume(self):
        conversation = get_latest_conversation(instance_id=self.instance_id)
        if conversation is None:
            conversation = create_conversation(
                title=self.title,
                instance_id=self.instance_id,
            )
        return conversation

    def history(self, *, conversation_id=None, limit=100):
        conversation = self.resume()
        if conversation_id and conversation_id != conversation["conversation_id"]:
            raise ChatServiceError(
                "That conversation is not available in this session.",
                code="conversation_not_found",
            )
        messages = build_archive_context(
            conversation["conversation_id"], max_messages=limit
        )
        rendered_messages = []
        for message in messages:
            item = {
                "message_id": message.get("message_id"),
                "role": message["role"],
                "content": message["content"],
                "created_at": message.get("created_at"),
            }
            if message["role"] == "assistant" and message.get("message_id"):
                receipt = load_context_receipt(message["message_id"])
                if receipt and receipt.get("presentation"):
                    item["presentation"] = receipt["presentation"]
                if receipt and receipt.get("media_sources"):
                    item["media"] = receipt["media_sources"]
                receipt_audit = receipt.get("retrieval_audit") if isinstance(receipt, dict) else None
                if (receipt and receipt.get("instance_id") == self.instance_id
                        and isinstance(receipt_audit, dict)
                        and isinstance(receipt_audit.get("context_composition"), dict)):
                    item["context_inspector_available"] = True
            rendered_messages.append(item)
        return {
            "phoenix": {"name": self.phoenix["name"]},
            "conversation": {
                "conversation_id": conversation["conversation_id"],
                "title": conversation["title"],
            },
            "messages": rendered_messages,
        }

    def context_inspector(self, response_message_id):
        """Read an existing response's body-free context evidence; never rerun retrieval."""
        try:
            require_id(response_message_id, "response_message_id")
        except (TypeError, ValueError) as exc:
            raise ChatServiceError("That context inspection request is invalid.", code="invalid_context_inspection")
        receipt = load_context_receipt(response_message_id)
        if not receipt:
            raise ChatServiceError("Context inspection is unavailable for that response.", code="context_inspection_not_found")
        if receipt.get("instance_id") != self.instance_id or receipt.get("response_message_id") != response_message_id:
            raise ChatServiceError("That context receipt does not belong to this Phoenix.", code="context_inspection_not_found")
        try:
            flight = load_flight(self.instance_id, response_message_id)
            return build_context_inspector(receipt, flight=flight)
        except ValueError as exc:
            raise ChatServiceError("Context inspection evidence is inconsistent and cannot be shown.",
                                   code="context_inspection_invalid") from exc

    def context_feedback(self, response_message_id, payload):
        """Record rider evidence about an exact inspected decision; apply nothing."""
        if not isinstance(payload, dict):
            raise ChatServiceError("Context feedback is malformed.", code="invalid_context_feedback")
        inspector = self.context_inspector(response_message_id)
        allocation = inspector.get("allocation") or {}
        transmission = inspector.get("transmission") or {}
        replay = inspector.get("replay") or {}
        expected = {
            "context_receipt_id": inspector.get("context_receipt_id"),
            "package_id": inspector.get("package_id"),
            "allocation_decision_sha256": allocation.get("decision_sha256"),
            "transmission_manifest_id": transmission.get("manifest_id"),
            "replay_flight_id": replay.get("flight_id"),
        }
        if not isinstance(expected["package_id"], str) or not isinstance(expected["allocation_decision_sha256"], str):
            raise ChatServiceError("Context feedback requires a complete recorded composition decision.",
                                   code="context_inspection_invalid")
        for key, value in expected.items():
            if payload.get(key) != value:
                raise ChatServiceError("That feedback does not match the inspected context decision.",
                                       code="invalid_context_feedback")
        try:
            return record_context_retrieval_feedback(
                instance_id=self.instance_id,
                rider_principal_id=f"authenticated-rider:{self.instance_id}",
                response_message_id=response_message_id,
                feedback_type=payload.get("feedback_type"), **expected)
        except ValueError as exc:
            raise ChatServiceError(str(exc), code="invalid_context_feedback") from exc

    def send(self, text, *, conversation_id=None, attachments=None, retrieval_clarification=None,
             source="fawkes_app"):
        if not isinstance(text, str) or not text.strip():
            raise ChatServiceError("Write a message first.", code="invalid_message")
        if source not in {"fawkes_app", "discord_dm"}:
            raise ChatServiceError("That conversation source is not permitted.", code="invalid_source")
        text = text.strip()
        if len(text) > 50_000:
            raise ChatServiceError("That message is too long.", code="invalid_message")

        with self._turn_lock:
            conversation = self.resume()
            if conversation_id and conversation_id != conversation["conversation_id"]:
                raise ChatServiceError(
                    "The conversation changed. Refresh and try again.",
                    code="conversation_changed",
                )
            conversation_id = conversation["conversation_id"]
            resolved_clarification=None
            if retrieval_clarification is not None:
                if not isinstance(retrieval_clarification,dict):
                    raise ChatServiceError("The clarification choice is malformed.",code="invalid_clarification")
                origin_response_id=retrieval_clarification.get("originating_response_message_id")
                messages=build_archive_context(conversation_id,max_messages=2)
                if not messages or messages[-1].get("message_id")!=origin_response_id:
                    raise ChatServiceError("That clarification choice is stale or belongs to another turn.",code="invalid_clarification")
                receipt=load_context_receipt(origin_response_id)
                if (not receipt or receipt.get("instance_id")!=self.instance_id
                        or receipt.get("conversation_id")!=conversation_id):
                    raise ChatServiceError("That clarification choice does not belong to this Phoenix conversation.",code="invalid_clarification")
                decision=(receipt.get("retrieval_audit") or {}).get("ambiguity_decision")
                if (not isinstance(decision,dict)
                        or decision.get("decision_id")!=retrieval_clarification.get("decision_id")
                        or decision.get("resulting_retrieval_plan_identity")!=retrieval_clarification.get("retrieval_plan_identity")):
                    raise ChatServiceError("That clarification decision is stale or mismatched.",code="invalid_clarification")
                resolved_clarification={"decision":decision,
                    "response":{"ambiguity_set_id":retrieval_clarification.get("ambiguity_set_id"),
                                "choice_id":retrieval_clarification.get("choice_id")},
                    "original_query":retrieval_clarification.get("original_query")}
            user_message_id = str(uuid.uuid4())
            try:
                media_attachments = validate_chat_media(
                    attachments, instance_id=self.instance_id,
                    owner_principal_id=f"authenticated-rider:{self.instance_id}",
                )
                if media_attachments:
                    enforce_capability_authority(
                        MEDIA_CHAT_DEFINITION,
                        CapabilityRequest(
                            instance_id=self.instance_id,
                            capability=MEDIA_CHAT_DEFINITION.name,
                            arguments={"source_ids": [item["source_id"] for item in media_attachments]},
                            requested_by="rider",
                            conversation_id=conversation_id,
                            request_message_id=user_message_id,
                            task_authorized=True,
                        ),
                        granted_permissions=("rider_media.external_analyze",),
                    )
                if any(item["modality"] == "audio" for item in media_attachments):
                    enforce_capability_authority(
                        AUDIO_TRANSCRIPTION_DEFINITION,
                        CapabilityRequest(
                            instance_id=self.instance_id,
                            capability=AUDIO_TRANSCRIPTION_DEFINITION.name,
                            arguments={"source_ids": [
                                item["source_id"] for item in media_attachments
                                if item["modality"] == "audio"
                            ]},
                            requested_by="rider", conversation_id=conversation_id,
                            request_message_id=user_message_id, task_authorized=True,
                        ),
                        granted_permissions=("rider_media.external_analyze",),
                    )
            except ValueError as exc:
                raise ChatServiceError(str(exc), code="invalid_media") from exc

            try:
                user_archive = persist_live_message(
                    instance_id=self.instance_id,
                    conversation_id=conversation_id,
                    message_id=user_message_id,
                    role="user",
                    text=text,
                    model_slug=self.runtime.model,
                    title=self.title,
                    source=source,
                )
                work_item = discover_candidate(
                    instance_id=self.instance_id,
                    conversation_id=conversation_id,
                    message_id=user_message_id,
                    canonical_revision=user_archive["archive_id"],
                    source_archive_ids=(user_archive["archive_id"],),
                    candidate_content=text,
                    candidate_created_at=user_archive["created_at"],
                )
                update_work_item(work_item["work_item_id"], status="queued")
            except Exception as exc:
                raise ChatServiceError(
                    "I couldn't safely preserve that message, so I didn't send it.",
                    code="persistence_failed",
                ) from exc

            try:
                chat_artifact = ephemeral_provider_artifact(
                    instance_id=self.instance_id, content=text,
                    artifact_kind="chat_reasoning_request",
                    source_domain="rider_chat_message",
                )
                chat_receipt_args = dict(
                    instance_id=self.instance_id, artifact=chat_artifact,
                    capability_id="chat.respond",
                    provider_class="configured_chat_reasoning_adapters",
                    purpose="rider_requested_conversation_reasoning",
                    authorization_source={"mode": "task_request", "request_message_id": user_message_id},
                    transformations=("context_composition", "reasoning", "optional_capability_planning"),
                    correlation_id=user_message_id, receipt_dir=self._provider_receipt_dir,
                )
                record_provider_transmission(status="authorized", **chat_receipt_args)
                if any(item["modality"] == "audio" for item in media_attachments):
                    media_attachments = self._transcribe_audio(
                        media_attachments, conversation_id=conversation_id,
                        request_message_id=user_message_id,
                    )
                for item in media_attachments:
                    if item["modality"] != "audio":
                        record_provider_transmission(
                            instance_id=self.instance_id, artifact=item["artifact"],
                            capability_id=MEDIA_CHAT_DEFINITION.name,
                            provider_class="configured_multimodal_chat_adapter",
                            purpose="rider_requested_media_analysis",
                            authorization_source={"mode": "task_request", "request_message_id": user_message_id},
                            status="authorized", correlation_id=user_message_id,
                            receipt_dir=self._provider_receipt_dir,
                        )
                try:
                    turn_started = time.monotonic()
                    result = self.runtime.respond(
                        user_message=text,
                        conversation_id=conversation_id,
                        current_message_id=user_message_id,
                        request_timestamp=user_archive["created_at"],
                        media_attachments=media_attachments,
                        retrieval_clarification=resolved_clarification,
                    )
                    turn_elapsed_ms = round((time.monotonic() - turn_started) * 1000, 3)
                except Exception as exc:
                    if media_attachments:
                        try:
                            self.runtime.capability_catalog.set_health(
                                MEDIA_CHAT_DEFINITION.name, "degraded",
                                reason="most recent rider-requested media analysis failed",
                                failure_code=type(exc).__name__,
                            )
                        except (AttributeError, ValueError):
                            pass
                    for item in media_attachments:
                        if item["modality"] != "audio":
                            record_provider_transmission(
                                instance_id=self.instance_id, artifact=item["artifact"],
                                capability_id=MEDIA_CHAT_DEFINITION.name,
                                provider_class="configured_multimodal_chat_adapter",
                                purpose="rider_requested_media_analysis",
                                authorization_source={"mode": "task_request", "request_message_id": user_message_id},
                                status="failed", failure_code=type(exc).__name__,
                                correlation_id=user_message_id,
                                receipt_dir=self._provider_receipt_dir,
                            )
                    record_provider_transmission(
                        status="failed", failure_code=type(exc).__name__, **chat_receipt_args
                    )
                    raise
                if media_attachments:
                    try:
                        self.runtime.capability_catalog.set_health(
                            MEDIA_CHAT_DEFINITION.name, "live",
                            reason="most recent rider-requested media analysis completed",
                        )
                    except (AttributeError, ValueError):
                        pass
                for item in media_attachments:
                    if item["modality"] != "audio":
                        record_provider_transmission(
                            instance_id=self.instance_id, artifact=item["artifact"],
                            capability_id=MEDIA_CHAT_DEFINITION.name,
                            provider_class="configured_multimodal_chat_adapter",
                            purpose="rider_requested_media_analysis",
                            authorization_source={"mode": "task_request", "request_message_id": user_message_id},
                            status="completed", correlation_id=user_message_id,
                            receipt_dir=self._provider_receipt_dir,
                        )
                record_provider_transmission(status="completed", **chat_receipt_args)
            except PermissionError as exc:
                if "chat_receipt_args" in locals():
                    record_provider_transmission(
                        status="failed", failure_code=type(exc).__name__, **chat_receipt_args
                    )
                raise ChatServiceError(str(exc), code="authorization_required") from exc
            except Exception as exc:
                if "chat_receipt_args" in locals():
                    record_provider_transmission(
                        status="failed", failure_code=type(exc).__name__, **chat_receipt_args
                    )
                raise ChatServiceError(
                    "Fawkes is unavailable right now. Your message was preserved; try again shortly.",
                    code="provider_unavailable",
                ) from exc

            assistant_message_id = str(uuid.uuid4())
            try:
                assistant_archive = persist_live_message(
                    instance_id=self.instance_id,
                    conversation_id=conversation_id,
                    message_id=assistant_message_id,
                    role="assistant",
                    text=result["text"],
                    model_slug=self.runtime.model,
                    title=self.title,
                    source=source,
                )
            except Exception as exc:
                raise ChatServiceError(
                    "Fawkes answered, but the reply could not be preserved. Refresh before continuing.",
                    code="response_persistence_failed",
                ) from exc

            media_attachments = self._retain_requested_media(
                media_attachments, conversation_id=conversation_id,
                request_message_id=user_message_id,
            )

            correction_observation = None
            correction = result.get("correction")
            if correction is not None and correction.is_correction:
                prior_assistant_id = next(
                    (
                        message.get("message_id")
                        for message in reversed(result.get("conversation_context", ()))
                        if message.get("role") == "assistant"
                        and message.get("message_id")
                    ),
                    None,
                )
                evidence_ids = tuple(
                    item for item in (prior_assistant_id, user_message_id) if item
                )
                if evidence_ids:
                    try:
                        correction_observation = create_development_observation(
                            instance_id=self.instance_id,
                            category="correction_signal",
                            interpretation=f"The rider corrected Fawkes: {text}",
                            uncertainty=(
                                "This records a correction signal; its broader "
                                "developmental meaning remains unassessed."
                            ),
                            conversation_id=conversation_id,
                            message_ids=evidence_ids,
                            status="tentative",
                            observed_by="runtime_correction_evaluator",
                        )
                    except Exception:
                        # The reply and existing development path remain intact.
                        correction_observation = None

            try:
                context_receipt = save_context_receipt(
                    instance_id=self.instance_id,
                    conversation_id=conversation_id,
                    request_message_id=user_message_id,
                    response_message_id=assistant_message_id,
                    response_archive_id=assistant_archive["archive_id"],
                    model=self.runtime.model,
                    memories=result.get("memories", ()),
                    archive_passages=result.get("archive_passages", ()),
                    conversation_context=result.get("conversation_context", ()),
                    development_sources=tuple(
                        source
                        for source in (
                            result.get("development", {}).get("record", {}).get("proposal_id")
                            if result.get("development") else None,
                            correction_observation.get("observation_id")
                            if correction_observation else None,
                        )
                        if source
                    ),
                    research_sources=(
                        ({
                            "research_session_id": result["research"]["session"]["research_session_id"],
                            "research_ids": list(result["research"]["session"]["research_ids"]),
                            "capability_receipt_ids": list(result["research"]["session"]["capability_receipt_ids"]),
                            "citation_validation": result.get("citation_validation", {}),
                        },)
                        if result.get("research") else ()
                    ),
                    library_sources=result.get("library_passages", ()),
                    media_sources=public_media_references(media_attachments),
                    presentation=result.get("presentation"),
                    retrieval_audit=result.get("retrieval_audit"),
                )
            except Exception:
                # The Archive remains complete; receipt repair can be audited later.
                context_receipt = None

            if context_receipt is not None:
                try:
                    record_live_flight(
                        instance_id=self.instance_id, conversation_id=conversation_id,
                        request_message_id=user_message_id,
                        response_message_id=assistant_message_id,
                        response_archive_id=assistant_archive["archive_id"],
                        request_text=text, model=self.runtime.model, result=result,
                        context_receipt_id=context_receipt["receipt_id"],
                        elapsed_ms=turn_elapsed_ms,
                    )
                except Exception:
                    # Diagnostic recording cannot invalidate an archived rider turn.
                    pass

            response_payload = {
                "conversation_id": conversation_id,
                "user_message_id": user_message_id,
                "user_message_created_at": user_archive["created_at"],
                "message": {
                    "message_id": assistant_message_id,
                    "role": "assistant",
                    "content": result["text"],
                    "created_at": assistant_archive["created_at"],
                    "presentation": result.get("presentation"),
                    "context_inspector_available": bool(context_receipt is not None
                        and isinstance((context_receipt.get("retrieval_audit") or {}).get("context_composition"), dict)),
                },
                "media": public_media_references(media_attachments),
                "retrieval_clarification": result.get("ambiguity_decision"),
                "events": [
                    {"event_id": "message.sent", "occurrence_id": user_message_id},
                    {"event_id": "message.received", "occurrence_id": assistant_message_id},
                    *([{"event_id": "task.research_completed", "occurrence_id": assistant_message_id}]
                      if result.get("research") else []),
                ],
            }
            self._schedule_memory_queue()
            return response_payload

    def create_observation(self, payload):
        """Record evidence without promoting it into personality state."""
        return create_development_observation(
            instance_id=self.instance_id,
            category=payload.get("category"),
            interpretation=payload.get("interpretation"),
            uncertainty=payload.get("uncertainty"),
            conversation_id=payload.get("conversation_id"),
            message_ids=payload.get("message_ids", ()),
            evidence_relation=payload.get("evidence_relation", "supporting"),
            status=payload.get("status", "tentative"),
            observed_by=payload.get("observed_by", "rider"),
            observed_pattern=payload.get("observed_pattern"),
            rider_evaluation=payload.get("rider_evaluation", "not_provided"),
            rider_reason=payload.get("rider_reason"),
            development_signal=payload.get("development_signal", "observe_only"),
            longitudinal_status=payload.get("longitudinal_status", "isolated"),
            confidence_state=payload.get("confidence_state", "tentative"),
            observer_attribution=payload.get("observer_attribution"),
        )

    def list_observations(self, *, category=None, status=None):
        return list_development_observations(
            instance_id=self.instance_id,
            category=category,
            status=status,
        )

    def inspect_observation(self, observation_id):
        record = get_development_observation(
            observation_id, instance_id=self.instance_id
        )
        if record is None:
            raise ChatServiceError(
                "Development observation not found.", code="observation_not_found"
            )
        return {
            "observation": record,
            "history": observation_history(
                observation_id, instance_id=self.instance_id
            ),
        }

    def add_observation_evidence(self, observation_id, payload):
        return add_observation_evidence(
            observation_id,
            instance_id=self.instance_id,
            conversation_id=payload.get("conversation_id"),
            message_ids=payload.get("message_ids", ()),
            relation=payload.get("relation"),
        )

    def revise_observation(self, observation_id, payload):
        return revise_observation(
            observation_id,
            instance_id=self.instance_id,
            interpretation=payload.get("interpretation"),
            uncertainty=payload.get("uncertainty"),
            status=payload.get("status"),
            reason=payload.get("reason"),
        )

    def development_dashboard(self):
        return build_development_dashboard(
            instance_id=self.instance_id,
            # Existing pre-instance Development records belong to the first
            # Fawkes migration and remain inspectable only in this deployment.
            include_legacy_unscoped=True,
        )

    def codex_development_handoff(self, payload, *, authenticated_rider=False):
        return run_codex_development_handoff(
            instance_id=self.instance_id, payload=payload,
            authenticated_rider=authenticated_rider,
        )

    def create_codex_development_campaign(self, payload, *, authenticated_rider=False):
        campaign = CodexDevelopmentCampaign(self.instance_id)
        record = campaign.create(payload, authenticated_rider=authenticated_rider)
        return {"campaign": campaign.presentation(record["campaign_id"])}

    def codex_development_campaign(self, campaign_id):
        return CodexDevelopmentCampaign(self.instance_id).presentation(campaign_id)

    def list_codex_development_campaigns(self):
        campaign = CodexDevelopmentCampaign(self.instance_id)
        return {"campaigns": campaign.list_presentations()}

    def cancel_codex_development_campaign(self, campaign_id, *, authenticated_rider=False):
        campaign = CodexDevelopmentCampaign(self.instance_id)
        record = campaign.cancel(campaign_id, authenticated_rider=authenticated_rider)
        return {"campaign": campaign.presentation(record["campaign_id"])}

    def review_codex_development_campaign(self, campaign_id, *, authenticated_rider=False):
        if authenticated_rider is not True:
            raise PermissionError("authenticated rider authority is required")
        campaign = CodexDevelopmentCampaign(self.instance_id)
        current = campaign.presentation(campaign_id)
        if current["status"] != "awaiting_independent_review":
            raise RuntimeError("campaign does not have a reviewable candidate")
        record = campaign.run_to_terminal(campaign_id)
        return {"campaign": campaign.presentation(record["campaign_id"])}

    def codex_development_campaign_evidence(self, campaign_id):
        campaign = CodexDevelopmentCampaign(self.instance_id)
        record = campaign.store.load(campaign_id)
        reports = []
        for run in record.get("builder_runs", []):
            for key in ("source_report_id", "return_report_id"):
                report_id = run.get(key)
                if report_id:
                    reports.append(campaign.exchange._load("reports", report_id))
        for review in record.get("reviews", []):
            if review.get("review_report_id"):
                reports.append(campaign.exchange._load("reports", review["review_report_id"]))
        return {"campaign_id": campaign_id, "reports": reports,
                "validation_evidence": [item for run in record.get("builder_runs", [])
                                        for item in run.get("validation_evidence", [])],
                "creates_authority": False}

    def development_attention(self, *, pending_only=False):
        from src.runtime.development_attention import DevelopmentAttentionStore
        return {"attention": DevelopmentAttentionStore().list(pending_only=pending_only),
                "creates_authority": False}

    def decide_development_attention(self, campaign_id, attention_id, choice,
                                     *, authenticated_rider=False):
        campaign = CodexDevelopmentCampaign(self.instance_id)
        result = campaign.decide_attention(campaign_id, attention_id, choice,
                                           authenticated_rider=authenticated_rider)
        return {"campaign": campaign.presentation(campaign_id),
                "attention": result["event"], "decision": result["decision"]}

    def production_component_status(self):
        import json
        state_root = Path.home() / ".local/state/fawkes"
        discord_path = state_root / "discord-bridge-status.json"
        discord = json.loads(discord_path.read_text()) if discord_path.exists() else {"state": "stopped"}
        from src.runtime.component_supervision import ComponentReceiptStore
        failures = ComponentReceiptStore(state_root).latest(limit=20)
        from src.runtime.production_control import component_states
        supervised = component_states()
        return {"components": {
                    "stack": supervised["stack"],
                    "app_server": supervised["app_server"],
                    "discord_bridge": {**supervised["discord_bridge"], **discord},
                    "development_coordinator": {"state": "READY"},
                    "worker_launcher": {"state": "IDLE"},
                    "reviewer_launcher": {"state": "IDLE"}},
                "latest_failure_receipts": failures, "creates_authority": False}

    def control_production_component(self, payload, *, authenticated_rider=False):
        if authenticated_rider is not True:
            raise PermissionError("authenticated rider authority is required")
        from src.runtime.production_control import control_component
        return control_component(payload.get("component"), payload.get("action"))

    def review_development_proposal(self, proposal_id, payload):
        return review_development_proposal(
            proposal_id,
            instance_id=self.instance_id,
            decision=payload.get("decision"),
            reviewer="rider",
            note=payload.get("note", ""),
        )
