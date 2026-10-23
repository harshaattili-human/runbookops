# Development backlog

Pick one coherent improvement at a time. Record the problem, validation method,
result, and any remaining limitation. Prefer a reproducible result to adding a
new dependency or framework without a measured need.

1. Continue answerability work only with a newly frozen holdout. The rejected
   [request-shape guard](information-type-v3.md) preserved expected-top-and-answered
   supported counts on v3 validation and holdout while reducing holdout unsupported
   answers from 6/10 to 1/10, but misclassified an existing descriptive incident that
   contained “maximum.” Preserve that runtime regression, the pool-size failure and
   both coverage-withheld supported cases. Do not tune rules on now-exposed v3; a
   future proposition/entailment comparison needs new data and phrasing variation.
2. Verify touch/physical-device behavior and perform manual assistive-technology
   checks. Chromium/Firefox/WebKit checks now exercise responsive layout and source
   inspection at three widths; see [browser checks](browser-checks.md).
3. Compare sparse retrieval against an optional local sentence embedding baseline;
   measure quality and runtime on a separately authored holdout.
4. Separate API reliability from access-control incidents and document taxonomy changes.
5. Add an operator refresh trigger and multi-process coordination. The trusted
   service supports [atomic in-process index refresh](index-refresh.md), and a
   manifest-pinned release workflow now prevents a refresh from mixing source-file
   generations. The stock HTTP app still uses its startup snapshot; each worker needs
   a trusted trigger and rollout coordination.
6. Extend the [Spring Boot client example](spring-client.md) when a concrete caller
   needs total deadlines, admission limits or tracing propagation. It now uses
   explicit connect/read timeouts, retains response request IDs and checks source
   hashes; its synchronous calls still need a caller concurrency budget.
7. Evaluate real local LLM outputs for citation entailment and unsupported claims.
   Verify provider-side compute termination. Client-disconnect cancellation now
   closes adapter I/O; see [HTTP disconnect checks](client-disconnect.md).
   A [30-second cooperative generation deadline](generation-deadline.md) now closes
   slow HTTP responses, with two per-process slots and immediate busy fallback.
8. Recheck unresolved OS advisories as base images receive fixes; extend auditing
   to the Node builder and assess native-library coverage. See the current
   [image/dependency audit scope](dependency-audits.md).
9. Extend the recorded walkthrough when new workflows are implemented. The
   [single-file replay](recorded-demo.md) now has an export receipt and offline
   browser checks; keep real inference local until deployment controls are addressed.

No paid services, production data, employer source code, or automated infrastructure
actions are required. Research and partially implemented experiments belong on a
branch; the default branch should remain runnable.

The triage HTTP boundary now rejects bodies above 32 KiB before parsing, including
chunked uploads. [Request-bound checks](request-bounds.md) cover framing and
disconnects. A single 30-second upload deadline now rejects stalled/trickling bodies;
[aggregate triage admission](triage-admission.md) now retains slots through response
completion and cancellation cleanup. Rate limits and fairness remain open.

Completed October 4: a same-fold dummy classifier comparison, fixed-gate ranking
ablations, separate synthetic validation/holdout suites, and per-case failure reports.
See [the protocol and results](evaluation-v1.md). The ranking variants tied on these
small sets; answerability remains unresolved.

Completed October 5: an explicit insufficient-evidence response, IDF-weighted
document-coverage gate, and a separately frozen 26-case answerability holdout. The
policy reduced unsupported answers from 11/14 to 3/14 while retaining 11/12 supported
answers. It is a measured partial safeguard, not a solved answerability problem. See
[the protocol and failures](answerability-v2.md).

Completed October 5: the source dialog now contains keyboard focus, closes on Escape,
restores the invoking source card and marks background regions inert. Vitest/jsdom
interaction tests cover that flow plus source errors, navigation and the empty state.
This does not replace real-browser or assistive-technology verification.

Completed October 6: a separate CI job builds the Docker image and checks its
packaged UI/API over HTTP, non-root read-only operation, health, shutdown and
restart. [Commands and observed environment](container-checks.md) distinguish
hosted container evidence from the local HTTP checks. Load testing and dependency
vulnerability auditing remain separate work.

Completed October 8: a reproducible passage-locality comparison tested a second
lexical gate. It reduced validation's unsupported answers from 1/10 to 0/10, but on
the exposed v2 regression suite it left unsupported answers at 3/14 and reduced
supported answers from 11/12 to 9/12. The candidate was not adopted. See the
[negative result and per-case reports](passage-experiment.md).

Completed October 21: a fixed request-shape guard was published after validation,
then scored once on the frozen v3 holdout. It retained 8/10 expected-top supported
answers and changed unsupported answers from 6/10 to 1/10, meeting the preregistered
numeric rule. Runtime integration was rejected after the existing generation-admission
suite exposed a false signal on a descriptive “maximum connections” sentence. The
service remains unchanged; v3 is exposed and cannot be used to repair the rule.

Completed October 10: integrated source-snapshot hashes and version-checked citation
inspection. A changed or removed runbook prompts a fresh analysis instead of opening
a different document under old line references. Library browsing remains unversioned.
The recorded demo and container checks use the updated API contract.

Completed October 12: live Chromium workflows now check desktop and narrow layouts,
versioned source inspection, keyboard source scrolling, abstention, navigation and
source-conflict recovery. They exposed a missing keyboard focus target in the
source document; the text is now a focusable region inside the modal trap. CI
retains reproducible screenshots and failure traces. This is resized desktop
Chromium, not physical-device or assistive-technology verification.

Completed October 12: CI records installed OS/Python package advisories and audits
the frontend lockfile. The runtime image no longer retains pip after installation.
Unfiltered reports preserve findings outside the blocking policy; this is known
advisory matching, not a clean bill of health or exploitability assessment.

Completed October 15: optional generation now bounds the provider JSON envelope,
requires normal completion and retains source text on oversized/incomplete replies.
Controlled loopback HTTP and stream tests cover the contract; live model quality
remains unmeasured. See [the boundary and reproduction](ollama-boundary.md).
