# Workflow routing and correlation failures

Area: workflow. Synthetic runbook for the fictional ApprovalLane service.

## Symptoms
An approval waits at a gateway, a message fails correlation, or a scheduled timer does not advance a process instance. A process definition change may leave existing instances using an earlier version.

## Investigation
- Inspect the current activity and process-definition version for the affected instance.
- Check gateway conditions and the presence and types of required variables.
- Compare the correlation key and message name with the waiting subscription.
- Inspect timer due dates and the job executor's availability.

## Review before mitigation
- Reproduce the route with synthetic inputs before changing a definition.
- Review migration compatibility for running process instances.
- Obtain process-owner approval before repairing variables or correlating a message manually.

## Verification
Confirm that the expected path is taken and that no duplicate approval or message subscription remains.
