# Pi-local temporary power control

Automatic navigation reserves the browser interaction boundary before capturing
state. An existing hold prevents reservation; a press during saving/navigation
cannot become a hold or a later click. The reservation spans sign-in and document
readiness. Timed-out navigation is stopped before controls are released, and failed
save leaves the live page intact. Offline waiting retains its local Idle control.

This follows the accepted notification at `73e4379`. It is not a hardware-button
implementation. Only the Pi companion receives the gesture; Windows/Worker keep
running. It needs independent acceptance, exact installation and a coordinated
physical shutdown check before it is called verified.

On every shared Idle button, a quick tap under 180 ms keeps normal Matrix Idle.
A longer uninterrupted press displays three-second progress and **Release to
cancel**. Releasing before three seconds, leaving the button, cancellation,
another touch, lost focus or page visibility cancels. Finishing the hold consumes
one intent and suppresses the resulting Idle click. The confirmation disables
further editing/action until the result or a deliberate page reload.
Progress occupies its own row below the current header controls, leaving their
labels visible; it is not an overlay over Idle or Send update to PC.
Cancelled pointers remain suppressed through their eventual release, including
moving back over Idle much later. A fresh deliberate tap remains usable.

The existing private Chromium pipe has one reader. The companion polls the local
hold before PC health/reconnection work, including its local waiting screen.
No HTTP shutdown endpoint, Worker prompt, model trial, clipboard write or native
permission decision is created. A PC network probe can delay dispatch by its
existing bounded timeout; the hold progress itself is local and does not depend
on Wi-Fi or the bridge. Healthy console and disconnected local-waiting states
both have the same gesture. Normal startup/wake still selects Summary.

Before the one fixed OS command, save the draft, existing reply/copy submission
identities, notification acknowledgments and page/reading position in private
Pi state (`~/.local/state/fawkes-pi-console-shutdown`, directory0700/files0600).
Only five explicitly allowlisted local-storage keys are retained; no cookies,
sign-in credentials or full browser profile are copied. A 192000-byte save limit
fails closed without shutdown. Private state is read back and fsynced. Save
before bridge-loss navigation; if saving fails, keep the existing draft page.
Checkpoint immediately before navigation, after any blocking PC probe; defer
navigation during an active hold. Validate each retained JSON value against its
actual supported schema, including embedded Worker-thread and submission IDs.
Browser storage/capture exceptions remain save failures; preserve the live draft
page and previous durable state instead of closing Chromium. Sign-in submission
and automatic Summary selection use the same hold/save guard as page navigation.
Restore into a fresh profile before app listeners without submitting anything.
Recorded page/reading position is retained when that page is deliberately opened;
startup itself remains Summary. Existing server-side history stays authoritative.
Wait for asynchronous history to have enough scrollable content before consuming
the saved reading position. Retain that intent across checkpoints; deliberate
user scrolling or interaction takes precedence.

The root-owned sudoers drop-in grants only `tvnner` running the exact argument
`poweroff` to `/usr/bin/systemctl` as root. No wildcard, shell, force, reboot,
arbitrary command, environment override or global permission change is added.
The inspected Pi is Raspberry Pi4 ModelB Rev1.5, UID1000, systemd257; initially
`sudo -n -l /usr/bin/systemctl poweroff` required a password. Native installation
therefore requires ordinary Pi SSH and sudo authentication once. The root helper
checks that actual model, owner and inspected systemctl digest and validates its
fixed policy with visudo. Runtime additionally refuses non-Pi hardware. The button
uses `sudo -n /usr/bin/systemctl poweroff`; no password is collected by the app.
The policy carries the exact rollout operation ID. Rollback atomically withdraws
the matching policy into a private, inactive recovery directory and verifies the
moved inode and bytes. A concurrent administrator replacement is preserved and
reported rather than unlinked. Rollout journals survive failures, and an interrupted operation must
be reconciled rather than blindly replayed. Duplicate completed installs verify
the current exact root policy and service/browser evidence without restarting or
installing again; a historical journal is not proof the permission still exists.
PC rollback restores the accepted parent's configured clipboard, conversation
and native-approval owners as well as its assets. Observe the Worker endpoints
and label an unavailable shared session honestly; process configuration alone
does not prove it is connected or that a message/clipboard write succeeded.

A private lock, boot identity, durable consumed request ID and fixed argv prevent
duplicate requests and ambiguous automatic retries. Persist intent before running
the command. A successful command return means shutdown requested, not physical
power-off observed; timeout or missing acknowledgment stays unknown. A lost final
browser display after dispatch does not become a claim that no command ran.
New boot permits a fresh hold, but old request IDs stay consumed. Keep saved
drafts and all operation records across rollback; never delete them to retry.

Normal OS shutdown is used, not forced power loss. See the [systemd shutdown
service documentation](https://www.freedesktop.org/software/systemd/man/254/systemd-halt.service.html)
and [sudoers reference](https://www.sudo.ws/docs/man/1.9.14/sudoers.man.pdf).
No battery saving/backlight or hardware-installation claim follows from this.

Qualification must cover tap, completed hold, every cancel path, once-only
dispatch, private durable draft/reload, failed save/no command, ambiguous outcome,
wrong machine/thread, disconnected local waiting, and original startup/notification
behavior. Browser-generated touch and mocked OS commands are supporting tests,
not physical shutdown proof. The final physical check is coordinated with Tanner:
cancel a hold, then complete one hold; confirm Pi shutdown while Windows/Worker
remain available. Disconnect the bridge for the local-only check only after the
accepted installation is stable. Reconnect/startup and draft recovery are checked
after Tanner powers the Pi on again.
# Interrupted rollout and automatic connection follow-up

The first accepted shutdown rollout wrote its exact files and fixed poweroff-only
policy, but timed out before a fresh browser observation. Its failed journal stays
failed. The completed rollback restored notification73e4379, verified Summary,
and withdrew that operation's exact policy. No physical shutdown was executed.

A newly reviewed successor uses a new operation identity, references the failed
installation, and requires one verified completed rollback plus matching current
rollback files before installing. It verifies the old policy is absent before
creating the new exact grant. Neither journal nor authoritative application is
replayed or relabeled. Failed/stale/unverified rollout output is not success.

Before PC cutover, the installer verifies the accepted bridge script/task and
starts that existing task if stopped. Fresh bridge activity must follow cutover;
old status-file text is not a running-process check. Rollback-mode output explicitly
says rollback and does not claim the shutdown control is installed. The Windows
Worker startup bundle is installed only after the Pi's accepted readiness passes.
The real hold/cancel/offline shutdown and reboot observations remain user checks.
