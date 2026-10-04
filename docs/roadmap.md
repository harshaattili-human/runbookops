# Development backlog

Pick one coherent improvement at a time. Record the problem, validation method,
result, and any remaining limitation. Prefer a reproducible result to adding a
new dependency or framework without a measured need.

1. Investigate answerability on the new validation cases: the fixed gate returns
   guidance for six of ten unsupported requests. Measure the tradeoff between
   withholding unsupported guidance and retaining supported coverage. Use a new
   frozen holdout for future improvement claims; v1 is now exposed. Add ambiguous
   supported cases that can distinguish ranking methods without hard-coding queries.
2. Add keyboard focus containment and automated browser coverage for source inspection,
   error handling, mobile navigation, and the empty state.
3. Compare sparse retrieval against an optional local sentence embedding baseline;
   measure quality and runtime on a separately authored holdout.
4. Separate API reliability from access-control incidents and document taxonomy changes.
5. Add content hashes to runbook evidence and invalidate cached indexes when sources change.
6. Add a Spring Boot integration example that calls the triage API with bounded
   timeouts and correlation IDs; use synthetic incidents only.
7. Evaluate real local LLM outputs for citation entailment and unsupported claims.
8. Add container-build verification and dependency auditing to the hosted CI workflow.
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
