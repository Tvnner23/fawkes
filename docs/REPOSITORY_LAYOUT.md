# Repository layout

Use the [README](../README.md) for run instructions and
[Contributing](../CONTRIBUTING.md) for isolated edits, focused checks and review.
This map describes retained repository material. Presence in this tree is not
evidence of deployment, acceptance or Git integration; existing uncommitted and
untracked work remains work to preserve.

## Source and clients

| Path | What to look for |
| --- | --- |
| [src/fawkes.py](../src/fawkes.py) | CLI dispatch for Chat, app and Archive/Memory utilities. |
| [src/](../src/) | Top-level Archive capture, indexing/search, instance, history and backup/restore helpers. |
| [src/app/](../src/app/) | Python HTTP server and browser client in [static/](../src/app/static/), including the [development console](../src/app/static/dev-console/). |
| [src/runtime/](../src/runtime/) | Chat orchestration, persistence, retrieval/context, worker exchange, review/application and release-control implementations. |
| [src/capabilities/](../src/capabilities/) | Capability registry, awareness, acceptance, research/media and provider-privacy boundaries. |
| [src/memory/](../src/memory/) | Memory records, processing, retrieval, import and Development/review code. This is source, not the private top-level `memory/` store. |
| [src/library/](../src/library/) | Retained-source artifact, storage, extraction and retrieval code; separate from private `library/` data. |
| [src/capture/](../src/capture/) | Canonical capture, normalization and reconstruction code. |
| [src/presentation/](../src/presentation/) | Structured response contracts and presentation orchestration. |
| [browser_extension/](../browser_extension/) | Live-capture extension source: [manifest](../browser_extension/manifest.json), page bridge, content script and background worker. Installation/capture is a separate runtime action. |
| [public/](../public/) | Static public pages, including privacy, SMS terms and opt-in material; their presence does not establish a public launch. |

## Tests, documentation and operations

| Path | What to look for |
| --- | --- |
| [tests/](../tests/) | Python unittest modules spanning unit, integration, HTTP and runtime scenarios; inspect each selected test before execution. |
| [tests/js/](../tests/js/) | Browser/client JavaScript harnesses. |
| [tests/fixtures/](../tests/fixtures/) | Retained synthetic test inputs and helper code, not user history. |
| [docs/](./) | Review, access, acceptance and engineering documentation. |
| [docs/phoenix/](phoenix/) | Architecture, contracts, roadmap/amendments and implementation handoffs. The [canonical roadmap](phoenix/CANONICAL_ROADMAP.md) remains the existing direction source. |
| [docs/phoenix/assessments/](phoenix/assessments/) | Dated assessments and proposals; a retained assessment is not automatically an adopted plan. |
| [deploy/](../deploy/) | Retained [systemd units](../deploy/systemd/), [Windows scripts](../deploy/windows/) and [sudoers material](../deploy/sudoers/). These describe operational configuration, not proof of an installed service. |
| [scripts/](../scripts/) | Development, acceptance, import, notification, credential setup and release/assurance helpers with differing side effects. Read their owners; do not run them as a generic smoke check. |
| [requirements.txt](../requirements.txt) | Python dependencies; the focused documentation checks need only the standard library. |
| [package.json](../package.json), [package-lock.json](../package-lock.json) | Browser Presence build dependencies and lockfile. `build:presence` bundles [the entry point](../src/app/presence-three-entry.js) into [the retained bundle](../src/app/static/presence-three.bundle.js); it is not a documentation check. |

## Private and generated material

[.gitignore](../.gitignore) separates repository material from local credentials,
runtime stores, dependency directories and generated output. Private top-level
`archive/`, `database/`, `memory/`, `library/`, `conversations/`, `instances/`
and `backups/` are ignored; `.env` files, `credentials/`, `secrets/`, logs and
database files are also excluded. `.venv/`, `node_modules/` and caches are local
tooling material. Ignored does not mean safe to delete, and untracked files may
be valuable unfinished source or tests.

Deployment definitions can point outside the repository: for example, the
[app service](../deploy/systemd/fawkes-app.service) names separate runtime-state
and environment-file locations. Those private locations are not navigation
targets or inputs to documentation tests. Do not inspect, copy or publish them
to validate this map.

## Reading status honestly

The [current implementation pointer](phoenix/CURRENT_IMPLEMENTATION.md) separates
the accepted/deployed console from the byte-preserved
[September 8 capture](phoenix/CURRENT_IMPLEMENTATION_2026-09-08_CAPTURE.md).
[Repository work and cleanup](REPOSITORY_WORK.md) links the exact unfinished-work
inventory, remaining causal groups and [status evidence](repository-status-evidence.json).
The [external review guide](EXTERNAL_REVIEW_GUIDE.md) retains a labeled historical
matrix; it cannot override newer accepted evidence.

A path in this map is navigation, not proof of acceptance, integration or
deployment. Cleanup is an active bounded assignment, not permission to discard
untracked work or start distant roadmap capabilities.
