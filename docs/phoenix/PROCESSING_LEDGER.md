# Universal Canonical Processing Ledger

Status: **Phase 2 foundation implemented.** This contract coordinates work; it
does not make staged history, Replay, Ghost Rider, or Development Orchestration
live.

## Boundary

The ledger answers: what bounded processing was registered, against which exact
source revision, by which processor version and actor, what happened to that
work, and which outputs or failures resulted?

It does not own source truth. Archive, Library, Memory, Development, Test
history, and future imported-history records remain authoritative in their own
domains. The ledger stores references and derived coordination state. It never
silently promotes derived data into those systems.

Each Phoenix has a physically separate SQLite ledger at:

`database/processing/<phoenix_instance_id>/ledger.sqlite3`

The database repeats and verifies its Phoenix owner. Phase 0 audit, verified
backup, and isolated restore include the owning directory. No unscoped or
legacy record is assigned to a Phoenix by this implementation.

## Stable work identity

A work item is idempotently identified by Phoenix, domain, and an explicit
idempotency key. Its immutable envelope records:

- Phoenix instance;
- domain and work kind;
- source, object, content, and revision IDs;
- source domain and evidence era;
- processor ID/version;
- actor/principal attribution;
- reality scope and time domain;
- typed provenance;
- dependency, correlation, and causation IDs;
- resource metadata;
- inert future extension metadata.

Reusing an idempotency key for materially different work fails closed.

## Lifecycle and evidence

The generic lifecycle is deliberately small:

`discovered → queued → running → completed / review / failure / quarantine`

with explicit pause, retry, cancellation, and supersession paths. Invalid
transitions fail. Atomic claims increment attempts. Registration, claims, and
transitions create append-only events; replaying an operation is idempotent and
cannot be reused to disguise a different transition.

Assessments, decisions, review references, errors, and result references remain
separate fields. A result reference does not make the result authoritative.

## Coverage projection

The initial Corpus Coverage projection reports bounded counts by domain and
status, incomplete work, failure/quarantine counts, and the absence of any
registered work. It is explicitly a projection over ledger registration, not a
claim that every source in Phoenix has been discovered. Phase 3–5 will extend
coverage using the staged corpus and known-answer retrieval evidence.

## Reserved extension namespaces

The following provider-neutral namespaces are accepted as inert metadata:

- `development_run`
- `experiment_run`
- `continuity_lineage`
- `validated_progression`
- `independent_reference`
- `historical_provenance`

They reserve stable IDs for later roadmap phases. They grant no authority,
start no agents or experiments, establish no continuity genesis, and create no
native-history claim. Production work cannot use Simulation Time.

The existing Memory work ledger remains in place. Moving or adapting real
Memory work requires a later explicit migration with compatibility tests; Phase
2 does not silently rewrite it.
