# Pi Worker conversation and Windows handoff

The Worker page displays the explicitly bound Codex thread's public conversation
and complete latest final answer. Summary links to Reply to Worker. This replaces
the former Summary-top-right progress-export requirement; historical progress
snapshots remain retrievable. Plain-text rendering preserves commands, paths,
newlines and decisions, and does not execute message markup. Tool output, private
reasoning, system instructions and compaction records are not conversation text.

Send update to PC re-reads the latest **completed-turn** final answer and verifies
thread/message/digest against the displayed identity. The server, not the browser,
supplies its exact content. The accepted Windows writer retains durable intent,
serializes writes, checks the latest fence and reads back the Windows clipboard.
Only matching native write/read-back permits “Copied verbatim to Windows.” A
saved snapshot or synthetic test is not clipboard success. Failed/unknown delivery
retains the snapshot and idempotency key. PC retrieval/download remain fallbacks;
manual browser Copy affects only the device running that browser.

Replies carry an immutable UUID, exact thread ID and public text through the
authenticated same-origin/CSRF route. A private durable intent precedes queueing.
Retries never send an existing intent again. An ambiguous acknowledgement stays
unknown; queue acknowledgement says **Queued**, not received. Only matching
public user-message client ID and exact text establishes the received turn/message.
Drafts and pending IDs survive reload. Typing/sending a reply is not an approval.
Dispatch requires a successful local identity write and exact local read-back;
unavailable/quota-failed storage blocks sending rather than risking a new ID after
reload. A reply-receipt lookup failure does not invalidate a separately successful
Worker connection or disable final-message copying. Retry uses the original ID.
Receipt reconciliation checks the newest page and at most one saved older page per
poll, durably advances its cursor and retains confirmed reception across recovery.
The 128,768-byte durable reply bound includes worst-case JSON escaping of every
accepted 16,000-byte reply plus bounded cursor/receipt metadata. Missing/null public
agent-message phase remains visible as unknown history, never inferred to be final.
The touch keyboard, textarea and native content scrolling share the existing drag
activation protection. Existing Approve Once, Deny, Cancel, expiry, conditional
Permissions, Matrix wake and native approval ownership are unchanged.

## Explicit same-session connection

The console uses official Codex 0.153.4's existing `app-server proxy --sock PATH`
against an already-running local shared app-server. Its executable and the actual
Unix peer executable are pinned to SHA-256
`56ef98ab4032d317ab26e9b5e5a175650717351edb16ed9cde0cb6d1734d62da`.
The control directory must be owned by the same OS user and private (0700).
The thread UUID and cwd are launcher configuration, never browser-selected.
Read-only projection uses `thread/read`, `thread/items/list`, and
`thread/turns/list`; reply submission uses experimental `thread/queue/add` with
`clientUserMessageId`. Version-generated complete schemas accompany the review.

This connector does **not** start/resume/fork a thread, start/steer a model turn,
respond to a native request, select an account/model or grant permissions. A
standalone resumed CLI is not automatically connected. Readable stored history
is not live ownership: `notLoaded` or missing `canAcceptDirectInput` disables
reply. An existing shared TUI/Core must own the exact thread and consume its queue.
The managed-approval feed in the existing header remains separately identified;
connecting the conversation does not claim standalone native approvals route to Pi.

For this rollout, thread `01a06f22-5b47-72c1-9b9c-b70157913436` in
`/home/tvnner/fawkes` must be handed over at a safe native terminal boundary from
the standalone TUI to the supported local shared server and remote TUI. Preserve
the thread/account, gpt-6-astra/xhigh configuration, workspace-write/on-request
profile and existing additional recovery directory. Do not run a second active
owner of this thread. A prepared native handover must first confirm the old TUI
has closed, then use official daemon start and `codex resume --remote unix://…`
without a prompt. This is not permission to inject terminal keys or manufacture a
user reply. Actual reception and clipboard paste remain human acceptance gates.

## Bounded observation and honest limits

Each proxy RPC has a 12-second deadline, 8 MB frame, 16 MB aggregate input and
2,000-frame bound; writes are nonblocking/deadline-bound. Only the short-lived
proxy is cleaned up. Unknown approval requests are not answered. Public history
uses 20-item pages, explicit Earlier/Latest browsing and a 480 KB projection bound.
The latest-final lookup checks eight recent turns and only completed-turn final
items. A missing final or over-limit complete message is unavailable, never
summarized/truncated. Public messages are bounded at 256 KB, copied final messages
at the existing 96 KB snapshot bound, and replies at 16 KB UTF-8. NUL is rejected
for native transfer. These byte limits do not assert provider context capacity.

Polling is five seconds while Worker is visible. Fifteen seconds without a
successful state synchronization disables actions; disconnection retains text as
last known. Quiet verified idle state is connected. Thread metadata model/effort
are configured/persisted values, not runtime-confirmed inference telemetry.

Reply-receipt lookup runs separately from state refresh and clipboard availability;
only one receipt observation runs at a time. A slow or failed lookup keeps the
original reply identity without preventing fresh connection checks or an exact
final-message copy. Sending remains serialized and never becomes an automatic retry.
Overdue state verification is visibly Stale with disabled actions until synchronization.
Text-entry gestures and arrow keys remain text editing, not page navigation.

Before external reply dispatch, both reply-directory entries and the durable
intent are synchronized to storage. Directory barriers also run on recovery when
the directories already exist, because an interrupted creation may not have been
durably published. A failed barrier prevents dispatch; it does not imply receipt.

## Qualification, deployment and rollback

Focused fake-peer tests cover fragmented real pipes, deadlines/cleanup, wrong
identities, unsupported requests, public-message filtering, completed-final
selection, exact Unicode/line endings, durable ambiguous replies, HTTP auth/CSRF,
clipboard fidelity/failure, keyboard and 720x720 browser interaction. None is a
new provider or approval trial. Reuse accepted G16 writer/fence qualification and
Tanner's passed pinch, scrolling, Idle/wake and real approval evidence only where
unchanged. Acceptance requires independent read-only review of this exact product
and separate launcher/handover proposal before canonical application and rollout.

Rollback restores the preserved accepted G15 preview and companion binding, not
Git history, clipboard contents, saved snapshots, reply intents or native touch
configuration. Preserve any queued reply and its identity for reconciliation;
never replay it as part of rollback. The Pi still needs the PC/bridge awake.

References: [official app-server contract](https://learn.chatgpt.com/docs/app-server),
[official CLI reference](https://learn.chatgpt.com/docs/cli/reference). Installed
version-generated schemas take precedence over assumptions about newer docs.
