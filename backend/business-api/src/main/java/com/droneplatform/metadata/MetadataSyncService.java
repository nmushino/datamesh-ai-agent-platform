package com.droneplatform.metadata;

import io.quarkus.vertx.ConsumeEvent;
import io.smallrye.mutiny.Uni;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import org.eclipse.microprofile.config.inject.ConfigProperty;
import org.eclipse.microprofile.rest.client.inject.RestClient;
import org.jboss.logging.Logger;
import java.time.Instant;
import java.util.Map;

@ApplicationScoped
public class MetadataSyncService {

    private static final Logger log = Logger.getLogger(MetadataSyncService.class);

    private static final String CUSTOMERS_TABLE_FQN =
        "postgresql-prod.dronedb.public.customers";

    @Inject
    @RestClient
    OpenMetadataClient openMetadataClient;

    @ConfigProperty(name = "openmetadata.jwt-token")
    String jwtToken;

    public void syncCustomerMetadataAsync() {
        // 非同期実行（ビジネス処理を止めない）
        Uni.createFrom().item(this::syncCustomerMetadata)
            .runSubscriptionOn(io.smallrye.mutiny.infrastructure.Infrastructure.getDefaultExecutor())
            .subscribe().with(
                result -> log.debugf("Metadata sync completed: %s", result),
                error  -> log.warnf("Metadata sync failed: %s", error.getMessage())
            );
    }

    private Map<String, Object> syncCustomerMetadata() {
        try {
            var patch = Map.<String, Object>of(
                "description", "顧客マスタデータ。顧客 ID・氏名・連絡先を管理する。",
                "tags", java.util.List.of(
                    Map.of("tagFQN", "PII"),
                    Map.of("tagFQN", "Customer")
                ),
                "customMetrics", java.util.List.of(
                    Map.of("name", "lastSyncAt", "value", Instant.now().toString())
                )
            );
            return openMetadataClient.patchTable(CUSTOMERS_TABLE_FQN, patch);
        } catch (Exception e) {
            log.warnf("OpenMetadata sync skipped: %s", e.getMessage());
            return Map.of("skipped", true);
        }
    }
}
