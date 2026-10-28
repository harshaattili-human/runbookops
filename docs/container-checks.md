# Container checks

The container job builds the multi-stage Dockerfile from a fresh checkout and tests
the packaged application over HTTP. It runs separately from the Python and frontend
test job, so missing image files cannot be hidden by an editable installation or a
mounted source directory. A separate second phase rehearses external corpus
releases with read-only data mounts; it does not replace the no-mount packaging check.

## Reproduce

Requires a local Linux Docker engine and Python 3.12 on the host. Run from the repo:

```sh
docker build --pull --tag runbookops:smoke .
python scripts/container_smoke.py
python scripts/corpus_container_smoke.py
```

For an existing image, pass `--image your-local-tag`. The runner does not pull it.
No application packages are needed on the host; the checkout supplies expected
fixture and report contents. The runner creates a uniquely named container, uses an
ephemeral port bound to `127.0.0.1`, prints diagnostics, and removes that container
when finished. It requires a local Docker context because HTTP requests use the
host's loopback address.

The image's default command and non-root user are retained. The test adds a read-only
root filesystem, a 64 MiB temporary `/tmp`, no Linux capabilities and
`no-new-privileges`. It waits for the image's Docker health check, using a shorter
interval and a 30-second startup allowance. `OLLAMA_MODEL` is deliberately empty;
the fallback check requires no model server or credentials.

## Checked behavior

- Health and overview include the expected runbook and incident counts.
- All ten synthetic runbooks and the evaluation report match the checkout.
- The frontend entry page and its linked JavaScript and CSS are served with the
  expected content types.
- A database-pool incident returns a source extract, a valid citation and exact
  runbook line ranges.
- The existing Redis-eviction and unrelated-query examples withhold guidance.
- Requesting an unconfigured local model returns the same source text with a warning.
- Invalid input is rejected; unknown runbooks and selected private file paths return 404.
- The process uses UID 10001 and the root filesystem is mounted read-only.
- A normal stop exits successfully; after restart, the index is rebuilt and the
  same incident has the same route, source, answer and answerability fields. Request
  IDs and timing are intentionally excluded from this comparison.

These are synthetic packaging regressions, not another held-out model evaluation.
The HTTP checks do not execute JavaScript, inspect layout, measure load capacity,
validate a live LLM, or establish production security. No image is pushed to a
registry and no service is deployed.

## Build inputs

The job logs the image ID, Docker server version, CPU architecture, Python version
and direct runtime package versions. Base image tags and transitive Python
dependencies can change between builds; this is not a bit-for-bit reproducible build
or a full dependency vulnerability audit. The compiled frontend uses its committed
npm lockfile. The separate [advisory scan](dependency-audits.md), added October 12,
records installed OS/Python findings and audits the npm lockfile after installation.

## Verified October 6, 2026

[Run 37455311551](https://github.com/harshaattili-human/runbookops/actions/runs/37455311551)
passed both jobs at implementation commit
[`461cc1a`](https://github.com/harshaattili-human/runbookops/commit/461cc1af1c05856c0afdc49a640340a36c7d104a).
The container job built the image, passed the HTTP checks above, stopped with exit
code 0, restarted and returned the same inference fields. It used Linux x86-64,
Docker 28.0.4 and Python 3.12.15. Runtime versions were FastAPI 0.142.2, Uvicorn
0.54.0, scikit-learn 1.8.0, NumPy 2.3.5 and httpx 0.28.1. The logged image ID was
`sha256:f4a669a2733dc3b931fff32fe28f9b866abbcbc0365a715a8fa1aa03daf959f1`;
this identifies that build, not a downloadable registry artifact.

The separate verification job passed the existing 27 Python tests, three frontend
interaction tests, classifier/retrieval/answerability validation and production
build. The Starlette/httpx deprecation and Lucide build warnings remain.

Docker was unavailable in the development workspace. Local checks exercised the
same HTTP assertions against Uvicorn and deliberately removed a built JavaScript
asset to confirm that the smoke check rejected it. Container execution evidence
comes from hosted CI. No application or Dockerfile fix was needed in this increment.

Docker references: [run options](https://docs.docker.com/reference/cli/docker/container/run/)
and [health checks](https://docs.docker.com/reference/dockerfile/#healthcheck).

## Mounted corpus release rehearsal

`scripts/corpus_container_smoke.py` runs the actual release CLI inside the built
image, producing two temporary synthetic generations with one runbook each. The
generations differ in an authored investigation line. The producer runs with the
host UID/GID so its files remain cleanable; the API containers retain the image's
default UID 10001, command and working directory. The CLI creates private release
directories (0700), so this public fixture explicitly grants traversal (0755) and
file reads (0644) to the different API UID. Operators must arrange appropriate
ownership/group access for their own release; this fixture permission choice is
not a recommendation for confidential documents.

Each API launch uses the same image ID, a read-only root, dropped capabilities,
`no-new-privileges`, a temporary `/tmp`, a loopback-only port and a
[read-only bind mount](https://docs.docker.com/engine/storage/bind-mounts/#use-a-read-only-bind-mount)
at `/corpus`. Only that generated release is mounted; application code, frontend,
training data and reports come from the image. The runner verifies the mount
configuration and attempts to open both manifest and runbook for writing, requiring
writes to fail for the API UID. It repeats those opens with the fixture-owning
UID, which has file write permission, requiring `EROFS` to isolate the read-only
mount check from ordinary Unix permission denial.

The HTTP checks distinguish the selected one-document corpus from the ten bundled
documents, compare source text/hash/line ranges, and require an extractive answer
from the selected version. The runner then checks:

1. A clean stop/start retains release A with the same pin.
2. A and B can run concurrently with different hashes; each rejects the other's
   expected document hash with 409 and no document content.
3. After both are removed, a fresh container explicitly selects retained A again.
4. B with A's manifest pin exits during startup for the expected mismatch.
5. Editing B's disposable runbook while retaining its manifest/pin also fails startup.

The two-container overlap deliberately shows why a staggered rollout can serve two
versions. It implements no load balancer, coordinated rollout, health-based traffic
switch, automatic rollback or durable release storage. Read-only mounting prevents
the container from writing through that mount; it does not stop a host writer.
No registry is pushed, and there is no deployment, crash-recovery, throughput or
model-quality measurement.

Success writes `artifacts/corpus-container.json` with image ID, Docker version,
manifest/document hashes, fixture denominators and completed checks. Stale receipts
are removed before execution; CI retains a successful receipt for 30 days. Containers
use unique names and are removed on exit; fixture files live in a temporary directory.
The existing image audit scans the same built image afterward.

Initial [run 39976528747](https://github.com/harshaattili-human/runbookops/actions/runs/39976528747)
passed the original packaging check, then stopped at the first new write probe.
UID 10001 received `EACCES` on the host-owned 0644 files before the read-only check,
while the probe expected only `EROFS`. The corrected harness checks API write denial
separately from an owner-UID open that must return `EROFS`. It does not change the
application UID, fixture permissions or mount configuration.

The corrected implementation head `eb0dd4c` passed the container job in
[run 39976997853](https://github.com/harshaattili-human/runbookops/actions/runs/39976997853).
The receipt records Docker 28.0.4 and image ID
`sha256:177275bbf14c3bf0545206b880b35e179ecbb4c985ee5b8f7514be7f0db7b309`.
Both one-document generations completed all eight declared checks; their manifest
and document hashes differed as required. The same run passed 184 Python cases plus
11 subtests, seven frontend component cases, the Spring client check, npm audit and
the runtime-image audit (164 finding entries, zero fixable high/critical entries).
The browser job was cancelled while installing engines, so that run is not browser
evidence. [Run 40099717252](https://github.com/harshaattili-human/runbookops/actions/runs/40099717252)
then passed all five jobs after the independently documented Undici lockfile update:
184 Python cases plus 11 subtests, seven component cases, 27 live and 18 recorded
browser executions, the Spring client/live JAR walkthrough, both container checks,
and the configured npm, runtime-image and Java audits. The mounted-release receipt
again covered two distinct one-document releases and all eight declared checks.
Hosted versions included Python 3.12.15, Java 17.0.20.1 and Ubuntu 24.04. The
runtime-image scan inventoried 24 Python package names and retained 164 finding
entries with zero fixable high/critical entries; the Java scan inventoried 26
libraries with zero advisory entries. These dated snapshots and gates do not
establish a vulnerability-free image or toolchain.

The [local operator rehearsal](operator-refresh.md) extends the mounted-corpus
script with a mode-0700 UID 10001 tmpfs socket directory, a second read-only release
mount, stale-pin retention, same-process live refresh/rollback and restart selection.
The production image still defaults to no operator socket. This is one disposable
container controlled through trusted `docker exec`, not multi-worker coordination.


## Configured admission rehearsal

`python scripts/admission_smoke.py --image runbookops:smoke` owns a separate hardened
container and verifies `RUNBOOKOPS_TRIAGE_CAPACITY=2` before and after restart.
Fixed/chunked partial uploads occupy both slots; excess work receives 503 before
body reading, health remains reachable, and disconnect cleanup restores exactly
two slots. See [the configuration contract and measured execution](triage-admission.md#operator-configuration--october-28-2026).
This lifecycle check does not measure a recommended operating capacity.
