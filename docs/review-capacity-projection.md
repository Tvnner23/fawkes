# Bounded lossless review presentation v2

The full measured Pi package has 882,017 changed-source bytes, 3,437,807 resolved
canonical bytes and 1,093,300 compressed/base64 Exchange transport bytes. Finite
limits are respectively 1,100,000, 4,500,000 and 1,400,000 bytes. The independently
bounded provider presentation is 1,400,000 bytes. These are byte/resource limits,
not promises of model-context fit or authority to execute a review.

Existing bounded raw and postimage-reference v1 presentations remain readable.
If v1 exceeds the presentation cap, v2 additionally replaces UTF-8 preimage base64
and repeated diff text with explicit same-package line copies and literal runs.
Every changed source section remains complete readable UTF-8. Copy ranges are
zero-based line offsets and counts, with an explicit literal prefix. They refer
only to the exact changed-artifact section for that same path. No diff is applied
to infer missing bytes, and no external retrieval is performed. Non-UTF8 preimages
keep their already-admitted exact base64. Null bodies and all metadata survive.

The decoder binds the original canonical length and SHA-256 supplied by its caller,
not merely the wrapper's self-reported identity. It checks the wrapper digest,
strict reference fields/types, section/path identity, line ranges, body hashes and
lengths, duplicate keys/paths and exact reconstructed canonical bytes. Line indexing
uses a dictionary, not alignment search. Literal lists are joined once. Aggregate
line-processing/copy operations are capped at 200,000; aggregate source/output work
bytes are capped at 4,500,000. Expansion is checked before materializing copy text.
Oversize inputs fail closed; limits do not grant retrieval or execution privileges.

The **small tooling prerequisite** and the **large Pi candidate** are separate review
subjects. Accepting this implementation does not establish the large Pi review's
supported context, deploy anything or authorize autonomy. Its full request/context
fit remains a separate gate. Token counts from o200k_base are proxies, not exact
selected-model counts. The accepted structured-repair topology launches a fresh
ephemeral transport: initial and repair request sizes must be measured separately,
not added into an assumed accumulated conversation. No model-list membership
requirement, context override, model/client substitution or authority change is
introduced here.

After independent tooling acceptance, exact canonical application needs a separate
grant. After that commit, preserve the historical Pi freeze and rebase context only:
retain all 25 intended Pi postimages and the exact companion patch without copying
old contextual reviewer-owner files over the accepted prerequisite. Refresh base,
snapshot, lineage, applicable qualification, package and the distinct unused Pi
review-grant binding. This document authorizes none of those operations.
