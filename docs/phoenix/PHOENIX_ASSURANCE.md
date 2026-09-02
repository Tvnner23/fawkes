# Phoenix Assurance Contract

**Contract ID:** `phoenix.assurance`  
**Version:** 1.0  
**Status:** Canonical cross-cutting contract; automated runtime not implemented

## Purpose

Phoenix Assurance provides risk-proportionate, independent evidence that an
exact candidate satisfies an exact acceptance contract. Builder-owned tests are
necessary but are not sufficient for consequential or protected work.

Assurance composes existing Test Center, Replay/Flight, artifact, recovery,
security, Ghost Rider, Human Review, and rider evidence. It does not create a
duplicate testing universe, canonical truth engine, promotion authority, or
permission source.

## Acceptance contract

Consequential work begins with a versioned bounded contract identifying:

- intended and forbidden behavior;
- rider-visible expectation;
- security, privacy, ownership, authority, identity, and continuity invariants;
- failure/degradation and protected behavior;
- regression boundary and rollback requirement;
- evidence and independent verification required;
- assurance tier;
- limitations and exclusions.

Builders may contribute, but a contract cannot be silently redefined after the
candidate exists. Material revision retains visible version history and cannot
turn observed failure into success by omission. The assurance tier is selected
before implementation and cannot be lowered by the builder alone.

## Assurance tiers

### Tier 0 — routine

Documentation, formatting, isolated low-risk refactors, and test maintenance.
Focused validation, appropriate regression checks, and diff inspection normally
suffice. Independent review is optional or sampled.

### Tier 1 — bounded

Meaningful prototypes and non-consequential bounded production behavior require
a predeclared target, builder evidence, affected-path acceptance, and an
independent spot-check before promotion/generalization when novelty or risk
justifies it.

### Tier 2 — consequential

Cross-system, durable, privacy/provider, recovery, production-context,
production-artifact, or authority-sensitive behavior requires a versioned
acceptance contract, builder whole-system sweep, independent verification,
failure/rollback evidence, relevant security review, and independent
re-verification after defects. Mandatory failure or inconclusive evidence blocks
completion/promotion.

### Tier 3 — protected foundation

Identity, continuity, permissions, secrets, autonomous external/physical action,
migration/restoration, and controlled promotion require strong builder/verifier/
promoter separation, multiple validation methods, recovery proof, security and
Human Review, explicit Tanner decision where required, different-model
verification when useful, and simulation/Ghost Rider evidence for longitudinal
claims.

Hard security, ownership, continuity, and authorization invariants require 100%
correctness wherever they apply. Tiers scale evidence effort, not permission.

Worker Exchange retirement is a Tier 2-or-higher promotion boundary. Its
predeclared hard invariant set must pass 100% against the exact production core
and every active real transport adapter; one hard failure blocks promotion.
Independent verification includes held-out adversarial derivation, real-route
round trips, corruption/truncation/injection/routing attempts, and failure-close
behavior. Passing Assurance supplies evidence but does not itself authorize
retirement of manual transfer.

## Independent verifier role

**Sentinel** is the provisional name for an independent verifier role. It is not
an authority class. The verifier independently derives checks from canonical
contracts, inspects exact candidate/artifact identities, exercises black-box,
adversarial, failure, rollback, recovery, and rider-visible paths as appropriate,
and reports missing evidence or overstated completion.

Sentinel must be distinct from the builder for assurance that requires
independence. It cannot modify the candidate under evaluation, approve its own
run, update canonical truth, grant permissions, promote, restore, or become
Phoenix identity/recovery authority. Verifier tests and conclusions are
attributed evidence and may themselves be disputed.

Different model/provider families are preferred for suitable higher-risk work
when capability, privacy, cost, and evidence quality permit. Diversity alone is
not independence. Deterministic tools, separate test derivation, black-box
evidence, context separation, and disclosed common-mode dependencies matter
more. Phase 18 later supplies systematic selection/calibration/budgets.

## Evidence responsibilities

- **Builder:** implements and supplies focused/whole-system evidence; cannot
  unilaterally certify higher-tier completion.
- **Test Center:** executes registered deterministic acceptance and separates
  runtime health from acceptance evidence.
- **Replay / Flight Recorder:** preserves what happened and supports detached
  inspection/replay; it does not judge desirability.
- **Sentinel:** determines whether the exact candidate satisfies the scoped
  contract and reports coverage/limitations.
- **Ghost Rider:** evaluates repeated, adversarial, experiential, and long-horizon
  behavior where synthetic evidence is valid; it is never promotion authority.
- **Human Review / Tanner:** makes decisions belonging to rider, aesthetic,
  identity-expression, protected, or consequential authority.

No evidence producer automatically promotes a candidate.

## Assurance record and rider verdict

An append-only assurance record references acceptance contract/version, exact
build/artifact/revision, builder evidence, verifier identity/scope/independence,
Test Center/Replay/artifact/recovery/Ghost Rider evidence, coverage, limitations,
disagreement, verdict, and recommendation.

The rider projection contains:

- **Expected:** contract and rider-observable behavior;
- **Observed:** independently reproduced or inspected result;
- **Verdict:** `pass`, `fail`, `partial`, or `inconclusive`, scoped to candidate
  and contract;
- **Failures / risks:** incorrect, fragile, untested, uncertain, or suspicious;
- **Authority check:** ownership/privacy/permission/transmission/promotion;
- **Rider impact:** what Tanner should experience;
- **Evidence:** stable underlying references;
- **Recommendation:** promote, fix/retest, prototype only, reject, or require
  more evidence.

The summary never replaces evidence. `Pass` is not a universal guarantee and
does not itself authorize promotion.

## Development Orchestrator boundary

Phase 10 formalizes acceptance/proposal/assurance evidence. Phase 17 may bind
candidates to contracts, assign separate roles, compose minimized handoffs over
Worker Exchange, schedule sandboxed checks, collect evidence, return failures,
and request re-verification. It cannot select only favorable evidence, suppress
dissent, rewrite failed contracts, certify itself, or promote.

## Recovery readiness

For consequential persistent changes, `recovery_ready` may be a prerequisite,
not a passing consequence. Sentinel may inspect candidate lineage, immutable
baseline, rollback point, dependency closure, dirty state, restore result,
isolated load, protected diagnostics, and regeneration evidence. This grants no
backup, restore, identity, or promotion authority.

## Security boundary

Verifier scope is deny-by-default, read-only/isolated where possible, exact-
candidate bound, Phoenix/reality scoped, expiring/revocable, resource bounded,
and separately authorized for provider/tool transmission. Production data and
secrets are excluded unless explicitly required through their own controls.
Worker output and artifacts remain untrusted. Conflicts and inconclusive results
remain visible. Fixes require a new candidate identity and re-verification.

## Explicit non-implementation

Manual independent review can follow this contract now. No Sentinel service,
assurance store/UI, automatic tier classifier, verifier router, Ghost Rider
execution, promotion gate, or Development orchestration is implemented here.
