package dev.harshaattili.runbookclient;

import java.net.URI;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class Walkthrough {
    public static void main(String[] args) {
        var app = new SpringApplication(Walkthrough.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args).close();
    }

    @Bean RunbookClient runbookClient(@Value("${runbook.base-url:http://127.0.0.1:8000}") URI base) {
        return new RunbookClient(base, 1_000, 2_000);
    }

    @Bean CommandLineRunner syntheticIncident(RunbookClient client) {
        return args -> {
            // Authored synthetic incident; avoid putting operational text in command arguments/logs.
            var result = client.triage("Database connection pool is exhausted and requests wait for connections.");
            System.out.printf("request_id=%s mode=%s category=%s needs_review=%s%n", result.requestId(),
                    result.mode(), result.routing().category(), result.routing().needsReview());
            if (!result.sources().isEmpty()) {
                var source = result.sources().get(0);
                client.inspect(source);
                System.out.printf("source=%s lines=%d-%d version_verified=true%n",
                        source.document(), source.startLine(), source.endLine());
            }
        };
    }
}
