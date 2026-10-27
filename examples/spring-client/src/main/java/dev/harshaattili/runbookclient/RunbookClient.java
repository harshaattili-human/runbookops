package dev.harshaattili.runbookclient;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

/** Small synchronous adapter for extractive triage and versioned source inspection. */
public final class RunbookClient {
    static final int MAX_RESPONSE_BYTES = 131_072;
    private final RestClient http;
    private final ObjectMapper json = new ObjectMapper()
            .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

    public RunbookClient(URI base, int connectMillis, int readMillis) {
        if (!("http".equals(base.getScheme()) || "https".equals(base.getScheme())) || base.getHost() == null
                || base.getUserInfo() != null || base.getQuery() != null || base.getFragment() != null
                || !(base.getPath().isEmpty() || base.getPath().equals("/"))) {
            throw new IllegalArgumentException("Configure an HTTP origin without credentials, path or query");
        }
        if (connectMillis < 1 || connectMillis > 60_000 || readMillis < 1 || readMillis > 60_000) {
            throw new IllegalArgumentException("Timeouts must be 1..60000 milliseconds");
        }
        var factory = new SimpleClientHttpRequestFactory() {
            @Override protected void prepareConnection(HttpURLConnection connection, String method)
                    throws IOException {
                super.prepareConnection(connection, method);
                connection.setInstanceFollowRedirects(false);
            }
        };
        factory.setConnectTimeout(connectMillis);
        factory.setReadTimeout(readMillis);
        http = RestClient.builder().baseUrl(base.toString()).requestFactory(factory)
                .defaultHeader("Accept-Encoding", "identity").build();
    }

    public TriageResult triage(String query) {
        TriageResult result = http.post().uri("/api/triage").contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("query", query, "use_llm", false))
                .exchange((request, response) -> decode(response, TriageResult.class));
        require(result != null && result.requestId() != null && !result.requestId().isBlank()
                && result.answer() != null && result.mode() != null && result.routing() != null
                && result.routing().category() != null && result.routing().needsReview() != null
                && result.citations() != null && result.sources() != null, "Incomplete triage response");
        if (result.mode().equals("abstained")) {
            require(result.citations().isEmpty() && result.sources().isEmpty()
                    && result.routing().needsReview(), "Inconsistent abstention");
        } else {
            require(result.mode().equals("extractive") && !result.sources().isEmpty()
                    && !result.citations().isEmpty(), "Unexpected answer mode");
            result.sources().forEach(RunbookClient::validateSource);
            require(result.citations().stream().allMatch(id -> id != null
                    && result.sources().stream().anyMatch(source -> id.equals(source.id()))),
                    "Citation is absent from the returned evidence");
        }
        return result;
    }

    public Document inspect(Source source) {
        validateSource(source);
        Document document = http.get().uri(builder -> builder.path("/api/runbooks/{slug}")
                .queryParam("expected_hash", source.documentHash()).build(source.document()))
                .exchange((request, response) -> decode(response, Document.class));
        require(document != null && source.document().equals(document.id()) && document.content() != null
                && source.documentHash().equals(document.contentHash())
                && source.documentHash().equals(hash(document.content())), "Source version mismatch");
        return document;
    }

    private <T> T decode(ClientHttpResponse response, Class<T> type) throws IOException {
        int status = response.getStatusCode().value();
        // Close the live stream before RestClient attempts its response-close drain.
        try (var input = response.getBody()) {
            // Do not buffer error pages or turn an unavailable backend into abstention.
            if (status != 200) throw new ClientFailure("RunbookOps returned HTTP " + status, status);
            String encoding = response.getHeaders().getFirst("Content-Encoding");
            require(encoding == null || encoding.equalsIgnoreCase("identity"), "Encoded response rejected");
            MediaType contentType = response.getHeaders().getContentType();
            require(contentType != null && MediaType.APPLICATION_JSON.isCompatibleWith(contentType),
                    "Expected a JSON response");
            long declared = response.getHeaders().getContentLength();
            require(declared <= MAX_RESPONSE_BYTES, "Response exceeds byte limit");
            byte[] body = input.readNBytes(MAX_RESPONSE_BYTES + 1);
            require(body.length <= MAX_RESPONSE_BYTES, "Response exceeds byte limit");
            require(declared < 0 || body.length == declared, "Response ended before declared length");
            return json.readValue(body, type);
        } catch (IOException failure) {
            // URLConnection can throw while opening an empty error stream. Retain the HTTP status.
            if (status != 200) throw new ClientFailure("RunbookOps returned HTTP " + status, status);
            throw failure;
        }
    }

    private static void validateSource(Source source) {
        require(source != null && source.id() != null && source.document() != null
                && source.document().matches("[a-z0-9][a-z0-9-]{0,80}")
                && source.documentHash() != null && source.documentHash().matches("[a-f0-9]{64}")
                && source.startLine() > 0 && source.endLine() >= source.startLine()
                && source.text() != null, "Invalid source reference");
    }

    static String hash(String text) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(text.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static void require(boolean valid, String reason) {
        if (!valid) throw new ClientFailure(reason, null);
    }

    public static final class ClientFailure extends RuntimeException {
        private final Integer status;
        ClientFailure(String reason, Integer status) { super(reason); this.status = status; }
        public Integer status() { return status; }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record TriageResult(@JsonProperty("request_id") String requestId, String mode, String answer,
            List<String> citations, List<Source> sources, Routing routing) {}
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Routing(String category, @JsonProperty("needs_review") Boolean needsReview) {}
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Source(String id, String document, @JsonProperty("document_hash") String documentHash,
            @JsonProperty("start_line") int startLine, @JsonProperty("end_line") int endLine, String text) {}
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Document(String id, String content, @JsonProperty("content_hash") String contentHash) {}
}
