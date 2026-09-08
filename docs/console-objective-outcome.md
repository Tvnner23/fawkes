# Current objective outcome prompt

This is an informational prompt, not an approval mechanism or an acceptance
receipt. Native decisions, plain chat replies, independent acceptance, and
recorded operation outcomes remain separate.

The live current objective in Summary supplies a **Paused — needs your
decision** prompt when its canonical state is `needs_you`. It includes the
recorded next action and objective identity. **Reply to Worker** opens the same
conversation and preserves its draft; it never sends or approves anything.

A successful campaign, a completed model turn, or an idle Worker does **not**
imply the entire requested task is done. A completion prompt requires an
explicit whole-user-objective closeout in the existing canonical campaign
record, after its actual implementation/review/integration/deployment/physical
gates, where applicable, have passed. There must be no remaining authorized
work for that objective. A helper/review child may not publish this closeout.

The supported existing campaign owner's event-retention mechanism records
`console_objective_closed` as the final event of an already successful root
objective. Its detail carries:

- `scope: whole_user_objective`, exact `campaign_id`, SHA-256 of the complete
  canonical objective, and `remaining_authorized_work: false`;
- a concise `result` (at most 1200 JSON-encoded UTF-8 content bytes);
- exactly one `gates` entry per original acceptance condition, each with
  `condition_id`, `status: satisfied`, and a retained evidence
  `reference_id`/`sha256`.

The record's `acceptance_satisfied` must contain all its original conditions.
These evidence links record previously established facts; writing a notice is
not independent review, deployment verification, new authority, or permission
to manufacture missing evidence. Never mark a preparation campaign as a whole
user objective. Retain missing gates as incomplete. A later lifecycle event or
changed objective invalidates this final closeout projection. Existing records
without this explicit closeout remain unchanged and do not acquire completion.

When the closeout is valid and the same current objective is observed live, the
prompt says **Task complete — ready for your next task**. No next task starts
automatically. The full source identity remains under Recorded evidence.

Both prompts have Close and Reply to Worker controls. A seen notice is retained
by objective/material identity in browser storage; refresh and reconnect do not
repeatedly open it. If storage cannot be verified, automatic opening is disabled
and the Summary entry remains available. No focus is taken from typing, an open
menu/dialog, native permission request, or Matrix. Ordinary completion is quiet
and does not wake Matrix. Native permissions retain their existing wake/decision
owner. Stale/disconnected observations are labelled last-known and never
automatically open a completion prompt.

Qualification uses synthetic canonical closeouts and disposable browser
fixtures, not invented live task completion or another Pi execution trial.
The actual cleanup remains blocked on the separately requested recovery-renewal
decision. Its expired ticket is not changed by this console feature.
