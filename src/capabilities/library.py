"""Provider-neutral capability contract for consulting one Phoenix's Library."""

from src.capabilities.core import CapabilityDefinition
from src.capabilities.multimodal import AuthorityContract, MultimodalCapabilityContract


LIBRARY_SEARCH_DEFINITION = CapabilityDefinition(
    name="library.search",
    version="1.0",
    description="Search durable rider-retained reference sources with exact source locators.",
    effect="read_only",
    modalities=MultimodalCapabilityContract(
        input_modalities=("text",), output_modalities=("text",)
    ),
    authority=AuthorityContract(
        actions=("read", "analyze"),
        execution_boundary="internal",
        authorization_mode="pre_granted",
    ),
    privacy_handling="instance_scoped_rider_visible",
    features=("lexical_segment_retrieval", "source_locators", "versioned_extractions"),
    display_name="Library search",
    appropriate_use=("rider asks about retained textbooks or documents", "page/chapter/section lookup", "cross-reference retained sources"),
    inappropriate_use=("the source was only attached temporarily", "current public facts are better answered by web research"),
    limitations=("available only when this Phoenix has retained indexed sources", "current retrieval is lexical rather than full semantic textbook intelligence"),
    presentation_options=("text", "table", "diagram"),
    dependencies=("instance-scoped retained source", "versioned extraction"),
    provenance_requirements=("source identity", "extraction version", "page/chapter/section locator when available"),
)

LIBRARY_CATALOG_DEFINITION = CapabilityDefinition(
    name="library.catalog", version="1.0",
    description="Inspect the current Phoenix's retained Library source catalog without changing it.",
    display_name="Library catalog", effect="read_only",
    modalities=MultimodalCapabilityContract(input_modalities=("text",), output_modalities=("text",)),
    authority=AuthorityContract(actions=("read",), execution_boundary="internal", authorization_mode="pre_granted"),
    privacy_handling="instance_scoped_rider_visible",
    features=("source_listing", "retention_status", "source_identity", "source_artifact_lifecycle", "verified_backup_restore"),
    appropriate_use=("rider inspects retained sources", "determine whether a textbook is available"),
    inappropriate_use=("silently retain temporary attachments", "modify or delete retained originals"),
    limitations=("ingestion requires explicit rider retention intent", "catalog access does not imply extracted content is searchable"),
    platform_support=("server", "web", "future_native_clients"),
    presentation_options=("text", "table"), dependencies=("instance-scoped Library store",),
    provenance_requirements=("source id", "content digest", "original filename", "retention timestamp", "owner principal", "typed lifecycle event"),
)

LIBRARY_RETAIN_DEFINITION = CapabilityDefinition(
    name="library.retain", version="1.0",
    description="Retain an explicitly selected temporary rider attachment as an immutable Phoenix-scoped Library source.",
    display_name="Keep in Library", effect="durable_library_write",
    permissions=("library.retain",),
    modalities=MultimodalCapabilityContract(
        input_modalities=("document", "pdf", "image", "audio"),
        output_modalities=("text",),
    ),
    authority=AuthorityContract(
        actions=("read", "create"), execution_boundary="internal",
        authorization_mode="explicit_confirmation",
    ),
    privacy_handling="explicit_rider_retention_instance_scoped_original",
    features=("explicit_keep", "content_addressed_original", "deduplication", "typed_lifecycle", "temporary_to_durable_provenance"),
    appropriate_use=("rider explicitly selects Keep in Library for an attachment",),
    inappropriate_use=("silently retaining a casual attachment", "inferring retention from repeated use"),
    limitations=("retention does not create Memory", "provider analysis authorization is separate"),
    platform_support=("server", "web", "future_native_clients"),
    presentation_options=("retention_status",),
    dependencies=("authenticated rider request", "Phase 0 artifact store"),
    provenance_requirements=("temporary artifact digest", "rider principal", "retention intent", "lifecycle events"),
)

LIBRARY_EXTRACT_DEFINITION = CapabilityDefinition(
    name="library.extract", version="1.0",
    description="Create a versioned, rebuildable, page-aware local extraction from a retained PDF.",
    display_name="Library document extraction", effect="rebuildable_library_derivation",
    permissions=("library.extract",),
    modalities=MultimodalCapabilityContract(input_modalities=("pdf",), output_modalities=("text",)),
    authority=AuthorityContract(actions=("read", "analyze", "create"), execution_boundary="internal", authorization_mode="pre_granted"),
    privacy_handling="local_instance_scoped_no_provider_transmission",
    features=("physical_pages", "displayed_page_labels", "versioned_extraction", "bounded_worker", "rebuildable_provenance"),
    appropriate_use=("retained PDF needs searchable text", "rider asks for a page or section in a retained document"),
    inappropriate_use=("source was not explicitly retained", "claiming OCR for scanned pages"),
    limitations=("image-only PDFs require future OCR", "chapter/section detection is not yet inferred", "maximum 2000 pages and bounded extracted text"),
    platform_support=("server", "web", "future_native_clients"),
    presentation_options=("text", "page_locator"),
    dependencies=("pypdf local adapter", "immutable retained original"),
    provenance_requirements=("source digest", "extractor identity/version", "physical page", "displayed page label"),
)
