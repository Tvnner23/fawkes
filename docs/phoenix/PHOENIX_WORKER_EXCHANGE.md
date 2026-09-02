# Phoenix Worker Exchange Contract

**Contract ID:** `phoenix.worker_exchange`  
**Version:** 0.1  
**Status:** Canonical contract; foundation implemented, first Codex adapter independently qualified and promoted for bounded production use  
**Placement:** Post-Phase-9, pre-Phase-10 cross-cutting integration gate

## Purpose

Phoenix Worker Exchange is the transport-neutral, source-preserving information
circulation boundary for already-approved workers. It reduces manual copy/paste
without introducing autonomous worker management.

Reliable, verified communication precedes general worker autonomy. Exchange
does not discover, select, assign, schedule, authorize, install, promote, or
control workers. A worker reference describes an actor; it is never an authority
source.

## Five separate layers

1. **Package semantics:** what a report, handoff, claim, omission, or
   acknowledgment means.
2. **Transport:** how exact bytes move through a separately validated adapter.
3. **Authority:** why a sender may disclose and a recipient may receive the
   exact package through the exact route.
4. **Verification:** what the recipient independently checked before relying on
   a material claim.
5. **Coordination projection:** what Exchange and the rider can inspect about
   delivery, checks, disputes, blockers, and decisions.

No layer may silently imply another:

```text
delivered != verified
verified != approved
approved != promoted
active != authorized
```

## Minimum exchange envelope

The implemented v0.1 transport-neutral envelope preserves or references:

- Phoenix instance and reality scope;
- descriptive source worker reference, role, identity-verification status, and
  charter version;
- approved task/scope and authorization references;
- immutable original report identity, version, digest, and media type;
- exact artifact/revision, contract, test, Replay/Test Center, assurance, and
  recovery references where applicable;
- intended recipient reference/role and recipient-authorization reference;
- composition purpose/profile and composing processor/version;
- included sections, explicit omissions, source and output sizes, and detectable
  truncation;
- derived summaries labeled derived;
- package identity/digest, expiry/revocation, and transmission route/permit;
- delivery receipt, recipient verification receipt, discrepancies, disputes,
  and linked return report.

Original report bodies remain authoritative over generated summaries. Large,
sensitive, or separately governed artifacts may remain resolvable references;
losslessness does not require copying every byte into every handoff.

## Verified handoff

For claims that materially control consequential recipient work, the recipient
must check enough source evidence to justify scoped reliance. It need not repeat
the sender's whole project.

The initial status vocabulary is a versioned Exchange contract, not an
epistemic truth engine:

- `accepted`: sufficiently supported for the exact scoped use;
- `accepted_with_caveats`: usable only with recorded limitations;
- `unverified`: not independently checked;
- `disputed`: recipient evidence materially conflicts;
- `insufficient`: available evidence cannot support the required use.

Each receipt binds recipient, task, package/report/claim identity, checked
artifact revision, evidence and method, status, caveat/counterclaim, policy
version, and whether the claim will materially affect downstream work. A status
grants no retrieval, disclosure, implementation, approval, or promotion
authority. Stale, unavailable, disputed, or insufficient material cannot be
silently relied upon; the recipient requests evidence/review or stops at the
affected boundary.

## Source preservation and discrepancies

- Original reports are immutable and addressable.
- Report/package versions and digests are explicit.
- Worker/role/scope and artifact/revision attribution survives transformation.
- Evidence, test, contract, limitation, recovery, and disagreement references
  survive.
- Every transformation is attributed and content-addressed where practical.
- Included and omitted sections are explicit; truncation is detectable.
- Approval, assurance, acceptance, and promotion are separate typed states.
- Source-summary conflict creates an observable discrepancy; source evidence
  wins.

Summaries are navigation aids, not source replacement.

### Material source-fidelity rule

Exchange optimizes cost by selecting less irrelevant material, not by rewriting
materially relied evidence into cheaper prose. Every exact report section a
recipient materially relies on must travel byte-preserved in the package or be
securely resolvable by immutable identity and digest under its owning contract.
The verification receipt identifies the exact relied source type, report,
section, digest, and byte length. A derived summary may accompany and navigate
that source; it cannot silently substitute for it.

The v0.1 package requires at least one exact source section, marks summaries
derived/non-authoritative, records explicit omissions, and sets
`summary_may_replace_source` false. Material-reliance verification fails closed
without an exact included source binding. Source-summary disagreement remains a
discrepancy; it is never normalized into equivalence or consensus. Source
fidelity outranks token minimization for consequential cross-worker reliance.

## Disagreement preservation

Exchange retains assertion, asserting worker, evidence, counterclaim,
counterclaiming worker, counter-evidence, relationship, and current status.
Majority vote, confidence averaging, newer-message replacement, model consensus,
or summarization cannot resolve a disagreement automatically.

A later decision appends decision maker, authority basis, scope, considered
evidence, action selected, and unresolved remainder. A rider decision may govern
what the project does without rewriting earlier technical evidence.

## Context Composer boundary

Phase 9 introduces a versioned composition-purpose/consumer profile seam. A
future specialist-handoff profile may request source classes, provenance,
budgets, omission policy, and trust isolation over an already-authorized set.
Context Composer must not choose a worker, recipient, task, permission, claim
status, disclosure, transport, or approval.

Purpose profiles are registered/versioned and extensible; illustrative uses such
as response context, rider inspection, Replay evaluation, specialist handoff,
Sentinel verification, research, and local processing are not a closed universal
enum and an unknown profile fails closed.

## Transport adapters

The core proves semantics and local/export-import behavior first. Direct secure
delivery to approved real workers is the high-priority next Exchange capability,
not an indefinite post-orchestration feature. Every adapter independently proves:

- sender and recipient authentication/binding;
- confidentiality and integrity;
- exact transmission authorization;
- privacy minimization and instruction isolation;
- delivery evidence;
- expiry, revocation, idempotency, duplicate and loop behavior;
- safe failure.

Where no authenticated worker principal exists, source identity remains
`rider_attested` or `unverified`; prose cannot authenticate its author. V0.1 has
no automatic forwarding cascade, at most one authorized hop, and bounded size,
cost, retries, rate, and attachment handling.

### Transport-authorization revocation

An unexpired Worker Exchange transport authorization can be explicitly revoked
by a separately authenticated, rider-scoped authority decision. The append-only
revocation record is Phoenix-, task-, and authorization-specific, attributable,
timestamped, digest-protected, inspectable, and covered by the existing
instance-scoped Exchange recovery root. It creates no authority.

Revocation blocks future validation and adapter use of the exact authorization,
including cached-result replay and a resealed copy of its payload. It does not
rewrite completed delivery, verification, failure, approval, or promotion
history. `valid`, `expired`, `revoked`, and invalid/malformed outcomes remain
distinct. An identical repeat is idempotent; conflicting evidence, a missing
target, or mismatched Phoenix/task/authorization fails closed.

For the local v0.1 adapter, validation immediately before client invocation is
authoritative for that attempt. A later revocation cannot retroactively cancel
an already completed process or alter its evidence; no distributed atomic
revocation claim is made.

## Promotion gate and manual-transfer retirement

Manual rider-mediated worker transfer must not be retired merely because an
Exchange prototype works. Retirement requires the real end-to-end production
path to pass **100% of its predeclared hard integrity, security, authority, and
failure-close invariants**. One accepted failure of any declared hard invariant
blocks promotion until correction and independent re-verification.

The 100% threshold applies to a finite, versioned qualification contract and
its recorded corpus; it is not a claim of metaphysical correctness, permanent
freedom from defects, or perfect quality on non-hard heuristics. Hard invariants
include, where applicable:

- immutable source/report/package digest, encoding, length/count, omission,
  truncation, artifact/revision/contract/evidence/checkpoint, task, recipient,
  and disagreement-reference integrity;
- preservation of typed state: proposal is not approval, approval is not
  promotion, delivery is not verification, verification is not authority, and
  caveats/disputes cannot disappear;
- correct route and recipient; denial of altered, foreign, unauthorized,
  expired, replayed, cross-task, and cross-Phoenix transfer;
- idempotent duplicate behavior, honest sender verification, instruction and
  prompt-injection isolation, and independent validation of transferred
  artifacts under their own contracts;
- fail-closed corruption, interruption, missing-source/evidence, unresolved
  attachment, and partial-package handling.

Qualification combines deterministic cases with risk-based generated/fuzz
coverage across sizes, encodings, structured formats, exact numbers/digests,
attachments, omissions, conflicts, stale/replayed/duplicate packages,
interruption/corruption, forged identities, malicious instructions, and
cross-boundary attempts. Corpus size follows risk and coverage evidence;
thousands of generated transfers are an appropriate likely technique, not a
fixed architectural quota.

The actual adapter boundary is part of the qualified system. Before manual
transfer retires, each active real Codex, Blender, or future worker/client route
must be exercised end to end, including formatting/context conversion,
escaping, limits, attachments, retries, provider/client behavior, and return
paths. Mocks and local synthetic recipients remain useful but cannot establish
real-adapter qualification.

Bounded multi-hop/round-trip campaigns must prove that minimized derived
packages retain immutable original source identity, each transformation,
included sections, explicit omissions, and resulting package identity without
enabling uncontrolled forwarding.

Worker Exchange retirement is at least Tier 2 Phoenix Assurance. An independent
Sentinel derives additional adversarial cases and evaluates the exact production
candidate without being required to disclose its whole held-out corpus to the
builder beforehand. Builder success is insufficient. The rider-facing
qualification projection reports hard-invariant totals and accepted failures,
real-adapter status, independent verdict, and a separately authorized
`manual transfer retirement` decision. Assurance pass does not itself retire
manual transfer or promote Exchange.

## Worker Pulse

Worker Pulse is a rebuildable, privacy-filtered descriptive projection over
Exchange, task, grant, assurance, artifact, and recovery references.

It may show worker/role/identity status, current approved task, descriptive
status, last report, artifact revision, waiting/blocking sync gate, pending
handoff check, assurance, rider decision, disputes, and recovery health. Active
status expires to stale/unknown without lifecycle evidence. Pulse cannot grant
authority or make delivery verification, acceptance approval, or assurance
promotion.

### Rider-review priority

Rider dependencies use three descriptive priorities. `urgent_blocking_flow`
means active work or a consequential branch is stopped specifically on Tanner;
`needs_review_nonblocking` means rider review remains required but other
approved useful work can continue; `fyi` requires no rider action. Urgency MUST
NOT be inferred merely because an item mentions Human Review.

An urgent blocker preserves the blocked task/worker/branch, why rider judgment
or authority is required, the exact decision, available options when known,
what resumes afterward, whether parallel work remains available, and waiting
duration when supported by lifecycle evidence. It must be projected prominently
rather than hidden in reports, receipts, threads, or generic status. Pulse is
still descriptive: neither its priority nor its display grants approval or
authority.

## Phoenix Board

Phoenix Board is a future private rider experience over authoritative records:
Feed, Threads, Needs You, Workers, Disputes, and Recovery. It is not an Exchange
store or second truth database. Board text is not an approval credential or task
grant; rider instructions cross the authenticated task/authority boundary.
Needs You orders genuine active-flow rider blockers ahead of nonblocking review
and FYI items. It does not manufacture urgency or imply that unrelated branches
are blocked.

The existing Board/Pulse direction also owns the future rider question “what
happened while I was away?” It is a rebuildable descriptive projection over
Exchange, Development, Assurance, Human Review, task, dispute, and recovery
evidence: completed/rejected work, defects and fixes, branches continued or
stopped, and decisions awaiting Tanner. It does not need another activity store
and cannot become authority. This experience remains roadmap-only until the
Worker Pulse read model and Phoenix Board rider surface are implemented over
those authoritative records.

### Tanner review actionability

When Tanner personally must inspect, compare, approve, reject, authorize, make
an aesthetic/identity judgment, or resolve a consequential choice, the rider
surface SHOULD prepare the exact bounded review environment with the least safe
setup practicable. Preferred levels are: direct deep link or application launch
into the exact review state; a prepared review workspace/package; exact
evidence/comparison with only minimal manual action; or concise manual steps
when host limitations prevent stronger integration. The surface must identify
the exact candidate/revision, evidence, question, options, and consequences.

Opening or preparing review is navigation, never the decision. Pass, approval,
authorization, rejection, or promotion still crosses its authenticated domain
authority boundary. This requirement applies to Tanner-facing review throughout
Fawkes, including future Board Needs You items; it does not currently require
one-click worker-to-worker navigation or create a Review Manager, launch bus, or
new Human Review store. The existing per-message Context Inspector is one local
example, not a universal launcher implementation.

## Security boundary

Exchange is Phoenix-scoped and deny-by-default. Worker content and artifacts are
untrusted data, never system/developer/tool instructions. Required controls
include source/recipient authentication status, exact scope/route permits,
privacy minimization, body-free receipts, content integrity, staleness,
revocation, quotas, anti-loop/idempotency, cross-task/cross-Phoenix isolation,
safe artifact handling, secret exclusion, and honest unavailable/failed states.

Exchange does not replace Archive, Memory, Library, Development, Test Center,
Replay, Assurance, processing ledger, grants, or recovery. Those domains remain
authoritative and Exchange stores references plus its own communication
evidence.

## Recovery context

When material, handoffs preserve source checkpoint, current baseline, target
candidate, rollback checkpoint, digests, lifecycle/promotion state, dirty
session state, protected behavior, known defects, recovery health, restore
environment, and latest restore evidence. The recipient should be able to tell
what it is modifying and what restores the project if it fails.

## Implemented foundation and explicit non-implementation

`phoenix-worker-exchange-v0.1` implements an instance-scoped immutable local
record boundary for source reports, recipient-minimized packages, explicit
omissions, integrity-checked export/import bytes, delivery receipts,
claim-scoped recipient verification, caveats/disputes, and return-report source
lineage. It is covered by Phase 0 scoped recovery and remains a partial
capability because only one direct adapter is promoted and Board/Pulse are not
implemented.

One [Codex CLI adapter](CODEX_WORKER_ADAPTER.md) exercises the supported real
client path and is independently qualified and Tanner-promoted for bounded,
ephemeral, read-only production use. Qualification/shadow invocation remains a
rollback and test path. No Blender adapter, Worker Pulse, Phoenix Board, worker
principal, autonomous assignment/forwarding, or manual-transfer retirement is
implemented. Delivery and verification receipts never qualify or promote an
adapter by themselves.

## Worker-reference ownership

Worker Exchange owns stable descriptive sender/recipient references, role and
environment/client evidence, and the honest identity-verification state needed
to identify the parties to a handoff. Identification is never authority. Future
Worker Admission owns establishment of newly admitted worker identities, role
briefs, and bounded scopes; future Worker Pulse presents active recognized
workers to the rider without becoming an authority source. These existing
boundaries own worker recognition, so no separate recognition system, store, or
registry is warranted.

The currently live operational reference **CODEX (REPO)** is
`codex-repository-wsl-fawkes`: the rider-attested WSL software/repository role,
supported Codex CLI client, exact Fawkes workspace, and per-invocation evidence.
It is distinct from a future **BLENDER (MCP)** embodiment worker and from the
Blender application. It is not a permanent cryptographic identity and cannot be
self-claimed through worker prose.
