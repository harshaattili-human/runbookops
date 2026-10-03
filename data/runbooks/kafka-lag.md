# Kafka consumer lag

Area: messaging. Synthetic runbook for the fictional EventBridge service.

## Symptoms
Consumer lag and event age increase while producers continue sending messages. The consumer group may repeatedly rebalance, or one partition may process more slowly than the others.

## Investigation
- Compare incoming message rate, processing rate, and lag per partition.
- Inspect consumer rebalances, processing time, and downstream dependency latency.
- Check for a hot partition or a message that repeatedly fails processing.
- Compare the last committed offset with application processing evidence.

## Review before mitigation
- Do not reset offsets or skip messages merely to make lag disappear.
- Review consumer concurrency relative to partition count and downstream capacity.
- Confirm idempotent processing and recovery ownership before replaying events.

## Verification
Confirm that event age and lag decrease while downstream records remain consistent. Check duplicate processing as well as throughput.
