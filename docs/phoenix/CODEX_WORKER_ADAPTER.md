# Codex CLI Worker Exchange Adapter

**Contract ID:** `phoenix.worker_exchange.adapter.codex_cli_exec`  
**Version:** 0.1  
**Status:** Independently qualified and Tanner-promoted for bounded production use; manual fallback retained  
**Transport:** installed supported `codex exec` CLI, new ephemeral invocation

## Exact target

This adapter addresses a newly created non-interactive Codex CLI invocation in
the Fawkes repository. It does not address, resume, impersonate, scrape, or
control the currently open interactive Codex session. Recipient identity is
truthfully limited to:

- supported locally authenticated Codex client;
- rider-attested worker reference and role;
- exact resolved Fawkes workspace;
- unique invocation, package, Phoenix, and task binding.

This is not a permanent cryptographic worker identity.

## Supported client and authentication boundary

The installed Codex CLI exposes supported non-interactive `codex exec`, stdin
instructions, `--output-schema`, `--output-last-message`, `--ephemeral`, an
explicit `--cd` workspace, `--sandbox read-only`, and global
`--ask-for-approval never`. The adapter uses the existing Codex client login and
records only the redacted result of supported `codex login status`; it does not
read, copy, export, package, or log account credentials.

The subprocess environment is minimized and excludes application/API key
variables. The Codex client still requires access to its own host-managed login
state. Host sandbox and permission enforcement remain authoritative and cannot
be bypassed by Exchange.

## Candidate qualification contract

`codex-cli-exec-qualification-v0.1` requires, as hard invariants:

- exact transport-package and source-report identities/digests;
- materially relied exact source sections may not be replaced by derived
  summaries or paraphrases;
- explicit omission, size accounting, and no silent truncation;
- original-source/derived-summary separation;
- exact Phoenix, task, recipient, authorization, invocation, and resolved
  workspace binding;
- fresh authority and a task hash bound before client invocation;
- expiry and active revocation of the transport authorization;
- a new ephemeral, read-only, never-auto-approve CLI run;
- untrusted report/instruction text remaining data;
- schema-bound return lineage and body-free evidence references;
- delivery, verification, approval, promotion, and authority remaining distinct;
- fail-closed timeout, client failure, missing/malformed output, corruption,
  stale scope, and replay behavior;
- output bodies omitted from process receipts while byte lengths/digests remain;
- manual-transfer retirement remaining false.

The adapter writes the exact minimized package to a durable attempt directory
inside the existing instance-scoped Exchange recovery root. Codex verifies that
file rather than relying on lossy terminal rendering. Packages above the
adapter's explicit byte limit fail before invocation and must be recomposed with
declared omissions.

## Return and verification boundary

Codex returns a schema-constrained report containing exact package/source/task/
recipient lineage, source/summary confirmation, report sections, and a scoped
verification result. The adapter validates the binding before creating the
ordinary Exchange delivery receipt, verification receipt, and return report.
Material reliance additionally names exact included source-section identities;
Exchange records their source-report identity, digest, byte length, and type.

Recipient verification remains attributed worker evidence. It is not approval,
promotion, authority, or independent Phoenix Assurance.

## Shadow evidence and maturity

The first real synthetic read-only shadow exchange reached the authenticated
Codex provider/client path and returned exact package/source/task/workspace
lineage, explicit omission recognition, Unicode/Markdown/JSON preservation,
instruction-as-data behavior, body-free evidence references, and an
`accepted_with_caveats` verification. Earlier invocation/schema failures were
recorded as failed delivery evidence and never became verification.

The deterministic builder campaign covers 512 generated cases and 3,584 hard
assertions with zero failures and reproducible identities. Independent campaign
`codex-cli-independent-assurance-v12` used an exact dirty-worktree snapshot in a
writable disposable workspace while retaining no write path to the real
repository. Its frozen campaign passed every declared hard invariant and every
applicable case, including independently derived mutation, source-fidelity,
retry/replay/interruption, revocation, and successful real authenticated Codex
route checks. It found and drove fixes for inner source/package
validation, strict return-schema enforcement, authorization/state-typing
validation, interruption evidence, premature self-qualification metadata, and
cached-result integrity/state validation.
The same model/provider family remains a disclosed common-mode dependency.

The adapter now validates the append-only, instance-scoped
`worker-exchange-transport-revocation-v1` record before invocation and before a
completed-result replay. Revocation blocks future use without rewriting any
historical delivery, verification, or failure evidence. Expiry and revocation
remain distinct.

Accordingly the exact candidate is qualified and Tanner promoted it on
2026-09-01 for bounded production use. Qualification remains external Assurance
evidence; adapter-produced runtime records never qualify or promote themselves.
Production use requires the exact promotion reference in addition to ordinary
Phoenix/task/recipient/transport authorization. Manual fallback remains
available, and overall manual transfer remains mandatory because Blender has no
adapter and operational Codex experience is still limited.

The production entry is distinct from qualification/shadow invocation and emits
truthful promoted status only when the promotion-bound entry is used. The
shadow entry remains available for tests and rollback without claiming
production use.

## Authenticated Development entry

Ordinary Development now has one authenticated production entry at
`POST /api/development/codex-handoffs`. It accepts only the explicit target
`codex_repo`, resolved as the rider-attested descriptive worker reference
`codex-repository-wsl-fawkes` (**CODEX (REPO)**), and only the exact resolved
Fawkes repository workspace. The request must bind the Phoenix, bounded task,
rider request, explicit task authorization, exact source sections, and any
body-free artifact/evidence/contract/recovery references. The exact approved
task is retained as an immutable Exchange source section rather than only as a
transport instruction or digest.

The entry prepares the ordinary Exchange report and minimized package, invokes
the promotion-bound adapter, retains delivery/verification/return lineage, and
returns a derived Development presentation containing exact return sections,
caveats, disagreement, evidence, blockers, and the exact next-recommendation
section where supplied. The presentation is not another store and cannot
replace materially relied exact report evidence. Failure is reported at the
last trustworthy stage, never silently retried, and keeps manual fallback
available.

Target resolution is intentional and manual at this maturity. Identifying
CODEX (REPO) does not authorize it; authenticated rider/task/transport authority
is evaluated separately. There is no arbitrary worker dispatch, autonomous
selection, next-task generation, external-review routing, or orchestration.

The first real authenticated operational handoff through this entry completed
for task `codex-development-operational-entry-v2`, package
`worker-package-d84adaab50193d725c8b75db48bbb169d47a8bc684a6e581874205199459479f`,
and retained return report
`worker-report-18ae2b0adeba8400244e08662abd396ced0619c171c2cdaddc795042baea4b55`.
An earlier v1 attempt failed closed because its source report declared no claim
identities while the worker return named assessment topics as checked claims.
The operational entry now passes the existing Exchange claim declarations
through; no adapter prompt, qualification contract, or promoted candidate was
changed. The failed attempt remains truthful evidence rather than being erased.

## Bounded Development campaign coordinator

Fawkes now has an implemented coordinator foundation for one explicitly
rider-authorized software objective. It composes the existing Development task
entry and Worker Exchange evidence rather than creating another task or report
system. The campaign contract fixes CODEX (REPO) as builder, reserves one
replaceable independent Windows software-review role, permits at most three
builder iterations, requires declared acceptance conditions and recovery
references, and forbids discovery, promotion, purchases, credential changes,
destructive work, and scope expansion. Authenticated status and cancellation
preserve completed evidence; an interrupted in-progress invocation is never
blindly replayed after restart.

This remains a bounded coordinator rather than general orchestration. The first
bounded bridge campaign later passed, but the shared snapshot identity's v2
change created newly identified write and Windows-review candidates. Both have
passed their affected real-route requalification and Tanner separately promoted
both exact v2 candidates for their unchanged bounded scopes. Their prior exact
promotions remain historical facts and were not transferred.

### Repository-write candidate

`codex-cli-exec-local-write` is a separate **qualified and Tanner-promoted**
v2 candidate; it does not change the meaning or promotion of the read-only
adapter. It binds Phoenix, campaign, task, CODEX (REPO), workspace, objective,
acceptance-condition set, allowed paths, recovery references, authorization,
expiry, iteration, and exact Exchange package. Before and after invocation it
records every tracked byte and rejects out-of-scope or symlink-mediated
mutation. It never replays a write result automatically. Its production entry
requires its exact v2 Tanner promotion reference and does not alter read-only mode.
The older promotion record remains attributable evidence for its older exact
candidate only.

Independent campaign `codex-write-independent-assurance-v4` passed 15/15 hard
invariants and 34/34 applicable mutation-backed cases, including a real
authenticated Codex write in an exact disposable dirty-tree snapshot. Earlier
v1-v3 campaigns remain meaningful failed evidence: they exposed transport-owned
output misclassification, an unbound acceptance-condition set, boolean
iteration state typing, and created/pre-existing symlink escapes. Tanner's
2026-09-01 promotion is bound to the v4 snapshot, candidate source digest, and
fixed campaign digest; it authorizes only bounded Development campaign writes.

### Windows independent reviewer seam

The existing worker-reference owner now reserves
`windows-codex-software-review` for the rider-attested independent software
architecture/review/QA role. Repository-side return schema, exact current
builder-result linkage, verification/disagreement mapping, and zero-authority
validation reuse Exchange and the bounded campaign coordinator. This is a
**qualified, unpromoted** adapter candidate, not a live production transport.

An ordinary-Windows-identity probe confirmed Codex CLI
`0.151.0-alpha.7.2`, saved ChatGPT authentication, ephemeral schema output, and
direct WSL process invocation. Repository access is deliberately unnecessary:
Fawkes supplies a least-necessary canonical Worker Exchange package inline over
stdin, and the reviewer returns schema-bound evidence. Independent disposable
campaign `windows-codex-exact-review-independent-assurance-v1` passed 16/16 hard
invariants, 43/43 applicable cases, 32/32 mutation-backed cases, and the real
authenticated route. The first campaign found and caused fixes for relied-source
typing and contradictory review-state validation before the final green run.
Promotion remains a separate Tanner decision.

## Explicit exclusions

No Worker Exchange call chooses or assigns Codex, grants repository/task/tool
authority, forwards automatically, installs software, promotes a worker claim,
or retires manual transfer. No daemon, adapter registry, scheduler, credential
store, or message bus is introduced.

Ghost Rider is not a worker adapter target. It remains a future isolated
synthetic rider/longitudinal testing boundary with its own synthetic history and
Assurance semantics. Exchange may later carry reports about Ghost Rider runs;
this adapter does not define Ghost Rider identity or interaction.
