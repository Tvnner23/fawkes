# Workshop normal-app foundation

This document describes the canonical Phase 10 evidence workflow implemented
in this source. Source availability is not proof of independent acceptance,
installation, a completed Alpha trial, or authority to apply a proposal.
Use the exact candidate's acceptance and integration receipts for those
delivery claims. The recording-policy dependency must be accepted and composed
before delivery. Qualification uses isolated synthetic data, not live
Archive/Memory or the running console and bridge.

## Ordinary-user path

In **Developer → Workshop**, preserve and classify a failure; record the
investigation, learned knowledge and hypothesis; design an improvement; declare
versioned acceptance; import existing isolated evaluation and Assurance reports;
then submit an inert proposal to Human Review. Workshop also appears beside the
existing Human Review items. Numbered forms describe recorded work, not commands
to run research, experiments, tests, providers or campaigns.

**Developer → Proposals → Continue existing proposal in Workshop** inspects one
existing, exactly owned Development source. The server returns the SHA-256 of
its actual bytes. Intake binds that digest, preserves its source snapshot,
origin and Memory/message references, and never edits the original file. The
browser cannot supply a substitute snapshot. Missing historical producer
identity is explicitly `not_recorded_by_legacy_owner`; missing investigation,
acceptance and evaluation stay incomplete. Rider-entered stages are attributed
to rider input, never relabeled Phoenix-generated or independently verified.

The evidence view includes exact revision/digest/history, expected versus
observed behavior, scoped verdict, risks, unknowns, and the complete underlying
record with disagreements and limitations. Historical and reviewed versions are
read-only. Approval records a rider decision only: `outcome=not_applied`,
`applied_revision=null`, `execution_allowed=false`. A failed or inconclusive
evaluation is not rewritten by approval.

## HTTP contract and boundaries

The versioned envelope is `fawkes.workshop.http.v1`, always server-instance scoped,
with `creates_authority=false` and `execution_allowed=false`.

- `GET /api/development/workshop`: current proposal list and recording policy.
- `POST /api/development/workshop`: exact core create fields; rider-attributed.
- `GET /api/development/workshop/<id>[?revision=N]`: exact record and revision
  metadata, without changing state.
- `POST /api/development/workshop/<id>/actions`:
  `{expected_revision, action, payload}`; actions are `investigate`, `design`,
  `declare_acceptance`, `record_evaluation`, `record_assurance`, and `submit`.
- `POST /api/development/workshop/<id>/review`:
  `{expected_revision, decision, note}`; authenticated Tanner rider decision only.
- `GET /api/development/workshop/development-source/<source-id>`: read the exact
  existing server-owned Development source and its byte digest.
- `POST /api/development/workshop/intake-development`:
  `{source_proposal_id, expected_source_sha256, classification}`.

All reads require existing app authentication. Writes additionally require a
current Tanner browser session, session-bound CSRF token and same-origin Origin.
Requests cannot select another instance, actor, source snapshot or authority.
JSON is size-bounded and rejects duplicate keys/non-finite numbers. Revision CAS
conflicts return 409. Typed state/durability uncertainty returns 503 and no
successful write claim; the UI never retries an uncertain or stale write.

Each mutation passes a latched effective personal policy and the core rechecks
current consent before publication. Private mode, Archive-off or personal
diagnostics-off blocks new Workshop retention; existing evidence remains
readable. The UI adds no browser storage. Metadata-only operational authority
and provider permissions are untouched.

Evaluation and Assurance imports accept only an exact existing Worker Exchange
report reference, not an inline verdict. The core validates the attributed
section against the proposal, acceptance version, isolated candidate, chronology
and underlying evidence. There is no run/apply/export/campaign/provider endpoint.
Actual isolated evaluation or verifier work needs its existing separately
authorized owner; this app neither runs it nor fabricates its authority.

Workshop snapshots and recording consent use the explicit runtime-state root.
Development intake and Exchange references use their existing server-owned
locations, which can be different from that root. Trusted release symlinks are
resolved when binding these locations; subsequent access uses no-follow walks.
No second Exchange store is created under the recording-policy root and no
historical source is migrated. Backup preparation must include all these bound
locations; a single-root backup is complete only when they actually share it.

Inert exports preserve existing Exchange report semantics while synchronizing
the report file and its directory before a Workshop revision may reference it.
Publication never replaces an existing report identity. A failed synchronization
does not create a successful Workshop reference; an explicit retry verifies and
synchronizes any matching retained report first. The browser does not retry it.
Current Assurance advice must match the exact candidate, evaluation report and
acceptance contract. Older advice and disagreements remain expandable history,
not current recommendations.

## Bounded qualification

Executed with synthetic disposable roots, actual Workshop and Worker Exchange
owners, a minimal non-runtime HTTP service, loopback-only test servers and a
synthetic DOM/transport for the actual client. No provider was constructed or
called. The original focused command passed **38 tests** before the correction:

```sh
python -B -m unittest \
  tests.test_workshop_http tests.test_workshop_client \
  tests.test_recording_settings_http tests.test_recording_settings_client \
  tests.test_app_client -v
```

Eleven new HTTP checks cover authentication/CSRF/Origin, real versioned flow and
inert review, ownership, disabled recording, exact existing-source intake,
strict JSON, missing evaluation, CAS, corrupt preferences and ambiguous
publication. One new actual-client harness covers safe text rendering, precise
import payloads, revision pinning, no blind retry, historical/recording-off
read-only state, inert review and source intake. The remaining 26 are retained
recording/client regressions. This is implementation qualification, not an
independent review or a replacement for the seven-day real Tanner trial.

Correction checks additionally cover distinct server-source and policy roots,
report file/directory sync ordering, interrupted publication and exact retry,
no-replace identity races, and stale candidate/contract/evaluation advice in the
actual client renderer. Actual production release composition, mobile/browser
use, provider behavior and live evaluation remain separate delivery checks.
No legacy Development root is changed or implicitly migrated.
