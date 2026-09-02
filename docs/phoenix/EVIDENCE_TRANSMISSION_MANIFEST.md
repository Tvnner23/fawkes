# Pre-call Evidence Transmission Manifest

Status: immutable manifest and permit boundary implemented and accepted through
default served planner Chat; legacy remains an explicit rollback.

The content-addressed manifest binds one Phoenix, rider, turn, correlation ID,
provider policy/class/model route, planner and eligibility-policy versions,
adapter versions, and the exact selected evidence set. Each item records domain,
authority, privacy or legacy compatibility, source reference and digest,
evidence-body digest, and provider decision/reason. Evidence bodies are never
stored in the manifest.

Authorization is limited to that exact response-model transmission and grants
no tool, external, public, cross-rider, or cross-Phoenix disclosure. A permit
revalidates the immutable file, identity, route, evidence set, and body digests
before releasing bodies. Missing, denied, stale, mismatched, changed, malformed,
or tampered evidence fails closed. An empty authorized set is valid.

The rollback switch is deterministic: disabled selects the untouched legacy
path; enabled selects the planner path; planner failure degrades to empty
retrieval instead of reopening legacy evidence and bypassing a denial.

The live response prompt builder now requires the permit in explicit planner
mode, verifies it before incorporating evidence, and verifies it again at the
real `responses.create` boundary. Failure scrubs retrieved evidence and proceeds
with zero-evidence Chat. Planner mode is the served default; production adapter
construction and authenticated served-client acceptance are verified.

A validated native clarification choice never reuses an earlier permit. The
served path reruns retrieval and Phase 7 eligibility, constrains only the chosen
ambiguity set, and authorizes a new exact evidence set through this same permit
boundary. The final provider call performs the normal immediate re-verification.
