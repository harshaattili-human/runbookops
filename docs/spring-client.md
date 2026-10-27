# Calling triage from Spring Boot

The [Java 17 example](../examples/spring-client/src/main/java/dev/harshaattili/runbookclient/RunbookClient.java)
calls the running FastAPI service through Spring's `RestClient`. It gives a backend
workflow a small typed interface for extractive triage and versioned source inspection.
It never runs remediation or turns a failed request into invented guidance.

Start RunbookOps using the README instructions, then in another terminal:

```sh
cd examples/spring-client
mvn verify
java -jar target/runbookops-client-example-0.1.0-SNAPSHOT.jar
```

Requires Java 17 and Maven. The Boot 3.5.16 executable is a command-line application,
not another web server. It submits one authored database-pool incident to
`http://127.0.0.1:8000`, prints the returned request ID/mode/route and checks the first
source. `--runbook.base-url=http://127.0.0.1:8001` changes the trusted operator-configured
origin. There is no caller-supplied URL, authentication or cloud/model dependency.
Do not expose the unauthenticated Python demo publicly.

## Contract and tradeoffs

- Requests explicitly set `use_llm=false`. The adapter accepts `extractive` and
  `abstained`, preserving the server's `needs_review` flag and request ID. This ID
  correlates a result with downstream handling; it is not an inbound distributed
  tracing header. Unknown modes, missing required fields and citations outside the
  returned evidence fail the call. Additional unused JSON fields are allowed.
- An abstention is a successful API result with no evidence. HTTP errors, malformed
  responses and transport failures throw exceptions instead. The caller decides
  how to report unavailability; no retry or synthetic fallback is added.
- Source inspection sends `expected_hash`. HTTP 409/404 stay errors. Even on HTTP
  200, the adapter compares the requested hash, returned hash and SHA-256 of the full
  returned UTF-8 content. Hash equality identifies a snapshot, not freshness,
  authenticity or answer entailment.
- Each successful JSON response is limited to 128 KiB before parsing, including
  trailing whitespace. Declared excess is rejected before reading; unknown lengths
  read at most cap+1 bytes. A body shorter than its declared length is rejected,
  even if the partial JSON parses. Compression and redirects are rejected. The bounded
  buffer does not bound socket buffers, parser copies or aggregate process memory.
- The example uses `SimpleClientHttpRequestFactory` with a one-second connect
  timeout and two-second read inactivity timeout. A continuously progressing reply
  can exceed two seconds overall. These are illustrative settings, not a total
  deadline, load measurement or service objective. There is no concurrency limit,
  circuit breaker, distributed tracing or provider generation path in this example.

Using a synchronous client keeps this one-call integration small, but blocks its
calling thread. A server adopting it must separately budget worker concurrency and
request lifetime. Error response bodies are not copied into exceptions or logs.
The adapter closes the network stream before Spring performs response cleanup;
otherwise Spring's close operation can drain the unread body after a rejection.
Empty error responses still preserve their HTTP status. See the
[held-response regression evidence](#response-cleanup-verification--october-27-2026).

## Checks

```sh
# Sixteen loopback HTTP/configuration executions; two live cases are explicitly skipped.
mvn -f examples/spring-client/pom.xml verify

# Owns a Uvicorn process, runs all eighteen Java executions, then the executable JAR.
python scripts/check_spring_client.py
```

The original seven fixture cases cover request serialization, abstention, Unicode source
hashes, changed content, HTTP errors/redirects without retry, exact/over-limit fixed
and chunked replies, malformed/inconsistent/encoded responses, stalled headers/body
and configuration bounds. Fixtures use synthetic JSON and local sockets. The two
live cases check source lines/hashes against the actual Python response, stale-source
409, unrelated-query abstention and invalid-query 422. They do not score new model
data or establish production interoperability.

CI has a separate `spring-client` job. The ordinary Python/frontend/container/browser
and audit jobs remain separate checks. Existing image/npm audits do not inventory
the example's Java JAR; it now has a separate [packaged-library audit](java-audit.md).

On October 17, [run 39012541145](https://github.com/harshaattili-human/runbookops/actions/runs/39012541145),
job `117337935353`, passed all nine Java cases with zero failures/errors/skips and
the executable walkthrough at commit `9158ab72c2bd78afd695ba9a4e3f31cc0c0e7005`.
The JAR returned an extractive database result and verified `database-pool` lines
5–7. Environment: Maven 3.10.0, Temurin Java 17.0.20.1, Spring Boot 3.5.16,
Python 3.12.15 on the Linux amd64 hosted runner. These are contract/packaging checks,
not new model-quality results.

The initial [run 39012419360](https://github.com/harshaattili-human/runbookops/actions/runs/39012419360)
passed all nine tests but its executable JAR exited with status 1. Inspection found
that the application class and runner bean were both named `walkthrough`; the runner
now has a distinct bean name. The initial subprocess wrapper did not print captured
startup diagnostics on failure, so that run did not retain the underlying exception.
It now prints stdout/stderr before checking exit status. No test or launch step was
skipped to obtain the passing result.

Local checks passed 120 Python cases, seven component cases, validation commands,
the frontend build, runner syntax/XML, documentation links and whitespace. Maven's
parent POM was not cached locally, so Java/live-integration execution was hosted.
No Python model/data/threshold changed and no exposed holdout was rescored.
The final documentation-head checks are linked in [PR 17](https://github.com/harshaattili-human/runbookops/pull/17).

References: [Spring REST clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html),
[request factory timeouts](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/http/client/SimpleClientHttpRequestFactory.html).

Interview exercise: why must a caller distinguish an answerability abstention from
an unavailable service, and why does a read inactivity timeout not bound total time?

## Response cleanup verification — October 27, 2026

Six added fixtures hold open an HTTP error, redirect, encoded response, non-JSON
response, declared oversized response or chunked oversized response. With a
five-second configured read timeout, each requires rejection within a one-second
outer guard after the endpoint signals entry, while the server's release latch
remains closed; the same client then recovers. Request counts detect retry/follow.
These are lifecycle assertions, not a one-second production latency promise.

Test-only commit `0fbe7bcb21eafdb5af6f4086278f1f9e65ae645d` reproduced all six
cleanup stalls in [run 40573472283](https://github.com/harshaattili-human/runbookops/actions/runs/40573472283),
job `122433545617`: nine existing cases passed and six new cases timed out. Spring
6.2's response close drains the unread stream. Explicit stream closure before
that cleanup made all 15 cases pass at `2e7c8b58a51b88663de518ef11f53e7072ded807`
in run `40573718317`, job `122434427877`.

The refinement `adb84763827f81599098e6d6ea513a3e86c25b19` also checks empty 404/500
status preservation and a raw-socket source reply that contains valid JSON but
ends before its declared length. In [run 40574314854](https://github.com/harshaattili-human/runbookops/actions/runs/40574314854),
job `122436512284`, all 18 Java executions passed with zero failures/errors/skips,
the live FastAPI executable walkthrough passed, and the packaged audit inventoried
26 libraries with zero advisory entries in that dated snapshot. This is not a
vulnerability-free claim. The final full-job results are linked in
[PR 32](https://github.com/harshaattili-human/runbookops/pull/32).

The byte/inactivity policies remain distinct from a total request deadline. Stream
closure is not proof of remote computation cancellation or a hard memory bound.
No Python model, corpus, thresholds or exposed evaluation data changed. Java and
live integration ran on hosted CI because the local parent POM is uncached;
local whitespace and documentation links passed.

Optional exercise: how can a callback reject before parsing yet the framework
continue reading, and why must a valid JSON prefix still fail when the response
promises more bytes than it delivers?
