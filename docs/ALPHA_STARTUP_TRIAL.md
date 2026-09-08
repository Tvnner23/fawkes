# Tanner Alpha: startup and real-use gates

This is a preparation checklist, not an acceptance, deployment, or trial receipt.
The [canonical Alpha boundary](phoenix/CANONICAL_ROADMAP.md#v01-alpha-boundary)
requires the Phase 0–10 trust gates and a seven-day real Tanner trial across
desktop and iPhone. Synthetic tests and inherited/manual-inspection evidence
must remain explicitly identified; neither substitutes for new real-use evidence.

## Exact source and existing state

Use the final independently accepted, integrated checkout containing recording
controls, the bounded Workshop foundation, and these release fixes. A clean Git
tree alone is not acceptance. The release manager requires the existing
integration result, its exact record SHA-256 from the trusted handoff, and the
independent acceptance receipt SHA-256. It checks the canonical receipt shape,
review-context/application/Git linkage, integrated HEAD, and full product
snapshot. Product and review-context snapshots are deliberately distinct.

The established state owner observed through registry/directory metadata on
2026-09-16 is `/home/tvnner/fawkes`, with existing Fawkes instance
`9b816885-df8b-4e75-8a4a-02d9d35771d5`. Reverify that binding before live action.
The alternate `~/.local/state/fawkes` root did not contain its registry; do not
create a replacement identity there. Source acceptance and state ownership are
separate inputs. No data migration or root merge is part of this preparation.

Before any owned-state backup, verify that all writers to that state are
quiescent. Phase-0 auditing uses read-only SQLite connections; complete backups
still require a quiescent source because scoped database files are copied.
Preserve and verify a private backup through an isolated restore. Do not repair,
reclassify, or delete real records automatically when an audit reports a problem.
A private Git/source backup is not proof of personal-state recovery.

## Native preparation and deployment

App/provider configuration was absent at the metadata check: original `.env`
and `~/.config/fawkes/app.env` were absent, and the provider-key environment
presence checks were false. Supply credentials locally through
`scripts/configure_fawkes_credentials.sh`; its default is app-only, prompts
privately, and refuses to overwrite any existing target. Never paste keys into
chat. Existing notification configuration is preserved. Discord and notification
setup are separate explicit `--component` choices, not Alpha requirements.

After exact source acceptance and rollout authority, the native operator can
prepare the release using the trusted handoff values:

```bash
scripts/prepare_fawkes_production.sh \
  --source "$ACCEPTED_CHECKOUT" \
  --state-root /home/tvnner/fawkes \
  --instance-id 9b816885-df8b-4e75-8a4a-02d9d35771d5 \
  --accepted-integration "$ACCEPTED_INTEGRATION_JSON" \
  --accepted-integration-record-sha256 "$INTEGRATION_RECORD_SHA256" \
  --acceptance-receipt-sha256 "$ACCEPTANCE_RECEIPT_SHA256" \
  --validation-reference "$QUALIFICATION_REFERENCE"
```

This future native operation creates a release-specific environment and installs
the unchanged requirements, then checks dependencies before any promotion.
The current release and its old environment are not changed by preparation.
No dependencies were installed during synthetic qualification.

On the first transition from the old schema-1 installation, explicitly run the
release manager's `bind-legacy` command with that same state root and instance.
It binds only the actual existing current/previous releases to the old venv.
A new-format release with a missing environment always fails; it never falls
back to that old venv.

Install the exact prepared release definitions with
`scripts/install_fawkes_systemd.sh RELEASE_ID`, then promote that exact release
with the release manager and start/restart `fawkes-app.service` under native
privilege approval. The installer defaults to app-only: it enables the app under
`multi-user.target`, not the full stack, social bridge, notifier timer, or sudo
policy. `--full-stack` is a separate explicit option. The native unit definitions
support the verified original state root; alternate-root preparation is only
a disposable rehearsal unless separately reviewed unit bindings are supplied.
The installer does not start a service or promote a release. Its private
supervision/attention directories contain metadata, not a new Phoenix identity.

The release-specific launcher selects both verified code and its environment,
sets the bound runtime root, and puts browser-session/update state under that
root. Release `memory` links and runtime-root Workshop paths refer to the same
existing tree. App-only restart/control remains a native operator action; this
does not broaden in-app sudo authority. Preserve the old release/environment
and private backup references before rollout.

## Entry points and observations

The maintained normal app service binds authenticated `0.0.0.0:8787`. Desktop
access is `http://127.0.0.1:8787` once native startup and the host's WSL forwarding
are verified. Check login/session/CSRF protection, the exact served build,
effective recording mode and settings revision, restart continuity, and honest
failure/health status before calling it usable.

iPhone private routing was not established by this preparation. The
[retained WSL2 phone guide](PHONE_ACCESS_WSL2.md) documents a previously inspected
LAN/NAT setup, not proof that its old addresses or rules are current. Reverify or
configure the approved private path natively and test on the actual phone.
Do not expose a public router port, disable authentication/firewalls, or change
Tailscale/network configuration as part of source preparation.

The normal app is separate from the accepted Pi/console preview on port 8790,
its bridge, and the existing Worker session. These installers do not stop or
replace those owners. If a required state writer cannot be quiesced without
affecting them, stop at that gate and coordinate the bounded maintenance action.

## Seven-day trial record

Record actual desktop/iPhone daily use, restarts, Library, History search and
manual source inspection, continuity, research, corrections, provider failure,
backup/restore, retrieval feedback, and at least one Phoenix-generated
improvement proposal. Workshop proposals must remain non-self-applying.
Check that recording settings apply prospectively: off/private does not delete
old history, and required authority/provider receipts stay body-free. Sensor
retention remains unsupported.

Passing means no canonical data loss, cross-Phoenix leakage, invented success,
or silent protected-state change. The real seven-day trial, credential validity,
native deployment, phone access, and live backup coherence remain unproven until
their own exact receipts/observations exist. Later embodiment, social rollout,
Ghost Rider, and broad cleanup are not additional Tanner Alpha prerequisites.
