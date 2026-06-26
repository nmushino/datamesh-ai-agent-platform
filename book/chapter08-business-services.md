# Chapter 8: Business Services (Quarkus)

## Quarkus Business API 構成

```
backend/business-api/
├── src/main/java/com/droneplatform/
│   ├── customer/
│   │   ├── CustomerResource.java      (REST エンドポイント)
│   │   ├── CustomerService.java       (ビジネスロジック)
│   │   ├── CustomerRepository.java    (DB アクセス)
│   │   └── CustomerEntity.java        (JPA エンティティ)
│   ├── bom/
│   ├── inventory/
│   ├── metadata/
│   │   └── MetadataSyncService.java   (OpenMetadata 同期)
│   └── kafka/
│       └── AgentEventProducer.java    (Kafka イベント発行)
└── src/main/resources/
    └── application.properties
```

## REST API 設計

### 顧客 API

```java
// backend/business-api/src/main/java/com/droneplatform/customer/CustomerResource.java

@Path("/api/v1/customers")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public class CustomerResource {

    @Inject
    CustomerService customerService;

    @POST
    @Operation(summary = "顧客登録")
    public Response registerCustomer(CustomerRequest request) {
        Customer customer = customerService.register(request);
        return Response.status(201).entity(customer).build();
    }

    @GET
    @Path("/search")
    @Operation(summary = "顧客検索")
    public List<Customer> searchCustomers(
        @QueryParam("q") String query,
        @QueryParam("status") String status,
        @QueryParam("limit") @DefaultValue("20") int limit
    ) {
        return customerService.search(query, status, limit);
    }

    @GET
    @Path("/{customerId}")
    @Operation(summary = "顧客取得")
    public Customer getCustomer(@PathParam("customerId") String customerId) {
        return customerService.findById(customerId)
            .orElseThrow(() -> new NotFoundException("Customer not found: " + customerId));
    }

    @PUT
    @Path("/{customerId}")
    @Operation(summary = "顧客更新")
    public Customer updateCustomer(
        @PathParam("customerId") String customerId,
        CustomerRequest request
    ) {
        return customerService.update(customerId, request);
    }
}
```

### OpenMetadata 同期サービス

```java
// backend/business-api/src/main/java/com/droneplatform/metadata/MetadataSyncService.java

@ApplicationScoped
public class MetadataSyncService {

    @ConfigProperty(name = "openmetadata.host")
    String openMetadataHost;

    @ConfigProperty(name = "openmetadata.jwt-token")
    String jwtToken;

    @Inject
    AgentEventProducer eventProducer;

    // 顧客登録後にOpenMetadataへ同期
    public void syncCustomerMetadata(Customer customer) {
        try {
            // OpenMetadata REST API にメタデータを登録
            var tableUpdate = Map.of(
                "description", "顧客マスタデータ",
                "tags", List.of("Customer", "PII"),
                "customMetrics", Map.of(
                    "lastSyncAt", Instant.now().toString(),
                    "recordCount", getCustomerCount()
                )
            );
            openMetadataClient.patchTable(
                "postgresql-prod.dronedb.public.customers",
                tableUpdate
            );
        } catch (Exception e) {
            // メタデータ同期失敗はビジネス処理を止めない
            log.warnf("OpenMetadata sync failed: %s", e.getMessage());
            eventProducer.sendSyncFailure(customer.id, e.getMessage());
        }
    }
}
```

## Kafka イベント

```java
// backend/business-api/src/main/java/com/droneplatform/kafka/AgentEventProducer.java

@ApplicationScoped
public class AgentEventProducer {

    @Channel("agent-completions")
    Emitter<AgentEvent> completionEmitter;

    @Channel("schema-changes")
    Emitter<SchemaChangeEvent> schemaChangeEmitter;

    @Channel("approval-requests")
    Emitter<ApprovalRequest> approvalEmitter;

    public void sendAgentCompletion(String agentId, String result) {
        completionEmitter.send(AgentEvent.of(agentId, "COMPLETED", result));
    }

    public void sendApprovalRequest(String threadId, String action, String requestor) {
        approvalEmitter.send(ApprovalRequest.of(threadId, action, requestor));
    }
}
```

## application.properties

```properties
# backend/business-api/src/main/resources/application.properties

# DB
quarkus.datasource.db-kind=postgresql
quarkus.datasource.username=${DB_USERNAME}
quarkus.datasource.password=${DB_PASSWORD}
quarkus.datasource.jdbc.url=jdbc:postgresql://${DB_HOST}:5432/${DB_NAME}
quarkus.hibernate-orm.database.generation=validate

# Kafka
kafka.bootstrap.servers=${KAFKA_BOOTSTRAP_SERVERS}
mp.messaging.outgoing.agent-completions.connector=smallrye-kafka
mp.messaging.outgoing.agent-completions.topic=agent-completions
mp.messaging.outgoing.schema-changes.connector=smallrye-kafka
mp.messaging.outgoing.schema-changes.topic=openmetadata-schema-changes

# OpenMetadata
openmetadata.host=${OPENMETADATA_HOST:http://openmetadata:8585}
openmetadata.jwt-token=${OPENMETADATA_JWT_TOKEN}

# Keycloak
quarkus.oidc.auth-server-url=${KEYCLOAK_URL}/realms/${KEYCLOAK_REALM}
quarkus.oidc.client-id=business-api
quarkus.http.auth.permission.authenticated.paths=/api/*
quarkus.http.auth.permission.authenticated.policy=authenticated

# OpenShift
quarkus.kubernetes.deployment-target=openshift
quarkus.openshift.replicas=2
```
