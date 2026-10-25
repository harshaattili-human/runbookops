# Dependency and image audits

Runtime smoke tests check behavior, not known dependency advisories. The container
job now scans the exact locally built image after its HTTP/restart checks. The
separate dependency job audits the frontend lockfile, including development tools.
Neither job deploys an image or sends application data to a service.

## Reproduce

From the repository root, with Docker and Python 3.12:

```sh
docker build --pull --tag runbookops:smoke .
bash scripts/audit_image.sh runbookops:smoke reports/security
cd frontend
npm ci
npm audit --audit-level=high --json > npm-audit.json
```

The scanner pulls `aquasec/trivy:0.75.0`, reads a Docker archive mounted read-only,
and downloads its advisory database. The output directory must be new; choose
another path for each local run so stale reports cannot survive a failed scan.
It does not receive the Docker socket. It
runs as the caller's UID/GID, with Linux capabilities dropped and no-new-privileges.
A temporary archive/cache directory is removed on exit. Run from the repository
root because the inventory check reads the project's runtime requirements.

The image scan includes installed OS packages and Python package metadata,
including transitive dependencies. An inventory check rejects a report missing OS
packages or any direct runtime Python dependency named in `pyproject.toml`. This
catches an empty or incorrectly scoped scan; it cannot prove complete scanner
coverage. The final image has compiled JavaScript, not the npm package tree, so
`npm audit` covers that separate lockfile, including build/test dependencies.
The Node builder's OS image is not scanned in this increment.

## Blocking policy and retained evidence

Trivy writes its unfiltered JSON report first, then runs a high/critical,
fixed-version-only gate with the same downloaded database. Low/medium/unknown and
unfixed findings remain in the JSON report, including findings that do not block
CI. A passing gate therefore does not mean zero vulnerabilities. No CVE ignore
list is applied. Severity and fixed-version classifications come from the scanner
and its advisory sources, not an application reachability analysis.

`npm audit` reports all findings and fails for high/critical findings, whether or
not an automatic fix is offered. Scan, registry, database-download and malformed
report errors fail their jobs; they are not treated as clean scans. CI retains
`image-audit` and `npm-audit` artifacts for 30 days, including on failed jobs:

- `trivy.json`: detected packages, installed versions and all reported findings.
- `image-id.json`: the local image content ID; no registry publication is implied.
- `scanner-digests.json` and `scanner-version.json`: resolved scanner image digest,
  scanner version and downloaded database metadata.
- `blocking-findings.txt`: the filtered image gate's output.
- `npm-audit.json`: npm findings and dependency counts.

These commands reproduce the procedure, not an immutable result. Base image tags,
transitive Python resolutions and advisory databases can change. The scanner has a
version tag; its observed digest is recorded, not enforced across future runs.
Reports should always be interpreted with their commit, image ID, database date
and scanner version. Keep unfavorable findings in the evidence when updating a
package; do not suppress advisories simply to turn CI green.

This is known-advisory matching. It does not establish exploitability, source-code
security, malicious-package detection, secret scanning, image signing, license
compliance, runtime isolation or production readiness. Python's source-built
interpreter and bundled native libraries may not have complete advisory coverage.
Authentication, rate limits and a separate deployment review remain necessary
before exposing the application publicly.

References: Trivy's [image CLI](https://trivy.dev/docs/v0.75/guide/references/configuration/cli/trivy_image/),
[Python metadata detection](https://trivy.dev/docs/latest/coverage/language/python/)
and [filtering policy](https://trivy.dev/docs/latest/configuration/filtering/).

Optional interview exercise: why can an image pass a fixed high/critical gate and
still contain known vulnerabilities? Which report fields would you preserve when
comparing a later rebuild?

## Implementation failure retained

The first [run 38265277265](https://github.com/harshaattili-human/runbookops/actions/runs/38265277265)
passed the runtime smoke and npm audit, but the image audit stopped before scanning:
`--disable-telemetry` was incorrectly passed as a global flag rather than an image
command option. Commit `149fd0b` fixes the command placement and requires a new
output directory. That failed run is not evidence of zero image vulnerabilities.

## First completed scan — October 12, 2026

[Run 38265529926](https://github.com/harshaattili-human/runbookops/actions/runs/38265529926)
at `149fd0b` scanned Debian 13.7: 87 OS package records and 25 distinct Python
package names (including this application and pip; duplicate application metadata
can occur). Trivy reported 172 package/advisory entries across 79 distinct IDs:
166 OS entries and six Python entries. The 44 high-severity OS entries represented
eight advisory IDs, all without a fixed version in that database. None were
critical. These counts are scanner findings, not 172 independently exploitable
application defects.

All six Python entries concerned inherited pip 25.0.1: five medium and one low.
The reported IDs were CVE-2025-8869, CVE-2026-13346, CVE-2026-3219,
CVE-2026-6357, CVE-2026-8643 and CVE-2026-1703. They concern installation/archive
handling. The Dockerfile now upgrades to pip 26.2.1 before installing the project,
instead of leaving this build tool outdated merely because it falls below the
blocking threshold. See the [upstream changelog](https://pip.pypa.io/en/stable/news/).

The original [image report](https://github.com/harshaattili-human/runbookops/actions/runs/38265529926/artifacts/11754905750)
and [npm report](https://github.com/harshaattili-human/runbookops/actions/runs/38265529926/artifacts/11754482240)
remain available until their artifact retention expires. npm reported zero known
advisories across its reported total of 148 dependencies; category counts overlap.
No application dependency was changed based on a zero result.

## Installer update exposed bundled dependencies

[Run 38265914656](https://github.com/harshaattili-human/runbookops/actions/runs/38265914656)
at `4c21382` removed the six findings against pip itself, but the report detected
pip's bundled Python dependencies through its SBOM. Six entries affected msgpack,
setuptools and urllib3; four were high and fixable, so the unchanged gate failed.
The application HTTP/restart checks still passed. An update passing behavioral
tests is not sufficient evidence that its dependency findings improved.

The final Dockerfile uses the updated installer to build the application, then
uninstalls pip in the same layer. Runtime startup uses Python/Uvicorn and does not
need an installer. This removes pip and its bundled libraries from the final
filesystem; it does not establish that the build environment is vulnerability-free.
To add dependencies, rebuild the image rather than installing into a running one.

## Runtime rescan and verification

[Run 38266383691](https://github.com/harshaattili-human/runbookops/actions/runs/38266383691)
at `61dbcfa` passed all four jobs: 45 Python cases (four audit-inventory checks),
seven component tests, nine Chromium executions (three workflows at three widths),
validation evaluations, production build, packaged HTTP/restart checks and both
audits. Docker execution was hosted; local Python tests, frontend tests/build,
evaluations and shell syntax checks passed. No new holdout was scored.

The final scan contained 24 distinct Python package names, with no reported Python
advisories and no retained pip inventory entry. Debian still had 166 entries across
73 distinct advisory IDs: 44 high, 58 medium, 61 low and three unknown. The 44 high
entries still represent eight IDs without a fixed version. Removing the installer
resolved the Python findings in this scan; it did not resolve those OS findings.
Do not describe this image as vulnerability-free or production-ready.

Trivy 0.75.0 used advisory database version 2, updated
`2026-10-12T13:18:23.1639207Z`. The image ID was
`sha256:5bd31f1912eb612c3ddfe79635005b3f0cd746cfd31cc33403fb77e41fe73fe4`.
The [final artifact](https://github.com/harshaattili-human/runbookops/actions/runs/38266383691/artifacts/11754154482)
ZIP SHA-256 was `9905fdac983e90b00ef89ebd66299298a299316164881d5afd3e306c5b84e16e`.
A [committed projection](../reports/dependency-audit-2026-10-12.json) retains the
final inventory and every final advisory/package pair, scanner metadata and the
Python findings from the earlier attempts after CI artifact expiry. It is a dated
observation, not a lockfile or a substitute for rescanning a later image.

Next: recheck the unresolved OS advisories against later base-image fixes, examine
build-stage/native-library coverage and assess exposure before any deployment.
The gate policy was not relaxed in response to these findings.

## Vite advisory response — October 21, 2026

The dependency job in [run 39610023279](https://github.com/harshaattili-human/runbookops/actions/runs/39610023279)
failed after npm's database began reporting a high-severity Windows command-injection
path for Vite 8.3.2. The audit artifact retained the complete finding. Vite is a direct
development dependency rather than a package in the Python runtime image, but the
unchanged high/critical lockfile gate correctly blocked the candidate.

The lockfile now pins Vite 8.3.5. Its resolved Rolldown, PostCSS, Nano ID and platform
bindings changed with that release; these transitive changes were retained rather
than manually spliced out. A local clean install reported 148 total dependencies and
zero npm advisory entries, and passed seven component tests plus the production build.
This dated advisory result does not establish that the toolchain is vulnerability-free.

## Undici advisory response — October 24, 2026

The dependency job in [run 40099286088](https://github.com/harshaattili-human/runbookops/actions/runs/40099286088)
failed after npm reported three new advisories against Undici 8.11.2, including the
high-severity [excessive content-encoding denial of service](https://github.com/advisories/GHSA-xjj6-f33q-929c).
Undici is a transitive development dependency of jsdom and is absent from the Python
runtime image. The unchanged high/critical lockfile gate still blocked the pull
request.

The lockfile now resolves the existing jsdom range to Undici 8.12.3, beyond the
affected `<8.12.2` ranges for that advisory and the two moderate findings reported
in the same artifact. No direct dependency or application code changed. A clean
local install reported 148 total dependencies and zero npm advisory entries, then
passed seven component tests and the production build. The dependency job in
[run 40099717252](https://github.com/harshaattili-human/runbookops/actions/runs/40099717252)
also reported zero entries and all five project jobs passed. This remains a dated
known-advisory scan, not a vulnerability-free claim.

## HTTP client migration — October 25, 2026

[Run 40197939275](https://github.com/harshaattili-human/runbookops/actions/runs/40197939275)
verified the runtime migration from HTTPX 0.28.1 to HTTPX2 2.16.0. The container
receipt reported HTTPX2 at the pinned version, and the existing inventory gate found
all direct runtime dependencies among 24 Python package names. The scan retained 164
finding entries and found zero fixable high/critical entries under the unchanged
policy. The npm audit reported zero entries. These observations are tied to that run's
image and advisory databases; they are not a vulnerability-free or reachability claim.
