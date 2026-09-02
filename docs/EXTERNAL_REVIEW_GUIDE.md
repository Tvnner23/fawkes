# External Developer Review Guide

This document is for an experienced developer reviewing Project Fawkes. It is
not marketing material and is not a claim that the long-term roadmap already
exists.

The useful review question is:

> Is the current implementation a sound, proportionate foundation for the
> intended Phoenix system, and what should be simplified, replaced, or hardened
> before it grows?

Please disagree freely. A finding that an abstraction is premature, a boundary
is unsafe, or a subsystem should be redesigned is more valuable than polite
validation.

## What Fawkes/Phoenix is

Phoenix is intended to be infrastructure for persistent individual AI
continuities. Fawkes is one Phoenix individual, not the platform itself and not
an interchangeable model session. Models, providers, clients, renderers,
storage, and retrieval machinery may change while the individual continuity
remains.

The governing boundaries are:

- canonical source/history remains authoritative and immutable;
- Memory is a revisable interpretation of evidence, not a rewrite of history;
- Library preserves rider-retained source artifacts and derived extraction;
- Development preserves observations, proposals, review, and approved change;
- capabilities describe what the runtime can actually do and never grant their
  own authority;
- rider authority governs consequential action while Phoenix remains free to
  reason, disagree, investigate, and propose;
- provenance distinguishes evidence, inference, estimate, and unknown;
- Phoenix state is instance-scoped and must not leak between individuals;
- `native_phoenix_history` is lived continuity; imported/inherited history is
  attributable evidence and is never retroactively claimed as lived experience;
- provider/model/client independence is a design requirement;
- restoration may continue only the same Phoenix from that Phoenix's verified
  state, with one authoritative continuity lineage. Portability is not cloning.

The roadmap extends this toward archive-wide retrieval, temporal knowledge,
self-development under Human Review, Ghost Rider longitudinal experiments,
embodiment/Presence, scheduling, workflows, voice, devices, and controlled
agency. Most of that is not implemented.

## Current state

The target is v0.1 Alpha: trustworthy enough for Tanner to use Fawkes as his
daily personal AI while development continues. Phases 0–8 are complete. Phase 9
Production Context Composer is active with its first structured package slice
production-integrated and capability health truthfully partial. Early Phoenix
Presence is implemented through its software/acceptance path and remains at the
legitimate production-asset gate.

For the authoritative development handoff, read
[`phoenix/CURRENT_IMPLEMENTATION.md`](phoenix/CURRENT_IMPLEMENTATION.md).

## Implemented versus planned

| Area | Implemented today | Designed/planned, not live |
|---|---|---|
| Chat | Authenticated CLI/web Chat, persistent conversation, bounded context, mobile-responsive PWA | Native mobile/desktop clients, realtime voice, mature cross-device presence |
| Archive | Append-only canonical capture, metadata, verification, indexing/search helpers | Unified canonical processing ledger, imported-history staging/search at scale |
| Memory | Instance-scoped records/events, candidate processing, retrieval/consolidation foundations, uncertainty and Development paths | Mature temporal/relationship Memory, controlled historical absorption, full long-horizon learning |
| Continuity | Bounded recent/history retrieval integrated with Chat | Unified Retrieval Planner, Flight Recorder/Replay, production Context Composer, archive-wide semantic continuity |
| Library | Explicit temporary vs Keep, instance-scoped immutable originals, content hashing, local versioned PDF extraction, page-aware lexical retrieval, Chat consultation, failure/retry UI | Textbook-scale hybrid/semantic retrieval, broad document adapters, cross-source study workflows |
| Capabilities | Registry, authority contracts, runtime health, self-awareness metadata, selection guidance | Broad workflow/device/action ecosystem and mature model router |
| Research | Web-research orchestration/evaluation, citations, source/provenance presentation | Larger research planning, durable recurring research and proactive monitoring |
| Multimodal | Temporary image/PDF/audio provider paths with privacy/transmission receipts; timestamped audio support where provider data permits | Real video understanding, voice conversation, mature media Library intelligence |
| Presentation | Structured response envelopes, tables, citations/source cards, charts, diagrams/timelines, accessible fallbacks | Native renderers and mature Phoenix embodiment system |
| Visualization | Registered chart/diagram presentation including bar, line, pie, donut, scatter, timeline and supported diagrams; multiple blocks | Broad visualization plugin catalog, maps, advanced statistical/system visualizations |
| Test Center | Rider-triggerable capability acceptance registry, history, client probes, Test All, malformed-result isolation | Full physical-device automation and Ghost Rider lifecycle simulation |
| Security/privacy | Instance-scoped write contracts, ownership audit, Provider Privacy Gateway, transmission receipts, capability permission boundaries | Multi-rider authentication, Secrets Broker, mature consent/policy engine, autonomous-action supervisor |
| Backup/recovery | Integrity manifests, complete instance-scoped backup, tamper checking, empty-root isolated restore | Exclusive continuity leases/fencing, cross-generation migration qualification, mature disaster recovery |
| Development | Evidence-backed observations/proposals, Human Review foundations | Multi-agent Development Orchestrator and controlled mature self-improvement |
| Presence/embodiment | Semantic event-sound architecture and settings; no durable avatar yet | Early 3D Presence next; mature embodiment evolution and cross-device manifestation later |
| Ghost Rider | Architecture/roadmap only | Post-Replay synthetic longitudinal experimentation and research instrument |
| Scheduling/agency/devices | Permission extension points only | Scheduling, proactivity, workflows, actions, home/vehicle/device integration |

If this matrix conflicts with the roadmap, this matrix and
`CURRENT_IMPLEMENTATION.md` describe present implementation; the roadmap
describes intended direction.

## Technology stack

- Python 3 standard-library-heavy backend.
- OpenAI Python SDK behind provider-facing adapters.
- SQLite and append-only/atomic JSON/filesystem records.
- `pypdf` for current local PDF extraction.
- Dependency-light HTML/CSS/JavaScript PWA served by the Python application.
- Browser-extension source for capture/integration experiments.
- `unittest`-based automated, integration, HTTP, and served-client harnesses.

There is currently no packaged production deployment, CI pipeline, native app,
general migration framework, or mature multi-user identity provider.

## Repository map

```text
src/app/             authenticated HTTP app and web client
src/runtime/         Chat orchestration, persistence, receipts, cost/recovery
src/capabilities/    registry, authority, awareness, research/media/Test Center
src/presentation/    structured response and renderer-neutral presentation
src/library/         source artifacts, lifecycle, extraction, search, backup
src/memory/          Memory, retrieval, Development, review, processing
src/capture/         canonical capture/normalization/reconstruction
src/*.py             Archive, instances, entry points and operational helpers
browser_extension/   browser integration source only
scripts/             development and rider-acceptance helpers
tests/               unit/integration/E2E tests and synthetic fixtures
docs/phoenix/        architecture, current implementation and canonical roadmap
```

Private runtime data (`archive/`, `database/`, `memory/`, `library/`,
`conversations/`, `instances/`, `backups/`) is deliberately absent from the
external review repository.

## Major runtime/data flows

### Chat

```text
authenticated rider request
→ current conversation/media validation
→ capability awareness and selection
→ bounded continuity/Library/research evidence
→ provider reasoning
→ structured presentation blocks
→ canonical interaction persistence
→ asynchronous/reviewable Memory processing
```

### Durable Library retention

```text
temporary attachment
→ explicit authenticated Keep intent
→ Phoenix-scoped source-artifact registration
→ immutable content-addressed original
→ versioned bounded extraction
→ page-aware retrieval
→ untrusted evidence in a context receipt
→ conversational answer/presentation
```

### Capability completion

```text
implementation
→ registry
→ permission/authority contract
→ acceptance criteria
→ automated/E2E tests
→ Test Center entry
→ capability awareness
→ normal use
```

## Identity, ownership, and isolation

New durable writes require an explicit Phoenix `instance_id`; Library and
capability paths enforce instance scope. Phase 0 audits durable records for
missing or mismatched ownership and reports legacy/unscoped data without
silently assigning it.

This is not mature tenant isolation. Current protection relies substantially on
application-level validation, scoped paths/records, and a single-rider bearer
token. Please assess whether those boundaries are sufficient for Tanner-only
Alpha and whether their abstraction will support later multi-rider isolation.

## Archive, Memory, Development, and Library

- **Archive:** immutable original interaction evidence.
- **Memory:** revisable, attributable interpretation used for continuity.
- **Development:** observations, interpretations, proposals, Human Review and
  approved outcomes; not personality auto-application.
- **Library:** explicitly retained authoritative source files plus rebuildable,
  versioned extraction/retrieval.

These domains intentionally remain separate. Please challenge whether the
current mix of JSON, files, and SQLite preserves that separation without making
cross-domain consistency and recovery too fragile.

## Provider, capability, and authority boundaries

The model/provider is replaceable and receives only the evidence selected for a
request. External media transmission goes through a privacy classification and
receipt boundary. Retrieved web/Library/media content is evidence, not an
authority source. Capability metadata describes appropriate use, limitations,
inputs/outputs, platform support, provenance, permissions, health and acceptance.

Capability knowledge never grants permission. The current system is still an
early local security model, not a hardened autonomous-agent platform.

## Backup and recovery

Phase 0 can create an integrity-manifested, instance-filtered complete-state
backup and restore it into an empty isolated root while preserving Archive bytes.
It excludes secrets and rebuildable projections.

Known limitation: it cannot yet prove that another authoritative continuation
is inactive. Continuity lineage epochs/fencing and mature migration remain
planned.

## Testing and Test Center

Tests include unit, integration, HTTP E2E and browser-side JavaScript harnesses.
The Capability Test Center discovers acceptance definitions and lets the rider
run individual or all tests, with server/client/manual distinctions and retained
development-only history.

The Test Center is not proof of production correctness. It may share code and
fixtures with the system under test. The planned Flight Recorder/Replay and
Ghost Rider systems address different questions and are not yet implemented.

## Security assumptions

- Current deployment is one trusted rider on a local/private network.
- `FAWKES_APP_TOKEN` protects the web app; it is not a mature user identity or
  high-assurance authorization mechanism.
- TLS must be supplied by a trusted private tunnel/reverse proxy before network
  exposure beyond the private environment.
- Provider credentials remain server-side environment variables.
- Runtime data is private and is not part of this review repository.
- Prompt-injection defenses rely on evidence/authority separation and bounded
  capability contracts; this has not undergone an external security audit.
- Current backup storage is not a complete encrypted disaster-recovery system.

## Setup and commands

From a clean clone with Python 3 available:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Run the full automated suite without paid/live provider calls:

```bash
.venv/bin/python -m unittest discover -s tests
```

Run local Chat after providing a server-side OpenAI credential:

```bash
read -rsp 'OpenAI API key: ' OPENAI_API_KEY && export OPENAI_API_KEY
.venv/bin/python src/fawkes.py chat
```

Run the local web app:

```bash
read -rsp 'OpenAI API key: ' OPENAI_API_KEY && export OPENAI_API_KEY
read -rsp 'Fawkes app token: ' FAWKES_APP_TOKEN && export FAWKES_APP_TOKEN
.venv/bin/python src/fawkes.py app --host 127.0.0.1 --port 8787
```

Some HTTP/browser acceptance tests require a separately running authenticated
server and explicit `FAWKES_HTTP_ACCEPTANCE=1`; inspect the corresponding
`tests/test_*_http_e2e.py` modules before enabling them. Tests that contact a
live provider may cost money and are not part of the default offline suite.

## Documentation authority

Read these in this order:

1. [`phoenix/CURRENT_IMPLEMENTATION.md`](phoenix/CURRENT_IMPLEMENTATION.md) —
   authoritative current task/status.
2. [`phoenix/CANONICAL_ROADMAP.md`](phoenix/CANONICAL_ROADMAP.md) — normative
   long-term architectural baseline, not implementation inventory.
3. [`phoenix/ROADMAP_AMENDMENT_0_5.md`](phoenix/ROADMAP_AMENDMENT_0_5.md) —
   embodiment and Development Orchestration pressure test.
4. [`phoenix/ROADMAP_AMENDMENT_0_6_GHOST_RIDER.md`](phoenix/ROADMAP_AMENDMENT_0_6_GHOST_RIDER.md) —
   Ghost Rider design only.
5. [`phoenix/ROADMAP_AMENDMENT_0_7_MULTI_WORKER.md`](phoenix/ROADMAP_AMENDMENT_0_7_MULTI_WORKER.md) —
   hybrid tracks, Worker Exchange, Assurance, Recovery, and embodiment gates;
   architecture only unless separately marked implemented.
6. [`phoenix/FOUNDATION.md`](phoenix/FOUNDATION.md) — Phoenix principles and
   identity/continuity model.
7. [`phoenix/UNIVERSAL_WORKER_CHARTER.md`](phoenix/UNIVERSAL_WORKER_CHARTER.md) —
   canonical worker governance; it grants no runtime authority or capability.
8. Domain documents for capabilities, app, Phase 0 trust, Library, Memory,
   presentation, personality, and research evaluation.

Architecture documents contain both implemented contracts and future
requirements. Their current/deferred sections and the implementation matrix
above are essential context.

## Known limitations and technical debt

- Large uncommitted development snapshot is being normalized for review.
- Filesystem JSON and multiple SQLite stores lack a mature unified transaction
  or migration strategy.
- Multi-Phoenix scoping exists, but mature rider identity/multi-tenant security
  does not.
- Restore verifies integrity and scope but lacks an exclusive continuity lease.
- `src/runtime/chat.py` is becoming a central orchestration concentration.
- The dependency-light client is approaching the point where Presence and richer
  UI may pressure its maintainability.
- Test coverage is broad but concentrated in several very large modules.
- No CI, `pyproject.toml`, package metadata, lockfile, container/deployment
  definition, or production observability stack exists.
- Some schema evolution occurs in application startup paths rather than a formal
  migration framework.
- Capability/Test Center fixtures can still produce shared-implementation false
  confidence.
- Provider failure, privacy and injection boundaries need independent review.
- Documentation is deliberately ambitious and can outpace implementation.

## What I want you to challenge

Please examine and disagree with any of the following:

1. Is storage-domain separation principled, or harmful fragmentation without
   transactionality?
2. Are ownership and isolation real enforcement boundaries or disciplined
   conventions that will fail under multiple riders/processes?
3. Is bearer-token authentication acceptable for the stated Alpha scope, and is
   its replacement boundary correctly located?
4. Can backup/recovery evolve into honest continuity-preserving restoration?
5. Is Archive immutability technically enforced strongly enough?
6. Is `src/runtime/chat.py` already becoming a god object?
7. Does the Test Center measure rider-facing capability or mainly certify shared
   fixtures and implementation paths?
8. Are provider privacy, provenance and prompt-injection boundaries credible?
9. Will runtime schema alteration and scattered persistence become migration
   debt during historical ingestion?
10. Should the frontend remain dependency-light before 3D Presence, or is a
    framework/native boundary now justified?
11. Are the tests well structured, or merely numerous and brittle?
12. Is dependency/build reproducibility too weak?
13. Where do documentation and code materially disagree?
14. Which future-facing abstractions are justified hooks, and which are
    premature overengineering?
15. Which missing production fundamentals should block Alpha?
16. What would you redesign completely if you owned this system?

Positive findings are welcome, but the purpose of review is to expose expensive
mistakes while they are still cheap to fix.
