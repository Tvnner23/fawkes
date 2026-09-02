# Phoenix App Architecture

## Governing boundary

The app is a home for a Phoenix, not a Phoenix of its own. App interfaces use
one application service and the existing conversational runtime:

```text
CLI / phone / future desktop
        -> authenticated Chat service
        -> FawkesChatRuntime
        -> instance-scoped Memory + canonical Archive + context receipts
        -> configured model provider
```

The Chat service coordinates a turn but owns no intelligence or durable store.
It archives the user message before generation, creates a queued Memory work
item for controlled processing, delegates response generation and retrieval to
the existing runtime, archives the response, and records the supplied context.
Conversation history displayed by the app is reconstructed from canonical
Archive evidence. This makes process restarts an ordinary continuity event.

## Identity and access

The server resolves one configured Phoenix instance. An API client cannot pick
or inject an `instance_id`. The current single-rider app uses a server access
token for non-loopback access; provider credentials remain on the host. Future
multi-Phoenix authentication must map an authenticated principal and selected
Phoenix to an authorized instance before any store is queried. Memory, Archive,
Library, Development, relationships, and conversation registries remain
instance-scoped.

## Future app areas

Search / Database is an inspection service over existing stores. A federated,
read-only query can return separately labeled Memory, Archive, Library, and
Development results with status and provenance. It must not copy results into a
new app database or flatten their domain distinctions.

Library UI will register immutable originals and versioned extractions through
the existing Library source contract. Page number, displayed label, chapter,
section, subsection, and native locator remain attached to source segments.

Low-friction flags such as “Remember this,” “That's wrong,” and “This feels like
Fawkes” should append instance-scoped evidence candidates referencing archived
message IDs and the action's classification. A flag is evidence for review or
controlled processing, never direct promotion to durable Memory, relationship
state, or personality. Raw conversation remains automatically preserved even
when no moment is flagged.

Development views will inspect longitudinal observations, proposals, evidence,
corrections, and versions. They must preserve the boundary between runtime
state, contextual observation, current expression, and evidence-supported
developed tendency.

The observation API is authenticated and resolves instance scope on the server.
Its records and append-only history are the future Developer tab's source; a UI
must query them rather than copy them into an app-owned development database.

The web-research API follows the same identity rule: clients supply a query but
cannot select a Phoenix instance. It delegates to the shared capability boundary
and returns a separate provenance-bearing research artifact. It does not place
web results into Archive, Memory, Library, or Development. Natural conversational
orchestration and citation presentation build on this service rather than
embedding a second search runtime in a client.

Ordinary Chat reaches the same capability through the shared runtime. The
runtime performs bounded research decision/planning, invokes the capability
within its external-read grant, supplies provenance-bearing results to response
synthesis, validates visible citation URLs, and includes research references in
the response context receipt. The client still submits an ordinary message;
provider choice and tool structures do not leak into the app contract.

The first Developer tab is a read-only projection across observations,
correction signals, development proposals, human-review items, and review
feedback. System Defects and Base Phoenix Candidates are filtered views over
observations rather than new stores. Observation detail resolves its evidence
and append-only interpretation history through the existing authenticated API.

A future Phoenix self-evaluation layer may form an overall, revisable assessment
and discover useful subcategories from longitudinal evidence. That assessment
must remain a provenance-linked interpretation above observations, not a
replacement ledger, fixed trait taxonomy, numerical personality score, or
automatic personality-control input.

## Stable client skeleton

Phoenix presentation may evolve around a stable client skeleton. Current and
future clients must preserve predictable Chat, primary navigation,
authentication, Settings, important warnings, Developer access, and rider
control. The current web client is a real development and interaction client and
an architectural prototype for iOS, not a separate intelligence or disposable
toy. Its presentation is replaceable; its runtime, instance, persistence,
provenance, and stable functional contracts are not.

The permanent [Phoenix Public Experience](PHOENIX_PUBLIC_EXPERIENCE.md) is a
distinct public product surface, not an unauthenticated mode of this private
client. One domain and coherent public home may eventually lead into
authenticated Phoenix access, but public content/companion sessions and private
Phoenix instance resolution remain separate trust, identity, storage, and
deployment boundaries. The anonymous public guide never upgrades or morphs
into a Phoenix; it visibly yields after the existing authenticated application
boundary resolves the rider and Phoenix instance.

Chat responses may include a versioned presentation envelope alongside their
canonical text. The web client renders the supported safe subset and ignores
unknown future versions; canonical textual fallbacks preserve continuity across
terminal, web, phone, and future native clients. Presentation metadata is loaded
from the existing context receipt for restart recovery and never becomes a
parallel message, Memory, or Development store.

Material native-retrieval ambiguity may also carry a turn-bound clarification
decision. The web client renders only its server-supplied rider labels as native
buttons and keeps opaque identifiers out of ordinary visible UI. A selection is
rider intent, not authority: the client submits the exact originating response,
decision, plan, ambiguity, choice, and original-query binding to the existing
Chat endpoint. It stores no reusable grant and cannot bypass the server's fresh
eligibility, planning, exact-set permit, or provider-boundary checks.

The Developer progression view is a read-only chronology over the observation
event ledger. Presentation and Growth panels are explicit extension surfaces;
they do not imply that active presentation state or Phoenix self-assessment has
been implemented.

## Client independence and capability negotiation

The authenticated application boundary exposes provider-neutral capability
manifests and supported presentation-envelope versions. Web, iOS, Android,
desktop, and device clients consume those contracts; they do not own research,
Memory retrieval, Library consultation, Development interpretation, permission
enforcement, or presentation validation. A client may provide microphone,
camera, notification, secure credential, and native rendering facilities, but
those platform APIs remain adapters around the shared Chat and capability
contracts.

Capability availability is runtime-derived. An extension point is not reported
as live, provider credentials never enter the manifest, and clients must retain
the canonical text fallback when they do not support a presentation feature.
This avoids both a web-only Phoenix and a static hand-maintained claim about what
Fawkes can do.
## Unified Chat routing

Chat is the rider-facing integration surface. Attachments, web research,
presentation selection, Memory retrieval, and Development evidence remain
separate capabilities underneath one turn contract. When rider-provided media
already supplies the requested evidence, the runtime does not perform a web
planning call unless the message contains an explicit current/external research
need. This keeps simple visual and lecture questions responsive without
restricting research when it is useful.
