package dev.harshaattili.runbookclient;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.web.client.ResourceAccessException;

@Timeout(10)
class RunbookClientTest {
    static final String CONTENT = "# Database\n\nCheck the pool — café.\n";
    static final String HASH = RunbookClient.hash(CONTENT);
    static final RunbookClient.Source SOURCE = new RunbookClient.Source("database:3", "database", HASH,
            3, 3, "Check the pool — café.");
    static final String ABSTAINED = """
            {"request_id":"abc123","mode":"abstained","answer":"Add context",
             "citations":[],"sources":[],"routing":{"category":"needs-review","needs_review":true}}
            """;
    HttpServer server;
    ExecutorService executor;
    RunbookClient client;
    final AtomicInteger calls = new AtomicInteger();
    final AtomicReference<String> body = new AtomicReference<>();
    final AtomicReference<String> target = new AtomicReference<>();
    final AtomicReference<Exception> fixtureFailure = new AtomicReference<>();
    Handler handler;

    @FunctionalInterface interface Handler { void handle(HttpExchange exchange) throws Exception; }

    @BeforeEach void start() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        executor = Executors.newCachedThreadPool();
        server.setExecutor(executor);
        server.createContext("/", exchange -> {
            calls.incrementAndGet();
            body.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            target.set(exchange.getRequestURI().toString());
            try { handler.handle(exchange); }
            catch (IOException ignored) { /* A rejected/timed-out client may close its socket. */ }
            catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); }
            catch (Exception unexpected) { fixtureFailure.set(unexpected); }
            finally { exchange.close(); }
        });
        server.start();
        client = new RunbookClient(origin(), 500, 200);
    }

    @AfterEach void stop() throws InterruptedException {
        server.stop(0);
        executor.shutdownNow();
        assertTrue(executor.awaitTermination(3, TimeUnit.SECONDS));
        assertNull(fixtureFailure.get());
    }

    URI origin() { return URI.create("http://127.0.0.1:" + server.getAddress().getPort()); }

    static void reply(HttpExchange exchange, int status, byte[] bytes, boolean chunked) throws IOException {
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, chunked ? 0 : bytes.length);
        exchange.getResponseBody().write(bytes);
    }

    void json(String value) { handler = e -> reply(e, 200, value.getBytes(StandardCharsets.UTF_8), false); }

    @Test void preservesAbstentionAndSendsExtractiveRequest() throws Exception {
        json(ABSTAINED);
        var result = client.triage("Synthetic unrelated question");
        assertEquals("abc123", result.requestId());
        assertEquals("abstained", result.mode());
        assertTrue(result.sources().isEmpty());
        var sent = new ObjectMapper().readTree(body.get());
        assertEquals("Synthetic unrelated question", sent.get("query").textValue());
        assertFalse(sent.get("use_llm").booleanValue());
        assertEquals(1, calls.get());
    }

    @Test void pinsAndRecomputesUnicodeDocumentHash() throws Exception {
        json(new ObjectMapper().writeValueAsString(Map.of("id", "database", "content", CONTENT, "content_hash", HASH)));
        assertEquals(CONTENT, client.inspect(SOURCE).content());
        assertEquals("/api/runbooks/database?expected_hash=" + HASH, target.get());
        json(new ObjectMapper().writeValueAsString(Map.of("id", "database", "content", CONTENT + "changed", "content_hash", HASH)));
        assertThrows(RunbookClient.ClientFailure.class, () -> client.inspect(SOURCE));
    }

    @Test void rejectsHttpErrorsAndRedirectWithoutRetryOrFollowing() {
        for (int status : new int[]{307, 404, 409, 422, 429, 500}) {
            int before = calls.get();
            handler = e -> {
                e.getResponseHeaders().set("Location", origin() + "/should-not-follow");
                reply(e, status, "{}".getBytes(StandardCharsets.UTF_8), false);
            };
            var error = assertThrows(RunbookClient.ClientFailure.class, () -> client.inspect(SOURCE));
            assertEquals(status, error.status());
            assertEquals(before + 1, calls.get());
        }
    }

    @Test void boundsFixedAndChunkedResponsesIncludingWhitespace() {
        for (boolean chunked : new boolean[]{false, true}) {
            for (int size : new int[]{RunbookClient.MAX_RESPONSE_BYTES, RunbookClient.MAX_RESPONSE_BYTES + 1}) {
                byte[] bytes = (ABSTAINED + " ".repeat(size - ABSTAINED.getBytes(StandardCharsets.UTF_8).length))
                        .getBytes(StandardCharsets.UTF_8);
                handler = e -> reply(e, 200, bytes, chunked);
                if (size == RunbookClient.MAX_RESPONSE_BYTES) assertEquals("abstained", client.triage("Synthetic query").mode());
                else assertThrows(RunbookClient.ClientFailure.class, () -> client.triage("Synthetic query"));
            }
        }
    }

    @Test void rejectsEncodingNonJsonIncompleteAndInconsistentSuccess() {
        for (String invalid : new String[]{"not json", "{}", ABSTAINED + "{}",
                ABSTAINED.replace("abstained", "future-mode"),
                ABSTAINED.replace("\"citations\":[]", "\"citations\":[\"invented\"]")}) {
            json(invalid);
            assertThrows(RuntimeException.class, () -> client.triage("Synthetic query"));
        }
        handler = e -> {
            e.getResponseHeaders().set("Content-Encoding", "gzip");
            reply(e, 200, ABSTAINED.getBytes(StandardCharsets.UTF_8), false);
        };
        assertThrows(RunbookClient.ClientFailure.class, () -> client.triage("Synthetic query"));
        handler = e -> { e.sendResponseHeaders(200, 2); e.getResponseBody().write("{}".getBytes(StandardCharsets.UTF_8)); };
        assertThrows(RunbookClient.ClientFailure.class, () -> client.triage("Synthetic query"));
    }

    @Test void readTimeoutCoversStalledHeadersAndStalledBodyWithoutRetry() throws Exception {
        for (boolean sendHeaders : new boolean[]{false, true}) {
            var entered = new CountDownLatch(1);
            var release = new CountDownLatch(1);
            int before = calls.get();
            handler = e -> {
                if (sendHeaders) {
                    e.getResponseHeaders().set("Content-Type", "application/json");
                    e.sendResponseHeaders(200, 20);
                    e.getResponseBody().write('{');
                    e.getResponseBody().flush();
                }
                entered.countDown();
                release.await(3, TimeUnit.SECONDS);
            };
            try {
                assertThrows(ResourceAccessException.class, () -> client.triage("Synthetic query"));
                assertTrue(entered.await(1, TimeUnit.SECONDS));
                assertEquals(before + 1, calls.get());
            } finally { release.countDown(); }
        }
    }

    @ParameterizedTest
    @ValueSource(strings = {"error", "redirect", "encoding", "type", "declared", "chunked"})
    void rejectsWithoutDrainingAHeldResponse(String kind) throws Exception {
        client = new RunbookClient(origin(), 500, 5_000);
        var entered = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        handler = e -> {
            e.getResponseHeaders().set("Content-Type", kind.equals("type") ? "text/plain" : "application/json");
            if (kind.equals("encoding")) e.getResponseHeaders().set("Content-Encoding", "gzip");
            if (kind.equals("redirect")) e.getResponseHeaders().set("Location", origin() + "/never-follow");
            int status = kind.equals("error") ? 500 : kind.equals("redirect") ? 307 : 200;
            e.sendResponseHeaders(status, kind.equals("chunked") ? 0 : RunbookClient.MAX_RESPONSE_BYTES + 1L);
            if (kind.equals("chunked")) e.getResponseBody().write(new byte[RunbookClient.MAX_RESPONSE_BYTES + 1]);
            else e.getResponseBody().write(' ');
            e.getResponseBody().flush();
            entered.countDown();
            release.await(4, TimeUnit.SECONDS);
        };
        try {
            var result = executor.submit(() -> {
                try {
                    if (kind.equals("error") || kind.equals("redirect")) client.inspect(SOURCE);
                    else client.triage("Synthetic query");
                    return null;
                } catch (RunbookClient.ClientFailure rejected) { return rejected; }
            });
            assertTrue(entered.await(2, TimeUnit.SECONDS));
            assertNotNull(result.get(1, TimeUnit.SECONDS));
            assertEquals(1, release.getCount(), "Reject while the endpoint still holds its response open");
            assertEquals(1, calls.get(), "No follow or automatic retry");
        } finally { release.countDown(); }
        json(ABSTAINED);
        assertEquals("abstained", client.triage("Synthetic recovery").mode());
    }

    @Test void rejectsUnsafeOriginAndUnboundedTimeoutConfiguration() {
        for (String invalid : new String[]{"/relative", "file:///tmp/x", "http://user:pass@localhost", "http://localhost/api", "http://localhost?q=x"}) {
            assertThrows(IllegalArgumentException.class, () -> new RunbookClient(URI.create(invalid), 500, 500));
        }
        assertThrows(IllegalArgumentException.class, () -> new RunbookClient(origin(), 0, 500));
        assertThrows(IllegalArgumentException.class, () -> new RunbookClient(origin(), 500, 60_001));
    }
}
