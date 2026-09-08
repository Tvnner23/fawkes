# Project Fawkes

Fawkes is a persistent, user-controlled personal AI system.

The current repository is an active pre-Alpha implementation, not a completed
Phoenix platform. It includes authenticated Chat, canonical history, Memory and
Development foundations, capability awareness, research and multimodal paths,
structured presentation, a rider-facing Capability Test Center, and an
instance-scoped durable Library/PDF vertical slice. The canonical roadmap also
describes substantial future work that is not live today.

Experienced external reviewers should begin with
[External Developer Review Guide](docs/EXTERNAL_REVIEW_GUIDE.md), which separates
implemented behavior from roadmap/design intent and identifies the areas where
critical disagreement is most valuable.

For focused changes, read [Contributing](CONTRIBUTING.md) and the
[Repository layout](docs/REPOSITORY_LAYOUT.md). Implementation/status documents
contain dated captures (including the 2026-09-08 implementation pointer); reconcile
them with current accepted evidence before relying on phase or deployment claims.
This contributor/navigation batch leaves the broader repository cleanup open.

## Core Architecture

Long-term direction and dated implementation handoff:

- [Project Fawkes Canonical Roadmap v1](docs/phoenix/CANONICAL_ROADMAP.md)
- [Current Project Fawkes Implementation](docs/phoenix/CURRENT_IMPLEMENTATION.md)

### Archive
The Fawkes Archive is the immutable, verbatim source of truth.
Original conversations are preserved and are never replaced by summaries.

### Memory
Fawkes Memory is the evolving interpretation of the Archive.
It can summarize, organize, connect, and update information without modifying the original history.

### Intelligence
The reasoning model is replaceable. Fawkes is not permanently tied to one AI model or provider.

### Tools
Fawkes can eventually interact with authorized computers, services, and home automation systems.

### Security
Access and permissions must be explicit, limited, auditable, and controlled by the user.

## Prime Rule

Memory may evolve. The Archive does not.

## Run the current Fawkes development build

Requirements:

- the repository virtual environment is installed;
- `OPENAI_API_KEY` is available in the environment.

Install or refresh the project dependencies with:

```bash
.venv/bin/pip install -r requirements.txt
```

Start the private single-instance conversation loop from the repository root:

```bash
.venv/bin/python src/fawkes.py chat
```

`FAWKES_CHAT_MODEL` is optional and defaults to `gpt-5.6-luna`. Enter `exit`
or press Ctrl+C to disconnect. Fawkes resumes the latest local conversation on
the next launch.

Each user turn is archived before the provider call. Each completed assistant
turn is then archived, indexed, and available after restart. The runtime uses
instance-scoped durable memories, relevant immutable archive passages, and a
bounded recent conversation window. If semantic memory ranking fails, it falls
back to local lexical retrieval and reports a warning instead of aborting the
conversation.

Memory evaluation remains a separate, reviewable operation; live user turns are
queued but are not silently converted into durable memory during chat.

## Run Fawkes Chat on a phone

The first app is a thin mobile web home for the same runtime used by the CLI.
It resumes the same Phoenix instance and canonical Archive conversation; it
does not maintain a separate transcript or memory store.

For access from another device on your private network, set a strong token and
bind the server to the network interface:

```bash
export FAWKES_APP_TOKEN='replace-with-a-long-random-secret'
.venv/bin/python src/fawkes.py app --host 0.0.0.0 --port 8787
```

Open `http://HOST-COMPUTER-IP:8787` on the phone, enter the token, and add the
page to the home screen if desired. Keep this service on a trusted private
network; use a TLS-terminating private tunnel or reverse proxy before exposing
it beyond that network. `OPENAI_API_KEY` and the optional `FAWKES_CHAT_MODEL`
remain server-side and are never sent to the browser.

When `FAWKES_APP_TOKEN` is set, the app defaults to `0.0.0.0`; without a token it
defaults to local-only `127.0.0.1`. A running local-only process must be restarted
before another device can connect. Platform-specific firewall, tunnel, and port
forwarding configuration is intentionally machine-local and is not part of the
shareable engineering repository.

Local-only use needs no token and defaults to `http://127.0.0.1:8787`:

```bash
.venv/bin/python src/fawkes.py app
```
