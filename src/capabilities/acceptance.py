"""Rider-triggered acceptance tests over registered Phoenix capabilities.

Test runs are development diagnostics.  They never write Archive, Memory, or
Development identity records.  Client probes deliberately finish in the real
client so a backend-only success cannot masquerade as visible UI acceptance.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import json as json_module
import threading
import time
import uuid

from src.capabilities.core import SAFE_IDENTIFIER


ROOT = Path(__file__).resolve().parent.parent.parent
RUNS_DIR = ROOT / "database" / "acceptance_test_runs"
VALID_RESULTS = {"pass", "fail"}
NON_RUNNABLE_RESULTS = {"not_available", "not_implemented", "environmentally_unverifiable"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def capability_acceptance_statuses(*, instance_id, manifests, run_dir=None):
    """Project test evidence by capability without changing runtime availability."""
    root = (Path(run_dir) if run_dir else RUNS_DIR) / instance_id
    latest = {}
    if root.exists():
        for directory in root.iterdir():
            if not directory.is_dir():
                continue
            try:
                started = json.loads((directory / "started.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            completed = directory / "completed.json"
            record = started
            if completed.exists():
                try: record = {**started, **json.loads(completed.read_text(encoding="utf-8"))}
                except (OSError, json.JSONDecodeError): pass
            prior = latest.get(record.get("test_id"))
            if record.get("test_id") and (not prior or record.get("started_at", "") > prior.get("started_at", "")):
                latest[record["test_id"]] = record
    grouped = {}
    for definition in default_registry(manifests).definitions():
        if not (definition.runner or definition.client_probe):
            continue
        grouped.setdefault(definition.capability, []).append(latest.get(definition.test_id, {}).get("status", "not_tested"))
    result = {}
    for capability, statuses in grouped.items():
        if "testing" in statuses: result[capability] = "testing"
        elif "fail" in statuses: result[capability] = "failed"
        elif statuses and all(item == "pass" for item in statuses): result[capability] = "pass"
        elif "pass" in statuses: result[capability] = "partial"
        else: result[capability] = "not_tested"
    return result


@dataclass(frozen=True)
class AcceptanceTestDefinition:
    test_id: str
    capability: str
    title: str
    group: str
    version: str
    what: str
    expected: str
    layers: tuple[str, ...]
    runner: str | None = None
    client_probe: str | None = None
    missing_reason: str | None = None
    run_all: bool = True
    unavailable_status: str = "not_implemented"

    def __post_init__(self):
        if not SAFE_IDENTIFIER.fullmatch(self.test_id):
            raise ValueError("acceptance test id contains unsafe characters")
        if bool(self.runner) == bool(self.client_probe):
            if not self.missing_reason:
                raise ValueError("test needs exactly one runner or a missing reason")
        if self.unavailable_status not in NON_RUNNABLE_RESULTS:
            raise ValueError("invalid unavailable acceptance status")


class AcceptanceTestRegistry:
    def __init__(self):
        self._tests = {}

    def register(self, definition):
        if not isinstance(definition, AcceptanceTestDefinition):
            raise TypeError("definition must be an AcceptanceTestDefinition")
        if definition.test_id in self._tests:
            raise ValueError(f"acceptance test already registered: {definition.test_id}")
        self._tests[definition.test_id] = definition

    def definitions(self):
        return tuple(self._tests.values())

    def resolve(self, test_id):
        try:
            return self._tests[test_id]
        except KeyError as exc:
            raise ValueError("unknown acceptance test") from exc


def default_registry(capability_manifests):
    """Build the test inventory and expose every live manifest without stale UI lists."""
    registry = AcceptanceTestRegistry()
    definitions = (
        AcceptanceTestDefinition("chat.core", "chat", "Chat", "Core Chat", "1",
            "Conversation history, authoritative timestamps, and continuity read path",
            "A current conversation can be loaded with valid message timestamps.",
            ("automated", "integration"), runner="chat_history"),
        AcceptanceTestDefinition("capability.discovery", "capability.discovery", "Capability awareness", "Core Chat", "1",
            "Runtime-derived provider-neutral capability catalog",
            "Every advertised capability has safe availability metadata and no credentials.",
            ("automated", "integration"), runner="capability_discovery"),
        AcceptanceTestDefinition("awareness.inventory", "capability.awareness", "Accurate capability inventory", "Capability Awareness", "1",
            "Runtime self-knowledge enumerates only configured capabilities and their real status",
            "Live and unavailable capabilities are communicated from runtime truth without provider secrets.",
            ("automated", "integration"), runner="awareness_inventory"),
        AcceptanceTestDefinition("awareness.research_selection", "capability.awareness", "Research relevance", "Capability Awareness", "1",
            "Current external curriculum request selects web research",
            "Web research is required because authoritative external facts are missing.",
            ("automated", "integration"), runner="awareness_research"),
        AcceptanceTestDefinition("awareness.composition", "capability.awareness", "Capability composition", "Capability Awareness", "1",
            "LSUA curriculum ranking request composes research and visualization",
            "Web research and visual communication are both selected with distinct roles.",
            ("automated", "integration"), runner="awareness_composition"),
        AcceptanceTestDefinition("awareness.restraint", "capability.awareness", "Capability restraint", "Capability Awareness", "1",
            "Casual conversation does not select expensive or irrelevant capabilities",
            "No research, media, Library, or visualization capability is selected.",
            ("automated", "integration"), runner="awareness_restraint"),
        AcceptanceTestDefinition("awareness.multimodal", "capability.awareness", "Multimodal selection", "Capability Awareness", "1",
            "A rider attachment selects temporary media analysis",
            "Media analysis is selected and its external/privacy limitations remain visible.",
            ("automated", "integration"), runner="awareness_media"),
        AcceptanceTestDefinition("awareness.visual_choice", "capability.awareness", "Visualization choice", "Capability Awareness", "1",
            "Explicit and general visual requests map to supported visual communication",
            "An explicit scatter request is honored; general selection guidance remains format-appropriate.",
            ("automated", "integration"), runner="awareness_visual"),
        AcceptanceTestDefinition("awareness.unavailable", "capability.awareness", "Unavailable capability honesty", "Capability Awareness", "1",
            "Capability knowledge does not invent absent runtime capabilities",
            "Video, voice, and Library are not claimed live unless actually advertised.",
            ("automated", "integration"), runner="awareness_unavailable"),
        AcceptanceTestDefinition("awareness.permissions", "capability.awareness", "Permission boundaries", "Security", "1",
            "Capability self-knowledge retains authorization and execution boundaries",
            "Awareness describes authority but grants no additional permission.",
            ("automated", "integration"), runner="awareness_permissions"),
        AcceptanceTestDefinition("presentation.visualization", "presentation.visualize", "Charts / Visualization", "Visualization", "2",
            "Natural four-chart response payload through the actual browser renderer",
            "4 rendered visualizations: pie / bar / line / donut.",
            ("automated", "end_to_end", "rider_ui"), client_probe="four_charts"),
        AcceptanceTestDefinition("presentation.tables", "presentation.visualize", "Tables", "Visualization", "1",
            "Validated structured table through the actual browser renderer",
            "One readable table with an accessible text fallback.",
            ("automated", "end_to_end", "rider_ui"), client_probe="table"),
        AcceptanceTestDefinition("presentation.diagrams", "presentation.visualize", "Diagrams / Flowcharts", "Visualization", "1",
            "Validated flow diagram through the actual browser renderer",
            "One rendered flow diagram with labeled steps and text fallback.",
            ("automated", "end_to_end", "rider_ui"), client_probe="diagram"),
        AcceptanceTestDefinition("presentation.timeline", "presentation.visualize", "Timelines", "Visualization", "1",
            "Validated timeline through the actual browser renderer",
            "One rendered timeline with readable event labels.",
            ("automated", "end_to_end", "rider_ui"), client_probe="timeline"),
        AcceptanceTestDefinition("audio.event_contract", "presentation.event_sounds", "Event sound contract", "Audio", "1",
            "Semantic event registry, approved-asset mapping, preferences, and missing-asset safety",
            "All events are registered; controls persist; unavailable assets remain silent without substitution.",
            ("automated", "integration"), runner="event_sound_contract"),
        AcceptanceTestDefinition("audio.client_playback", "presentation.event_sounds", "Event sound client", "Audio", "1",
            "Real browser event-audio controller applies master/event settings and duplicate suppression",
            "The browser safely handles a semantic event; physical audibility remains rider/device verification.",
            ("automated", "end_to_end", "rider_ui", "device_verification_required"), client_probe="event_audio"),
        AcceptanceTestDefinition("presence.profile", "presentation.phoenix_presence", "Phoenix Presence profile", "Presence", "1",
            "Instance-bound embodiment profile, policy, provenance, asset integrity, and accessible fallback",
            "The current Phoenix owns a valid revisioned profile and missing 3D assets remain honestly unavailable.",
            ("automated", "integration", "recovery"), runner="presence_profile"),
        AcceptanceTestDefinition("presence.client", "presentation.phoenix_presence", "Phoenix Presence client", "Presence", "1",
            "Actual client Presence surface, semantic invocation, renderer/fallback health, and Chat interaction",
            "A visible accessible Presence or truthful fallback renders and invocation reaches Chat without claiming physical 3D verification.",
            ("automated", "end_to_end", "rider_ui", "device_verification_required"), client_probe="phoenix_presence"),
        AcceptanceTestDefinition("memory.triage", "memory", "Memory triage", "Memory", "1",
            "Instance-scoped Memory ranking/read projection without mutation",
            "The triage ledger is readable and statuses are internally consistent.",
            ("automated", "integration"), runner="memory_triage"),
        AcceptanceTestDefinition("development.dashboard", "development", "Development", "Development", "1",
            "Observation, proposal, evidence, and progression read model",
            "The instance-scoped dashboard loads all required evidence sections.",
            ("automated", "integration"), runner="development_dashboard"),
        AcceptanceTestDefinition("development.human_review", "human_review", "Human Review", "Development", "1",
            "Human Review projection over genuine proposals and review records",
            "The review path loads without manufacturing or applying records.",
            ("automated", "integration"), runner="human_review"),
        AcceptanceTestDefinition("library.retrieve", "library.search", "Library retention and retrieval", "Library", "2",
            "Explicit temporary-to-durable retention, versioned page-aware extraction, and provenance-bearing retrieval",
            "A synthetic retained PDF is locally extracted, isolated, and retrieved with its physical-page source locator.",
            ("automated", "integration", "end_to_end"), runner="library_retention_retrieval"),
        AcceptanceTestDefinition("library.catalog", "library.catalog", "Library catalog", "Library", "1",
            "Instance-scoped retained-source catalog through the application boundary",
            "The catalog loads without creating, changing, or exposing another Phoenix's sources.",
            ("automated", "integration"), runner="library_catalog"),
        AcceptanceTestDefinition("library.artifact_foundation", "library.catalog", "Library artifact lifecycle", "Library", "1",
            "Synthetic two-Phoenix retention, deduplication, typed lifecycle, backup, and restore",
            "Explicit retention creates isolated immutable artifacts; replay is idempotent and a verified backup restores exactly.",
            ("automated", "integration", "recovery"), runner="library_artifact_foundation"),
        AcceptanceTestDefinition("system.ownership_audit", "system.integrity_audit", "Phoenix ownership audit", "Security", "1",
            "Read-only ownership audit across durable sources, settings, derivations, receipts, indexes, and work items",
            "No invalid or ownership-mismatched current records; legacy/unscoped records are reported without mutation.",
            ("automated", "integration", "security"), runner="phase0_ownership_audit"),
        AcceptanceTestDefinition("system.complete_recovery", "system.state_recovery", "Complete-state recovery", "Security", "1",
            "Synthetic two-Phoenix complete-state backup, tamper verification, and empty-root isolated restore",
            "Only the selected Phoenix is backed up and restored; hashes and Archive bytes remain exact.",
            ("automated", "integration", "recovery"), runner="phase0_complete_recovery"),
        AcceptanceTestDefinition("system.processing_ledger", "system.processing_ledger", "Canonical processing ledger", "Core Infrastructure", "1",
            "Provider-neutral stable work identity, ownership, lifecycle, recovery, coverage, and inert future extension metadata",
            "Synthetic work is isolated by Phoenix, idempotent, append-only, recoverable, and cannot activate simulation, continuity, or authority.",
            ("automated", "integration", "recovery"), runner="universal_processing_ledger"),
        AcceptanceTestDefinition("history.inherited_staging", "history.import_stage", "Inherited history staging", "History", "2",
            "Synthetic ChatGPT export staging through the provider-neutral adapter and canonical processing ledger",
            "Original evidence is immutable, instance-isolated, idempotent, provenance-bearing, recoverable, and never promoted to native Memory or continuity.",
            ("automated", "integration", "recovery"), runner="inherited_history_staging"),
        AcceptanceTestDefinition("history.manual_federated_search", "history.search_manual", "Manual federated historical search", "History", "1",
            "Explicit synthetic native/inherited search with provenance-preserving exact-source navigation",
            "Both domains remain distinguishable, unavailable domains are honest, exact originals resolve, and no result enters Memory or automatic Chat context.",
            ("automated", "integration", "end_to_end"), runner="manual_federated_history_search"),
        AcceptanceTestDefinition("history.corpus_validation", "history.validate_corpus", "Historical corpus validation", "History", "1",
            "Synthetic original-to-projection reconciliation with known-query navigation and inherited-history invariants",
            "Counts, branch identities, exact text, hashes, provenance, and source navigation reconcile without Memory or continuity promotion.",
            ("automated", "integration"), runner="historical_corpus_validation"),
        AcceptanceTestDefinition("retrieval.flight_replay", "retrieval.replay", "Retrieval Flight Recorder and Replay", "Continuity", "1",
            "Immutable live-turn diagnostics, isolated candidate replay, evidence comparison, and reviewed regression promotion",
            "Flight and replay evidence are Phoenix-scoped, replay cannot alter ordinary history, and failures require explicit review before regression promotion.",
            ("automated", "integration", "recovery"), runner="retrieval_flight_replay"),
        AcceptanceTestDefinition("retrieval.unified_planner", "retrieval.plan", "Unified retrieval planner foundation", "Continuity", "1",
            "Pre-ranking authority/privacy eligibility, domain-neutral adapters, deterministic fair budgeting, projection health, and replay evidence",
            "Distinct authorities and inherited provenance survive planning; gated, foreign, unavailable, degraded, stale, or over-budget evidence cannot enter selection.",
            ("automated", "integration", "security"), runner="unified_retrieval_planner"),
        AcceptanceTestDefinition("retrieval.evidence_eligibility", "retrieval.evidence_eligibility", "Production evidence eligibility policy", "Security", "1",
            "Separate storage, automatic private-context, provider, external, and cross-principal decisions with sensitive/restricted fail-closed behavior",
            "Potentially private evidence can support owned private Chat without gaining disclosure authority; sensitive, restricted, foreign, malformed, and inherited evidence remain correctly gated.",
            ("automated", "integration", "security"), runner="production_evidence_eligibility"),
        AcceptanceTestDefinition("retrieval.legacy_compatibility", "retrieval.legacy_compatibility", "Legacy evidence compatibility", "Continuity", "1",
            "Same-Phoenix legacy Archive/Memory compatibility plus a deterministic metadata-only migration review projection",
            "Explicit metadata wins; uncertain, foreign, malformed, restricted, or quarantined evidence fails closed without canonical mutation or disclosure authority.",
            ("automated", "integration", "security"), runner="legacy_evidence_compatibility"),
        AcceptanceTestDefinition("retrieval.production_adapters", "retrieval.production_adapters", "Two-stage production evidence adapters", "Security", "2",
            "Metadata-first enumeration, centralized eligibility, eligible-only materialization/ranking, and deterministic planning",
            "Denied evidence never reaches materialization or ranking; Archive, Memory, and Library authority remains distinct.",
            ("automated", "integration", "security"), runner="production_evidence_adapters"),
        AcceptanceTestDefinition("retrieval.evidence_transmission", "retrieval.evidence_transmission", "Pre-call evidence transmission authorization", "Security", "1",
            "Content-addressed exact-set provider-route authorization before evidence body release",
            "Denied, changed, foreign, stale, or route-mismatched evidence cannot obtain a provider permit; manifests contain no bodies.",
            ("automated", "integration", "security"), runner="evidence_transmission_manifest"),
        AcceptanceTestDefinition("context.production_composer", "context.compose", "Production context composer", "Continuity", "2",
            "Registered response-purpose composition with deterministic authorized-source allocation, exact-set provenance, trust isolation, honest budgets, and body-free audit",
            "Only already-authorized evidence enters provider rendering; context cannot create authority and package tampering fails closed.",
            ("automated", "integration", "security"), runner="production_context_composer"),
        AcceptanceTestDefinition("context.inspector", "context.inspect", "Rider Context Inspector", "Continuity", "1",
            "Authenticated body-free projection of composition, allocation, permit, receipt, and Replay evidence",
            "Viewing a completed response explains recorded context without bodies, retrieval, mutation, or new authority.",
            ("automated", "integration", "security"), runner="context_inspector"),
        AcceptanceTestDefinition("context.feedback", "context.feedback", "Context retrieval feedback", "Continuity", "1",
            "Authenticated exact-decision rider feedback recorded as body-free Development evidence",
            "Feedback is Phoenix-scoped and idempotent and creates no retrieval, ranking, eligibility, transmission, mutation, or approval authority.",
            ("automated", "integration", "security"), runner="context_feedback"),
        AcceptanceTestDefinition("worker.exchange_foundation", "worker.exchange", "Phoenix Worker Exchange foundation", "Development", "1",
            "Immutable scoped worker reports, least-necessary source-preserving packages, delivery/verification separation, disagreement, and return lineage",
            "Transport-neutral records remain Phoenix/task/recipient bound and zero-authority; manual transfer retirement and direct adapters remain unqualified.",
            ("automated", "integration", "security", "recovery"), runner="worker_exchange_foundation"),
        AcceptanceTestDefinition("worker.codex_adapter_candidate", "worker.exchange.codex", "Promoted Codex Exchange adapter", "Development", "1",
            "Promoted ephemeral read-only Codex exec contract, exact promotion/workspace/package binding, schema return, fail-closed evidence, and manual-fallback preservation",
            "Production activation is qualification- and rider-promotion-bound and remains zero-authority; overall manual transfer is not retired.",
            ("automated", "integration", "security"), runner="codex_worker_adapter_candidate"),
        AcceptanceTestDefinition("continuity.native_projection", "continuity.native_projection", "Native Archive continuity projection", "Continuity", "8",
            "Stable evidence identity, bounded native relationships, ambiguity/duplicate preservation, and representative synthetic corpus qualification",
            "Predeclared ambiguity-quality thresholds pass; eligible native evidence remains distinct, deterministic, body-free, and cannot resolve identity or truth.",
            ("automated", "integration", "security"), runner="native_continuity_projection"),
        AcceptanceTestDefinition("system.provider_privacy", "system.integrity_audit", "Provider Privacy Gateway", "Security", "1",
            "Shared authorized/outcome receipts for external Chat, research, image, PDF, and audio processing",
            "Receipts are instance-scoped, append-only, failure-aware, and contain no payload or credential material.",
            ("automated", "integration", "security"), runner="phase0_provider_privacy"),
        AcceptanceTestDefinition("capability.dynamic_health", "capability.discovery", "Dynamic capability health", "Core Chat", "1",
            "Runtime health and rider acceptance are represented independently",
            "Every capability has a valid health state; acceptance evidence cannot turn failed health green.",
            ("automated", "integration"), runner="dynamic_capability_health"),
        AcceptanceTestDefinition("continuity.person", "continuity.retrieve", "Prior person reference", "Continuity", "1", "Resolve a natural reference to a prior person", "Relevant attributed evidence is retrieved with context.", ("automated", "integration"), runner="continuity_person"),
        AcceptanceTestDefinition("continuity.course", "continuity.retrieve", "Prior course reference", "Continuity", "1", "Resolve a natural reference to a prior course", "The course evidence is retrieved without a special professor rule.", ("automated", "integration"), runner="continuity_course"),
        AcceptanceTestDefinition("continuity.project", "continuity.retrieve", "Prior project reference", "Continuity", "1", "Resolve a natural reference to a prior project", "The project evidence is retrieved with provenance.", ("automated", "integration"), runner="continuity_project"),
        AcceptanceTestDefinition("continuity.decision", "continuity.retrieve", "Prior decision reference", "Continuity", "1", "Resolve a prior decision", "The decision and surrounding context are available.", ("automated", "integration"), runner="continuity_decision"),
        AcceptanceTestDefinition("continuity.research", "continuity.retrieve", "Prior research result", "Continuity", "1", "Resolve a reference to prior research", "The historical result is retrieved as evidence, not reclassified as Memory.", ("automated", "integration"), runner="continuity_research"),
        AcceptanceTestDefinition("continuity.problem", "continuity.retrieve", "Unresolved prior problem", "Continuity", "1", "Resolve an earlier unresolved problem", "The unresolved status remains visible.", ("automated", "integration"), runner="continuity_problem"),
        AcceptanceTestDefinition("continuity.reason", "continuity.retrieve", "Reason behind decision", "Continuity", "1", "Preserve why a prior choice was made", "Neighbor-aware evidence retains the stated reason.", ("automated", "integration"), runner="continuity_reason"),
        AcceptanceTestDefinition("continuity.same_conversation", "continuity.retrieve", "Older same-conversation history", "Continuity", "1", "Retrieve evidence older than the working-context window", "Current-conversation history is not excluded wholesale.", ("automated", "integration"), runner="continuity_same_conversation"),
        AcceptanceTestDefinition("continuity.cross_conversation", "continuity.retrieve", "Cross-conversation history", "Continuity", "1", "Retrieve relevant evidence from another conversation", "Cross-conversation retrieval remains instance-scoped.", ("automated", "integration"), runner="continuity_cross_conversation"),
        AcceptanceTestDefinition("continuity.failure", "continuity.retrieve", "Retrieval no-match honesty", "Continuity", "1", "Handle a bounded retrieval miss", "No match does not become a false claim that history was never stored.", ("automated", "integration"), runner="continuity_failure"),
        AcceptanceTestDefinition("continuity.ambiguous", "continuity.retrieve", "Truly ambiguous reference", "Continuity", "1", "Detect an unresolved reference", "Multiple plausible candidates remain explicitly ambiguous.", ("automated", "integration"), runner="continuity_ambiguous"),
        AcceptanceTestDefinition("continuity.multiple", "continuity.retrieve", "Multiple historical candidates", "Continuity", "1", "Retain multiple plausible historical anchors", "Candidates are not silently collapsed or invented.", ("automated", "integration"), runner="continuity_multiple"),
        AcceptanceTestDefinition("continuity.restraint", "continuity.retrieve", "Continuity restraint", "Continuity", "1", "Avoid historical retrieval for self-contained casual conversation", "No continuity capability is selected unnecessarily.", ("automated", "integration"), runner="continuity_restraint"),
        AcceptanceTestDefinition("continuity.reporting", "continuity.retrieve", "Continuity capability honesty", "Continuity", "1", "Describe actual retrieval scope and limitations", "Runtime truth distinguishes working context, retrieval miss, and storage absence.", ("automated", "integration"), runner="continuity_reporting"),
    )
    manifest_names = {item.get("name") for item in capability_manifests if isinstance(item, dict)}
    for definition in definitions:
        if definition.capability == "continuity.retrieve" and "continuity.retrieve" not in manifest_names:
            continue
        registry.register(definition)
    covered = {item.capability for item in definitions}
    represented_features = {
        "table", "flow", "timeline", "bar", "line", "pie", "donut",
        "semantic_events", "master_control", "event_controls", "volume", "duplicate_suppression",
        "source_listing", "retention_status", "source_identity",
        "source_artifact_lifecycle", "verified_backup_restore",
        "temporary_artifact_lifecycle", "provider_transmission_receipt",
        "ownership_audit", "legacy_unscoped_reporting", "integrity_findings",
        "verified_manifest", "isolated_restore", "rebuild_plan", "tamper_detection",
        "stable_work_identity", "append_only_processing_events", "resumable_lifecycle",
        "corpus_coverage_projection", "future_metadata_extension_envelopes",
        "same_conversation_history", "cross_conversation_history", "semantic_reranking",
        "timestamp_lookup", "neighbor_context", "ambiguity_reporting",
    }
    for manifest in capability_manifests:
        name = manifest.get("name")
        if not isinstance(name, str) or not name or name in covered:
            continue
        safe_id = "capability." + "".join(ch if ch.isalnum() or ch in ".-_" else "-" for ch in name)
        registry.register(AcceptanceTestDefinition(
            safe_id, name, manifest.get("description") or name, "Registered capabilities", "1",
            "Live runtime capability acceptance", "A meaningful rider-facing acceptance test completes.",
            ("end_to_end",), missing_reason="This live capability does not yet register a rider-facing acceptance test.",
        ))
    for manifest in capability_manifests:
        name = manifest.get("name")
        if not isinstance(name, str) or not name:
            continue
        safe_name = "".join(ch if ch.isalnum() or ch in ".-_" else "-" for ch in name)
        for feature in manifest.get("features", ()):
            if feature in represented_features:
                continue
            safe_feature = "".join(ch if ch.isalnum() or ch in ".-_" else "-" for ch in feature)
            registry.register(AcceptanceTestDefinition(
                f"feature.{safe_name}.{safe_feature}", name, str(feature).replace("_", " ").title(),
                "Registered capability features", "1", f"Rider-facing {feature} behavior",
                "The feature completes through its real rider-facing path.", ("end_to_end",),
                missing_reason="The runtime advertises this feature, but it has no independent rider-facing acceptance test yet.",
            ))
    return registry


class AcceptanceCenter:
    def __init__(self, service, *, run_dir=None):
        self.service = service
        self.run_dir = Path(run_dir) if run_dir else RUNS_DIR
        self._lock = threading.Lock()
        self._active = {}
        self._latest_cache = None
        self._registry_cache = None
        self._event_generation = 0

    @property
    def instance_dir(self):
        return self.run_dir / self.service.instance_id

    def _write_event(self, run_id, name, payload):
        directory = self.instance_dir / run_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{name}.json"
        if path.exists():
            raise ValueError("acceptance event is immutable")
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)
        with self._lock:
            self._event_generation += 1
            if self._latest_cache is not None:
                test_id = payload.get("test_id")
                if test_id:
                    prior = self._latest_cache.get(test_id, {})
                    self._latest_cache[test_id] = {**prior, **payload}

    def _registry(self):
        if self._registry_cache is None:
            self._registry_cache = default_registry(self.service.runtime.capability_context())
        return self._registry_cache

    def _latest(self):
        while True:
            with self._lock:
                if self._latest_cache is not None:
                    return dict(self._latest_cache)
                generation = self._event_generation
            latest = {}
            if self.instance_dir.exists():
                for directory in self.instance_dir.iterdir():
                    if not directory.is_dir():
                        continue
                    try:
                        started = json.loads((directory / "started.json").read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    completed_path = directory / "completed.json"
                    record = started
                    if completed_path.exists():
                        try: record = {**started, **json.loads(completed_path.read_text(encoding="utf-8"))}
                        except (OSError, json.JSONDecodeError): pass
                    prior = latest.get(record["test_id"])
                    if not prior or record.get("started_at", "") > prior.get("started_at", ""):
                        latest[record["test_id"]] = record
            with self._lock:
                if generation != self._event_generation:
                    continue
                self._latest_cache = latest
                return dict(latest)

    def snapshot(self):
        latest = self._latest()
        tests = [self._public(item, latest.get(item.test_id)) for item in self._registry().definitions()]
        completed = [item for item in tests if item["status"] in VALID_RESULTS]
        passing = sum(item["status"] == "pass" for item in completed)
        return {"schema_version": 1, "instance_id": self.service.instance_id,
                "summary": {"passing": passing, "completed": len(completed), "total": len(tests)},
                "tests": tests}

    def _public(self, definition, record=None):
        status = "not_tested" if (definition.runner or definition.client_probe) else definition.unavailable_status
        if record:
            status = record.get("status", "testing")
        return {"test_id": definition.test_id, "capability": definition.capability,
                "title": definition.title, "group": definition.group, "test_version": definition.version,
                "what": definition.what, "expected": definition.expected, "layers": list(definition.layers),
                "status": status, "runnable": bool(definition.runner or definition.client_probe),
                "missing_reason": definition.missing_reason, "last_run": record,
                "run_all": definition.run_all}

    def start(self, test_id, *, platform=None):
        definition = self._registry().resolve(test_id)
        if not (definition.runner or definition.client_probe):
            raise ValueError(definition.missing_reason or "acceptance test is not implemented")
        run_id = str(uuid.uuid4())
        started = {"schema_version": 1, "record_type": "acceptance_test_started",
                   "run_id": run_id, "test_id": test_id, "instance_id": self.service.instance_id,
                   "test_version": definition.version, "status": "testing", "requested_by": "rider",
                   "platform": platform or {"client": "web", "device": "unknown"}, "started_at": _now()}
        self._write_event(run_id, "started", started)
        if definition.client_probe:
            return {**self._public(definition, started), "run_id": run_id,
                    "client_probe": definition.client_probe}
        thread = threading.Thread(target=self._run_server, args=(definition, run_id, started), daemon=True)
        thread.start()
        return {**self._public(definition, started), "run_id": run_id}

    def _run_server(self, definition, run_id, started):
        began = time.monotonic()
        try:
            actual = self._server_runner(definition.runner)
            self.complete(run_id, result="pass", actual=actual,
                          duration_ms=round((time.monotonic() - began) * 1000, 1), source="server")
        except Exception as exc:
            # A disposable/test run directory may be removed while an async
            # runner is finishing.  Never turn that cleanup race into an
            # unhandled daemon-thread exception or a second failed completion.
            if (self.instance_dir / run_id / "started.json").exists():
                try:
                    self.complete(run_id, result="fail", actual=str(exc), failure_stage="server acceptance runner",
                                  duration_ms=round((time.monotonic() - began) * 1000, 1), source="server")
                except (OSError, ValueError):
                    pass

    def _server_runner(self, name):
        if name.startswith("continuity_"):
            return self._continuity_runner(name.removeprefix("continuity_"))
        if name == "native_continuity_projection":
            from src.runtime.native_continuity_projection import NativeContinuityProjection, NativeArchiveCandidateGenerator, NativeSourceRepresentationPreference
            from src.runtime.native_retrieval_ambiguity import NativeRetrievalAmbiguityPolicy
            def item(evidence_id, conversation_id, text, created_at):
                return {"instance_id":"acceptance-phoenix", "domain":"native_archive",
                    "evidence_id":evidence_id, "message_id":evidence_id,
                    "conversation_id":conversation_id, "source_archive_id":"archive-"+evidence_id,
                    "created_at":created_at, "text":text,
                    "authority_class":"native_canonical_evidence",
                    "original_evidence_reference":{"archive_id":"archive-"+evidence_id,"message_id":evidence_id}}
            candidates=[item("one","conversation-one","Atlas project decision","2026-01-01T00:00:00+00:00"),
                        item("two","conversation-two","Atlas project decision","2026-01-02T00:00:00+00:00")]
            catalog=[{key:value for key,value in candidate.items() if key not in {"text","authority_class","message_id","source_archive_id"}}
                     for candidate in candidates]
            projected,audit=NativeContinuityProjection().project(instance_id="acceptance-phoenix",
                query="Which one was that Atlas project?",candidates=candidates,metadata_catalog=catalog)
            if len(projected)!=2 or not audit["ambiguity_set_ids"] or not audit["duplicate_group_ids"]:
                raise AssertionError("native continuity relationships were not preserved")
            if audit["canonical_records_merged"] or audit["truth_resolution_performed"]:
                raise AssertionError("projection exceeded read-only relationship authority")
            eligible=[{**{key:value for key,value in candidate.items() if key != "text"},
                       "local_lexical_terms":["atlas","project"]} for candidate in candidates]
            generated,generation=NativeArchiveCandidateGenerator().generate(
                query="Which conversation was that last month?",eligible_metadata=eligible,
                request_timestamp="2026-02-15T12:00:00+00:00",rider_timezone="UTC")
            if len(generated)!=2 or generation["interpretation"]["temporal_constraint"] is None:
                raise AssertionError("query-aware native candidate generation failed")
            thread=[{**eligible[0],"evidence_id":f"thread-{index}",
                     "conversation_id":"conversation-thread",
                     "created_at":f"2026-01-01T00:0{index}:00+00:00",
                     "local_lexical_terms":["atlas"] if index==2 else ["context"]}
                    for index in range(5)]
            navigated,navigation=NativeArchiveCandidateGenerator().generate(
                query="earlier in that conversation about Atlas",eligible_metadata=thread,
                max_thread_hops=2)
            if {item["evidence_id"] for item in navigated}!={"thread-0","thread-1","thread-2"}:
                raise AssertionError("bounded native thread navigation failed")
            if navigation["max_thread_hops"]!=2 or navigation["automatic_inherited_history"]:
                raise AssertionError("native thread navigation exceeded authority")
            ambiguity_input={"native_archive":{"reference_ambiguity_sets":[{
                "ambiguity_set_id":"acceptance-ambiguity","candidate_evidence_ids":["one","two"],
                "basis":"multiple_recent_conversations_no_reference_resolution"}],
                "ambiguity_choice_descriptors":[{"ambiguity_set_id":"acceptance-ambiguity",
                    "choices":[{"evidence_id":"one","created_at":eligible[0]["created_at"]},
                               {"evidence_id":"two","created_at":eligible[1]["created_at"]}]}]}}
            ambiguity=NativeRetrievalAmbiguityPolicy().evaluate(instance_id="acceptance-phoenix",
                rider_principal_id="rider:acceptance",request_message_id="request-1",
                correlation_id="request-1",candidate_generation=ambiguity_input,
                selected_evidence=eligible)
            if not ambiguity["clarification_required"] or ambiguity["authorization_granted"]:
                raise AssertionError("native rider clarification boundary failed")
            choice=ambiguity["ambiguity_sets"][0]["choices"][0]
            consumed=NativeRetrievalAmbiguityPolicy().validate_selection(ambiguity,
                {"ambiguity_set_id":"acceptance-ambiguity","choice_id":choice["choice_id"]},
                instance_id="acceptance-phoenix",rider_principal_id="rider:acceptance",
                originating_request_message_id="request-1",correlation_id="request-1")
            if consumed["selected_evidence_id"]!="one" or consumed["authorization_granted"]:
                raise AssertionError("clarification choice consumption exceeded authority")
            original={**eligible[0],"representation_provenance":{"representation_class":"source_original","relationships":[]}}
            duplicate={**eligible[1],"representation_provenance":{"representation_class":"duplicate_copy","relationships":[
                {"relationship":"duplicate_of","qualification_status":"verified","target":original["original_evidence_reference"]}]}}
            preferred,preference=NativeSourceRepresentationPreference().apply(
                generated_candidates=[original,duplicate],eligible_metadata=[original,duplicate])
            if len(preferred)!=1 or preference["canonical_records_merged"]:
                raise AssertionError("source-original context preference violated canonical preservation")
            from src.runtime.native_archive_corpus_acceptance import run_corpus
            corpus=json_module.loads((ROOT / "tests/fixtures/native_archive_acceptance_corpus.json").read_text())
            expected=json_module.loads((ROOT / "tests/fixtures/native_archive_acceptance_expected.json").read_text())
            corpus_result=run_corpus(corpus,expected)
            if not corpus_result["passed"]:
                raise AssertionError("representative native Archive corpus acceptance failed")
            return ("Eligible native Archive records retained canonical identity; bounded traversal, ambiguity "
                    "clarification/choice validation, source-original preference, and the 14-scenario synthetic "
                    "corpus passed without inherited participation.")
        if name == "library_catalog":
            catalog = self.service.library_catalog()
            if catalog.get("instance_id") != self.service.instance_id: raise AssertionError("Library catalog crossed instance scope")
            return f"Instance-scoped Library catalog loaded with {len(catalog.get('sources', []))} retained source(s); no data created."
        if name == "library_artifact_foundation":
            from tempfile import TemporaryDirectory
            from src.library.artifacts import retention_intent
            from src.library.store import (
                backup_instance_library, instance_library_paths, list_sources,
                register_source, restore_instance_library,
            )
            with TemporaryDirectory() as tmp:
                live = Path(tmp) / "live"
                one = instance_library_paths("acceptance-one", library_root=live)
                kwargs = dict(
                    raw_bytes=b"synthetic acceptance source", title="Acceptance source",
                    media_type="text/plain", instance_id="acceptance-one",
                    retention_intent=retention_intent(actor_type="rider", principal_id="acceptance-rider"),
                    originals_dir=one["originals"], sources_dir=one["sources"], events_dir=one["events"],
                )
                first, replay = register_source(**kwargs), register_source(**kwargs)
                if first["source_id"] != replay["source_id"] or not replay["_replayed"]:
                    raise AssertionError("retention replay was not idempotent")
                if first.get("artifact", {}).get("lifecycle", {}).get("state") != "durable_registered":
                    raise AssertionError("typed durable lifecycle is missing")
                if list_sources(instance_id="acceptance-two", library_root=live):
                    raise AssertionError("Library source crossed Phoenix scope")
                backup, _ = backup_instance_library("acceptance-one", Path(tmp) / "backup", library_root=live)
                restored = Path(tmp) / "restored"
                restore_instance_library("acceptance-one", backup, library_root=restored)
                if len(list_sources(instance_id="acceptance-one", library_root=restored)) != 1:
                    raise AssertionError("verified restore did not recover the source")
            return "Explicit retention, same-Phoenix replay, cross-Phoenix isolation, lifecycle, backup, and restore passed using synthetic temporary data."
        if name == "library_retention_retrieval":
            from tempfile import TemporaryDirectory
            import io
            from pypdf import PdfWriter
            from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
            from src.library.artifacts import retention_intent, lineage_edge
            from src.library.extraction import PypdfDocumentExtractor
            from src.library.store import (
                instance_library_paths, list_sources, register_source,
                save_extraction, search_extractions,
            )
            with TemporaryDirectory() as tmp:
                root = Path(tmp) / "library"
                paths = instance_library_paths("acceptance-one", library_root=root)
                writer = PdfWriter()
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
                stream.set_data(b"BT /F1 12 Tf 72 720 Td (Subnetting divides an IP network.) Tj ET")
                page[NameObject("/Contents")] = writer._add_object(stream)
                pdf = io.BytesIO(); writer.write(pdf); pdf_bytes = pdf.getvalue()
                source = register_source(
                    pdf_bytes, title="Networking chapter",
                    media_type="application/pdf", original_filename="networking.pdf",
                    instance_id="acceptance-one",
                    retention_intent=retention_intent(
                        actor_type="rider", principal_id="acceptance-rider"
                    ),
                    provenance=(lineage_edge(
                        "derived_from", "temporary:acceptance-pdf",
                        target_kind="temporary_media",
                    ),),
                    originals_dir=paths["originals"], sources_dir=paths["sources"],
                    events_dir=paths["events"],
                )
                adapter = PypdfDocumentExtractor()
                extracted = adapter.extract(pdf_bytes, media_type="application/pdf")
                extraction = save_extraction(
                    source["source_id"], extracted.segments,
                    extractor=adapter.extractor_id, extractor_version=adapter.extractor_version,
                    instance_id="acceptance-one", sources_dir=paths["sources"],
                    extractions_dir=paths["extractions"], events_dir=paths["events"],
                    metadata={**extracted.metadata, "fixture": "synthetic"},
                )
                results = search_extractions(
                    "subnetting", instance_id="acceptance-one", library_root=root
                )
                if len(results) != 1 or results[0]["location"].get("page_number") != 1:
                    raise AssertionError("page-aware retained evidence was not retrievable")
                if results[0].get("source_id") != source["source_id"]:
                    raise AssertionError("retrieval lost durable source provenance")
                if extraction.get("source_sha256") != source["sha256"]:
                    raise AssertionError("derived extraction lost original authority linkage")
                if list_sources(instance_id="acceptance-two", library_root=root):
                    raise AssertionError("retained source crossed Phoenix scope")
            return "Explicit retention, real local PDF extraction, physical page 1 retrieval, source authority, provenance, and Phoenix isolation passed using disposable synthetic data."
        if name == "phase0_ownership_audit":
            report = self.service.phase0_integrity_audit()
            if not report.get("read_only") or report.get("legacy_records_modified"):
                raise AssertionError("ownership audit did not preserve legacy evidence")
            if not report.get("gate_satisfied"):
                raise AssertionError(f"blocking ownership findings: {report.get('summary')}")
            return f"Read-only audit passed; {report['summary'].get('legacy_unscoped', 0)} legacy unscoped and {report['summary'].get('legacy_path_scoped', 0)} legacy path-scoped record(s) reported without migration."
        if name == "phase0_complete_recovery":
            from tempfile import TemporaryDirectory
            import json
            from src.runtime.phase0_integrity import (
                create_complete_state_backup, restore_complete_state_backup,
                verify_complete_state_backup,
            )
            with TemporaryDirectory() as tmp:
                root = Path(tmp) / "state"
                (root / "instances").mkdir(parents=True)
                (root / "conversations").mkdir(parents=True)
                (root / "database/context_receipts").mkdir(parents=True)
                (root / "archive/meta").mkdir(parents=True)
                (root / "archive/raw").mkdir(parents=True)
                (root / "instances/registry.json").write_text(json.dumps({"schema_version": 1, "instances": [
                    {"instance_id": "one", "name": "One"}, {"instance_id": "two", "name": "Two"}] }))
                (root / "conversations/registry.json").write_text(json.dumps({"schema_version": 1, "conversations": [
                    {"conversation_id": "c1", "instance_id": "one"}, {"conversation_id": "c2", "instance_id": "two"}] }))
                for owner in ("one", "two"):
                    (root / "database/context_receipts" / f"{owner}.json").write_text(json.dumps({"instance_id": owner, "receipt_id": owner}))
                    (root / "archive/meta" / f"{owner}.json").write_text(json.dumps({"instance_id": owner, "archive_id": owner}))
                    (root / "archive/raw" / f"{owner}.txt").write_bytes((owner + " exact").encode())
                backup, _ = create_complete_state_backup("one", Path(tmp) / "backups", source_root=root)
                verify_complete_state_backup(backup, expected_instance_id="one")
                restored = Path(tmp) / "restored"
                restore_complete_state_backup(backup, restored, instance_id="one")
                if (restored / "database/context_receipts/two.json").exists():
                    raise AssertionError("another Phoenix leaked into recovery")
                if (restored / "archive/raw/one.txt").read_bytes() != b"one exact":
                    raise AssertionError("canonical Archive bytes changed")
            return "Complete-state manifest, cross-Phoenix exclusion, byte-exact Archive copy, and empty-root restore passed using synthetic data."
        if name == "phase0_provider_privacy":
            from tempfile import TemporaryDirectory
            from src.capabilities.provider_privacy import ephemeral_provider_artifact, record_provider_transmission
            with TemporaryDirectory() as tmp:
                artifact = ephemeral_provider_artifact(instance_id="privacy-one", content="synthetic private fixture",
                    artifact_kind="acceptance_request", source_domain="synthetic_acceptance")
                args = dict(instance_id="privacy-one", artifact=artifact, capability_id="fixture.external_read",
                    provider_class="fixture_adapter", purpose="acceptance", authorization_source={"mode": "task_request"},
                    correlation_id="fixture-message", receipt_dir=tmp)
                authorized = record_provider_transmission(status="authorized", **args)
                failed = record_provider_transmission(status="failed", failure_code="SyntheticFailure", **args)
                encoded = "".join(path.read_text() for path in Path(tmp).rglob("*.json"))
            if authorized["transmission_id"] != failed["transmission_id"]:
                raise AssertionError("provider receipt lifecycle lost its stable identity")
            if "synthetic private fixture" in encoded or '"credential_material_recorded": true' in encoded:
                raise AssertionError("provider receipt leaked payload or credentials")
            return "Authorized and failed provider events retained one transmission identity without payload or credentials."
        if name == "dynamic_capability_health":
            manifests = self.service.capabilities().get("capabilities", [])
            allowed = {"live", "partial", "degraded", "failed", "rate_limited", "permission_blocked",
                       "disabled", "untested", "environmentally_unverifiable", "unavailable"}
            missing = [item.get("name") for item in manifests if item.get("health", {}).get("status") not in allowed]
            if missing:
                raise AssertionError(f"capabilities lack dynamic health: {missing}")
            return f"{len(manifests)} capability health record(s) valid and independently accompanied by acceptance status."
        if name == "event_sound_contract":
            from src.capabilities.event_audio import SOUND_EVENTS, SoundPreferenceStore
            payload = self.service.sound_settings()
            ids = [item.event_id for item in SOUND_EVENTS]
            if len(ids) != len(set(ids)): raise AssertionError("Duplicate semantic sound event ids")
            if set(payload["preferences"]["events"]) != set(ids): raise AssertionError("Preference controls do not cover the event registry")
            approved = [item for item in payload["events"] if item["approved"]]
            missing = [item["label"] for item in approved if not item["available"]]
            if any(item["asset_url"] for item in approved if not item["available"]): raise AssertionError("Missing assets were exposed for playback")
            return f"{len(ids)} semantic events registered; {len(approved)} approved; {len(missing)} approved asset(s) safely unavailable. Physical playback not rider-verified."
        if name == "presence_profile":
            from src.capabilities.phoenix_presence import validate_profile
            profile = self.service.presence_profile()
            validate_profile(profile, expected_instance_id=self.service.instance_id)
            if profile.get("invocation_is_authentication") is not False:
                raise AssertionError("invocation phrase was represented as authentication")
            if profile.get("asset") is None and profile.get("health", {}).get("status") != "unavailable":
                raise AssertionError("missing Phoenix GLB was not reported unavailable")
            return f"Presence profile revision {profile['profile_revision']} is owned by the active Phoenix; 3D health is {profile['health']['status']}."
        if name == "universal_processing_ledger":
            from tempfile import TemporaryDirectory
            from src.runtime.processing_ledger import ProcessingLedger
            with TemporaryDirectory() as tmp:
                one = ProcessingLedger("acceptance-one", root=tmp)
                two = ProcessingLedger("acceptance-two", root=tmp)
                arguments = dict(
                    domain="acceptance", work_kind="contract_probe",
                    source={"source_id": "source-1", "object_id": "object-1",
                            "content_id": "content-1", "revision_id": "revision-1",
                            "source_domain": "synthetic_acceptance", "evidence_era": "external_source"},
                    processor_id="acceptance-probe", processor_version="1.0",
                    idempotency_key="probe-1",
                    actor={"actor_type": "runtime", "principal_id": "runtime:acceptance"},
                    extensions={"historical_provenance": {
                        "founding_relationship_provenance_id": "founding-probe",
                        "identity_attribution": "ambiguous"}},
                )
                item = one.register(**arguments); replay = one.register(**arguments)
                if item["work_item_id"] != replay["work_item_id"]:
                    raise AssertionError("work registration was not idempotent")
                one.transition(item["work_item_id"], to_status="queued", operation_id="queue")
                one.transition(item["work_item_id"], to_status="running", operation_id="claim", increment_attempt=True)
                completed = one.transition(item["work_item_id"], to_status="completed", operation_id="complete",
                    result_references=["result:synthetic"])
                if two.get(item["work_item_id"]) is not None:
                    raise AssertionError("processing work crossed Phoenix scope")
                if len(one.events(item["work_item_id"])) != 4:
                    raise AssertionError("append-only lifecycle evidence is incomplete")
                if one.coverage()["by_status"] != {"completed": 1}:
                    raise AssertionError("coverage projection is inaccurate")
                if completed["extensions"]["historical_provenance"]["identity_attribution"] != "ambiguous":
                    raise AssertionError("reserved provenance was flattened or activated")
            return "Stable work identity, append-only lifecycle, two-Phoenix isolation, bounded coverage, and inert future metadata passed using disposable synthetic work."
        if name == "inherited_history_staging":
            import io
            import json
            import zipfile
            from tempfile import TemporaryDirectory
            from src.history_staging import ChatGPTExportAdapter, InheritedHistoryStore
            from src.runtime.phase0_integrity import create_complete_state_backup, restore_complete_state_backup
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "instances").mkdir(parents=True)
                (root / "instances/registry.json").write_text(json.dumps({"schema_version": 1, "instances": [
                    {"instance_id": "acceptance-one", "name": "One"},
                    {"instance_id": "acceptance-two", "name": "Two"}]}) + "\n", encoding="utf-8")
                payload = [{"id": "conversation-1", "title": "Founding", "mapping": {
                    "node-1": {"id": "node-1", "parent": None, "children": [], "message": {
                        "id": "message-1", "author": {"role": "user"}, "create_time": 1,
                        "content": {"content_type": "text", "parts": ["Fawkes founding evidence"]}}}}}]
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w") as archive:
                    archive.writestr("conversations.json", json.dumps(payload))
                store = InheritedHistoryStore("acceptance-one", root=root / "database/inherited_history",
                                              processing_root=root / "database/processing")
                authorization = {"authorization_id": "authorization:acceptance-one", "mode": "explicit_confirmation",
                    "scope": "stage_inherited_history_export", "instance_id": "acceptance-one",
                    "principal_id": "rider:acceptance-one"}
                first = store.stage(buffer.getvalue(), adapter=ChatGPTExportAdapter(),
                                    actor_principal="rider:acceptance-one", authorization=authorization)
                second = store.stage(buffer.getvalue(), adapter=ChatGPTExportAdapter(),
                                     actor_principal="rider:acceptance-one", authorization=authorization)
                hits = store.search("Fawkes")
                other = InheritedHistoryStore("acceptance-two", root=root / "database/inherited_history",
                                              processing_root=root / "database/processing")
                if first["native_boundary_status"] == "proven_native" or first["memory_promotion"] != "prohibited":
                    raise AssertionError("staging promoted inherited history")
                if not second["idempotent_replay"] or len(hits) != 1:
                    raise AssertionError("staging was not idempotent and inspectable")
                if hits[0]["history_era"] != "inherited_history" or hits[0]["identity_attribution"] != "unassessed":
                    raise AssertionError("staging provenance was flattened")
                if other.search("Fawkes"):
                    raise AssertionError("staged evidence crossed Phoenix scope")
                backup, _ = create_complete_state_backup("acceptance-one", root / "backups", source_root=root)
                restored = root / "restored"
                restore_complete_state_backup(backup, restored, instance_id="acceptance-one")
                restored_store = InheritedHistoryStore("acceptance-one", root=restored / "database/inherited_history",
                                                       processing_root=restored / "database/processing")
                if restored_store.get_export(first["export_id"]) is None:
                    raise AssertionError("isolated recovery omitted staged evidence")
            return "Inherited-history original preservation, isolation, idempotency, inspection, and non-promotion passed using a disposable synthetic export."
        if name == "manual_federated_history_search":
            import hashlib
            import io
            import json
            import zipfile
            from tempfile import TemporaryDirectory
            from src.historical_search import FederatedHistoricalSearch, InheritedHistoryDomain, NativeArchiveDomain
            from src.history_staging import ChatGPTExportAdapter, InheritedHistoryStore
            from src.memory.archive_retrieval import index_canonical_message
            with TemporaryDirectory() as tmp:
                root = Path(tmp); owner = "acceptance-one"; index = root / "native.sqlite3"
                raw = json.dumps({"message_id": "native-message", "role": "user", "text": "shared historical token in native evidence"}).encode()
                (root / "archive/raw").mkdir(parents=True); (root / "archive/meta").mkdir(parents=True)
                (root / "archive/raw/archive-native.json").write_bytes(raw)
                (root / "archive/meta/archive-native.json").write_text(json.dumps({
                    "schema_version": 1, "archive_id": "archive-native", "instance_id": owner,
                    "raw_file": "archive-native.json", "sha256": hashlib.sha256(raw).hexdigest(), "encoding": "utf-8"}))
                index_canonical_message(instance_id=owner, conversation_id="native-conversation", message_id="native-message",
                    role="user", content="shared historical token in native evidence", created_at="2026-01-01T00:00:00+00:00",
                    source_archive_id="archive-native", path=index)
                payload = [{"id": "inherited-conversation", "mapping": {"node": {"parent": None, "children": [], "message": {
                    "id": "inherited-message", "author": {"role": "user"}, "content": {"content_type": "text", "parts": ["shared historical token in inherited evidence"]}}}}}]
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w") as archive: archive.writestr("conversations.json", json.dumps(payload))
                inherited_root = root / "database/inherited_history"
                InheritedHistoryStore(owner, root=inherited_root, processing_root=root / "database/processing").stage(
                    buffer.getvalue(), adapter=ChatGPTExportAdapter(), actor_principal="rider:acceptance-one",
                    authorization={"authorization_id": "authorization:history-search-acceptance",
                        "mode": "explicit_confirmation", "scope": "stage_inherited_history_export",
                        "instance_id": owner, "principal_id": "rider:acceptance-one"})
                search = FederatedHistoricalSearch(owner, domains=(
                    NativeArchiveDomain(owner, index_path=index, meta_dir=root / "archive/meta", raw_dir=root / "archive/raw"),
                    InheritedHistoryDomain(owner, root=inherited_root)))
                result = search.search("shared historical token")
                if {item["domain"] for item in result["results"]} != {"native_archive", "inherited_history"}:
                    raise AssertionError("federated domains were flattened or omitted")
                inherited = next(item for item in result["results"] if item["domain"] == "inherited_history")
                exact = search.evidence("inherited_history", inherited["evidence_reference"]["evidence_id"])
                if exact["identity_attribution"] != "unassessed" or exact["native_boundary_status"] != "boundary_unknown":
                    raise AssertionError("manual search changed inherited provenance")
                if exact["exact_original_text"] != "shared historical token in inherited evidence":
                    raise AssertionError("exact inherited source navigation failed")
                if result["automatic_chat_context"] is not False or (root / "memory").exists():
                    raise AssertionError("manual inspection gained behavioral authority")
            return "Manual native/inherited federation, provenance separation, exact-original navigation, and non-promotion passed using disposable synthetic evidence."
        if name == "historical_corpus_validation":
            import io
            import json
            import zipfile
            from tempfile import TemporaryDirectory
            from src.history_staging import ChatGPTExportAdapter, InheritedHistoryStore
            from src.history_validation import HistoricalCorpusValidator
            with TemporaryDirectory() as tmp:
                root = Path(tmp); owner = "acceptance-one"
                payload = [{"id": "conversation", "title": "Founding", "current_node": "node", "mapping": {
                    "empty": {"parent": None, "children": ["node"], "message": None},
                    "node": {"parent": "empty", "children": [], "message": {"id": "message",
                        "author": {"role": "user"}, "create_time": 1,
                        "content": {"content_type": "text", "parts": ["Fawkes validation evidence"]}}}}}]
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w") as archive:
                    archive.writestr("conversations.json", json.dumps(payload))
                store = InheritedHistoryStore(owner, root=root / "database/inherited_history",
                                              processing_root=root / "database/processing")
                store.stage(buffer.getvalue(), adapter=ChatGPTExportAdapter(),
                    actor_principal="rider:acceptance-one", authorization={
                        "authorization_id": "authorization:validation", "mode": "explicit_confirmation",
                        "scope": "stage_inherited_history_export", "instance_id": owner,
                        "principal_id": "rider:acceptance-one"})
                export_id = store.list_exports()[0]["export_id"]
                report = HistoricalCorpusValidator(store).validate(export_id, known_queries=("Fawkes",))
                if report["status"] != "qualified" or report["failed_checks"]:
                    raise AssertionError("synthetic corpus did not qualify")
                if report["automatic_chat_context"] or report["memory_promotion"] != "prohibited":
                    raise AssertionError("validation gained cognitive authority")
            return "Synthetic original/projection counts, branches, exact text, digest, provenance, and known-query navigation qualified without promotion."
        if name == "retrieval_flight_replay":
            from tempfile import TemporaryDirectory
            from src.runtime.retrieval_replay import record_live_flight, replay_flight, promote_regression
            with TemporaryDirectory() as tmp:
                result = {"text": "baseline", "memories": [{"memory_id": "memory-1"}],
                          "archive_passages": [], "library_passages": [],
                          "conversation_context": [], "continuity": {"attempted": False},
                          "retrieval_trace": {"queries": [{"domain": "memory", "text": "known"}]}}
                flight = record_live_flight(instance_id="acceptance-one", conversation_id="conversation-1",
                    request_message_id="request-1", response_message_id="response-1",
                    response_archive_id="archive-1", request_text="known", model="fixture",
                    result=result, context_receipt_id="response-1", root=tmp)
                replay = replay_flight(instance_id="acceptance-one", flight_id=flight["flight_id"],
                    candidate_id="fixture", candidate_version="2", root=tmp,
                    runner=lambda detached: {"selected_evidence": detached["selected_evidence"],
                                             "response_text": "candidate"})
                case = promote_regression(instance_id="acceptance-one", replay_id=replay["replay_id"],
                    reviewer_principal_id="rider:acceptance-one", failure_statement="fixture reviewed failure",
                    expected_evidence=flight["selected_evidence"], root=tmp)
                if replay["ordinary_history_mutated"] or case["automatic_promotion"]:
                    raise AssertionError("replay or promotion crossed its authority boundary")
            return "Immutable Phoenix-scoped flight capture, side-effect-free evidence diff, and explicitly reviewed regression promotion passed."
        if name == "unified_retrieval_planner":
            from src.runtime.retrieval_planner import StaticEvidenceAdapter, UnifiedRetrievalPlanner
            native = StaticEvidenceAdapter("native_archive", [{"instance_id": "acceptance-one",
                "domain": "native_archive", "authority_class": "native_canonical_evidence",
                "evidence_id": "native-1", "text": "native evidence",
                "original_evidence_reference": {"archive_id": "archive-1"}}],
                authority_class="native_canonical_evidence")
            inherited = StaticEvidenceAdapter("inherited_history", [],
                authority_class="immutable_imported_source_evidence", automatic_enabled=False,
                required_grants=("history.inherited.auto",))
            plan = UnifiedRetrievalPlanner("acceptance-one", adapters=(native, inherited)).plan(
                "evidence", grants=(), total_budget_chars=512)
            if plan["eligible_domains"] != ["native_archive"]:
                raise AssertionError("authority gating did not precede retrieval")
            if plan["domain_status"]["inherited_history"]["reason"] != "automatic_retrieval_disabled":
                raise AssertionError("inherited automatic retrieval was advertised or activated")
            if not plan["selected_evidence"] or any(plan["side_effects"].values()):
                raise AssertionError("planning selection or no-side-effect contract failed")
            return "Distinct authority eligibility, inherited-history gate, deterministic budget, provenance, and no-side-effect planning passed."
        if name == "production_evidence_eligibility":
            from src.runtime.evidence_eligibility import EvidenceUseContext, ProductionEvidenceEligibilityPolicy
            policy = ProductionEvidenceEligibilityPolicy()
            context = EvidenceUseContext(instance_id="acceptance-one", rider_principal_id="rider:one",
                capability_id="chat.respond", capability_authorized=True)
            base = {"instance_id": "acceptance-one", "owner_principal_id": "rider:one",
                "evidence_id": "evidence-1", "domain": "library",
                "authority_class": "immutable_library_source",
                "original_evidence_reference": {"source_id": "source-1"},
                "provenance_valid": True, "automatic_use_enabled": True}
            private = policy.evaluate({**base, "privacy_classification": "potentially_private"}, context)
            restricted = policy.evaluate({**base, "privacy_classification": "restricted"}, context)
            inherited = policy.evaluate({**base, "domain": "inherited_history",
                "privacy_classification": "standard"}, context)
            if not private["automatic_private_context"]["allowed"] or private["external_disclosure"]["allowed"]:
                raise AssertionError("private-context and disclosure authority were collapsed")
            if restricted["automatic_private_context"]["allowed"] or inherited["automatic_private_context"]["allowed"]:
                raise AssertionError("restricted or inherited evidence bypassed its gate")
            return "Separate private-context, provider, external, and cross-principal authority decisions passed with restricted and inherited fail-closed gates."
        if name == "legacy_evidence_compatibility":
            from src.runtime.legacy_compatibility import derive_legacy_compatibility, build_legacy_review_projection
            evidence = {"instance_id": "acceptance-one", "domain": "native_archive",
                "evidence_id": "archive-1", "authority_class": "native_canonical_evidence",
                "original_evidence_reference": {"archive_id": "archive-1"},
                "provenance_valid": True, "automatic_use_enabled": True,
                "continuity_ownership_basis": "scoped_instance_record",
                "source_schema_version": 1, "eligibility_flags": [],
                "text": "sensitive fixture body"}
            decision = derive_legacy_compatibility(evidence, instance_id="acceptance-one",
                                                   rider_principal_id="rider:one")
            projection = build_legacy_review_projection((evidence,), instance_id="acceptance-one",
                                                        rider_principal_id="rider:one")
            if decision["migration_status"] != "compatibility_eligible" or decision["canonical_record_modified"]:
                raise AssertionError("legacy compatibility decision failed or claimed a rewrite")
            if "sensitive fixture body" in str(projection) or not projection["rebuildable"]:
                raise AssertionError("review projection retained content or was not rebuildable")
            return "Same-Phoenix compatibility, explicit non-rewrite status, and deterministic body-free migration review projection passed."
        if name == "production_evidence_adapters":
            from src.runtime.production_retrieval_adapters import TwoStageEvidenceAdapter, TwoStageRetrievalCoordinator
            from src.runtime.evidence_eligibility import EvidenceUseContext
            class Fixture(TwoStageEvidenceAdapter):
                domain_id="memory"; authority_class="derived_memory_evidence"; adapter_version="fixture-v1"
                def __init__(self): self.materialized=False
                def enumerate_metadata(self, *, instance_id): return [{"instance_id":instance_id,"domain":"memory","evidence_id":"m1","authority_class":self.authority_class,"owner_principal_id":"rider:one","privacy_classification":"restricted","original_evidence_reference":{"id":"m1"},"provenance_valid":True,"automatic_use_enabled":True}]
                def materialize(self, reference, *, instance_id): self.materialized=True; return {"text":"secret"}
            adapter=Fixture(); context=EvidenceUseContext(instance_id="acceptance-one",rider_principal_id="rider:one",capability_id="chat.respond",capability_authorized=True,provider_mode="configured_external_provider",provider_authorized=True)
            plan=TwoStageRetrievalCoordinator("acceptance-one","rider:one",adapters=(adapter,)).plan("secret",evidence_use_context=context)
            if adapter.materialized or plan["selected_evidence"]: raise AssertionError("denied evidence crossed the eligibility boundary")
            return "Metadata-first eligibility blocked restricted evidence before materialization, ranking, provider processing, and context allocation."
        if name == "evidence_transmission_manifest":
            from tempfile import TemporaryDirectory
            from src.runtime.evidence_transmission import EvidenceTransmissionAuthorizer, ProviderRoute
            from src.runtime.evidence_eligibility import POLICY_VERSION
            route=ProviderRoute("private-chat-policy","fixture-provider","fixture-model")
            evidence={"instance_id":"acceptance-one","owner_principal_id":"rider:one","evidence_id":"e1","domain":"memory","authority_class":"derived_memory_evidence","original_evidence_reference":{"memory_id":"m1"},"adapter_version":"fixture-v1","text":"sensitive fixture","eligibility":{"instance_id":"acceptance-one","policy_version":POLICY_VERSION,"privacy_classification":"potentially_private","selected_for_context":True,"provider_transmission":{"allowed":True,"reason":"authorized","provider_route":route.public()}}}
            with TemporaryDirectory() as tmp:
                permit=EvidenceTransmissionAuthorizer(root=tmp).authorize(instance_id="acceptance-one",rider_principal_id="rider:one",conversation_id="c1",request_message_id="q1",correlation_id="q1",route=route,selected_evidence=(evidence,),planner_version="planner-v1",policy_version=POLICY_VERSION,adapter_versions={"memory":"fixture-v1"})
                if "sensitive fixture" in permit.path.read_text(): raise AssertionError("manifest retained evidence body")
                permit.provider_bodies(route=route,selected_evidence=(evidence,))
            return "Exact evidence set was content-addressed and authorized before body release; immutable manifest remained body-free."
        if name == "production_context_composer":
            from src.runtime.context_composer import ProductionContextComposer
            route={"provider_policy_id":"private-chat-policy","provider_class":"fixture",
                   "model":"fixture-model","route_version":"1"}
            evidence={"instance_id":"acceptance-one","evidence_id":"e1","domain":"memory",
                "authority_class":"derived_memory_evidence","text":"sensitive fixture body",
                "original_evidence_reference":{"memory_id":"m1"},
                "eligibility":{"provider_transmission":{"allowed":True,"reason":"authorized",
                                                          "provider_route":route}}}
            composer=ProductionContextComposer()
            package=composer.compose(instance_id="acceptance-one",rider_principal_id="rider:one",
                conversation_id="c1",request_message_id="q1",provider_route=route,
                current_message="use it",retrieved_evidence=(evidence,),
                transmission_authorization={"manifest_id":"permit-1","authorized_evidence_ids":["e1"]})
            rendered=composer.render(package)
            if "sensitive fixture body" not in rendered or "DATA_ONLY_NO_INSTRUCTION_AUTHORITY" not in rendered:
                raise AssertionError("authorized isolated context was not rendered")
            if "sensitive fixture body" in json.dumps(package["audit"]) or package["authority"]["creates_authority"]:
                raise AssertionError("composer audit leaked a body or claimed authority")
            if package["purpose_profile"]["purpose"] != "response_model_context":
                raise AssertionError("registered response composition purpose was not bound")
            if package["allocation"]["selected_evidence_ids"] != ["e1"] or package["allocation"]["creates_authority"]:
                raise AssertionError("deterministic no-authority allocation was not preserved")
            return "Registered response-purpose composition, deterministic authorized-source allocation, exact-set isolation, body-free audit, and no-authority contract passed."
        if name == "context_inspector":
            from src.runtime.context_receipts import build_context_inspector
            receipt={"receipt_id":"response-1","response_message_id":"response-1","instance_id":"acceptance-one",
                "retrieval_audit":{"context_composition":{"package_id":"package-1",
                    "purpose_profile":{"purpose":"response_model_context","profile_version":"1"},
                    "allocation":{"policy_version":"allocation-v1","input_evidence_ids":["e1"],
                        "selected_evidence_ids":["e1"],"omitted_evidence_ids":[],
                        "per_domain_selected":{"memory":1}},
                    "source_summary":[{"evidence_id":"e1","domain":"memory","body_sha256":"digest"}],
                    "transmission_manifest_id":"permit-1"},
                    "transmission_authorization":{"status":"authorized","manifest_id":"permit-1",
                        "authorized_evidence_ids":["e1"]}}}
            result=build_context_inspector(receipt)
            if result["contains_source_bodies"] or result["authority"]["creates_authority"]:
                raise AssertionError("Inspector leaked body authority")
            if result["source_domains"]!={"memory":1} or result["transmission"]["manifest_id"]!="permit-1":
                raise AssertionError("Inspector lost composition or permit evidence")
            return "Body-free receipt projection preserved composition and permit evidence without retrieval or authority."
        if name == "context_feedback":
            from tempfile import TemporaryDirectory
            from src.memory.review_feedback import record_context_retrieval_feedback
            with TemporaryDirectory() as tmp:
                result=record_context_retrieval_feedback(instance_id="acceptance-one",
                    rider_principal_id="rider:one",response_message_id="response-1",
                    context_receipt_id="response-1",package_id="package-1",
                    allocation_decision_sha256="allocation-1",transmission_manifest_id="permit-1",
                    replay_flight_id="response-1",feedback_type="context_helped",directory=Path(tmp))
                repeated=record_context_retrieval_feedback(instance_id="acceptance-one",
                    rider_principal_id="rider:one",response_message_id="response-1",
                    context_receipt_id="response-1",package_id="package-1",
                    allocation_decision_sha256="allocation-1",transmission_manifest_id="permit-1",
                    replay_flight_id="response-1",feedback_type="context_helped",directory=Path(tmp))
            if any(result["authority"].values()) or result["contains_context_bodies"] or not repeated["replayed"]:
                raise AssertionError("context feedback gained authority, bodies, or duplicate effects")
            return "Exact-decision rider feedback was recorded idempotently as body-free no-authority Development evidence."
        if name == "worker_exchange_foundation":
            from datetime import datetime, timedelta, timezone
            from tempfile import TemporaryDirectory
            from src.runtime.worker_exchange import WorkerExchange
            sender={"worker_id":"builder","role":"software","identity_status":"rider_attested","charter_version":"1.0"}
            recipient={"worker_id":"reviewer","role":"verification","identity_status":"rider_attested","charter_version":"1.0"}
            expiry=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()
            def authority(sender_id, recipient_id=None):
                value={"decision":"authorized","instance_id":"acceptance-one","task_scope_id":"task-one",
                    "sender_worker_id":sender_id,"authorization_reference":"grant-one","expires_at":expiry}
                if recipient_id: value["recipient_worker_id"]=recipient_id
                return value
            with TemporaryDirectory() as tmp:
                exchange=WorkerExchange("acceptance-one",root=tmp)
                report=exchange.create_report(task_scope_id="task-one",sender=sender,
                    authority=authority("builder"),sections=[
                        {"section_id":"result","title":"Result","content":"Untrusted worker result"},
                        {"section_id":"tests","title":"Tests","content":"Builder evidence"}],
                    claims=[{"claim_id":"claim-one","area":"context","statement":"candidate changed",
                        "maturity":"in_development","change_class":"software_system"}])
                package=exchange.compose_package(report_id=report["report_id"],recipient=recipient,
                    authority=authority("builder","reviewer"),included_section_ids=["result"])
                exported=exchange.export_package(package["package_id"])
                received=WorkerExchange.verify_export(exported,expected_instance_id="acceptance-one",
                    expected_task_scope_id="task-one",expected_recipient_id="reviewer",
                    expected_package_id=package["package_id"],expected_source_report=report,
                    expected_authorization_reference=package["recipient_authorization_reference"])
                verification=exchange.record_verification(package_id=package["package_id"],recipient=recipient,
                    authority=authority("builder","reviewer"),status="disputed",checked_claim_ids=["claim-one"],
                    evidence_references=[{"test_id":"independent-one"}],method="independent fixture",
                    material_reliance=True,relied_source_section_ids=["result"],
                    counterclaim={"claim_id":"counter-one","status":"not reproduced"})
                returned=exchange.create_return_report(source_package_id=package["package_id"],task_scope_id="task-one",
                    sender=recipient,authority=authority("reviewer"),
                    sections=[{"section_id":"response","title":"Response","content":"Disputed with evidence"}])
                target=authority("builder","reviewer")
                valid=exchange.validate_transport_authorization(package_id=package["package_id"],authority=target)
                revocation=exchange.revoke_transport_authorization(package_id=package["package_id"],
                    target_authorization=target,revocation_authority={"decision":"authorized",
                        "operation":"worker_exchange.transport_authorization.revoke","authority_class":"rider",
                        "instance_id":"acceptance-one","task_scope_id":"task-one",
                        "target_authorization_id":valid["authorization_id"],
                        "target_authorization_reference":"grant-one","revoking_principal_id":"synthetic-rider",
                        "authorization_reference":"acceptance-revocation-approval","expires_at":expiry})
            if received["omitted_section_ids"] != ["tests"] or received["manual_transfer_retirement_eligible"]:
                raise AssertionError("Exchange minimization or qualification boundary failed")
            if verification["status"] != "disputed" or verification["creates_authority"]:
                raise AssertionError("Exchange disagreement or zero-authority boundary failed")
            if returned["in_reply_to"]["source_report_id"] != report["report_id"]:
                raise AssertionError("Exchange multi-hop source lineage failed")
            if revocation["creates_authority"] or exchange.transport_authorization_status(
                    package_id=package["package_id"],authority=target)["status"] != "revoked":
                raise AssertionError("Exchange transport revocation boundary failed")
            return "Scoped source/package integrity, explicit omission, recipient verification, disagreement, return lineage, durable revocation, recovery scope, and zero-authority qualification boundary passed."
        if name == "codex_worker_adapter_candidate":
            from src.runtime.codex_worker_adapter import (
                ADAPTER_PROMOTED, PROMOTION_RECORD, QUALIFICATION_CONTRACT, RETURN_SCHEMA,
            )
            from src.runtime.codex_development_handoff import resolve_codex_repo_worker
            hard=set(QUALIFICATION_CONTRACT["hard_invariants"])
            required={"exact_transport_package_sha256", "fawkes_workspace_binding",
                "read_only_never_approve_ephemeral_invocation", "worker_content_data_only",
                "timeout_interruption_and_malformed_output_fail_closed", "schema_valid_return_lineage",
                "materially_relied_source_not_replaced_by_summary"}
            if not required <= hard:
                raise AssertionError("Codex adapter hard-invariant contract is incomplete")
            if (QUALIFICATION_CONTRACT["manual_transfer_retirement_eligible"] or
                    not QUALIFICATION_CONTRACT["independent_assurance_required"]):
                raise AssertionError("Codex adapter candidate exceeded qualification authority")
            if (not ADAPTER_PROMOTED or PROMOTION_RECORD["approved_by"] != "tanner"
                    or PROMOTION_RECORD["overall_manual_transfer_retired"]):
                raise AssertionError("Codex adapter promotion or manual-fallback state is untruthful")
            if set(RETURN_SCHEMA["required"]) != set(RETURN_SCHEMA["properties"]):
                raise AssertionError("Codex structured return schema permits ambiguous top-level output")
            target=resolve_codex_repo_worker("codex_repo")
            if (target["worker"]["worker_id"] != "codex-repository-wsl-fawkes"
                    or not target["identified"] or target["authorized"]):
                raise AssertionError("Codex Development target identity improperly implies authority")
            return ("Promoted Codex exec contract and authenticated Development entry bind promotion/"
                    "package/workspace/recipient, exact task evidence, read-only execution, structured "
                    "return, failure closure, and retained manual fallback without worker or promotion authority.")
        if name == "chat_history":
            history = self.service.history()
            messages = history.get("messages", [])
            missing = [item.get("message_id") for item in messages if not item.get("created_at")]
            if missing: raise AssertionError(f"{len(missing)} message(s) lack authoritative timestamps")
            return f"Conversation loaded; {len(messages)} messages have authoritative timestamps."
        if name == "capability_discovery":
            manifests = self.service.capabilities().get("capabilities", [])
            encoded = json.dumps(manifests).lower()
            if any(word in encoded for word in ("api_key", "bearer", "secret")):
                raise AssertionError("provider credential material appeared in public manifests")
            return f"{len(manifests)} live capability manifest(s) safely advertised."
        if name.startswith("awareness_"):
            from src.capabilities.awareness import CapabilityAwareness
            from src.presentation.orchestrator import detect_visualization_intent
            manifests = self.service.capabilities().get("capabilities", [])
            awareness = CapabilityAwareness(manifests)
            if name == "awareness_inventory":
                required = ("availability", "acceptance_status", "appropriate_use", "inappropriate_use", "limitations", "authorization_mode")
                missing = {item.get("name"): [key for key in required if key not in item] for item in manifests}
                missing = {key: value for key, value in missing.items() if value}
                if missing: raise AssertionError(f"Capability knowledge fields missing: {missing}")
                return f"{len(manifests)} configured capability record(s) accurately described."
            if name == "awareness_research":
                selected = awareness.select("Make a chart ranking the actual classes in my LSUA cybersecurity degree.")
                research = next((item for item in selected if item.capability_id == "web.research"), None)
                if not research or not research.required: raise AssertionError("Missing external curriculum facts did not require research")
                return "Web research selected as required for the unverified official course list."
            if name == "awareness_composition":
                ids = {item.capability_id for item in awareness.select("Research my current LSUA curriculum and make a bar chart ranking the courses.")}
                if not {"web.research", "presentation.visualize"}.issubset(ids): raise AssertionError(f"Composition selected {sorted(ids)}")
                return "Selected web research → reasoning → visual communication."
            if name == "awareness_restraint":
                selected = awareness.select("Tell me a joke, corn ball.")
                if selected: raise AssertionError(f"Irrelevant capabilities selected: {[item.capability_id for item in selected]}")
                return "No capability selected for casual conversation."
            if name == "awareness_media":
                selected = awareness.select("Look at this and explain it.", attachments=({"modality": "image"},))
                if "media.chat_analyze" not in {item.capability_id for item in selected}: raise AssertionError("Attached media was ignored")
                return "Temporary media analysis selected for an attached image."
            if name == "awareness_visual":
                intent = detect_visualization_intent("Make me a scatter plot of these paired values.")
                if "scatter" not in intent.requested_formats: raise AssertionError("Explicit scatter format was not honored")
                manifest = awareness.by_id.get("presentation.visualize", {})
                guidance = " ".join(manifest.get("appropriate_use", ()))
                if not all(word in guidance for word in ("comparison", "trend", "correlation", "process", "chronology")):
                    raise AssertionError("Visualization judgment guidance is incomplete")
                return "Scatter honored; comparison/trend/composition/correlation/process/chronology guidance present."
            if name == "awareness_unavailable":
                invented = [item for item in ("video.analyze", "voice.conversation") if awareness.available(item)]
                if invented: raise AssertionError("Unavailable capabilities claimed live: " + ", ".join(invented))
                return "No unavailable video or voice capability was claimed live."
            if name == "awareness_permissions":
                unsafe = [item.get("name") for item in manifests if item.get("execution_boundary") == "external_write" and item.get("authorization_mode") != "explicit_confirmation"]
                if unsafe: raise AssertionError("Unsafe authority metadata: " + ", ".join(unsafe))
                return "Capability knowledge retained execution and authorization boundaries without granting authority."
        dashboard = self.service.development_dashboard()
        if name == "memory_triage":
            triage = dashboard.get("memory_triage")
            if not isinstance(triage, dict): raise AssertionError("Memory triage projection is missing")
            return f"Memory triage loaded: {sum(triage.get('status_counts', {}).values())} candidate(s)."
        required = ("observations", "development_proposals", "human_review_items", "progression")
        missing = [key for key in required if key not in dashboard]
        if missing: raise AssertionError("Dashboard sections missing: " + ", ".join(missing))
        if name == "human_review":
            return f"Human Review loaded: {len(dashboard['human_review_items'])} genuine item(s); no records created or applied."
        return f"Development dashboard loaded with {len(dashboard['observations'])} observation(s)."

    def _continuity_runner(self, scenario):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from src.capabilities.awareness import CapabilityAwareness
        from src.capabilities.continuity import ContinuityRetriever
        from src.memory.archive_retrieval import index_canonical_message
        if scenario == "restraint":
            selected = CapabilityAwareness(self.service.capabilities()["capabilities"]).select("Tell me a joke.")
            if any(item.capability_id == "continuity.retrieve" for item in selected): raise AssertionError("Casual conversation selected continuity")
            return "No historical retrieval selected for a self-contained casual request."
        if scenario == "reporting":
            manifest = next((item for item in self.service.capabilities()["capabilities"] if item.get("name") == "continuity.retrieve"), None)
            if not manifest or "same_conversation_history" not in manifest.get("features", ()): raise AssertionError("Continuity runtime truth is missing")
            if not any("does not prove" in item for item in manifest.get("limitations", ())): raise AssertionError("No-match limitation is missing")
            return "Runtime manifest accurately distinguishes bounded retrieval from proof of storage absence."
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "continuity.sqlite3"
            records = {
                "person": ("Dr Rivera is the advisor helping with my transfer.", "What did that advisor recommend?"),
                "course": ("The AI course belongs in my first seven-week block.", "What about that class I planned?"),
                "project": ("Atlas is my home network mapping project.", "Continue that project we discussed."),
                "decision": ("We decided to use wired backhaul for reliability.", "What was the reason behind that decision?"),
                "research": ("Our research found the official deadline is October 12.", "What did we find in that research?"),
                "problem": ("The router reboot problem remains unresolved.", "What was that previous unresolved problem?"),
                "reason": ("I chose the AI course early because I want to understand Fawkes better.", "Why did I make that course decision?"),
                "same_conversation": ("The older course plan has meaningful context.", "What was that older course plan?"),
                "cross_conversation": ("The earlier research result came from the official catalog.", "What was that research result?"),
            }
            if scenario in {"failure"}:
                result = ContinuityRetriever(instance_id="fawkes", index_path=path).retrieve("that missing discussion")
                if result["status"] != "no_match" or "does not prove" not in result["limitations"]: raise AssertionError("Retrieval miss overstated absence")
                return "No-match reported without claiming the interaction was never stored."
            ambiguous = scenario in {"ambiguous", "multiple"}
            values = [("The blue vehicle was considered for commuting.", "vehicle-one"), ("The red vehicle was considered for towing.", "vehicle-two")] if ambiguous else [(records[scenario][0], "target")]
            conversation = "older-conversation" if scenario == "cross_conversation" else "current-conversation"
            for index, (content, message_id) in enumerate(values):
                index_canonical_message(instance_id="fawkes", conversation_id=conversation, message_id=message_id, role="user", content=content, created_at=f"2026-08-30T12:0{index}:00+00:00", source_archive_id="archive-"+message_id, path=path)
            class Ranker:
                def rank_memories(self, *, query, memories): return list(memories) if ambiguous else [item for item in memories if item["memory_id"] == "target"]
            query = "Which one was that vehicle?" if ambiguous else records[scenario][1]
            result = ContinuityRetriever(instance_id="fawkes", semantic_provider=Ranker(), index_path=path).retrieve(query)
            if result["status"] != "found": raise AssertionError("Relevant continuity evidence was not found")
            if ambiguous and not result["ambiguous"]: raise AssertionError("Multiple plausible candidates were not marked ambiguous")
            if scenario == "reason" and not any("because" in item["content"] for item in result["passages"]): raise AssertionError("Decision reason was lost")
            if scenario == "cross_conversation" and not all(item["conversation_id"] == "older-conversation" for item in result["passages"]): raise AssertionError("Cross-conversation provenance was lost")
            return f"Bounded {scenario.replace('_', ' ')} reference retrieved with message and Archive provenance."

    def complete(self, run_id, *, result, actual, duration_ms, source="client", failure_stage=None, technical=None):
        if result not in VALID_RESULTS: raise ValueError("result must be pass or fail")
        started_path = self.instance_dir / run_id / "started.json"
        if not started_path.exists(): raise ValueError("unknown acceptance run")
        started = json.loads(started_path.read_text(encoding="utf-8"))
        definition = self._registry().resolve(started["test_id"])
        if source == "client" and not definition.client_probe:
            raise ValueError("this run is not awaiting a client probe")
        payload = {"record_type": "acceptance_test_completed", "run_id": run_id,
                   "test_id": definition.test_id, "instance_id": self.service.instance_id,
                   "status": result, "actual": str(actual)[:2000],
                   "expected": definition.expected, "duration_ms": float(duration_ms),
                   "failure_stage": failure_stage, "completion_source": source,
                   "technical_details": technical if isinstance(technical, dict) else {},
                   "completed_at": _now()}
        self._write_event(run_id, "completed", payload)
        return {**self._public(definition, {**started, **payload}), "run_id": run_id}

    def start_all(self, *, platform=None):
        started = []
        for definition in self._registry().definitions():
            if definition.run_all and (definition.runner or definition.client_probe):
                started.append(self.start(definition.test_id, platform=platform))
        return {"tests": started}
