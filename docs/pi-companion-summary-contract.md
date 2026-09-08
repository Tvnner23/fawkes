# Pi companion Summary navigation contract

The September 14 design adds briefing and description text inside the Summary
menu button. The retained companion looked for an entire textContent equal to
"Summary", so it rejected that real button after successful sign-in and live
projection. The installer retained RETRYING / "The Summary tab could not be
identified", then restored the PC to G22. This is a navigation-contract defect,
not evidence of failed Wi-Fi, credentials, or the earlier Summary-byte problem.

deploy/pi_console_supervisor.py retains the installed companion's implementation
and changes only its Summary-control expressions. This is the source for the
next independently accepted companion payload; adding the file does not install
it. Its existing browser_pipe.py sibling remains an unchanged installation
dependency. All native keyring, authentication, private credential handoff,
service supervision, fixed origin, accepted snapshot and live-projection checks
remain in force.

The control contract is one enabled button inside #dev-console with
data-page-target="0" and one Summary section with data-page="0". Visible
labels can contain descriptions or translations. Missing, duplicate, disabled
or aria-disabled controls fail closed. Startup clicks that actual button, then
checks shell page0, aria-current and the non-hidden Summary section before
configuring Matrix. No text match or synthetic route substitutes for navigation.

Authenticated refresh recovery uses the same identity checks but does not click,
change the selected page, move focus or reset reading position. Matrix's existing
two-minute idle configuration and mouse-emulation scrolling setting are unchanged.
Its configured Summary selector references that same unique page0 button.
The Matrix script, touch calibration, screen orientation and all permission,
reply and clipboard owners are unchanged.

Qualification must execute the actual companion expressions against the actual
accepted design DOM, including the former failing expression; synthetic tests
also cover duplicate/missing/disabled controls, wrong accepted context and
origin, missing live state, failed navigation, legacy simple text, and restoration
without navigation. Browser checks of Idle and Matrix return are supporting
evidence, not a claim of physical Pi observation.

The interrupted rollout installed the accepted91ef5b0 companion binding before
readiness failed. The next payload must name those retained installed preimages,
not silently assume the old G22 marker remains. The scoped installer rechecks
all preimages before writing. Its separately retained G22 rollback does not
erase prior failed records or restore service health beyond verified evidence.
The original design and Summary correction remain accepted and applied once.
Prepare the accepted installer, then stop for Tanner's installation action.
