package com.droneplatform.customer;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.transaction.Transactional;
import jakarta.ws.rs.NotFoundException;
import jakarta.ws.rs.core.Response;
import java.util.List;
import java.util.Map;

@ApplicationScoped
public class CustomerService {

    @Transactional
    public CustomerEntity register(CustomerRequest req) {
        if (CustomerEntity.findByCustomerId(req.customerId()) != null) {
            throw new jakarta.ws.rs.WebApplicationException(
                Response.status(409).entity(Map.of("message", "顧客IDが既に存在します: " + req.customerId())).build()
            );
        }

        var entity = new CustomerEntity();
        entity.customerId = req.customerId();
        entity.name       = req.name();
        entity.email      = req.email();
        entity.phone      = req.phone() != null ? req.phone() : "";
        entity.address    = req.address() != null ? req.address() : "";
        entity.persist();

        return entity;
    }

    public CustomerEntity findById(String customerId) {
        var entity = CustomerEntity.findByCustomerId(customerId);
        if (entity == null) {
            throw new NotFoundException("顧客が見つかりません: " + customerId);
        }
        return entity;
    }

    @SuppressWarnings("unchecked")
    public List<CustomerEntity> search(String query, String status, int limit) {
        var sb = new StringBuilder("(customerId LIKE :q OR name LIKE :q OR email LIKE :q)");
        var params = new java.util.HashMap<String, Object>();
        params.put("q", "%" + query + "%");

        if (status != null && !status.isBlank()) {
            sb.append(" AND status = :status");
            params.put("status", status);
        }

        return CustomerEntity.find(sb.toString(), params)
            .page(0, Math.min(limit, 100))
            .list();
    }

    @Transactional
    public CustomerEntity update(String customerId, Map<String, String> fields) {
        var entity = findById(customerId);

        if (fields.containsKey("name") && !fields.get("name").isBlank()) {
            entity.name = fields.get("name");
        }
        if (fields.containsKey("email") && !fields.get("email").isBlank()) {
            entity.email = fields.get("email");
        }
        if (fields.containsKey("phone")) {
            entity.phone = fields.get("phone");
        }
        if (fields.containsKey("address")) {
            entity.address = fields.get("address");
        }
        if (fields.containsKey("status") && !fields.get("status").isBlank()) {
            entity.status = fields.get("status");
        }

        return entity;
    }
}
