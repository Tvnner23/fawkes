# Contributing to Fawkes

Start with the [README](README.md) for existing run instructions and the
[repository layout](docs/REPOSITORY_LAYOUT.md) to locate the relevant code and
tests. The [external review guide](docs/EXTERNAL_REVIEW_GUIDE.md) explains review
questions; the [Universal Worker Charter](docs/phoenix/UNIVERSAL_WORKER_CHARTER.md)
records existing worker boundaries. This guide adds no permissions or release
policy.

## Keep changes small and preserve existing work

1. Establish the authorized outcome, exact editable paths, baseline and recovery
   evidence before editing. Inspect local differences and untracked filenames;
   keep private runtime data and credentials out of the inspection and report.
2. Work in an isolated candidate or checkout with the necessary existing work
   preserved. A checkout from HEAD alone may omit unfinished changes. Record
   pre-existing file bytes, modes and staged state through the existing recovery
   process; absence from Git does not mean a file is disposable or integrated.
3. Make one reviewable change. Read the affected implementation and test owners
   before choosing checks. Preserve unrelated edits, untracked files and modes;
   separate later improvements into suggestions rather than starting them.

Do not use reset, clean, stash or blanket staging to make a working tree appear
clean. Keep dependencies, generated bundles and runtime state out of a
documentation change.

## Focused offline checks

From the repository root, Python 3's standard library is enough for these two
documentation checks; no dependency installation or credentials are required:

```bash
python3 -B -m unittest discover -s tests -p 'test_repository_documentation.py' -v
python3 -B -m unittest discover -s tests -p 'test_worker_charter.py' -v
```

The [navigation tests](tests/test_repository_documentation.py) check local links
in the README, this guide and the layout, including missing-target fixtures.
The [charter tests](tests/test_worker_charter.py) read the existing governance
documents. Neither invokes the application or a provider; `-B` avoids writing
bytecode caches. Passing these checks establishes documentation evidence, not
runtime acceptance.

For other changes, select tests only after inspecting their imports, setup and
side effects. The [general test launcher](src/run_tests.py) discovers the broad
suite; it is not this focused check. Do not automatically run provider tests,
live-assurance, capture/import, deployment or notification helpers. The README's
Chat/app commands are runtime operations, not documentation validation.

## Review, application and integration

Submit the exact candidate diff, changed paths and hashes, baseline/preservation
evidence, commands and results, limitations and recovery instructions for
independent review. Review must precede canonical application and Git
integration; passing tests or receiving a worker package does not authorize
either action. The responsible owners must complete review, authorized
application and integration before reporting them as done.

When separately authorized to integrate, the integration owner should recheck
the baseline and existing index, then stage only the exact reviewed paths or
hunks. Whole-file staging can include unrelated edits in a shared file: isolate
and review the intended delta first. Inspect the staged diff and path list
before any commit; do not stage an entire directory or all working-tree changes.
Never include credentials, private histories, machine-local configuration or
runtime databases in a patch or example.

## Recovery and handoff

Retain the original bytes/modes and exact candidate delta until the owning
review/application/integration process has finished. Before application, a
rejected candidate can remain unapplied. If an applied change needs rollback,
the authorized owner should verify that affected paths still match the applied
candidate, then reverse only that delta using the recorded baseline. Preserve
all earlier and intervening work. A mismatch calls for reconciliation, not
overwriting a file or rolling the repository back wholesale. Removal of a file
added by the change also requires checking for subsequent work.

Report **Accomplished** (exact changes/checks), **Gained** (evidence and useful
findings), and **Next** (suggested follow-up, owners, caveats and recovery).
Keep review, application and integration marked pending until those owners
complete them. Reconcile dated status captures in the
[implementation handoff](docs/phoenix/CURRENT_IMPLEMENTATION.md) and review
guide against current accepted evidence; do not repeat old phase claims as
present truth or create a new roadmap here. This batch improves contributor
guidance and navigation; the broader repository cleanup remains open.
