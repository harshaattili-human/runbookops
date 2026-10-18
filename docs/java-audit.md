# Packaged Java dependency audit

The audit scans the executable Spring Boot JAR, including the libraries actually
shipped under `BOOT-INF/lib`. A POM-only scan can differ from the packaged runtime;
the plain application JAR does not contain those dependencies.

After packaging, reproduce with Docker and Python 3:

```sh
python3 scripts/test_jar_audit.py
bash scripts/audit_jar.sh examples/spring-client/target/runbookops-client-example-0.1.0-SNAPSHOT.jar examples/spring-client/target/java-audit
```

Use a new output directory each time. The script refuses an existing directory so
a failed invocation cannot reuse a previous success receipt. It copies the JAR into
a temporary read-only scanner input and records that copy's SHA-256 plus hashes of
every packaged library. It does not execute the JAR.

Trivy 0.75.0 runs as the caller's UID/GID with dropped capabilities and no Docker
socket. Only its input, cache and output directories are mounted. The version-tagged
scanner's resolved image digest and scanner/database metadata are retained; the
digest is observed, not pinned. Network access is required for advisory and Java
identification databases. See [Trivy's Java detection contract](https://trivy.dev/docs/v0.75/guide/coverage/language/java/).

One unfiltered JSON scan supplies both evidence and the gate. The inventory checker
requires Trivy schema 2 and a named, versioned Java package with a matching archive
path for every `BOOT-INF/lib/*.jar` entry. Empty scans, missing libraries, plain JARs
and scanner errors fail. Matching inventory paths establish detection coverage, not
that the scanner inferred every package coordinate correctly.

The gate rejects HIGH/CRITICAL advisory entries with a known fixed version. Unfixed
high-severity findings and lower-severity findings remain in the report; passing
does not mean vulnerability-free. No ignore list or reachability exception is used.
CI retains full findings, inventory/hashes and scanner metadata for 30 days.

The four Python fixture tests exercise coverage rejection and the gate policy; they
do not run Trivy. The hosted scan is separate evidence. This audit excludes the
JVM/host OS, Maven/plugins/test dependencies absent from the executable JAR, and
first-party application or embedded loader bytecode. It does not establish
exploitability, provenance authenticity or production readiness. Re-run as advisory
databases change; a JAR hash identifies an artifact, not a reproducible-build claim.

This covers the Spring client example. Python image and frontend dependencies have
[separate audits](dependency-audits.md).

## Initial findings, October 18, 2026

[Run 39103265554](https://github.com/harshaattili-human/runbookops/actions/runs/39103265554)
at `daf9f8b` identified all 26 packaged libraries and reported 12 advisory entries,
including five fixable HIGH entries. The gate failed. The
[baseline report](../reports/java-audit-baseline-2026-10-18.json) retains every
finding, library hashes and database metadata; matches are not demonstrated exploits.

The preceding command used `filesystem`, which skipped the JAR. The inventory
checker rejected that empty scan. The corrected command uses `rootfs`, following
[Trivy's target coverage matrix](https://trivy.dev/docs/v0.75/guide/coverage/language/).

The candidate dependency update selects Jackson BOM 2.21.7, preserving module
alignment, and Log4j 2.25.5. See the upstream
[Jackson release](https://github.com/FasterXML/jackson/wiki/Jackson-Release-2.21.7)
and [Log4j release notes](https://logging.apache.org/log4j/2.x/release-notes.html).

## Updated verification

[Run 39103512837](https://github.com/harshaattili-human/runbookops/actions/runs/39103512837)
at `a58c49f` passed all five jobs. All 26 packaged libraries were identified with
zero advisory entries in this scan, compared with 12 before the dependency updates.
The [updated receipt](../reports/java-audit-updated-2026-10-18.json) records hashes
and scanner metadata. Both scans used the vulnerability database updated
2026-10-18T00:43:37Z and Java identification database updated 2026-10-18T00:58:00Z.
This observation applies to the Java example, not the separate runtime-image audit.

All nine Java cases passed with no failures/errors/skips, and the executable
walkthrough verified the live API's database-pool source hash and lines 5–7.
The run also passed 120 Python tests, seven component tests, validation/build,
27 live plus 18 recorded browser executions and container/runtime/restart/audit
checks. No model, corpus or thresholds changed; exposed holdouts were not rescored.
Environment: Ubuntu 24.04.5, Java 17.0.20.1, Maven 3.10.0, Python 3.12.15,
Boot 3.5.16. Java/scanner/browser/container execution was hosted. Local verification
covered four audit fixtures, shell syntax and documentation/diff review; the old
local Python virtual environment was unavailable.

Interview exercise: why is a zero-finding report meaningless unless the scanner
actually identified the libraries in the packaged artifact?
