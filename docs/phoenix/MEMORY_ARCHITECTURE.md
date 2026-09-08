# Phoenix Memory Architecture

## Purpose

The Phoenix memory system exists to transform experience into durable, retrievable understanding without replacing or corrupting the historical Archive.

Memory is an interpretation of experience.

The Archive remains the historical evidence.

Memory must therefore be:

- contextual
- structured
- provenance-aware
- revisable
- associative
- confidence-aware
- importance-aware
- temporally aware
- extensible

---

## 1. The Memory Pipeline

The intended pipeline is:

Raw Archive
    ↓
Canonical History
    ↓
Experience Understanding
    ↓
Memory Candidates
    ↓
Semantic Evaluation
    ↓
Memory Consolidation
    ↓
Persistent Memory
    ↓
Associations
    ↓
Retrieval
    ↓
Contextual Recall

No memory layer should destroy the evidence from which it was derived.

---

## 2. Memory Is Not the Archive

The Archive answers:

"What happened?"

Memory answers:

"What do I currently understand from what happened?"

These are deliberately different.

A conversation may contain thousands of messages while only a small portion becomes durable memory.

Conversely, one important experience may produce several different memories.

---

## 3. Memory Categories

The system should support an extensible taxonomy.

### 3.1 User Facts

Stable factual information about the person.

Examples:

- education
- occupation
- location
- relevant background
- recurring circumstances

---

### 3.2 Preferences

Things the person likes, dislikes, prefers, avoids, or tends toward.

Examples:

- communication preferences
- product preferences
- entertainment preferences
- food preferences
- workflow preferences

Preferences may change over time.

---

### 3.3 Goals

Desired future outcomes.

Examples:

- career goals
- educational goals
- financial goals
- personal goals
- project goals

Goals should have lifecycle state.

Possible states:

- active
- paused
- completed
- abandoned
- superseded
- uncertain

---

### 3.4 Plans

Strategies for achieving goals.

A plan is distinct from a goal.

A goal may survive while its plan changes.

Plans should preserve:

- objective
- approach
- reasoning
- status
- relevant constraints

---

### 3.5 Decisions

Important choices made by the user or jointly made during interaction.

A decision should preserve:

- what was decided
- when
- why
- alternatives considered when available
- constraints
- evidence
- whether the decision remains current

---

### 3.6 Projects

Ongoing bodies of work.

A project may contain:

- goals
- tasks
- decisions
- architecture
- milestones
- unresolved problems
- history
- related memories

Fawkes itself is a project and also the subject of self-related memories.

---

### 3.7 Experiences

Significant events or interactions.

An experience may matter even when it does not produce a simple factual statement.

Examples:

- major conversations
- milestones
- successes
- failures
- discoveries
- meaningful moments
- important turning points

---

### 3.8 Relationships

Information describing the relationship between the Phoenix and people or entities.

Potential information includes:

- shared history
- recurring patterns
- trust
- familiarity
- shared references
- meaningful interactions
- relationship changes

Relationship memory must not be reduced to a list of user facts.

---

### 3.9 Knowledge

Things learned during interaction.

Knowledge may be:

- user-provided
- discovered through research
- jointly developed
- project-specific
- domain-specific

Knowledge should retain provenance and confidence.

---

### 3.10 Beliefs and Understanding

Current interpretations held by the Phoenix.

These are not automatically historical facts.

A belief should be capable of:

- gaining confidence
- losing confidence
- being contradicted
- being revised
- being superseded
- retaining its historical versions

---

### 3.11 Open Threads

Things that remain unresolved.

Examples:

- unanswered questions
- unfinished projects
- decisions awaiting action
- subjects to revisit
- promises to return to a topic

Open threads should remain retrievable even when temporarily dormant.

---

### 3.12 Personality Development

Memories that contribute to understanding how the Phoenix itself has developed.

Examples:

- learned conversational patterns
- recurring humor
- preferred ways of explaining things
- changes in opinions
- important lessons
- recurring behavioral tendencies

Personality memories should have evidence.

---

### 3.13 Self-History

The Phoenix's own developmental history.

This should preserve:

- previous states of understanding
- major developmental milestones
- important changes
- reasons for changes
- significant experiences
- architectural evolution

The Phoenix should eventually be able to reconstruct how it became its current self.

---

## 4. Memory Structure

A memory should conceptually contain more than text.

The eventual representation should support:

- memory_id
- memory_type
- content
- status
- importance
- confidence
- created_at
- updated_at
- valid_from
- valid_until
- source_message_ids
- source_archive_ids
- related_memory_ids
- supersedes
- superseded_by
- evidence_count
- access_count
- last_recalled_at
- tags
- entities
- context
- provenance

Not every field must be implemented immediately.

The architecture should allow them to exist later without requiring a destructive migration.

---

## 5. Current vs Historical Memory

A memory may have multiple historical states.

Related education and career facts must not be collapsed merely because they
share a subject area. They answer different questions and should be represented
independently:

- `education_institution`: where the rider studies
- `degree`: the exact degree or credential being pursued
- `career_direction`: the current professional field or specialization
- `career_goal`: the broader long-term professional progression

For example, a cybersecurity degree and a networking career direction may
support and contextualize each other, but neither supersedes nor proves the
other. Asking for the degree must not return a career direction as if it were
the degree.

True changes within one concept should preserve evolution. A former career
direction may be superseded by a newer career direction while the independent
education records remain current.

---

## 6. Confidence

Confidence represents how strongly the evidence supports the current memory.

Confidence is not the same as importance.

A memory can be:

- highly important but uncertain
- unimportant but certain
- highly important and highly certain
- low importance and uncertain

Confidence should be evidence-based where possible.

---

## 7. Importance

Importance represents how valuable the memory is for future continuity.

Potential factors include:

- long-term relevance
- impact on future decisions
- frequency of relevance
- relationship significance
- contribution to identity
- contribution to ongoing goals
- explicit importance
- repeated confirmation

Importance should not be determined solely by how emotionally dramatic a statement appears.

---

## 8. Temporal State

Memory must understand time.

A memory may be:

- currently true
- historically true
- future-oriented
- temporarily true
- recurring
- uncertain
- expired
- superseded

The system must avoid treating historical information as automatically current.

---

## 9. Evidence

Every durable memory should ideally be traceable to evidence.

Evidence may include:

- message IDs
- archive IDs
- conversations
- timestamps
- repeated statements
- explicit corrections
- related experiences

A memory without evidence may still exist, but its confidence should reflect that limitation.

---

## 10. Semantic Equivalence

Memory formation must not depend on exact wording.

These may represent the same underlying memory:

"I want to become a network engineer."

"I'm trying to move into networking."

"I think networking is where I want my career to go."

The system should eventually recognize semantic equivalence and consolidate these into a coherent underlying memory rather than creating three unrelated memories.

---

## 11. Contradictions

Contradictory information must not be silently merged.

Example:

"I want to work remotely."

Later:

"I've decided I want to work in a data center."

The system should recognize a possible change rather than treating both statements as simultaneously current without qualification.

The historical statements remain preserved.

The current memory state should reflect the most defensible current understanding.

---

## 12. Memory Consolidation

Consolidation transforms multiple pieces of evidence into coherent memory.

Conceptually:

Experience A
    +
Experience B
    +
Experience C
    ↓
Underlying concept
    ↓
Consolidated memory

Consolidation should be capable of:

- deduplication
- semantic merging
- confidence updates
- importance updates
- contradiction detection
- temporal reasoning
- relationship creation
- supersession

---

## 13. Associative Memory

Memories should eventually form relationships.

Example:

Career Goal
    ├── Cybersecurity degree
    ├── Networking
    ├── Certifications
    ├── Job search
    └── Fawkes career discussions

A future conversation about networking could therefore retrieve the broader career context.

Retrieval should not require exact keyword matching.

---

## 14. Memory Retrieval

Retrieval should consider multiple dimensions.

Potential retrieval signals include:

- semantic similarity
- current conversation context
- recency
- importance
- confidence
- relationship relevance
- project relevance
- goal relevance
- temporal validity
- prior successful recall
- associative relationships

The highest semantic similarity should not automatically win.

A less similar memory may be much more important to the current conversation.

---

## 15. Proactive Recall

The Phoenix should retrieve relevant memories automatically when context warrants them.

Automatic recall is an intended behavior, not a feature the rider must invoke
with phrases such as "remember" or "pick this back up." Filtering exists to
improve the relevance of proactive recall, not to make the Phoenix passive.

Current intent takes priority over weak historical similarity. Relevant prior
experience, decisions, preferences, relationship history, and project state may
be recalled naturally. Stale procedural commands, terminal transcripts, and
transient development instructions require strong, intent-compatible relevance
and must not be injected on the strength of a generic shared word.

It should not dump every related memory into the conversation.

Good recall should feel like:

"Oh, I remember this is connected to that earlier thing."

Not:

"Here are 47 memories containing the word networking."

---

## 16. Memory Formation Must Be Conservative

The system should prefer:

"I am not confident enough to make this a durable memory."

over:

"I will permanently remember every sentence."

False memories are more dangerous to continuity than missing low-value memories.

When uncertain, information can remain in the Archive or as a review candidate.

---

## 17. Memory Review

Some information should enter a review state before becoming durable.

Possible decisions:

- likely_memory
- likely_ephemeral
- needs_review
- contradiction
- duplicate
- supersedes_existing
- insufficient_evidence

Human confirmation may eventually be available for important memories.

---

## 18. Memory Decay

Memory should not simply disappear because it has not been mentioned recently.

Instead, the architecture should distinguish:

- relevance decay
- confidence decay
- access decay
- temporal expiration
- historical status

An old but foundational memory may remain extremely important despite rarely being accessed.

---

## 19. Memory Strengthening

Repeated independent evidence can strengthen a memory.

For example:

Statement A
    ↓
initial confidence

Statement B
    ↓
corroboration

Statement C
    ↓
stronger confidence

Repeated evidence should not create unnecessary duplicate memories.

### Local persistence and interrupted operations

The scoped JSON store stages a record mutation and its derivation events together.
A durable, private pending intent binds their complete preimages/postimages to
the configured record/event directories. Store readers and writers use the same
thread/process lock. After interruption, they finish that exact intent before
returning state; a conflicting uncoordinated change stops recovery instead of
being overwritten. Historical events and Archive bytes are not rewritten.

Repeated source evidence does not accumulate confidence again. A new work-item
identifier alone is not new independent evidence. Scoped mutation requires the
explicit matching instance, including supersession, quarantine and duplicate
retirement. Duplicate merge and supersession publish as complete units.

Legacy records remain readable without migration. A historical work-item record
without its event/retirement evidence is not proof of completed consolidation:
it goes to review rather than inventing a recovery intent or silently retiring
another record. New interrupted intents can be recovered without a provider.

This consistency boundary is the store API over caller-owned local directories,
not protection against an adversary controlling the same operating-system
account. POSIX locking/crash recovery is directly qualified; Windows lock support
is retained but is not claimed physically exercised by that qualification.

---

## 20. Memory Graph

The eventual memory system should support relationships between memories.

Possible relationship types:

- supports
- contradicts
- supersedes
- derived_from
- related_to
- caused_by
- part_of
- follows
- precedes
- associated_with
- same_concept_as

This graph should allow contextual recall.

---

## 21. Separation From Personality

Memory contributes to personality.

Memory is not personality.

Personality should eventually be represented as a higher-level evolving state derived from accumulated experience, memory, and interaction.

This prevents one isolated statement from permanently changing the Phoenix's personality.

---

## 22. Separation From Active Context

Active context is temporary working information.

Memory is durable state.

Archive is historical evidence.

The intended separation is:

Archive
    = what happened

Memory
    = what matters / what is currently understood

Active Context
    = what matters right now

Personality
    = who the Phoenix has become

---

## 23. Recalling the Past

When relevant, the Phoenix should be able to move through levels of recollection:

Current context
    ↓
Relevant memory
    ↓
Related memories
    ↓
Historical evidence

This allows the Phoenix to answer questions such as:

- "What did we decide?"
- "Why did we decide that?"
- "When did my thinking change?"
- "What were we working on?"
- "How did you come to understand this about me?"

The deepest layer should remain the Archive.

---

## 24. Reconstruction

If the active Phoenix instance is lost, reconstruction should use:

Seed Identity
    +
Persistent Personality State
    +
Persistent Memories
    +
Canonical History
    +
Immutable Archive

The Phoenix should not need the original runtime session to recover continuity.

---

## 25. Extensibility

New memory types must be addable without redesigning the entire architecture.

Unknown future memory types are expected.

The architecture should therefore favor:

- typed records
- flexible metadata
- explicit relationships
- provenance
- versioning
- schema evolution

over rigid assumptions about what a memory must be.

---

## 26. Current Implementation

The current implementation contains:

- basic Memory storage
- memory IDs
- memory types
- content
- timestamps
- status
- importance
- confidence
- source message IDs
- source archive IDs
- supersession support
- memory fingerprinting
- candidate extraction
- preliminary evaluation

These are foundations only.

The existing evaluator is intentionally not considered the final semantic memory system.

---

## 27. Guiding Rule

The Phoenix should never confuse:

"I saw this."

with:

"This is permanently who we are."

Experience becomes evidence.

Evidence becomes understanding.

Understanding may become memory.

Memory contributes to personality.

Personality develops through accumulated experience.

The Archive preserves the history underneath all of it.
## Live candidate processing visibility

The live app must not merely enqueue candidates. It advances the durable,
instance-scoped processing ledger in a bounded background worker after turns.
The response path never waits for this work. Evaluation records confidence,
importance, evidence, uncertainty, and disposition; consolidation may accept,
reject, or route conflicts and ambiguous cases to review. The Developer read
model exposes queue and review state so stalled processing cannot masquerade as
an absence of uncertain memories. This processing never rewrites Archive.

## Working context and continuity retrieval

Working context is the bounded recent conversation window supplied directly to
the model. Continuity retrieval is a separate read path over derived indexes of
canonical interaction evidence. Memory remains the smaller set of evaluated,
durable understanding. A historical message can therefore be stored and
retrievable without being promoted to Memory, and it can be outside working
context without being inaccessible.

Continuity retrieval may consult older evidence from the current conversation
or another conversation belonging to the same Phoenix. It excludes messages
already supplied in the working window, semantically reranks a bounded local
candidate set for referential requests, and retains a small neighbor window for
meaning and reasons. A retrieval miss is uncertainty about the bounded search,
not proof that the Archive lacks the interaction.
# F05 recovery/ownership correction — source adoption boundary

New work-item completion is bound to its actual mutation event. Provenance on
a later quarantine or merge is not completion evidence. Legacy work-item
records without an exact completion binding remain available to read but need
explicit review before being reported recovered. Recovery synchronizes every
affected publication directory before discarding its intent, including already
renamed postimages. No automatic historical migration is performed.

Archive context retains instance ownership; explicit instance selection occurs
before message revision grouping and provider input. Development history follows
that same owner before ranking/evaluation. Legacy unscoped records remain a
separate explicit decision for mutation. Completing missing provenance does not
constitute independently new evidence or automatically increase confidence.
# Processing ownership and administrative listing

Memory processing selects one explicit instance, or legacy unscoped records
when the processing instance is omitted. This default is not an all-owner
provider grant. The administrative `list_memories()` API still lists all owners;
processing uses `list_memories_for_context()` before ranking or comparison.
An explicit `include_unscoped` read does not authorize reassigning or mutating
legacy records. Extracted candidates retain their known owner; mismatched
candidate/context ownership requires review before evaluation. Low-level callers
without retained owner metadata remain responsible for their explicit scope.
