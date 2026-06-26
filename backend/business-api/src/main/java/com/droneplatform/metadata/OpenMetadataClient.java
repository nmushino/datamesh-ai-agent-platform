package com.droneplatform.metadata;

import jakarta.ws.rs.*;
import jakarta.ws.rs.core.MediaType;
import org.eclipse.microprofile.rest.client.inject.RegisterRestClient;
import java.util.Map;

@RegisterRestClient(configKey = "openmetadata")
@Path("/api/v1")
@Produces(MediaType.APPLICATION_JSON)
@Consumes(MediaType.APPLICATION_JSON)
public interface OpenMetadataClient {

    @GET
    @Path("/tables/name/{fqn}")
    Map<String, Object> getTable(@PathParam("fqn") String fqn);

    @PATCH
    @Path("/tables/name/{fqn}")
    Map<String, Object> patchTable(
        @PathParam("fqn") String fqn,
        Map<String, Object> patch
    );

    @GET
    @Path("/system/status")
    Map<String, Object> getStatus();
}
