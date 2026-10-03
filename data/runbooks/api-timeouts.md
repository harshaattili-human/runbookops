# API timeouts and circuit breakers

Area: api-security. Synthetic runbook for the fictional AccessGate service.

## Symptoms
REST calls time out, return HTTP 502 or 504, or fail while a circuit breaker is open. Repeated retries can amplify traffic during a downstream outage.

## Investigation
- Compare connection and read timeout settings across the calling chain.
- Inspect downstream latency, error rate, and circuit-breaker transitions.
- Check retry count, backoff, and the total request time budget.
- Use correlation identifiers to follow a representative request without logging sensitive bodies.

## Review before mitigation
- Do not blindly increase all timeouts or add unbounded retries.
- Review a bounded retry policy only for operations that are safe to repeat.
- Check that fallback behavior does not report success for an incomplete operation.

## Verification
Confirm that latency and failure rate recover while duplicate requests and downstream load remain within the expected baseline.
