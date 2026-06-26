package com.droneplatform.kafka;

import com.droneplatform.customer.CustomerEntity;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.smallrye.reactive.messaging.annotations.Broadcast;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import org.eclipse.microprofile.reactive.messaging.Channel;
import org.eclipse.microprofile.reactive.messaging.Emitter;
import org.jboss.logging.Logger;
import java.time.Instant;
import java.util.Map;

@ApplicationScoped
public class AgentEventProducer {

    private static final Logger log = Logger.getLogger(AgentEventProducer.class);

    @Inject
    @Channel("customer-events")
    Emitter<String> customerEmitter;

    @Inject
    ObjectMapper objectMapper;

    public void sendCustomerEvent(String eventType, CustomerEntity customer) {
        try {
            var event = Map.of(
                "specversion", "1.0",
                "type", "com.droneplatform.customer." + eventType,
                "source", "/api/v1/customers",
                "time", Instant.now().toString(),
                "data", Map.of(
                    "customerId", customer.customerId,
                    "name", customer.name,
                    "email", customer.email,
                    "status", customer.status
                )
            );
            customerEmitter.send(objectMapper.writeValueAsString(event));
        } catch (Exception e) {
            log.warnf("Failed to send customer event: %s", e.getMessage());
        }
    }
}
