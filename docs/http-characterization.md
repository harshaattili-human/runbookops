# Closed-loop HTTP concurrency characterization

Admission tests establish correctness under held work; they do not show observed
throughput or latency. `scripts/http_characterization.py` measures the actual built
image through a loopback-only Docker port and records every request. It accepts no
remote URL. The default application, model, corpus and admission policy are unchanged.

```sh
docker build --pull --tag runbookops:smoke .
python scripts/http_characterization.py
python tests/test_http_characterization.py
```

The script resolves the image tag to its immutable local ID, then owns one container
with one Uvicorn worker, two CPU quota units, 512 MiB memory/no additional swap,
read-only root, dropped capabilities and no-new-privileges. Host and container runtime
versions, enforced limits, Git checkout/dirty state, image ID, workload hash and
corpus identities appear in `artifacts/http-characterization.json`. CI retains it
for 30 days. The JSON is updated after every cell; incomplete and invalid runs remain
identifiable and fail the command. Only the uniquely named owned container is removed.

## Protocol and interpretation

Four authored synthetic smoke descriptions cover database guidance, workflow
guidance, an unrelated question and an unsupported request. They are visible workload
fixtures, not a held-out quality dataset. No model generation or holdout scoring runs.
Twelve sequential warmups establish stable response hashes. Only request ID and
duration are excluded; all routing, answerability, evidence and corpus fields remain.

Five client counts (1, 2, 4, 8, 16) each run five times, with 1,024 attempts in every
cell: 25 cells and 25,600 measured attempts. A cyclic Latin square puts each client
count in each order position once. Every client issues one request at a time with
no think delay, no application retry and a new HTTP/1 connection. Clients synchronize
at the start of a cell, not before each request. Each client cycles all four query
types equally; each cell uses the same attempted query mix. Per-query status counts
retain the successful mix, which can change when the service rejects some requests.
Four final sequential requests verify recovery against the initial hashes.

Record start offsets, client/query IDs, complete-response latency and outcome for
every attempt. Report nearest-rank p50/p95/max **separately** for 200, 503 and any
transport-error group; successful responses/second excludes rejections. A fast 503
must not appear as improved successful latency or useful throughput. A 200 must
match its reference hash; a 503 must match the exact admission/no-store contract.
Other statuses, transport failures or semantic drift fail after retaining the report.
There is no speed threshold or requirement that any particular cell reject requests.

This is a short closed-loop characterization, not an open-arrival load test, SLO,
capacity recommendation, production benchmark or quality improvement. Slow responses
reduce offered load (coordinated omission relative to open arrivals). Client and
server share a host; Python driver scheduling, new connections, Docker networking,
health probes, CPU throttling, shared-runner noise and warm caches affect results.
Counterbalancing reduces one order effect; it does not isolate all of those causes.
The 512 MiB limit is a test setting, not a measured total-memory requirement. Results
do not generalize to multiple workers, other corpora, provider generation or remote
networks. Preserve individual trials and adverse tails instead of reporting only a
pooled or best-case number.

Three standard-library checks validate outcome denominators, fingerprint sensitivity
and equal-work/counterbalanced scheduling. Local checks pass; actual container
measurements require hosted Docker in the current environment. Observed evidence
will be added after the run, before any measured-performance claim.

Interview exercise: why can attempted requests/second increase while successful
responses/second falls, and what does closed-loop traffic hide about an overloaded API?
