# Summary objective / installation readiness correction

The accepted September14 design remains the product baseline at
baf526c8e3107e9f530f8de5a325ee9829efa545. Its installation stopped on the PC,
before Pi SSH. The old G22 assets were restored; the accepted design was not
observed on the Pi.

## Reproduced fault and correction

The canonical campaign owner accepts objectives up to32,000 UTF-8 bytes.
The design review's valid11,073-byte objective was rejected by the compact
console's2,048-byte text-field bound. The HTTP owner returned503; the cutover
assertion did not distinguish that from total-response overflow. Total overflow
was not established. Neither original campaign data nor historical records
should be rewritten to make a presentation fit.

Keep the2,048-byte compact text limit and512,000-byte total Summary limit.
Long objectives have an explicitly labeled UTF-8-safe excerpt, exact full-text
SHA-256 and byte length. Summary jobs and Campaign share that same reference.
Details can load the complete objective through a narrowly scoped authenticated,
passive read. Both server and browser check the exact campaign/hash/length;
changed, ambiguous, unavailable or unauthorized sources never yield another
objective. All original bytes stay with the canonical owner. Cached verified
text survives ordinary refreshes and is bounded to32 references.

Prepared text updates identify excerpts and retain the exact campaign/digest,
with instructions to retrieve the complete text in authenticated PC Details.
The Worker-page verbatim final-message Windows clipboard path is unchanged.
No permission, chat send, Rider activity, campaign mutation or provider call
comes from objective retrieval.

## Rollout gate

The reviewed launcher template projects actual retained campaign state before
stopping the previous preview. It records success bytes/digest or a bounded
private error. The HTTP cutover check still enforces512,000 bytes and now retains
status/length/digest on failure. Isolated readiness must check the authenticated
Summary and exact full-objective retrieval, not static assets alone.

Existing acceptance of the design, purple flame, five pages, same Worker,
native command cards, supported choices, history, clipboard, touchscreen
keyboard and navigation is inherited only for unchanged bytes and behavior.
This correction does not authorize a new Pi trial or answer any permission.
The installer must still stop for Tanner's native installation action. Reuse
passed G22 physical checks where applicable; the new design remains a separate
post-install observation. G22 rollback material and its known old-objective
presentation limitation remain retained, not silently called fully healthy.

The correction3 independent review passed nine requirements but reproduced an
escaping-heavy failure:32 valid32,000-byte objectives containing NUL characters
made campaigns and jobs alone serialize to818,596 bytes. Correction4 budgets
the JSON-encoded string content (excluding its two structural quotes), including
escaping and the visible excerpt suffix. It preserves the same2,048-byte cap and
the full-source32,000-byte canonical bound. An escaping-heavy objective can need
an excerpt even when its raw text is under2,048 bytes; the browser and exact
retrieval metadata explicitly support that case. Regression cases cover NUL,
other controls, quotes, backslashes, Unicode, both projected copies, full
retrieval and export identity without changing any original record.
