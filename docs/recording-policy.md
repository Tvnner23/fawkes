# Personal recording policy

This describes the prepared recording controls, not an accepted or deployed release.
The authority is the [canonical roadmap's personal-recording requirement](phoenix/CANONICAL_ROADMAP.md#pre-phase-10-stabilization-and-rider-supervision-gate).

## Controls and effective mode

In the normal app, open Settings → Personal recording. Changing a setting requires
an authenticated browser session and its CSRF token. The mode beside Chat reports
the last confirmed interaction separately from the next configured interaction.

| Setting | Future personal content governed |
| --- | --- |
| Archive recording | Rider/Phoenix Chat messages and native continuity. Off makes Chat private. |
| Memory learning | New learned or derived Memory from interactions, including background processing. |
| Personal diagnostics | Personal context receipts, replay flights, feedback and diagnostic observations. |
| Research records | Reviewable research records; required-retention research is bounded when off. |
| Library retention | Explicitly keeping attachments or extracted content in Library. |
| Social Archive | Retention through the existing social Chat path; that path is bounded when off. |

Sensor retention is unavailable and cannot be enabled. These settings do not
authorize social delivery, providers, tools, code changes or physical actions.

Retained mode permits only the enabled categories. Private mode, or Archive off,
forces all effective personal-retention categories off for that interaction.
A request for retained mode cannot override configured Private mode or Archive off.
Saved category choices remain available for a later return to retained mode.
An instance with no settings file starts at retained revision zero, with the six
editable categories enabled; invalid or unreadable settings never imply defaults.

## Prospective, not deletion

Changes apply to the next interaction and survive restart. A turn latches one
policy before its personal-content/provider work; changing settings during that
turn does not retroactively change its result. Turning recording off does not
delete, redact or rewrite existing Archive, Library, Memory or required evidence.
Deletion and recovery are separate operations, not provided by these controls.

Archive on with Memory learning off is supported: the conversation remains
readable as retained history, but its immutable eligibility marker prevents later
learning from those turns even after learning is re-enabled. Current learning
off also pauses scoped learning work. Existing eligible records are not erased.
Read access to permitted retained History is distinct from learning permission;
ordinary retained context can still read owned history. Private Chat does not
automatically retrieve old personal Archive/Memory.

## Private interaction limits

Private text and replies use bounded process-local context and a volatile
`private-…` conversation identity. They are not a recoverable Archive: restart
loses that private buffer. The normal client does not save it in browser storage.
Switching to a new retained interaction discards private context instead of
copying it into retained history; a draft begun privately stays private.
A failed or slow request is not proof that a message was preserved.

Private Chat currently supports text only. Media, retained-retrieval
clarification, social Chat, durable research, Library retention and personal
diagnostic feedback are bounded when their required retention is unavailable.
These are actual capability limits, not permission to retain secretly.

Private does not mean offline: messages may still reach the configured provider.
Provider authorization and metadata-only provider/authority receipts remain
required; they contain no private message/reply bodies. Feature-coupled
Development, Worker Exchange, authority and Recovery evidence is distinct from
personal Archive and is not silently disabled by these settings.

## Conflicts and failed saves

Settings use an exact revision check. A stale save is rejected; the app reloads
the actual revision and requires another explicit choice. It never automatically
retries a write. A durability error can mean a new setting is visible without
confirmed durable publication, so the app reports uncertainty and reloads rather
than claiming success or rollback. Corrupt settings block affected recording
work until handled; they do not silently turn recording on.

This preparation does not establish live migration, device/browser visual
qualification, a daily-use trial, Workshop readiness or the full Alpha gate.
