# Workflow jobs with exhausted retries

Area: workflow. Synthetic runbook for the fictional ApprovalLane service.

## Symptoms
A Camunda-style workflow task is stuck, a job has exhausted retries, or an external worker stops advancing process instances. The same business step may repeatedly fail.

## Investigation
- Inspect the failed activity, exception category, retry count, and incident timestamp.
- Check external worker availability and the downstream dependency used by that activity.
- Compare process variables with the documented input contract without exposing private values.
- Check whether a worker completed a side effect before failing to acknowledge the task.

## Review before mitigation
- Confirm idempotency before proposing a retry of an activity with side effects.
- Ask the process owner to approve a bounded retry after the underlying failure is understood.
- Do not modify process variables or retry all failed instances without a reviewed recovery plan.

## Verification
Confirm that the affected process reaches the expected next activity and that the business operation happened only once.
