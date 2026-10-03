# Development backlog

Pick one coherent improvement at a time. Record the problem, validation method,
result, and any remaining limitation. Prefer a reproducible result to adding a
new dependency or framework without a measured need.

1. Add near-topic negative retrieval cases and study abstention failures without
   repeatedly tuning on the same evaluation set. Keep a separate validation set.
   Compare classification against a simple dummy baseline, and retrieval against
   BM25-only and TF-IDF-only variants. Report unsupported-answer cases and routing
   abstention separately from forced-label classifier F1.
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
