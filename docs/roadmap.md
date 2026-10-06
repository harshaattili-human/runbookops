# Development backlog

Pick one coherent improvement at a time. Record the problem, validation method,
result, and any remaining limitation. Prefer a reproducible result to adding a
new dependency or framework without a measured need.

1. Compare passage-level answerability methods on validation. The lexical document-
   coverage gate still passes requests for absent credentials, numeric guarantees
   and business decisions, and it suppresses some useful paraphrases or padded text.
   Preserve the v2 failures and freeze a new holdout before another improvement claim.
2. Add real-browser coverage for responsive layout, source inspection and mobile
   navigation. Component tests now cover source-dialog focus containment, Escape,
   focus restoration, fetch errors, keyboard navigation and the empty state.
3. Compare sparse retrieval against an optional local sentence embedding baseline;
   measure quality and runtime on a separately authored holdout.
4. Separate API reliability from access-control incidents and document taxonomy changes.
5. Add content hashes to runbook evidence and invalidate cached indexes when sources change.
6. Add a Spring Boot integration example that calls the triage API with bounded
   timeouts and correlation IDs; use synthetic incidents only.
7. Evaluate real local LLM outputs for citation entailment and unsupported claims.
8. Add explicit Python dependency and base-image vulnerability auditing to CI.
9. Add a reproducible visual demo or short recording with source inspection and
   abstention. Label recorded responses explicitly; keep real inference local until
   the deployment controls in the model card are addressed.

No paid services, production data, employer source code, or automated infrastructure
actions are required. Research and partially implemented experiments belong on a
branch; the default branch should remain runnable.

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
