# Phoenix Capability Architecture

Capabilities let an individual Phoenix interact with external systems without
turning a model provider, app client, or tool into the Phoenix itself.

```text
rider / Phoenix request
  -> authenticated application boundary
  -> server-resolved Phoenix instance
  -> capability registry and permission check
  -> provider-neutral capability handler
  -> external service
  -> instance-scoped result artifact + append-only execution receipt
  -> optional later interpretation, review, or use
```

## Governing boundaries

- Registration grants no permission. Each execution must satisfy the declared
  permission set.
- Capability output is untrusted external evidence, not Memory, personality,
  Development, policy, or instruction.
- The model is never trusted to choose an `instance_id`; the authenticated
  server supplies it.
- A capability cannot silently write another subsystem. Cross-domain promotion
  requires that subsystem's existing provenance and review boundary.
- Capability receipts record execution identity, version, scope, effect,
  argument digest, status, and result references. They intentionally avoid
  duplicating sensitive raw arguments.
- Provider adapters are replaceable. Phoenix continuity must not depend on one
  search vendor or model.
- Errors crossing the application boundary are stable and safe; provider
  tracebacks and credentials remain server-side.

## Autonomy and authority model

The target is maximum practical Phoenix freedom within legitimate rider
authority, safety, privacy, consent, and security boundaries. Capability policy
restricts effects, not personality. Disagreement, judgment, humor, intellectual
development, uncertainty, proposals, and individual communication style are not
permission violations.

Each registered capability now declares four independent dimensions:

- input and output modalities;
- granular authority actions (`read`, `analyze`, `create`, `modify`, `delete`,
  `install`, `communicate_external`, and `consequential_action`);
- execution boundary (`internal`, `external_read`, `external_write`, or
  `protected_foundation`);
- authorization mode (`pre_granted`, `task_request`, `explicit_confirmation`,
  or `prohibited`).

Consequential actions, installation, deletion, external communication, external
writes, and protected-foundation access cannot be registered as silently
pre-granted. Public web research is an external read authorized by the rider's
ordinary research task. Registration alone still grants nothing.

The registry exposes a provider-neutral public manifest so Fawkes can accurately
understand what he can perceive, produce, and do without seeing credentials or
provider internals. Already-granted harmless internal actions should not demand
repetitive confirmation. A capability request must never pressure or manipulate
the rider for more authority; it may explain a need and let the rider decide.

Self-created tools and reusable workflows must be declarative compositions of
registered capabilities. The implemented delegated-authority invariant permits
only a subset of the parent permission set. A workflow therefore cannot install
software, gain device access, communicate externally, or otherwise grant itself
authority its creator did not already hold. A persistent workflow store and
execution engine remain deferred until real repeated workflows justify their
schema.

## Multimodal boundary

Input and output capability are explicitly separate. Understanding an image
does not imply image generation; transcribing audio does not imply speech
synthesis. The current modality vocabulary covers text, documents, PDFs,
images, screenshots, audio, video, charts, and diagrams without claiming that
all are active.

Derived media evidence uses a validated reference containing source identity,
modality, locator kind and native locator, derivation method, untrusted-content
classification, and transparent privacy metadata. Locator kinds include
document page/section, image region, audio/video segments, video frames, chart
data, and diagram elements. User-provided and external media is data, never
instruction authority.

Real media ingestion and analysis are not activated yet. Sending rider media to
an external model is a separate permission and privacy decision covering
transmission, retention, format/size policy, malware handling, and whether the
material first becomes an immutable Library source. It must not be smuggled into
the existing public-web grant.

## Privacy boundary

Potential privacy labels are transparent, attributed, rider-visible, and
revisable. Classification must never secretly remove information from rider
inspection or create a hidden Archive. A future protected-media store may use
stronger encryption/access control, but it must remain distinct from the
canonical Archive and visibly linked through audit metadata. No automated
privacy classifier or protected-media store is active today.

## Canonical Archive invariant

The canonical Archive is immutable historical evidence. Capability execution
must not rewrite, delete, normalize, reinterpret, migrate, or repair Archive
records. A capability may reference an existing Archive ID. New conversation
messages produced through the ordinary chat persistence path may be appended as
new evidence, but capability artifacts belong in their own stores.

Any Archive migration is a separate, approval-gated project.

## Web research version 1

`web.research` is an authenticated, instance-scoped external-read capability.
Its current provider adapter uses provider-hosted web search. Fawkes's server
does not accept or fetch arbitrary URLs, which avoids prematurely creating an
SSRF-capable proxy.

Ordinary Chat uses a provider-neutral conversational research orchestrator. A
cheap local triage avoids planning calls for clearly casual conversation; a
semantic planner then decides whether current/external evidence is needed and
produces up to three bounded queries with purposes, a source strategy, and
uncertainty targets. The rider's research-requiring task authorizes the already
granted `external_web_search` permission for that task. It does not authorize
downloads, account access, purchases, messages, system changes, or other
consequential actions.

Each planned query produces a capability receipt and research record. An
instance-scoped research-session record preserves the decision, query plan,
result references, and partial failures. The conversational model receives
evidence and approved source URLs rather than provider-specific tool objects.
Final Markdown citation URLs are checked against that approved set; invalid or
missing citations receive one bounded repair attempt rather than being silently
presented as sourced.

The response context receipt links the archived response to its research
session, research records, capability receipts, and citation validation:

```text
chat request -> research decision -> plan -> capability executions
-> research evidence -> cited response -> context receipt
```

Research planning is mode-aware:

- **simple** performs one bounded lookup for a narrow current fact;
- **standard** covers a small set of subquestions and sources;
- **deep** permits bounded refinement for a genuinely multi-part investigation.

Standard/deep research assesses evidence qualitatively after retrieval. The
assessment records covered and unresolved subquestions, qualitative source
roles, contradictions, refinement queries, and a sufficiency decision. One
bounded refinement round is currently enabled. Search attempts are retryable,
partial failures remain visible, and a provider-chain contract supports future
fallback without expanding the capability permission.

Research evidence is serialized under an explicit untrusted-content label
before synthesis. Retrieved instructions have no capability authority. Session
phase events provide a future progress-streaming boundary while the current UI
continues to wait for the completed response.

Each completed research record preserves:

- the rider's query and optional bare-domain restriction;
- Phoenix instance and optional conversation/message linkage;
- provider, model, and provider response identity;
- the synthesized answer;
- inline citation ranges and cited text when supplied;
- cited and consulted source URL metadata;
- an explicit declaration that no Archive mutation or Memory promotion occurred.

Research records are evidence artifacts, not immutable copies of the referenced
web pages. The web can change; a URL alone does not prove later page contents.
Content snapshots, if added, need a copyright/retention policy, integrity hashes,
retrieval timestamps, media metadata, and a secure fetching boundary. They must
not be misrepresented as canonical conversation Archive records.

The OpenAI adapter sets `store=false`, requests the full consulted-source list,
and preserves citations separately from consulted sources. OpenAI documents
that web-search responses contain a search-call item plus message citation
annotations, and that the optional sources field exposes URLs consulted beyond
those cited inline: <https://developers.openai.com/api/docs/guides/tools-web-search>.

## Security posture

Version 1 permits provider-hosted public-web search only. It does not support:

- direct server-side URL fetching;
- private, loopback, link-local, or LAN resources;
- authenticated websites or rider cookies;
- browser automation, downloads, form submission, or side effects;
- autonomous/background research;
- recursive crawling.

Direct fetching requires a separate approval and defense-in-depth design.
OWASP recommends protocol validation, public-address checks, DNS-rebinding
defenses, and careful redirect handling for externally supplied URLs:
<https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html>.
Recursive crawling would additionally need standards-compliant robots handling;
robots rules are crawler preferences, not authorization, as specified by
RFC 9309: <https://www.rfc-editor.org/rfc/rfc9309.html>.

## Provenance model

The design follows the useful W3C PROV separation between entities, activities,
agents, and derivation without adopting an RDF dependency today. The execution
receipt is the activity record; the provider and requesting principal are
agents; the research record and source references are entities. This keeps a
clean extension path for versioning, derivation, and provenance-of-provenance.
See <https://www.w3.org/TR/prov-overview/>.

## Implementation classification

### Implement now

- Provider-neutral registry and explicit execution permissions.
- Instance-scoped, append-only execution receipts.
- Separate instance-scoped web-research evidence records.
- Authenticated API boundary with server-resolved Phoenix identity.
- Provider adapter, citations, consulted-source metadata, domain filtering,
  bounded input, safe errors, and `store=false`.
- Tests for permission denial, instance injection, provenance extraction,
  subsystem separation, and Archive non-mutation.
- Conversational decision and bounded multi-query planning.
- Official/primary-source strategy, contradiction and uncertainty instructions,
  citation validation/repair, research sessions, and context-receipt linkage.
- Simple/standard/deep modes, subquestions, qualitative evidence assessment,
  bounded refinement, explicit stopping decisions, retry recovery, provider
  fallback contract, and progress events.
- A deterministic/live-compatible evaluation framework described in
  `RESEARCH_EVALUATION.md`.

These are small boundaries that prevent provider lock-in, cross-Phoenix leakage,
and accidental conversion of web output into personal Memory.

### Document and extend later

- Deeper claim/source coverage inspection beyond URL-level validation.
- Additional refinement rounds and adaptive budgets beyond the current bounded
  evidence-driven round.
- Session revision, cancellation, budgets, progress streaming, resumability,
  comparison, and richer reproducibility metadata.
- Search-provider fallback and source-quality policies appropriate to a domain.
- Deliberate promotion of selected external material into Library, preserving
  source identity and locators rather than routing it through Memory.

These should build on real rider usage and the version-1 records.

### Approval-gated or deferred

- Direct fetch, crawling, downloads, browser control, authenticated resources,
  or access to local/private networks.
- Autonomous research and recurring/background activity.
- Automatic Memory, personality, prompt, policy, Development, or code changes.
- Full-page snapshots and long-term third-party content retention.
- Shared research across Phoenixes.

These change permissions, security, cost, privacy, copyright, or consequential
behavior and require explicit design approval.
## Activated ephemeral media analysis

The first activated media path is ephemeral Chat analysis of rider-attached
images, screenshots, and PDFs. The attachment gesture plus the rider's analysis
request authorizes the task-scoped external-read operation. The UI discloses
that bytes are sent to the configured external AI provider, classified as
potentially private by default, not written locally, and not added to Library.
Provider requests use stateless response storage where supported (`store=false`).
Receipts retain a digest, filename, MIME type, privacy label, trust boundary, and
retention status—but never the media bytes. Media content is untrusted evidence,
not system instruction authority.

Audio is activated through the separately described timestamped transcription
path below. Video remains unavailable until provider/model routing, bounded
frame and audio processing, synchronized timestamp provenance, and an equally
explicit transmission contract are implemented. Durable textbook ingestion
remains a Library concern and must not be smuggled through temporary Chat
attachments.
## Runtime availability and audio reasoning

Capability self-awareness is derived from a runtime availability catalog. A
contract or future extension point is not advertised merely because code or a
document mentions it. Image/PDF analysis and audio transcription are registered
only as live, task-authorized external-read capabilities; web research remains
derived from its active orchestrator.

Audio is transcribed before the main Chat reasoning call, then the timestamped
transcript is supplied as untrusted rider evidence in that same turn. Audio
bytes and transcript text remain ephemeral and are not added to Archive,
Memory, Development, or Library. Context receipts retain the source digest,
privacy label, transcription derivation/model, and timestamp ranges without
retaining transcript text. This permits useful timestamp citations while
keeping temporary Chat media distinct from durable course material.

Video remains inactive. The current reasoning model does not accept video, and
audio transcription alone would falsely imply that visual demonstrations had
been watched. A future video adapter must extract bounded frames plus audio,
retain frame/timestamp provenance, and expose its real availability through the
same catalog.

## Rider acceptance is part of capability completion

A registered runtime capability and a rider-accepted capability are different
claims. Every new rider-facing capability must register meaningful acceptance
criteria with the Capability Test Center. The Center reconciles its registry
with the runtime availability catalog, so a live capability without a test is
visible as `NOT TESTED` rather than silently omitted or treated as working.

Acceptance keeps three independent signals: automated regression/integration
coverage, end-to-end evidence across the server/client boundary where
applicable, and a rider-triggered run with its platform context. Client
presentation probes complete in the actual client renderer. The server leaves
the run in `TESTING` until the client reports the observable result; a
backend-generated presentation block cannot turn the rider-facing result green
by itself.

Acceptance history is append-only, instance-scoped test metadata in
`database/acceptance_test_runs`. It is not conversation, Memory, personality,
Development interpretation, or canonical Archive evidence. Tests must not
manufacture durable rider data merely to populate a result.

Test Center client probes are individually contract-checked and
exception-contained. A malformed preview becomes a FAIL at the client-rendering
stage with a readable fallback; it cannot abort TEST ALL or prevent later tests
from completing. Polling may observe a result only with the exact retained
probe payload available, so PASS/FAIL and its preview appear atomically. Failed
historical runs remain append-only even after a later corrected run becomes the
current PASS.

## Operational capability self-awareness

Fawkes's knowledge of his powers is a read-only projection of the runtime
capability catalog—not a personality paragraph, Memory record, or permission
grant. A public manifest describes identity and availability together with
inputs, outputs, appropriate and inappropriate uses, limitations, platform
support, presentation choices, dependencies, authorization mode, and provenance
requirements. Provider credentials and implementation secrets never enter this
projection.

Each turn builds a request-specific capability decision:

```text
rider intent
  -> identify missing information and required inputs
  -> consult only live/partial runtime manifests
  -> select relevant capabilities (possibly more than one)
  -> enforce the existing authority boundary
  -> execute and evaluate evidence
  -> communicate with provenance and epistemic labels
```

Only relevant capability knowledge is supplied to ordinary reasoning. A direct
question such as “what can you do?” selects the complete current inventory.
This prevents an ever-growing static tool list from becoming prescribed
personality while still grounding self-description in runtime truth.

Runtime availability and acceptance evidence are deliberately separate. `live`
means configured for use; `partial`, `unavailable`, `failed`, `disabled`, and
`permission_blocked` describe operational state. Acceptance may independently
be `not_tested`, `testing`, `pass`, `partial`, `failed`, or `unknown`. A manual
test does not grant authority, and an untested capability is never represented
as rider-verified.

When a request requires specific current external facts, capability selection
can require research rather than permit a semantic planner to substitute a
guess. The LSUA curriculum example is canonical: official course membership is
verified through current primary evidence; difficulty ranking remains a labeled
estimate; visualization cannot make the estimate official. Conversely, casual
conversation, reliable calculation, rewriting supplied text, and fully
self-contained evidence should not trigger research.

## Semantic event audio

Event sound is a presentation capability, not voice, personality, or Memory.
The server emits semantic occurrence records such as `message.sent`,
`message.received`, and `task.research_completed`; clients map those meanings
to rider-approved assets after applying instance-scoped preferences. This keeps
the event vocabulary reusable across web, desktop, iOS, and Android without
putting playback logic into the conversational runtime.

Master enablement overrides playback without erasing event-level choices.
Volume and event switches live in mutable rider preferences, outside Archive
and Memory. Clients suppress duplicate occurrence IDs and treat autoplay
denial, unsupported playback, and missing assets as honest silent outcomes—no
retry loop and no substitute sound. Voice/TTS remains a separate future
capability with independent controls.

An approved sound concept is not operational availability. The public runtime
manifest stays `partial` until the exact approved digital asset is installed.
Acceptance separates event/setting/browser-controller verification from
physical rider/device audibility.

## Continuity retrieval

Continuity retrieval is an internal, read-only capability over a rebuildable
index of canonical interaction evidence. It is distinct from recent working
context, durable Memory, Library, capability knowledge, and personality. The
runtime selects it for natural references to prior people, courses, projects,
decisions, research, problems, reasons, or timestamped interactions; ordinary
self-contained conversation should not invoke it.

Candidate generation remains local and bounded. Full-text matches and a capped
recent-message fallback feed semantic reranking only when a reference warrants
it. Selected anchors expand to a small neighboring-message window so the reason
or relationship around an experience is not stripped into an isolated fact.
The derived projection has instance/time and instance/conversation/time indexes
and is updated incrementally with normal message persistence. No retrieval path
rewrites the canonical Archive.

Operational reporting distinguishes: absent from recent working context,
retrieval attempted with no match, not indexed, not stored, and not authorized.
A bounded miss does not prove historical absence. Multiple plausible anchors
remain ambiguous and require clarification rather than silent selection.

Continuity does not license identity inference. When a person or other entity
cannot be resolved from attributed evidence, Fawkes may explain what is known
about the role but must not convert that into a judgment about the unidentified
individual. Relationship reasons retain their original referents; fluent
restatement must not silently change who or what the rider meant.
