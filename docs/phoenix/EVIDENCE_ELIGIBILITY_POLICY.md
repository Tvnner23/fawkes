# Production Evidence Eligibility Policy

Status: Phase 7 policy implemented on the default served planner Chat path;
legacy Archive and Memory gaps use the non-mutating compatibility policy.

Policy version: `production-evidence-eligibility-v1`.

## Separate authorities

The policy makes five independent decisions:

1. storage/access authority;
2. automatic authenticated primary-rider private-Chat eligibility;
3. inference-provider transmission eligibility;
4. external/tool disclosure eligibility;
5. cross-Phoenix or cross-rider disclosure eligibility.

Private-context eligibility never implies disclosure, transmission through an
unrelated capability, cross-principal access, privacy downgrade, or promotion
to another evidence authority.

Every decision requires exact Phoenix ownership, owner principal, privacy
classification, evidence/domain/authority identity, an original-evidence
reference, valid provenance, enabled automatic use, and authorized capability.
Unknown or missing metadata fails closed for automatic use. Storage access is
still represented separately: evidence does not disappear merely because its
automatic-use metadata is incomplete.

## Privacy behavior

- `standard` and `potentially_private` evidence may enter an authenticated
  owning rider's private context when the capability and provider path are
  authorized.
- `highly_private` requires an explicitly relevant sensitive category supplied
  by the request/capability boundary or a scoped rider grant. Generic lexical
  similarity is not a relevance authorization.
- `restricted` requires an evidence-specific automatic-use grant.
- Inherited history is unconditionally disabled for automatic retrieval in
  policy v1. Grants cannot bypass the real-corpus qualification and activation
  gate.

External-provider processing is a separate decision. Standard and potentially
private evidence require an authorized private-context provider path. Highly
private and restricted evidence additionally require a privacy-class or
evidence-specific provider grant. Local-only use requires no provider
transmission. External and cross-principal disclosure require their own
evidence-specific grants and are denied otherwise.

## Audit and enforcement

Decisions contain stable reason codes, policy version, source domain, authority
class, privacy classification, and a digest of the original evidence reference.
They never contain evidence text.

The Unified Retrieval Planner can apply the policy before context selection.
Selected candidate envelopes retain the decision; exclusions retain only
identity and policy metadata. Context receipt schema v7 supports sanitized
planning audits. Flight records remove candidate/exclusion content while
preserving policy, eligibility, allocation, and replay evidence.

The Provider Privacy Gateway accepts an eligibility decision, refuses denied
transmission, and records policy version/reason without payload. Existing
provider call sites that do not yet supply evidence-level decisions remain a
declared limitation rather than being silently reclassified.

## Current integration gate

The approved compatibility policy now derives `legacy_private_unclassified`
for trustworthy scoped same-Phoenix Archive/Memory evidence without rewriting
it. Explicit modern metadata wins; uncertain, foreign, malformed, restricted,
revoked, quarantined, shared, or otherwise ineligible evidence fails closed.
See [Legacy Archive and Memory Compatibility](LEGACY_EVIDENCE_COMPATIBILITY.md).

Ordinary Chat is not yet switched because current retrievers rank before
unified evidence eligibility, and semantic Memory ranking can transmit
candidates before an evidence-level provider decision. Production adapters
must enumerate and gate candidates locally before ranking/transmission.

The required two-stage adapters are now implemented. The remaining live-Chat
gate is enforcement at the final response-provider boundary: selected evidence
requires immutable per-evidence authorization receipts before the combined
prompt is transmitted, not an audit written afterward.

That content-addressed manifest/permit boundary is now implemented. Ordinary
Chat remains gated until its prompt builder consumes the permit before request
construction.
