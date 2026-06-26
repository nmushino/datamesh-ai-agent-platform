package com.droneplatform.customer;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "customers")
public class CustomerEntity extends PanacheEntityBase {

    @Id
    @Column(name = "customer_id", nullable = false, unique = true, length = 20)
    public String customerId;

    @Column(nullable = false, length = 100)
    public String name;

    @Column(nullable = false, unique = true, length = 200)
    public String email;

    @Column(length = 20)
    public String phone;

    @Column(length = 500)
    public String address;

    @Column(nullable = false, length = 20)
    public String status = "active";

    @Column(name = "created_at", nullable = false, updatable = false)
    public Instant createdAt = Instant.now();

    @Column(name = "updated_at", nullable = false)
    public Instant updatedAt = Instant.now();

    @PreUpdate
    void onUpdate() {
        updatedAt = Instant.now();
    }

    // --- Panache 静的ファインダー ---

    public static CustomerEntity findByCustomerId(String customerId) {
        return find("customerId", customerId).firstResult();
    }

    public static CustomerEntity findByEmail(String email) {
        return find("email", email).firstResult();
    }
}
