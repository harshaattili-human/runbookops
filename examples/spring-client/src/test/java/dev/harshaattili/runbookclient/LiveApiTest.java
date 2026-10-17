package dev.harshaattili.runbookclient;

import static org.junit.jupiter.api.Assertions.*;

import java.net.URI;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;

@EnabledIfSystemProperty(named = "runbook.live-url", matches = "http://127\\.0\\.0\\.1:[0-9]+")
class LiveApiTest {
    final RunbookClient client = new RunbookClient(URI.create(System.getProperty("runbook.live-url")), 1_000, 2_000);

    @Test void supportedTriageAndVersionedSourceMatchTheLivePythonContract() {
        var result = client.triage("Database connection pool is exhausted and requests wait for connections.");
        assertEquals("extractive", result.mode());
        assertFalse(result.requestId().isBlank());
        assertFalse(result.citations().isEmpty());
        for (var source : result.sources()) {
            var document = client.inspect(source);
            var lines = document.content().split("\n", -1);
            String passage = String.join("\n", java.util.Arrays.copyOfRange(lines, source.startLine() - 1, source.endLine())).strip();
            assertEquals(source.text(), passage);
        }
        var source = result.sources().get(0);
        var stale = new RunbookClient.Source(source.id(), source.document(), "0".repeat(64), source.startLine(), source.endLine(), source.text());
        assertEquals(409, assertThrows(RunbookClient.ClientFailure.class, () -> client.inspect(stale)).status());
    }

    @Test void abstentionAndValidationAreDifferentOutcomes() {
        var result = client.triage("How do I bake a chocolate cake for a birthday party?");
        assertEquals("abstained", result.mode());
        assertTrue(result.routing().needsReview());
        assertTrue(result.sources().isEmpty());
        assertEquals(422, assertThrows(RunbookClient.ClientFailure.class, () -> client.triage("short")).status());
    }
}
