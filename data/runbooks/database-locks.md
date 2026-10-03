# Database lock contention and deadlocks

Area: database. Synthetic runbook for the fictional LedgerFlow service.

## Symptoms
Transactions wait on row locks, deadlock errors appear, or reconciliation updates stop making progress. A request timeout can be a downstream symptom of lock contention.

## Investigation
- Inspect blocking and waiting sessions with read-only database diagnostics.
- Identify the transaction age, affected tables, and query associated with the blocking session.
- Compare update ordering across workers and check whether transactions contain external calls.
- Check whether a recent batch increased transaction size or concurrency.

## Review before mitigation
- Preserve the diagnostic evidence and contact the owning team before terminating sessions.
- Propose smaller transaction boundaries or consistent update ordering after reproducing the issue.
- Review retry logic for bounded backoff and idempotency.

## Verification
Confirm that lock waits decline and reconciled records remain consistent. A lower error count alone does not prove that skipped work was recovered.
