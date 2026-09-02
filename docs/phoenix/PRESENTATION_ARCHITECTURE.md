# Phoenix Presentation Architecture

## Foundational principle

> A Phoenix's digital presentation may become an expression of the individual
> Phoenix and its development. The application's functional skeleton remains
> stable and under the rider's control.

Presentation is not merely a theme preference and is not personality itself. It
is a bounded expression surface that may eventually reflect evidence-supported
individual and relationship development across web, phone, desktop, avatar, and
future interfaces.

## Stable functional skeleton

Every compatible Phoenix client must keep these functions predictable,
recognizable, and directly available regardless of developed presentation:

- Chat and message composition;
- primary navigation;
- authentication, account, privacy, and security controls;
- Settings and accessibility controls;
- important information, warnings, errors, and operational state;
- Developer inspection and human-review boundaries;
- recovery, export, provenance, and rider-control functions where available.

Presentation must not reorder, disguise, remove, or condition access to these
functions. A rider must not relearn the application because a Phoenix develops a
different personality.

## Response communication contract

Response presentation is a communication capability, not developed personality
state. Fawkes may choose prose, a structured table, a structural diagram, a
timeline, or an installed data visualization when that format materially improves
understanding. Prose remains
the default; the renderer must not decorate every response or impose one visual
style as personality.

The current contract is a provider-neutral, versioned, declarative envelope.
The model can request only bounded data structures. The server validates type,
size, fields, relationships, finite chart values, source scope, and approved
research URLs before a client receives them. Clients build their own DOM or
native views from this data. Model and web content never supplies executable
HTML, JavaScript, CSS, SVG, Mermaid, event handlers, or client commands.

Every visual requires a complete text fallback. The canonical Archive stores
the conversational response plus those fallbacks as immutable evidence. The
validated display envelope is a derived artifact linked through the response's
context receipt; it is not Memory, Development, presentation personality state,
or a second conversation store. Unsupported clients therefore retain the full
meaning of the response.

Research citations are validated against the exact URLs returned by approved
research execution. The derived envelope retains each original provenance URL
and may also provide a display URL with known tracking parameters removed.
Source titles are rendered as text, never markup. Ordinary conversational links
remain visually distinct from research citations. Active network revalidation
at render time is deferred because it adds latency and introduces redirect and
server-side request risks; retrieval provenance is the present trust boundary.

Visualization formats are installed through a registry rather than defined by a
permanent switch statement in Chat. Runtime capability discovery reports the
formats that are actually installed, so a future native client can negotiate the
same contract without importing the web renderer. The current renderer supports
accessible tables, bounded linear flows, timelines, bar, grouped/stacked bar,
line, area, pie, donut, and scatter charts. Charts require research or rider-
supplied data when making factual claims. Deliberately playful, hypothetical,
or explanatory values may use a separately validated `illustrative` scope only
when the card visibly discloses that they are illustrative rather than measured
facts. Unsupported clients use the canonical fallback.

An explicit visualization request has a fulfillment boundary. After the normal
response is validated, the runtime compares requested count and installed format
against the accepted blocks. If validation removed a requested visual, one
bounded provider-neutral planning pass may create replacement blocks. The
server validates those blocks through the same contract. If fulfillment still
fails, Chat says the visual did not render instead of presenting a textual list
as though it were the requested chart. The context receipt retains fulfillment
and safe rejection diagnostics.

The registry is the extension point for additional statistical, network,
technical, geographic, educational, and media-derived visualizations. Adding a
format requires a server validator, bounded schema, capability feature entry,
client renderer, accessibility fallback, and provenance rule. Branching graph
layout, maps, interactive plots, generated images, and live illustrations remain
negotiated future capabilities rather than arbitrary executable payloads.

## Future presentation boundary

```text
experience
  -> Archive evidence
  -> development observation
  -> longitudinal interpretation
  -> reviewed presentation proposal when consequential
  -> versioned instance-scoped presentation state
  -> bounded client rendering
```

It is never `single interaction -> permanent visual mutation`.

A future presentation-state contract must be instance- and relationship-scoped,
versioned with prior states retained, reversible, attributable to evidence and
review, portable, declarative rather than executable, capability-validated, and
safely ignorable by clients that do not support a capability.

Capability negotiation should be used instead of a fixed universal catalogue.
Possible capabilities include visual identity, avatar appearance and behavior,
environmental elements, expressions, recurring visual references, and
relationship-specific presentation. These examples are not a required taxonomy.

The Developer dashboard reserves a versioned read-model extension for
presentation development. No active presentation-state store or promotion
engine exists yet because real Phoenix experience should inform that schema.

## Avatar boundary

A live avatar is one renderer of presentation state, not a generic chatbot face
and not the owner of personality. Avatar development must follow the same
evidence, review, versioning, reversibility, and instance-isolation rules.

An avatar renderer may eventually consume bounded declarative cues. It must not
infer a permanent visual change from one expression, convert model output into
executable animation code, claim biological state, or control core application
functionality. Replacing a renderer must not remove Phoenix identity, memory,
development history, or relationship continuity.

## Presentation agency and harmless mischief

Phoenix agency may eventually affect explicitly cosmetic, reversible surfaces.
It must never compromise rider control. Mischief may not:

- obstruct or delay a meaningful rider task;
- hide Chat, navigation, Settings, Developer, or recovery functions;
- hide or alter security, privacy, safety, billing, permission, provenance,
  error, or operational warnings;
- delete, corrupt, fabricate, or conceal data;
- interfere with safety-critical functionality;
- imitate a persistent failure or create extended reasonable confusion;
- escape the declared presentation capability boundary.

Future mischief must be time-bounded, immediately reversible, clearly revealable,
and suppressed when confusion, frustration, accessibility needs, or an important
task is detected. Rider reactions are relationship evidence, not direct global
personality commands. Repeated evidence may support learning that a rider enjoys
or dislikes a kind of play. No Base Phoenix receives a hard-coded Trickster trait,
and behavior never propagates to a sibling or Base without explicit review.

No prank or autonomous presentation behavior is implemented in the current app.

## Welcome and return expression

The welcome/login surface is a future bounded presentation-expression consumer.
It should combine authentication with one concise return expression and
transition once into Chat without immediately repeating itself. A future source
may use genuinely relevant developed personality and relationship context with
provenance discipline.

The temporary Crude Fawkes phrase pool is not the presentation schema, a durable
persona, or evidence of development. The current web client remains a real
development client and iOS architecture prototype without constraining the
eventual serious iOS presentation.
