# Container checks

The container job builds the multi-stage Dockerfile from a fresh checkout and tests
the packaged application over HTTP. It runs separately from the Python and frontend
test job, so missing image files cannot be hidden by an editable installation or a
mounted source directory.

## Reproduce

Requires a local Linux Docker engine and Python 3.12 on the host. Run from the repo:

```sh
docker build --pull --tag runbookops:smoke .
python scripts/container_smoke.py
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
npm lockfile.

Docker references: [run options](https://docs.docker.com/reference/cli/docker/container/run/)
and [health checks](https://docs.docker.com/reference/dockerfile/#healthcheck).
