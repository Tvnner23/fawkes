# Fawkes: repository assessment

**8 September 2026 · Read-only assessment of the supplied export**

This is a source-informed assessment and a proposed change in execution strategy. It is not a canonical acceptance receipt, a production qualification, or authorization to change personal history, identity, permissions, or deployed services. The companion **Fawkes-Revised-Roadmap.md** supplies the proposed execution order.

## My judgment

**Keep building Fawkes. Keep its persistent personal-AI purpose. Change the way progress is selected and demonstrated.**

The repository contains a real foundation: immutable source retention, derived Memory, historical staging, retrieval and context composition, an application with Library/media/research, presence infrastructure, supervised development, and release tooling. It is substantially more than the approval loop visible in recent transcripts.

The strongest idea is that a particular Phoenix can retain attributable history and develop useful understanding while models, interfaces, and hardware change. The architecture already makes meaningful distinctions between an original, an interpretation, a proposed change, and permission to act. Those distinctions are worth preserving.

The weakest part of execution is the imbalance between sophisticated development-authority machinery and ordinary continuity correctness. Basic valid-input combinations still disagree at subsystem boundaries. Some tests replace the exact dependency whose behavior they claim to qualify. Status documents preserve old milestones without consistently retiring their obsolete present-tense claims. As a result, locally successful work can remain globally unusable, and the user receives an enormous evidence trail without a corresponding usable feature.

My assessment is therefore: **promising architecture, substantial implementation, uneven integration, and insufficient evidence of dependable daily personal use.** This warrants consolidation and real product use, not abandonment, a new orchestration framework, or an expansion into every future feature.

The public ambition may eventually be valuable, but the supplied evidence cannot establish market demand, willingness to pay, subjective AI experience, or durable human attachment. The first persuasive result is much smaller: Fawkes helps Tanner, accurately carries context across sessions, accepts correction, preserves his data, and respects his boundaries over actual daily use.

## What I would correct in my earlier advice

1. **I treated repeated stops as too reassuring.** A safe stop is evidence about containment. It is not evidence that the workflow is effective. A system can prevent unauthorized effects while failing nearly every useful completion. Both rates matter.
2. **I put too much of the console behind the autonomy chain.** A genuinely observational interface can be built and exercised without starting autonomous work. The real dependency is a safe, truthful read path. Physical input and richer repository views can follow independently of personal-Memory hardening.
3. **I overinterpreted elapsed transcript time.** Tanner explicitly said permissions sat unanswered. The code also distinguishes Attention waiting from provider execution time. I withdraw any inferred active-time or budget violation based on those elapsed durations. No honest completion estimate follows from them.
4. **I accepted the SQLite “harness-only warning” explanation too readily.** The exported broad log contains an unhandled memory-worker exception. Passing in isolation does not disprove a concurrency defect. The failure must become visible to qualification, not disappear into a separate green run.
5. **I treated large passing test counts as stronger evidence than they were.** They demonstrate useful coverage, but do not establish a composed successful campaign, observational HTTP behavior through real dependencies, or daily continuity. Several important behaviors are mocked at their boundary.
6. **I should have insisted earlier on a reproducible material baseline.** Preserving the 127 dirty paths prevented accidental destruction. Leaving runnable dependencies outside a reproducible committed baseline has also repeatedly complicated qualification. Both observations can be true.
7. **I would not now recommend replacing accepted components merely to simplify the diagram.** P1–P4 are integrated in this export. Removing LangGraph, replacing the Reviewer adapter, or inventing bootstrap authority now would add work without addressing the immediate defects demonstrated below.
8. **I blurred development autonomy and Fawkes's personal readiness.** A reviewed local coding campaign is one capability. It does not finish Memory integrity, recording controls, native continuity, daily reliability, or mature physical agency.

These revisions come from the repository evidence. I cannot attribute them to a measurable change in model capability, and I should not pretend that a more capable model makes an untested claim certain.

## What is actually established now

The capture binds HEAD `640f4246ab93f29f7d3e4d9c1747c7b0f98be2a0`, branch `fawkes/cleanup-drift-aware-write-rollback-v6`, 127 historical dirty paths, status digest `a2370cec42e3e64fde377b09e3e2d15a0b8510973d4fa264c4af0ff7f77a6543`, and zero staged paths.

| Work item | Evidence in this export | What that means |
|---|---|---|
| P1 browser Attention | Accepted canonical integration handoff | Preserve the integrated work; the earlier failed invocations are historical evidence. |
| P2 / Gate 1 multi-action Attention | Accepted canonical integration handoff | The current task is not to rebuild this from scratch. |
| P3 / Gate 2 Git prerequisite | Accepted canonical integration handoff | Preserve its canonical protection and restart semantics. |
| P4 / Stage B | Accepted integration at the captured HEAD | The runner is integrated. A generally successful live campaign is a separate claim. |
| P5 console and inert pilot | Candidate exists; independent review requires correction; no integration | Console implementation has begun. It is not yet an accepted available console. |
| One-batch pilot | Specification prepared, zero live budget, no campaign or launcher started | Preparation is not execution and creates no permission to start. |
| Personal Alpha | Several foundations exist; remaining trust obligations and real-use trial are open | Stage B completion does not close Alpha. |

Sources: `development-evidence/p1/p1-handoff.json` through `p5/p5-handoff.json`, `repository-context`, and the corresponding source. This assessment does not independently authenticate a live deployment or repeat the historical reviews.

## Findings that should change the roadmap

“Source-confirmed” below means the control flow or representation mismatch is visible in the export. “Isolated reproduction” means exact extracted functions were exercised with temporary or in-memory persistence seams, without importing the application. It is not a production reproduction. “Race risk” identifies a specific interleaving that still needs fault injection.

### 1. The console's read path has two separate side effects

**F01 · Console blocker · Source-confirmed, with an existing Reviewer finding for the first path.**

The console projection calls the canonical pending-Attention listing. That listing refreshes expiration, creates persistent locking state, and rewrites expired events. The Reviewer correctly caught this.

Independently, the HTTP authentication helper calls `RiderActivityStore.touch()` for authenticated requests. The P5 console polls every ten seconds. An unattended console can therefore keep writing a fresh human-activity timestamp and suppress inactivity-based progress notifications. Fixing only Attention listing will leave this second defect intact.

**Smallest correction:** provide an observational Attention projection and separate authentication from recording human activity. A read can display “expired as of this observation” without persisting a lifecycle transition. Mutations must continue to revalidate expiry. If genuine user activity is reported, distinguish it from background device polling. This does not require eliminating normal operational access logs or weakening authentication.

**Proof required:** repeated authenticated console requests through real service/store dependencies, with pending, expired, and absent Attention records, leave protected domain records and Rider-activity state unchanged. Existing HTTP tests mock authentication and the service, so they cannot prove that property.

Evidence: `development-evidence/p5/candidate-only/src/app/server.py` 211–227, 400–407, 519–526; `working-tree/src/runtime/chat_service.py` 1241–1244; `development_attention.py` 470–496; `autonomy_supervision.py` 67–77, 353–374.

### 2. The console exists, but does not yet deliver all the intended experience

**F02 · Product completion · Source-confirmed gaps; refresh behavior is a static risk.**

P5 contains the square shell, fixed header, four pages, swipe/keyboard navigation, idle return, and wheel equivalents. Preserve those. Its Repository and Architecture pages are currently much closer to summaries of system structure and metadata than full repository browsing or an observed architecture view. Code/diff explanations, changed-file inspection, and evidence-document navigation remain incomplete; even objective and remaining-budget context are missing from the small projection.

The source reconstructs detail nodes during refresh, which can discard expansion/focus. A retained selected-card reference can point to a detached element. This needs a focused interaction test; it was not reproduced in a browser during this audit.

The projected coordinator `READY` and Worker/Reviewer `IDLE` values originate in hardcoded service values. They should be labeled configured/unknown until there is observed runtime evidence. An honest empty state is better than an invented heartbeat.

**Smallest correction:** keep the existing frontend; preserve expansion/selection by stable record identity; label evidence age and unknown states; add bounded task/diff/source views only as their server projections become available. No second authority endpoint, showcase mode, or comprehensive graph explorer is needed.

Evidence: P5 `candidate-only/src/app/static/dev-console/console.js` refresh/render/selection paths; `working-tree/src/runtime/chat_service.py` 1264–1280; `development-evidence/p5/console-access-and-limitations.md`.

### 3. A replay can make derived search content disagree with its immutable source

**F03 · Personal-continuity blocker · Source-confirmed.**

`ingest_bytes()` returns an existing record for a matching capture-event ID before comparing the new payload or owner. `persist_live_message()` then indexes the newly supplied text using that old Archive ID. Identical retries are fine; the same event ID with changed text can produce a search projection that claims a source says something it does not say.

This is not evidence that Archive bytes were overwritten. It is evidence that immutable bytes alone do not guarantee truthful derived provenance.

**Smallest correction:** an existing event identity must require equality of its defined payload and ownership binding, otherwise reject or use an explicitly new revision identity. Build the projection from validated retained source content. Include changed-payload and changed-owner retries, not just identical retries.

Evidence: `working-tree/src/ingest.py` 30–39, 71–83; `src/runtime/persistence.py` 30–55; related capture receiver path. Current replay tests primarily exercise equal payloads.

### 4. State location is inconsistent across persistence, rebuild, and release

**F04 · Continuity/release blocker · Source-confirmed configuration mismatch; no deployed data loss demonstrated.**

Ingestion honors `FAWKES_RUNTIME_STATE_ROOT`, while canonical conversation reconstruction reads repository-root Archive directories. A rebuild deletes an instance's derived projection, enumerates configured-root conversations, then asks the other-root canonicalizer for their contents. That can commit an empty rebuilt projection despite valid originals in the configured root.

Production configuration compounds this: the supplied service selects `.local/state/fawkes`, while release construction links historical state from `/home/tvnner/fawkes`; some stores honor the environment and others use release-root defaults. The instance helper creates a default identity when the selected registry is empty. The export cannot tell us whether the actual installation has already reconciled those roots.

**Smallest correction:** one injected state-location contract for existing stores, explicit migration/compatibility handling, and a production startup guard requiring the expected identity. A missing production registry must not silently mean “make a replacement.” First qualify copied state at a non-default path; do not move live data as part of the audit.

Evidence: `ingest.py` 8–11; `capture/canonical.py` 8–10; `memory/archive_retrieval.py` 148–205; `instances.py` 7–12, 73–82; `runtime/production_release.py`; `deploy/systemd/fawkes-app.service` 15–35.

### 5. Memory needs one consistent mutation and recovery boundary

**F05 · Personal-continuity blocker · Isolated reproductions plus source inspection.**

Three specific problems matter:

- Supersession persists the replacement before retiring the old record. If interrupted between them, recovery treats a record with the work-item ID as proof that the whole mutation completed. An isolated fault injection left both records active while recovery reported `consolidated`.
- Reprocessing the same evidence can repeatedly increase confidence without adding new evidence: the extracted strengthening function produced `.60 → .84 → .936` for repeated identical evidence. Duplicate evidence is not independent confirmation; even distinct correlated evidence should not be described as a calibrated probability without justification.
- Owner checks differ among mutation functions. Supersession accepts another instance's target in an isolated function test. Scoped duplicate creation also omits the scope argument when falling back to strengthening. The ordinary Worker does some earlier filtering; no external attack path was established here.

**Smallest correction:** consolidate the existing mutation boundary so ownership, evidence idempotence, record changes, events, and ledger completion share one recoverable operation. Do not build a second memory system or transplant the entire development-authority framework into it. A database transaction or a bounded journal is an implementation choice based on the existing stores.

Evidence: `memory/store.py` 137–149, 298–335, 402–445; `memory/worker.py` 313–323. Recovery must prove the complete intended state transition, not merely find one product of it.

### 6. Canonical chronology and owner selection can distort context

**F06 · Personal-continuity blocker · Source-confirmed.**

Canonicalization selects a message's latest capture and uses that capture time as its conversation ordering time. Recapturing an earlier message can move it after later turns. It also groups by conversation/message identity before filtering the instance, allowing overlapping source IDs across owners to collapse before downstream isolation runs.

**Smallest correction:** preserve source-turn order separately from revision/capture time, and include owner scope before grouping revisions. Keep uncertain timestamps uncertain; do not manufacture precision.

Evidence: `capture/canonical.py` 24–26, 42, 57–70, 85–100; `memory/archive_context.py`; `memory/archive_retrieval.py` 162–201.

### 7. Important truth annotations do not reliably reach the response model

**F07 · Personal-Alpha quality gate · Source-confirmed omission.**

The production Memory adapter drops confidence/time information, and the final Composer rendering emits retrieved bodies plus evidence locators without the available uncertainty/contradiction annotations. Retaining a field internally is not enough if the model sees an unqualified statement.

**Smallest correction:** carry the minimal relevant uncertainty, source era, contradiction, and temporal qualification into the actual provider-visible context. Test that final representation. Keep it attributed data with no instruction authority. This does not mean dumping every metadata field into every prompt.

A separate Composer budget issue can reject a fully omitted contradiction group; its reachability is mitigated by upstream allocation and it should rank below the provenance and recovery defects.

Evidence: `runtime/production_retrieval_adapters.py` 172–191; `runtime/context_composer.py` 240–242, 457–470.

### 8. Two ordinary valid-input combinations still break reviewed application

**F08/F09 · General development-pilot blockers · Isolated exact-helper proofs plus source-confirmed call chains.**

**Condition order:** the builder hashes conditions in supplied order; the Reviewer hashes the sorted satisfied conditions; application requires those hashes to match. A caller can provide the same valid conditions in a different order and fail application. Sorting a particular external harness avoided that case without fixing the shared contract.

**Scope versus changes:** request preparation excludes every authorized path from the neighboring-workspace digest; durable application excludes only mutated paths. Authorizing `a.py` and `b.py` while changing only `a.py` is explicitly allowed by the validator, yet the clean workspace produces different digests and is quarantined. Directory-scope semantics also need consistent treatment.

**Smallest correction:** one canonical representation for condition identity, and one consistent scope/projection contract carried through both owners. Preserve original display order separately where useful. Old accepted evidence remains under its original schema; do not rewrite historical receipts to make a comparison pass.

Evidence: `codex_write_builder_adapter.py` 661–675, 720–731, 1032–1033, 1131–1139; `windows_codex_reviewer.py` 349–350; `durable_reviewed_application.py` 49–58, 220–228. Exact helpers demonstrated different hashes; the candidate-change validator accepted the unchanged authorized file.

### 9. Application protection needs the same seriousness already given to Git

**F10 · Pilot qualification gate · Specific static race and restart risks, not executed end-to-end.**

Cancellation uses the protected campaign store. The pending application path does not visibly hold the same protection through the mutation boundary. A possible interleaving is: load eligible campaign → prepare application intent → cancel persists → application replaces files → campaign update loses its revision race. Separately, expiry is checked before attempting durable application reconciliation, potentially stranding a partially applied operation instead of resolving it safely.

**Smallest correction:** reproduce those exact interleavings using existing hooks. Reuse existing campaign protection and explicit operation reconciliation. Define the irreversible boundary honestly: cancellation accepted before a new protected mutation must prevent it; an already-started operation must finish a safe reconciliation instead of pretending it never began. Expiry forbids new work, not accurate observation or required rollback of earlier work.

The runner should also reject a plan repository that differs from the canonical campaign's repository before any action. It should not interpret another repository as authority.

Evidence: `codex_development_campaign.py` 651–689, 2193–2198, 2232–2243; adapter application path; `langgraph_development_runner.py` 180, 194–202, 409–415. The protected Git path is comparatively coherent; preserve it rather than reopening its accepted design wholesale.

### 10. Qualification can report success after a background component failed

**F11 · Trust in test evidence · Directly observed in retained log; source shows the race.**

P5's broad log begins with `sqlite3.OperationalError: duplicate column name: candidate_content` in `fawkes-memory-triage`, then ends with `Ran 1003 tests` and `OK (skipped=15)`. The ledger uses a check-then-ALTER migration without serializing that sequence. Initial worker failure can escape its daemon thread without a component-failure receipt.

This does not invalidate every passing assertion. It does invalidate the stronger statement “the broad run completed with no unexpected failures.” Isolation is useful diagnosis; it is not a fix for a race.

**Smallest correction:** serialize schema migration, surface background worker failure, and make qualification drain/join relevant workers and fail on unexpected thread exceptions. Keep explicitly expected failure fixtures distinct. Do not repeatedly rerun until an unexplained exception disappears.

Evidence: `development-evidence/p5/qualification/broad-final.log` 1–21, 617–619; `memory/ledger.py` 71–86; `runtime/chat_service.py` 125–194.

### 11. Runnable and releasable are not yet fully reproducible claims

**F12/F13 · Stabilization/release gates · Source and export evidence; deployment not exercised.**

The export has 25 modified and 102 untracked paths, including material dependencies such as Library code and package/lock files. HEAD alone is not a reproduction of the supplied working tree. Preserve that distinction; do not blanket-commit the 127 paths or treat them as disposable dirt.

The supplied preparation script selects a release before installing dependencies into a shared production environment. A failed install can leave the new code selected, and code rollback does not restore the dependency environment. The web service's `NoNewPrivileges` configuration also conflicts with a control path that invokes `sudo systemctl`; the source tree is protected read-only under that service. Those behaviors need a real deployment-boundary qualification before claiming in-app restart or production-driven code application works.

**Smallest correction:** make the necessary material baseline reproducible in separately reviewed logical groups; parameterize hardcoded test paths; bind code to a reproducible runtime/dependency environment; validate before selecting a release. For now, disable unsupported privileged UI controls and use the documented local operator path. Add a narrow privileged helper only if in-app control is actually required; keep the web process hardened.

Evidence: `repository-context` dirty-path classification; `scripts/prepare_fawkes_production.sh` 8–15; `runtime/production_release.py`; `runtime/production_control.py` 17–19; `deploy/systemd/fawkes-app.service` 24–35; release/service tests.

### 12. Personal recording and native genesis are still real unfinished obligations

**F14 · Personal-Alpha gate · Source-confirmed in ordinary Chat; private live state excluded.**

The roadmap requires prospective native continuity binding identity, lineage, an authoritative writer epoch, and monotonic continuity position. The inspected ordinary write path has instance IDs, capture IDs, hashes, and atomic writes, but not enforcement of that whole contract. Existing complete-restore receipts verify backups; they do not prove exclusive continuation or fence an old writer. This is not a claim that Fawkes has no identity or no recovery tooling.

Chat also records accepted user/assistant turns and queues Memory candidates without a personal ephemeral-mode input. Disabling the Memory worker only stops background processing. Flight evidence can retain raw request/response text, so a future recording switch must cover derived traces too. Temporary attachment controls are real but are not equivalent to a non-recorded conversation.

**Smallest correction:** before counting native lived Alpha history, establish the smallest prospective single-writer/lineage/restart boundary required by the accepted doctrine. Never backdate it. Before offering private conversation, implement one authoritative recording policy applied to Archive, queued Memory, Flight and other body-bearing derived records. Keep minimal operational evidence separate and disclose any unavoidable retention; otherwise bound the dependent feature.

Evidence: roadmap 262–272, 1177–1197; `instances.py` 22–43; `runtime/persistence.py`; `runtime/phase0_integrity.py` 267–330; `chat_service.py` 776–873, 987–1001, 1043–1091; `retrieval_replay.py` 125, 139. These are not prerequisites to viewing synthetic development status on the console.

## Adjudicating the earlier Claude memo against this repository

| Claim | Judgment after source inspection |
|---|---|
| Identity-representation fragmentation is the root cause | **Important, but not the sole root cause.** Condition order and scope projection are concrete examples. Side-effectful reads, incomplete transactions, background exceptions, state-root disagreement, and missing product acceptance are separate mechanisms. One giant identity object would not fix them. |
| Three UI defects really belong server-side | **Right about authority ownership; too broad about the actual code.** The export has server-owned validation/consumption and accepted P1/P2 corrections. The browser still must present truthful success, expiry, and failure. Server checks do not make a misleading approval UI harmless. |
| Humans must never block inside a provider turn | **A good optimization target, not an absolute correctness rule.** The current code separates some clocks and can safely pause. Prefer preflighted bounded verification and durable campaign checkpoints outside provider execution where supported. Do not kill a turn and pretend it can resume without consuming a fresh bounded invocation. |
| Attention should occur at exactly three points | **Too rigid.** Authorization, consequential execution, and exceptions are useful classes. Actual interrupts depend on the grant and action. Preauthorized apply need not demand an invented extra approval; an unanticipated protected action cannot be auto-approved to meet a quota. |
| Replace megabyte packages with a manifest and content-addressed storage | **Directionally useful; not an immediate migration.** This repo already has digests and lossless bounded projections. Referencing bytes reduces transport only if the Reviewer can retrieve every required byte under the same scope. Missing evidence remains missing. A store containing the sole copy is not a disposable cache. Reuse existing retained blobs; remove duplication only after equivalence is established. |
| Inspect AI should own the Reviewer sandbox | **Not established by this evidence.** A new harness may be useful later, but no framework makes disk exhaustion impossible or proves compatibility with current provider, approval, and receipt semantics. First fix the current local preflight and boundary tests. |
| Drop LangGraph | **I disagree for the current point in the project.** Stage B is now integrated and delegates authority to canonical owners. The demonstrated bugs live at other seams. Keep the pinned local runner; reconsider deletion only if maintenance evidence shows it costs more than it provides. |
| Temporal/DBOS/Restate migration fixes none of the actual defects | **Correct as a decision against migrating now; “none” is too absolute.** Durable infrastructure can help some transaction/recovery problems, but moving code does not fix semantic mismatches, provenance, or authority. There is no evidence-led case for that migration here. |
| Circular review requires a new bootstrap tier | **The old harness had an operational bootstrap dependency; a new authority tier is now unnecessary.** Existing zero-provider readiness and exact native decisions have produced accepted P1–P4 integrations. Preserve them. Testing an approval subsystem with an external fixture is possible; accepting it need not mean self-approval. Do not introduce a new bypass or a mandatory retrospective review program. |

This table evaluates the memo's architectural argument. It does not make fresh claims about third-party licensing, pricing, or current product capabilities.

## What all of us underweighted

**A source locator is a claim, not a proof.** Immutable originals can coexist with a false index. Every replay/revision/rebuild path must preserve the source relationship.

**A status digest is not a content snapshot.** The same porcelain status listing can describe different bytes in already-dirty files. A stable HEAD, dirty count and status hash are useful checks, but content stability needs the retained per-file material manifest. This export provides substantially better evidence than a status banner alone.

**Content integrity is not hostile-process isolation.** A SHA-256 field identifies bytes; it does not authenticate a writer who can also replace the record and recompute its hash. Canonical ownership must be supported by actual process/filesystem permissions and trusted entrypoints. This audit does not establish resistance to an arbitrary hostile process with the same host-account access.

**A display is not automatically observational.** Authentication, constructor recovery, expiry refresh, and presence telemetry may all mutate state beneath an innocent GET. Testing only the projection formatter misses them.

**Recognition is not authority.** Familiarity, relationship Memory, an instance name, a healthy-looking dashboard, or an old approval must never authorize a new effect. This remains true when the body becomes more emotionally compelling.

**The boring successful case needs stronger composition tests.** Reversed condition order and an unchanged authorized file should not require an expensive Reviewer to discover. Actual-owner fixtures are more valuable here than another test of a mocked state label.

**Liveness belongs in acceptance.** Fail-closed behavior is essential, but Fawkes must also complete authorized ordinary work, deliver a pending decision, and give the user a visible outcome. Track useful completion and interruptions as well as prevented effects.

**Unattended permission waits are a workflow state.** Measure human wait separately. Avoid interpreting silence as consent or automatic failure, and avoid making the user watch a terminal to learn whether anything happened.

**The roadmap is carrying history and current state in the same tense.** This creates apparent contradictions and repeats already completed work. Preserve historical evidence, but give the present exactly one short status description and one next boundary.

## Execution changes I recommend

| Add or strengthen | Remove or consolidate to pay for it |
|---|---|
| One observational console read contract | Expiry mutation and human-presence writes from polling |
| One current milestone/status table in existing docs | Duplicate stale immediate-action lists and present-tense historical progress |
| One configurable qualification/review harness | Per-generation copied launch scripts with hardcoded roots and binding literals; preserve old scripts as evidence |
| One condition-identity and scope-projection convention | Repeated local serialization and exclusion interpretations |
| A small actual-owner campaign acceptance fixture | Redundant mocked “succeeded” assertions and broad reruns used only to obtain prettier counts |
| One state-root contract and guarded production identity selection | Independent repository/default/environment root choices |
| One recoverable Memory mutation boundary | Inconsistent direct mutation/recovery shortcuts |
| Qualification failure on unexpected worker exceptions | “Harness-only” labels based solely on an isolated pass |
| One minimal recording decision applied to all body-bearing outputs | Separate ad hoc flags that leave traces or queued Memory behind |
| Measured active work, provider use, and human wait | Estimates based on elapsed terminal banners and abstract cost units presented as dollars |

Do not add a new Board, framework migration, generic capability hierarchy, token tier, permanent Challenger, or new full-repository review cycle to deliver these changes. Use the existing ownership and acceptance mechanisms for the changed candidates. This assessment is an input to the existing stabilization work, not another supervisory product.

## Efficiency: what can actually be measured

The supplied transcripts are insufficient for an honest dollar total or completion date. A provider “cost unit” is not a dollar and a reserved turn is not necessarily a completed call. Background Memory evaluation also sits outside the development-campaign accounting path; that is an accounting gap, not evidence of unauthorized spending.

For a simple successful campaign, the design target is one Builder turn and one Reviewer turn. A structured-output repair can add a Reviewer turn; a substantive correction commonly requires another Builder/Reviewer pair. These are targets conditional on the current contracts, not guaranteed counts. Preserve conservative reservation and ambiguity rules.

Reduce provider turns by preflighting environment and real-owner composition locally, retaining a frozen candidate, and fixing the entire proven cause within a bounded correction rather than guessing at individual symptoms. Reduce input tokens by omitting duplicate materialization and supplying exact required context once; do not assume compressed transport bytes equal model tokens. Use actual reported input/output/cache usage before estimating currency.

Reduce human interrupts by consuming authorization already granted for exact routine work, making scope understandable in advance, and keeping exceptions meaningful. Keep grant and action boundaries exact. Reduce wall time by separating harmless console/hardware work from mutation readiness, avoiding unnecessary provider calls for deterministic checks, and showing durable progress without requiring terminal attendance.

Record the next few completed campaigns' provider processing, local qualification, human waiting, turns, interruptions, and outcomes in the existing campaign evidence. Use that small sample for future estimates. Do not turn measurement into another large prerequisite.

## Confidence and coverage

The archive SHA-256 is `26221846b5aa429dd9aac5ab8e2d5a2ec5bc64c053f31c975a0c903dfb5f7300`. It contains 1,088 tar members, including directories; 846 regular files have recorded content hashes and all verified. Three metadata files intentionally lack self-referential content hashes. The live working-tree export contains 367 files, including 160 source files, 104 test files, and 40 documentation files. Five parallel subsystem audits and targeted primary-source checks covered the main contracts and their integration seams.

This is not a claim to have manually reviewed every line of every exported file. Historical duplicate trees and every test body were not exhaustively read. The full Fawkes suite, live providers, production services, browser UI, and physical hardware were not run. Selected exact-function reproductions establish narrow claims only. Historical green results are reported as retained evidence, not tests rerun by this assessment.

The export excludes private runtime data, credentials, dependency installations, full Git objects, and raw provider messages. It includes binary-capable patches, status/history context, and selected structured development evidence. P5 includes its six postimages, snapshot digest inventory and exact-change bytes inside `prepared-v2.json`; some standalone package/preflight artifacts are unavailable. Do not mistake their absence for absence of all candidate evidence.

The remaining information most likely to change these conclusions is, in order: a redacted effective deployed state-root/instance/release binding; a real composed campaign result using the general inputs above; copied-state rebuild/restore and concurrent-worker results; actual daily-use continuity/correction examples; and Pi4 interaction measurements. None requires credential disclosure or indiscriminate private-history export.

No exported source file was changed. No Fawkes Worker/Reviewer invocation, message delivery, application, Git advancement, production change, history ingestion, or autonomous session was started.

`canonical_memory=false` · `creates_continuing_authority=false` · `live_autonomous_session_started=false`
