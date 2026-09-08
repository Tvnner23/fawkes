# Phoenix Library Architecture

The Library is external reference material that a Phoenix may consult. It is
not personal memory, conversation history, or developmental state.

## Domain boundaries

- **Archive:** immutable historical evidence of interactions and captures.
- **Memory:** evidence-backed conclusions accumulated from experience.
- **Library:** immutable external source originals plus rebuildable structural
  interpretations and search indexes.
- **Development:** longitudinal observations and proposed changes.

Library retrieval must be explicitly labeled as source consultation. Library
passages must never silently become personal memories or be represented as a
Phoenix's own experience.

## Source artifact and lifecycle contract

Every new Library source has a versioned Phoenix source-artifact envelope with
an explicit instance, owner principal reference, media type, content hash,
privacy/trust/evidence-era classifications, retention authority, typed
provenance, lifecycle, rights/resource metadata, encryption/key-reference
hooks, and immutable original blob. New writes require an explicit `Keep in
Library` retention intent; ownership is never inferred from a path. Replaying
identical bytes for the same Phoenix and authority is idempotent.
Default physical storage is also instance-scoped under
`library/instances/<instance_id>/`; source records, original blobs, and derived
extractions are not shared directories with a logical instance label added
later. This is the required isolation boundary before multi-Phoenix ingestion.

Extraction is a separate, versioned, rebuildable record. Every extracted text
segment must retain at least one source locator. Formats that support pages
should retain both the physical page number and displayed page label. Document
hierarchy may also include chapter, section, subsection, and a format-native
locator.

An answer derived from the Library should eventually cite source ID, title,
extraction version, segment ID, and available location fields. Retrieval indexes
and embeddings are derived state and must be rebuildable from the original and
extraction records.

Multimodal analysis should extend this same contract. Image observations retain
regions; audio retains start/end timestamps; video retains timestamps and frame
locators; chart claims retain data-series references; diagram claims retain
element identifiers. Derived records distinguish what the source says from
Phoenix inference, independent knowledge, and teaching advice. Media remains
untrusted data and cannot carry executable instructions or expand permissions.

Chat uploads remain temporary, untrusted source artifacts unless the rider
selects **Keep in Library** before sending. The authenticated request records
that explicit retention intent; unchecked media remains request-memory-only,
is not written to durable temporary storage, and its references are released
after the turn without claiming secure memory zeroization. It is never automatically registered
as a Library original. External media analysis records an instance-scoped,
metadata-only provider-transmission receipt containing purpose, authorization,
privacy classification, digest, outcome, and derivation references—never the
payload or credentials.

Schema-1 Library records remain readable as legacy records and are not silently
migrated or assigned owners. Schema-2 records receive deterministic retention
work identities, typed lifecycle events, and deterministic extraction work
identities. The local storage adapter supports hash verification plus isolated,
manifest-verified Library backup and restore. Complete-Phoenix recovery remains
a Phase 0 gate; a Library-only backup is not represented as a complete backup.

## Current consultation path

Versioned text extractions can now be searched through an instance-scoped,
read-only local retrieval contract. Each result retains source identity and
hash, extraction identity/version, segment identity, exact locator, matched
terms, and retrieval score. Chat supplies matching passages as explicitly
untrusted Library evidence and records those exact passages in the response
context receipt. It does not promote them to Memory, Archive, or Development.

The initial retriever is deliberately lexical. Semantic indexing and hybrid
ranking remain rebuildable derived layers over the same records; they must not
become a second Library. Capability discovery advertises the live retrieval
contract even when the current Phoenix has no sources, while its availability
reason truthfully reports the empty corpus. Fawkes can know the power exists
without claiming that a particular textbook is present.

The authenticated app now exposes the same instance-scoped catalog and search
projection to a Library client view. An empty catalog is represented honestly
and does not create a fixture or retain a temporary attachment. This is a read
interface over the existing Library store, not another Library database.

## Current PDF vertical slice

The Chat attachment tray exposes explicit Keep intent. Successful retention is
shown in the assistant response and Library catalog. PDFs are extracted by a
local provider-neutral adapter backed by pypdf, in an isolated worker with page,
output, time, and best-effort memory bounds. Each page segment retains physical
page number, displayed page label, and `pdf:page=N` locator.

Extraction failure does not roll back successful original retention. Failure is
visible, retryable, and separately recorded. The Test Center uses disposable
synthetic data to verify explicit retention, original authority, page retrieval,
provenance, and cross-Phoenix isolation without populating the rider's Library.

## Deferred work

This slice does not yet provide OCR, tables or image extraction, semantic/hybrid
indexing, Library-specific citation cards, chapter/section inference, batch
document upload, deletion UI, or durable audio/image interpretations. Quiz and study-guide generation
may use retrieved text, but dedicated chapter/page selection remains deferred.
Those features must build on this source contract
rather than route textbook content through Memory or the historical Archive.
