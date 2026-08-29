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

For example:

Version 1:
"The user plans to become a network engineer."

Later:

Version 2:
"The user is pursuing cybersecurity with networking as a major career direction."

Version 1 should not necessarily be destroyed.

Instead:

Version 1
    ↓ superseded by
Version 2

This preserves the evolution of understanding.

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

