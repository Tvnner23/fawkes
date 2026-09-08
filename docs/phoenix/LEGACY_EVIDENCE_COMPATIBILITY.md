# Legacy Archive and Memory Compatibility

Status: non-destructive compatibility policy and rebuildable review projection
implemented; live Unified Planner integration remains gated.

Compatibility version: `legacy-private-compatibility-v1`.

## Derived state, not canonical classification

Legacy Archive and Memory evidence may lack modern privacy or owner-principal
metadata because it predates those schemas. When existing provenance proves
current Phoenix ownership and primary-rider continuity, the compatibility layer
can derive `legacy_private_unclassified` at retrieval time.

This is an eligibility projection. It is never written into Archive or Memory
and does not claim the historical record originally carried a privacy label.
Explicit modern metadata always wins and disables compatibility inference.

Compatibility requires native Archive or Memory domain, exact current Phoenix
scope, valid original-evidence provenance, a recognized scoped continuity-
ownership basis, known source schema, and no foreign, shared, restricted,
synthetic-inappropriate, revoked, quarantined, suppressed, unauthorized, or
conflicting ownership flag. Missing or uncertain ownership and malformed
provenance fail closed. Unscoped legacy data is not silently assigned to Fawkes.

## Authority and audit

Compatibility can support only automatic retrieval into the authenticated
owning rider's private Fawkes context. Provider transmission remains separate.
It never grants disclosure, cross-principal access, retention, Memory promotion,
authority conversion, identity classification, or privacy reclassification.

Decisions preserve compatibility version, source reference, original schema
status, derived classification, ownership basis, migration/review status,
provider decision, and selection reason without evidence bodies.

## Rebuildable review projection

The deterministic metadata-only rider review inventory reports:
`compatibility_eligible`, `needs_review`, `explicit_classification_present`,
`ownership_uncertain`, and `blocked`. It is rebuildable and declares that no
canonical records were modified. No classification-write workflow exists yet.

## Live integration boundary

Current Archive, Memory, and Library retrievers rank before unified evidence
eligibility. Semantic Memory ranking may transmit candidates to a provider.
Putting the planner after those operations would violate eligibility-before-
ranking/provider processing.

Safe activation requires two-stage adapters: enumerate metadata and evaluate
eligibility locally, then rank or transmit only eligible candidates. Until
those adapters exist, ordinary Chat retains its established retrieval path and
the compatibility capability remains `partial`.

The two-stage production adapters now satisfy eligibility-before-ranking. Live
Chat remains separately gated on pre-response-call evidence-level provider
receipts and rollback/equivalence integration.
