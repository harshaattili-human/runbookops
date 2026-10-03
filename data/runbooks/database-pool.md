# Database connection pool exhaustion

Area: database. Synthetic runbook for the fictional LedgerFlow service.

## Symptoms
Requests wait for a database connection and end with HikariPool connection timeout errors. Active connections remain at the configured maximum while pending requests rise. HTTP latency can increase even when CPU is low.

## Investigation
- Compare active, idle, and pending pool connections with the time of the first timeout.
- Inspect slow queries and long-running transactions using a read-only database view.
- Compare recent traffic and application changes with the baseline before the incident.
- Check that each request returns its connection after success, failure, and cancellation.

## Review before mitigation
- Identify the slow query or leaked connection before proposing a larger pool.
- Confirm the database connection budget across all application replicas.
- Ask the service owner to review a bounded change and its rollback plan.

## Verification
Check that pending requests drain, connection usage stabilizes, and latency returns to the previous baseline. Increasing pool size alone is not evidence that the underlying cause was fixed.
