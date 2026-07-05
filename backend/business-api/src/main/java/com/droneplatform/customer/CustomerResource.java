package com.droneplatform.customer;

import com.droneplatform.kafka.AgentEventProducer;
import com.droneplatform.metadata.MetadataSyncService;
import jakarta.annotation.security.RolesAllowed;
import jakarta.inject.Inject;
import jakarta.validation.Valid;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import org.eclipse.microprofile.openapi.annotations.Operation;
import org.eclipse.microprofile.openapi.annotations.tags.Tag;
import java.util.List;
import java.util.Map;

@Path("/api/v1/customers")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
@Tag(name = "Customer", description = "顧客管理 API")
public class CustomerResource {

    @Inject
    CustomerService customerService;

    @Inject
    MetadataSyncService metadataSync;

    @Inject
    AgentEventProducer eventProducer;

    // NOTE: metadataSync / eventProducer は register()・update() の @Transactional
    // コミット後に呼ぶこと。トランザクション内から呼ぶと、非同期実行スレッドが同じ
    // JTA トランザクションに enlist された DB コネクションへ同時アクセスし、
    // "Enlisted connection used without active transaction" でコミットが失敗する。

    @POST
    @RolesAllowed({"operator", "admin"})
    @Operation(summary = "顧客登録", description = "新規顧客を登録します")
    public Response register(@Valid CustomerRequest req) {
        var entity = customerService.register(req);
        eventProducer.sendCustomerEvent("registered", entity);
        metadataSync.syncCustomerMetadataAsync();
        return Response.status(201).entity(entity).build();
    }

    @GET
    @Path("/{customerId}")
    @RolesAllowed({"viewer", "operator", "admin"})
    @Operation(summary = "顧客取得", description = "顧客 ID で顧客情報を取得します")
    public CustomerEntity getById(@PathParam("customerId") String customerId) {
        return customerService.findById(customerId);
    }

    @GET
    @Path("/search")
    @RolesAllowed({"viewer", "operator", "admin"})
    @Operation(summary = "顧客検索", description = "クエリで顧客を検索します")
    public Map<String, Object> search(
        @QueryParam("q") @DefaultValue("") String query,
        @QueryParam("status") @DefaultValue("") String status,
        @QueryParam("limit") @DefaultValue("20") int limit
    ) {
        List<CustomerEntity> customers = customerService.search(query, status, limit);
        return Map.of(
            "customers", customers,
            "total", customers.size()
        );
    }

    @PATCH
    @Path("/{customerId}")
    @RolesAllowed({"operator", "admin"})
    @Operation(summary = "顧客更新", description = "顧客情報を部分更新します")
    public CustomerEntity update(
        @PathParam("customerId") String customerId,
        Map<String, String> fields
    ) {
        var entity = customerService.update(customerId, fields);
        eventProducer.sendCustomerEvent("updated", entity);
        return entity;
    }
}
