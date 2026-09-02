"""Provider-neutral contracts for Phase 0 integrity and recovery operations."""

from src.capabilities.core import CapabilityDefinition
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract


STATE_AUDIT_DEFINITION = CapabilityDefinition(
    name="system.integrity_audit", version="1.0",
    description="Audit durable Phoenix ownership and integrity without modifying historical records.",
    effect="read_only_diagnostic", modalities=MultimodalCapabilityContract(
        input_modalities=("text",), output_modalities=("text",)),
    authority=AuthorityContract(actions=("read", "analyze"), execution_boundary="internal",
                                authorization_mode="pre_granted"),
    privacy_handling="instance_scoped_metadata_only",
    features=("ownership_audit", "legacy_unscoped_reporting", "integrity_findings"),
    appropriate_use=("verify Phoenix isolation", "inspect legacy ownership gaps"),
    inappropriate_use=("silently assign legacy ownership", "modify canonical Archive evidence"),
    limitations=("audit findings do not migrate records", "legacy records remain outside new ownership guarantees"),
    platform_support=("server", "development_test_center", "future_native_clients"),
    presentation_options=("text", "table"),
    provenance_requirements=("component", "record path or identifier", "ownership status"),
)

STATE_RECOVERY_DEFINITION = CapabilityDefinition(
    name="system.state_recovery", version="1.0",
    description="Create and verify isolated per-Phoenix complete-state recovery snapshots.",
    effect="internal_recovery_artifact", modalities=MultimodalCapabilityContract(
        input_modalities=("text",), output_modalities=("text",)),
    authority=AuthorityContract(actions=("read", "create"), execution_boundary="internal",
                                authorization_mode="explicit_confirmation"),
    privacy_handling="instance_scoped_private_backup_no_secrets",
    features=("verified_manifest", "isolated_restore", "rebuild_plan", "tamper_detection"),
    appropriate_use=("rider-approved backup", "isolated disaster-recovery verification"),
    inappropriate_use=("cross-Phoenix restoration", "restoring over live non-empty state"),
    limitations=("normal Chat cannot trigger restore", "encryption at rest requires a future configured key provider"),
    platform_support=("server", "development_test_center"),
    dependencies=("writable backup destination",),
    provenance_requirements=("backup manifest", "file digests", "restore receipt"),
)
