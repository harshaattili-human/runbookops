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

## Observed evidence — October 28, 2026

The first 64-attempt-per-cell pilot (`1d14e0e`, run 40701090296) passed but its cells
lasted fractions of a second. Inspection also showed that the original modulo
assignment pinned clients to one query type at concurrency four or above. The
measurement protocol was revised to 1,024 attempts per cell and a complete rotating
query mix in every client. This is a protocol refinement, not an application speedup.
The [pilot raw data](../reports/http-characterization-pilot-2026-10-28.json.gz) is retained;
do not pool it with or present it as a controlled baseline for the revised protocol.

Revised implementation `06561405603e37afb37537660dc7a5dda90d1af2` passed all five
jobs in [run 40703077735](https://github.com/harshaattili-human/runbookops/actions/runs/40703077735).
All 25 cells completed. Every 200 response matched its sequential decision/evidence
hash, every 503 matched the admission contract, there were no transport errors,
and all four final recovery responses matched. Measured cells lasted 2.12–3.76 seconds;
these remain brief observations, not a long soak or stable tail-latency estimate.

Each row below has five trials and **5,120 attempted requests**. Ranges preserve the
lowest/highest per-trial value rather than pool samples or select a best run:

| Concurrent clients | HTTP 200 / 503 totals | Successful responses/s range | Successful-response p95 ms range |
| ---: | ---: | ---: | ---: |
| 1 | 5120 / 0 | 272.06–292.33 | 3.79–5.33 |
| 2 | 5120 / 0 | 287.85–298.28 | 8.55–8.97 |
| 4 | 5120 / 0 | 289.76–302.61 | 17.53–18.54 |
| 8 | 5120 / 0 | 298.11–299.57 | 34.64–35.44 |
| 16 | 2843 / 2277 | 255.87–265.73 | 55.10–57.44 |

Increasing clients did not yield proportional successful throughput on this fixture.
At 16 clients, 2,277 of 5,120 attempts were rejected while successful latency rose.
These outcomes do not select a new default admission capacity: query mix among
successful requests can differ after rejection, and the shared driver/server host,
new connections, warm caches and two-CPU quota remain confounders. Profile those
costs and test representative workloads/open arrivals before deployment sizing.

The [complete compressed JSON](../reports/http-characterization-2026-10-28.json.gz)
preserves 25,600 request samples, all per-query outcome counts and environment data.
Decompressed SHA-256 is
`a0706b28fa0c0c96ef4c6ffd1bce82e388e1c1f2e79e76e695da2a2dc3809508`.
The measured image was `sha256:e20c3a83318f674e43a2a94f30ce4dd2323ff9a800a81b650b47996849526b6d`,
at GitHub test-merge checkout `674359f40f2622580968fced240b343c9db878d6` with no tracked
changes. Host: four available CPUs, AMD EPYC 7763 model string, Linux amd64/Docker
28.0.4/Python 3.12.15; container: Python 3.12.16, FastAPI 0.142.2, Uvicorn 0.54.0,
scikit-learn 1.8.0, NumPy 2.3.5, HTTPX2 2.16.0. Enforced container limits were two CPU
quota units and 536,870,912 bytes of memory with no additional swap.

```sh
python scripts/summarize_http_characterization.py reports/http-characterization-2026-10-28.json.gz
```

The same run passed 231 Python cases plus 11 subtests, seven component cases/build,
18 Java executions/live JAR, 36 live plus 18 recorded browser executions, default
and mounted-release container checks and configured audits. No runtime, model,
ranking, threshold or holdout decision changed. Full application/browser/container
execution was hosted; the three measurement-contract cases ran locally as well.
