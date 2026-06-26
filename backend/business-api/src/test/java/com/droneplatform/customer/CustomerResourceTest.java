package com.droneplatform.customer;

import io.quarkus.test.junit.QuarkusTest;
import io.restassured.http.ContentType;
import org.junit.jupiter.api.Test;

import static io.restassured.RestAssured.given;
import static org.hamcrest.Matchers.*;

@QuarkusTest
class CustomerResourceTest {

    @Test
    void testRegisterCustomer() {
        given()
            .contentType(ContentType.JSON)
            .body("""
                {
                  "customerId": "CUST-ABCD1234",
                  "name": "山田太郎",
                  "email": "yamada@example.com"
                }
                """)
        .when()
            .post("/api/v1/customers")
        .then()
            .statusCode(201)
            .body("customerId", equalTo("CUST-ABCD1234"))
            .body("name", equalTo("山田太郎"))
            .body("status", equalTo("active"));
    }

    @Test
    void testRegisterCustomer_DuplicateId() {
        // 1回目
        given().contentType(ContentType.JSON)
            .body("""
                {"customerId":"CUST-DUPL0001","name":"Test","email":"dup1@example.com"}
                """)
            .post("/api/v1/customers").then().statusCode(201);

        // 2回目（重複）
        given().contentType(ContentType.JSON)
            .body("""
                {"customerId":"CUST-DUPL0001","name":"Test2","email":"dup2@example.com"}
                """)
            .post("/api/v1/customers")
        .then()
            .statusCode(409);
    }

    @Test
    void testRegisterCustomer_InvalidId() {
        given()
            .contentType(ContentType.JSON)
            .body("""
                {"customerId":"INVALID","name":"Test","email":"test@example.com"}
                """)
        .when()
            .post("/api/v1/customers")
        .then()
            .statusCode(400);
    }

    @Test
    void testGetCustomer_NotFound() {
        given()
        .when()
            .get("/api/v1/customers/CUST-NOTEXIST")
        .then()
            .statusCode(404);
    }

    @Test
    void testSearchCustomers() {
        given().contentType(ContentType.JSON)
            .body("""
                {"customerId":"CUST-SRCH0001","name":"検索テスト","email":"search@example.com"}
                """)
            .post("/api/v1/customers");

        given()
            .queryParam("q", "検索テスト")
        .when()
            .get("/api/v1/customers/search")
        .then()
            .statusCode(200)
            .body("customers", hasSize(greaterThanOrEqualTo(1)))
            .body("customers[0].name", equalTo("検索テスト"));
    }
}
