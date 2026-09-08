# Pi-to-Windows clipboard handoff

Status: isolated G16 proposal, not independently accepted or deployed.

Tanner's requirement is a Pi **Send update to PC** tap followed directly by
Windows Ctrl+V. The old immutable snapshot/manual browser Copy remains available
as recovery, but is not automatic Windows delivery or its acceptance evidence.

The same authenticated, same-origin, CSRF-protected console POST saves the exact
server-derived campaign snapshot. `ConsoleClipboardDelivery` serializes attempts
and retains a separate, private receipt before calling the explicitly configured
Windows writer. It never changes the immutable snapshot, campaign or permission
records. GET, reload and retries cannot initiate a second write of that snapshot.
Older/interrupted retries cannot overwrite a newer sent snapshot. A new explicit
tap after a completed response creates a new timestamped snapshot and attempt.

`WindowsClipboardWriter` verifies the pinned System32 PowerShell executable and
sends the saved UTF-8 bytes on stdin to one fixed STA helper. No browser-supplied
script, executable, account, command or content is accepted. The helper checks
snapshot/attempt, digest/length, SID/session and a short expiry, holds a per-user
Windows mutex, checks the service's durable latest-attempt fence under that mutex,
writes persistent Unicode text without retries, and verifies exact
read-back. The acknowledgement binds those identities. Only a matching verified
acknowledgement says **Copied to Windows clipboard**. Another application can
subsequently overwrite the clipboard; this is a timestamped write confirmation,
not a continuing guarantee about its contents. Existing Windows clipboard/history
settings remain the user's settings; the handoff adds no network upload.

Snapshot content is bounded by the existing 96,000-byte limit. Native stdin is
bounded to 140,000 characters, response to 4,096 bytes, execution to 15 seconds,
and native expiry to 12 seconds. Cross-process file and Windows mutex locks prevent
overlapping delivery. A timeout, crash or lost acknowledgement is unknown, never
assumed success, zero work or permission to replay. The durable snapshot survives.
No diagnostic persists clipboard contents beyond that existing private snapshot.

The service atomically publishes a bounded ASCII intent (attempt, snapshot and
content digest) before dispatch. The native helper reads at most 257 bytes from
that local WSL file while holding the clipboard mutex and requires an exact match.
The file is data, not code, and cannot be selected by the browser. Missing or
unreadable intent fails closed. This closes G16-PC-001: after service loss, an
older surviving helper either finishes before the newer helper holds the mutex,
or sees the newer intent and refuses to write. Mutex/expiry alone did not enforce
ordering. The reproduction was a process-interleaving counterexample, not an
observed physical clipboard overwrite. The original rejected generation remains
retained. The shared local intent directory must remain available to Windows;
its loss reports failure rather than assuming delivery.

## Exact adoption and rollback

After canonical independent acceptance and integration, rebind the existing
accepted PC console launcher to the reviewed source and inject
`console_clipboard_writer=WindowsClipboardWriter(...)` into `FawkesAppServer`.
Its explicit parameters are `executable_sha256`, `windows_sid` and
`windows_session_id`, verified on the intended signed-in Windows host immediately
before cutover. A changed executable or Windows session fails closed and requires
revalidation, not a browser override. Do not change the global PowerShell/Codex
configuration, Pi bridge key, native approval handler or companion scripts.
All other callers default to no writer and report unavailable honestly.

Keep the prior accepted PC launcher and Pi metadata as rollback, preserving all
snapshots and receipts. Rollback disables new writes by restoring the prior
server; it must not clear or restore a user's clipboard or delete handoff history.
This proposal does not grant itself deployment or review authority.

## Qualification boundary

Offline checks exercise crash/retry ordering, authoritative content, tampering,
Unicode/line endings, bounded native calls, typed acknowledgements and unchanged
HTTP authentication. Native syntax/assembly checks never touch the clipboard.
Synthetic browser tests use an injected fake writer; they cannot prove Windows
delivery. Required post-acceptance physical check: tap Send update to PC on the Pi,
wait for its Windows confirmation, then Ctrl+V in a Windows editor and compare the
newest snapshot ID/time/content. No new model or approval trial is needed.

The existing eight console requirements remain; this adds automatic Windows
delivery to pc-update-durability. Passed pinch, swipe/Idle/Matrix, real approval
trial, roadmap, timing and unchanged source evidence are retained, not rerun as
new physical proof.

Microsoft's [Clipboard.SetDataObject documentation](https://learn.microsoft.com/en-us/dotnet/api/system.windows.forms.clipboard.setdataobject?view=windowsdesktop-9.0)
specifies the persistent-copy overload and STA requirement; exact text is checked
with [Clipboard.GetText](https://learn.microsoft.com/en-us/dotnet/api/system.windows.forms.clipboard.gettext?view=windowsdesktop-9.0).
