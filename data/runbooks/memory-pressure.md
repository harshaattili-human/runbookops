# Container memory pressure

Area: deployment. Synthetic runbook for the fictional WorkflowDesk service.

## Symptoms
The container is OOMKilled, memory usage climbs toward its limit, or garbage collection pauses increase. Restarts may temporarily clear the symptom without resolving retained objects or oversized workloads.

## Investigation
- Compare working-set memory, configured container limits, and JVM heap settings.
- Inspect workload size, queue growth, and the timing of recent releases.
- Review heap diagnostics only in an approved environment because dumps can contain sensitive data.
- Compare steady-state usage with peaks during batch processing.

## Review before mitigation
- Propose a bounded workload or concurrency change before requesting more memory.
- Review available cluster capacity and rollback criteria with the service owner.

## Verification
Confirm that memory stabilizes over representative load and that restarts and long pauses stop.
