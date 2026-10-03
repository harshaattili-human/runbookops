# Message retries and dead-letter queues

Area: messaging. Synthetic runbook for the fictional EventBridge service.

## Symptoms
The dead-letter queue grows, retries repeat for the same event, or duplicate messages create repeated side effects. Serialization failures can cause a poison message to cycle indefinitely.

## Investigation
- Compare the failing message schema version with the consumer contract.
- Inspect retry count, retry interval, and the original failure category.
- Check the deduplication key and idempotency boundary around side effects.
- Separate transient dependency failures from invalid payloads.

## Review before mitigation
- Preserve the original event and failure reason without exposing personal payload data.
- Require an owner-reviewed replay plan with a small batch and a stopping condition.
- Avoid infinite retries; propose bounded backoff for transient failures.

## Verification
Confirm that replayed records produce one intended side effect and that dead-letter growth stops for the corrected cause.
