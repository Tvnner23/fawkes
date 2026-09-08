# Alpha source dependencies

This bounded adoption supplies the normal application's missing inherited-history
staging, manual search and validation modules, strict Archive metadata reader,
and the corresponding conversation, instance, ingest, canonicalization and
Archive projection APIs. Its parent is the accepted continuity integration
`38d26df22f005f01bc279290792c968be115fbac`.

History, its processing ledger and capability receipts, and HTTP rider activity
follow `FAWKES_RUNTIME_STATE_ROOT`, like ingest and canonical indexing. The latter
three defaults were corrected after the isolated tests demonstrated metadata
escaping into the development checkout. Explicit caller paths still take precedence. Configure the runtime
root before starting the process; changing an environment variable after module
import does not relocate live data. This adoption performs no data migration.

Qualification covers a nonempty first startup, exact original evidence navigation,
inert inherited staging, event replay and publication, revision chronology,
owner isolation, populated-index preservation on failures, normal chat and CLI
persistence. `tests/test_alpha_startup.py` uses only synthetic state and forbids
provider/network calls. The same default-root regression fails against the
retained pre-correction modules and passes against the corrected ones.

Native History navigation also requires the retained digest and byte length,
regular non-symlink source bytes, and containment in the selected Archive roots.
Invalid or unverifiable sources are refused, not silently repaired. Malformed,
non-object or duplicate-key native metadata degrades only the native domain;
healthy inherited results remain available. `tests/test_history_integrity.py`
reproduces both independently reviewed failures and covers altered bytes, unsafe
references and nonregular sources. Synthetic fixtures include the byte length
that actual Archive writers retain; missing historical identity is not invented.

The separate capture receiver is not a normal-app startup dependency. Its retained
replay test and source correction remain together in the deferred Archive adoption
inventory; neither is claimed accepted by these normal-app tests. All original
source, the complete original test and prior findings remain retained. No capture
receiver or external capture service is launched or enabled here.

Source readiness is not an Alpha release or a claim that personal recording
controls, Phase 10 Workshop, final trust/release checks or the seven-day Tanner
daily-use trial have passed. Those remain the next canonical gates. The working
Pi developer console, Worker conversation, bridge, private data and rollback are
not changed by this source batch. Broad cleanup remains deferred except for
demonstrated Alpha dependencies.
