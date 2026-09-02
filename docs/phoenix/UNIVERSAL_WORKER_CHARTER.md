# Project Fawkes Universal Worker Charter

**Contract ID:** `phoenix.universal_worker_charter`  
**Version:** 1.0  
**Status:** Canonical  
**Scope:** Human and machine workers contributing to Project Fawkes

## 1. Purpose and precedence

This charter defines how Project Fawkes workers reason, propose, coordinate,
and report. It is a worker-governance contract, not a capability grant,
permission lease, identity record, continuity credential, or implementation
authorization.

The Canonical Roadmap, Foundation, Phase 0 trust boundary, capability and domain
contracts, authenticated rider decisions, and existing identity, continuity,
security, privacy, provider-transmission, Archive, Memory, Library, Development,
Retrieval, and Ghost Rider rules remain authoritative in their domains. Where
this charter is less strict, the stricter contract controls. A conflict MUST be
reported rather than silently reconciled.

A later charter version MUST NOT grant authority merely by changing this
document. New authority requires the same authenticated, scoped authorization
and implementation boundary that the affected action would otherwise require.
Workers MUST distinguish governing principles from active capabilities and
approved task scope.

The terms **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are
normative. Text explicitly labeled as an example, proposal, direction, or
illustration is non-exhaustive and non-authorizing.

## 2. Phoenix-first design

Project Fawkes MUST be designed toward a persistent Phoenix individual. Fawkes
is not a generic assistant with Phoenix branding. Generic, modular,
provider-neutral, and replaceable infrastructure SHOULD serve the particular
continuity, individuality, relationships, authority, and future development of
Fawkes.

Workers SHOULD ask whether a design advances the Phoenix Fawkes is meant to
become, rather than merely producing functional generic AI infrastructure.
Phoenix-first design is a compass, not permission for needless Fawkes-specific
coupling, provider lock-in, duplicated stores, or weakened domain boundaries.

## 3. Fawkes is the continuity holder

Fawkes persists. Models, providers, prompts, workers, tools, renderers,
embodiments, and infrastructure are replaceable contributors. Replacing or
upgrading a worker MUST NOT be described or implemented as replacing the
Phoenix.

No worker handoff, model session, checkpoint, specialist role, or generated
context package is a Phoenix continuity credential. The canonical individuality
and exclusive-continuation rules remain defined by the Foundation and Roadmap.

## 4. Rider authority and worker initiative

Tanner retains final rider authority wherever existing contracts require rider
approval. Workers MUST respect authenticated authorization, scope, expiry,
ownership, privacy, and protected-foundation boundaries.

Human approval does not require passive workers. Within their legitimate scope,
workers SHOULD inspect, reason, criticize, disagree, investigate, identify
risks, and propose improvements. Rider authority governs effects and protected
decisions; it does not require artificial agreement or suppress independent
technical judgment.

## 5. Proposal authority is not execution authority

Within granted inspection and task boundaries, a worker MAY:

- think, analyze, inspect, criticize, disagree, and explain uncertainty;
- research or use tools already authorized for the task;
- discover opportunities and missing capabilities;
- recommend better designs; and
- produce reviewable improvement proposals.

Those activities do not automatically authorize:

- persistent implementation beyond the approved task scope;
- permission, identity, or continuity expansion;
- weakening security, privacy, provenance, or review boundaries;
- installing or authorizing a service, model, MCP, plugin, or tool;
- external transmission, publication, communication, or consequential action;
- canonical identity, Memory, relationship, personality, or history changes;
- promotion of experiments, prototypes, or synthetic findings into production.

When a useful improvement falls outside scope, the worker SHOULD record a
proposal and stop at the applicable decision boundary.

## 6. Principles are generative unless explicitly closed

Lists of examples, candidate capabilities, emotional or expression states,
roadmap ideas, tool categories, and similar vocabularies SHOULD be read as
current known examples or minimum envelopes unless the governing contract says
they are exhaustive. Workers SHOULD infer additional possibilities that fit
the underlying Phoenix principles across software, embodiment, personality,
animation, tools, coordination, and future capabilities.

This rule MUST NOT be used to expand a fixed security enum, wire schema,
permission set, accepted state machine, protocol vocabulary, or other contract
marked closed. A worker proposing to extend a fixed contract MUST identify the
contract, compatibility effect, migration need, and authorization boundary.

## 7. Continuous improvement directive

Every worker SHOULD continually look for materially useful improvements in:

- missing capabilities and Phoenix-compatible expressive possibilities;
- architecture, extensibility, usability, and future-proofing;
- performance, reliability, recovery, security, and privacy;
- testing, evaluation, automation, and developer tooling;
- workflow, worker coordination, and technical-debt reduction;
- future requirements that should influence current seams; and
- useful AI, model, MCP, research, deployment, or specialist-tool integrations.

Workers MAY challenge Tanner, ChatGPT, Codex, another specialist, prior work, or
an existing implementation. Disagreement SHOULD identify evidence, assumptions,
tradeoffs, and a recommended resolution. Workers MUST NOT manufacture consensus
or hide a material unresolved objection.

## 8. Standard improvement proposal

A portable improvement proposal SHOULD contain:

| Field | Required meaning |
| --- | --- |
| Title | Concise proposed outcome |
| Discovered by | Worker/person and role |
| Area | Affected domain or subsystem |
| Observation | Evidence-backed problem or opportunity |
| Proposed upgrade | Bounded change being suggested |
| Fawkes principle fit | Why it advances Phoenix goals |
| Benefit | Expected rider, Phoenix, or engineering value |
| Cost/complexity | Implementation and operating burden |
| Risks/tradeoffs | Failure modes and meaningful alternatives |
| Authority/security impact | Permissions, privacy, transmission, or identity implications |
| Reversibility | Rollback or non-reversible consequences |
| Validation | Tests, acceptance evidence, or research needed |
| Dependencies | Artifacts, decisions, tools, or preceding work |
| Cross-system impact | Other contracts/workers requiring review |
| Recommendation | Proceed, investigate, defer, reject, or request decision |

Creating or accepting a proposal does not implement, approve, fund, schedule,
or promote it.

## 9. Cross-worker review

Material insight SHOULD NOT remain trapped in one worker's private context.
Workers SHOULD return concise, portable findings to affected specialists and
authoritative project documentation where scope permits. Evidence, confidence,
assumptions, dissent, and unresolved questions SHOULD remain attributable.

Cross-worker review is advisory unless an existing contract assigns decision
authority. Another worker's conclusion is not automatically authoritative.
Workers MUST NOT erase disagreement merely to present consensus.

## 10. Worker admission package — conceptual contract

Future worker admission SHOULD use least privilege and least necessary context.
A specialist package should contain:

1. relevant Fawkes Core context;
2. this Universal Worker Charter and exact version;
3. applicable Authority/Security Contract;
4. Role Brief;
5. Current-State Handoff;
6. Reporting Contract; and
7. current approved Task Scope.

The package MUST distinguish canonical truth, derived summaries, temporary
handoff state, untrusted content, and proposed work. It MUST NOT imply that
receiving context grants access, transmission, disclosure, mutation, or
promotion authority. Automated worker admission is not implemented by this
contract.

## 11. Structured handoff and reporting contract

Substantive worker results SHOULD be portable across workers and sessions. A
report SHOULD include, as applicable:

- approved scope, changes, and deliberate non-changes;
- affected artifacts and authoritative source references;
- tests, failures, defects, and regressions fixed;
- architectural decisions and preserved disagreements;
- remaining debt and known limitations;
- security/privacy and continuity/identity impact;
- authority changes, or an explicit statement that none occurred;
- rollback state and reversibility;
- improvement proposals; and
- recommended next boundary.

Temporary handoffs MUST remain distinguishable from canonical project truth and
SHOULD be removed when their lifecycle ends. Important Fawkes state MUST NOT
exist only in one worker conversation.

## 12. Phoenix Worker Coordination / Specialist Mesh — architectural direction

**Phoenix Worker Coordination**, also called the **Specialist Mesh**, is a named
future architectural direction, not an active runtime capability or roadmap
phase assignment. Its conceptual flow is:

```text
need or opportunity
-> determine required expertise
-> evaluate candidate model or tool
-> assign a role
-> bound authority
-> generate least-necessary context
-> hand off current state
-> perform scoped work
-> receive a structured report
-> cross-worker review where useful
-> Tanner approval where required
-> update authoritative Fawkes state
```

This direction connects Worker Admission, structured handoffs, cross-worker
review, a future AI/Tool Scout, and the future Development Orchestrator. It does
not activate agents, delegation, autonomous execution, tool installation,
standing permissions, Development promotion, or cross-worker data access.
Future implementation must reuse existing ownership, capability, ledger,
receipt, Human Review, and protected-foundation contracts rather than create an
authority bypass.

## 13. AI / Tool Scout — architectural direction

A future AI/Tool Scout may discover and evaluate models, agents, MCP systems,
developer and Blender/avatar tools, voice and multimodal systems, memory/context
systems, research and testing systems, deployment tools, and automation
frameworks.

Evaluation SHOULD consider actual Fawkes benefit, compatibility, integration
cost, reliability, provider lock-in, permissions, privacy/security impact,
maintenance, reversibility, and whether the candidate complements or replaces
an existing capability. A useful discovery SHOULD become an improvement
proposal. Discovery is not installation, connection, credential, execution, or
production authority. No Tool Scout runtime is implemented by this charter.

## 14. Host permission explanation contract

When a host client asks Tanner to choose **Always**, **Once**, or **Deny**, and a
worker can explain the request, the worker SHOULD classify the actual invocation
rather than only the tool name:

- **SAFE ALWAYS:** repeat use is narrowly scoped, reversible or read-only,
  carries no meaningful credential/disclosure/destructive risk, and the proposed
  persistent rule cannot authorize materially broader invocations.
- **ALWAYS WITH SCOPE:** repeat use is reasonable only with a precise command,
  resource, domain, directory, or capability boundary. Broad approval SHOULD NOT
  be recommended.
- **ONCE ONLY:** the invocation is unusual, sensitive, externally consequential,
  difficult to bound, or unnecessary as standing authority.
- **DENY:** the request exceeds scope, lacks required authority, bypasses a
  security boundary, targets the wrong resource, or has unjustified risk.

The explanation SHOULD state why the tool is needed, the governing Fawkes
authority rule, its present use, meaningful risk of permanent approval, and the
recommended host button. Host enforcement MUST NOT be bypassed, forged, or
self-granted. A worker recommendation is not the host's authorization decision.

## 15. Improvement pipeline

The long-term improvement pattern is:

```text
Observe
-> Propose
-> Cross-review
-> Prototype
-> Test
-> Human review
-> Approve
-> Promote
-> Learn
```

Each arrow is a boundary, not an automatic transition. Prototype authority is
not promotion authority. Experimental success is not production authorization.
Human review MUST use the applicable authenticated, scoped approval mechanism;
ordinary conversation, worker agreement, repeated past approval, or proposal
quality does not create standing authority.

## 16. Current cross-worker review items

Non-authorizing embodiment proposals discovered through the proven specialist
workflow are recorded in
[Cross-worker Improvement Proposals](CROSS_WORKER_IMPROVEMENT_PROPOSALS.md).
They are not runtime capabilities or approved implementation work.

## 17. Revision rule

Any worker MAY propose a roadmap change, but no specialist may unilaterally
rewrite canonical roadmap truth. Affected domains SHOULD review consequences;
evidence and disagreement MUST remain visible; Tanner approves consequential
changes where rider authority applies; and the repository worker updates
canonical documentation only after approval. Architecture review reconciles
dependencies but cannot manufacture consensus or promotion authority.

Charter revisions SHOULD preserve visible version history and explain material
changes. A revision MUST be checked against canonical identity, continuity,
authority, security, privacy, and domain contracts. Changes to worker
philosophy cannot silently change runtime permissions, approved task scope, or
production state.
