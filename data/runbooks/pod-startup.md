# Container startup and readiness failures

Area: deployment. Synthetic runbook for the fictional WorkflowDesk service.

## Symptoms
A Kubernetes or OpenShift deployment has unavailable replicas, CrashLoopBackOff, or readiness probes that fail after a rollout. An image pull failure may prevent the container from starting at all.

## Investigation
- Compare the deployed image digest and configuration with the last known working release.
- Inspect container exit reason and startup logs with secrets redacted.
- Check readiness and liveness probe path, port, and startup timing.
- Verify required configuration references and image pull permissions.

## Review before mitigation
- Distinguish a process crash from a healthy process failing its readiness probe.
- Ask the release owner to review rollback eligibility and database compatibility.
- Do not disable health probes to conceal a failed startup.

## Verification
Confirm that replicas become ready, restarts stop, and a representative request succeeds after the rollout stabilizes.
