# Explicit read-only Reviewer client profile (unaccepted proposal)

The default remains Codex 0.151.0. Explicitly constructing
`CodexAppServerTransport(protocol_version=REVIEWER_PROTOCOL_VERSION, codex_binary=exact_staged_binary)`
selects 0.153.4 for read-only execution. The existing `WslCodexReviewAdapter(...,
app_server_transport=transport)` injection seam can consume this profile after
independent qualification, exact acceptance and Tanner's scoped adoption approval.
No caller, running Worker, default model, global configuration, promotion record,
Pi companion or preview is switched by this proposal.

The Reviewer profile never enters detached continuation, including when callers
leave the public default unchanged or explicitly request continuation. Process
loss during a decision or after acknowledgement fails closed without another
process, action reservation or replay. Legacy Worker recovery is unchanged.

Qualification checks the exact stdout version and regenerates experimental JSON
schemas from that executable. Nineteen complete method schemas, including their
referenced definitions, must match the fixed length/hash manifest. The manifest's
own digest is pinned in source. Generation has a 40-second deadline and uses the
supplied external TMPDIR. A schema mismatch is not normalized or ignored.

The 0.151.0 versus 0.153.4 comparison found identical initialization inputs and
response, thread/turn start inputs, approval parameters/responses and resolution
notifications. Changed response closures add optional Thread.model and
Thread.reasoningEffort, and nullable AgentMessage.questions referencing a new
AsyncUserInputQuestion definition. Existing required fields, final text, terminal
status/error and approval semantics remain unchanged. Questions are not approval
requests, structured acceptance, or new authority; final review output still goes
through the existing independent validator. Unknown server requests are rejected.

The explicit profile rejects non-read-only execution and broad permission grants;
keeps file-change denial, canonical one-action handlers and existing deadlines;
checks item/terminal thread/turn identity and exact one-time resolution identity.
It does not add support for writeStdin, session grants or new native request types.
Cancellation and failure retain the existing process cleanup. Default 0.151.0
behavior is unchanged. Canonical receipt validation remains unchanged outside
this transport.

Local protocol tests, executable readiness and a separately authorized tiny
diagnostic are evidence, not independent review or promotion. A small successful
acknowledgement cannot establish larger package/context capacity. The existing
tooling and Pi freezes stay unchanged and unaccepted. Rollback before adoption is
simply not selecting this profile. After separately authorized integration, any
rollback must reconcile active transactions and use an exact authorized revert;
never reset refs, replay application or overwrite old receipts.

Official schema-generation reference: https://learn.chatgpt.com/docs/app-server
