package com.droneplatform.customer;

import jakarta.validation.constraints.*;

public record CustomerRequest(
    @NotBlank(message = "顧客IDは必須です")
    @Pattern(regexp = "CUST-[A-Z0-9]{8}", message = "顧客IDの形式は CUST-XXXXXXXX です")
    String customerId,

    @NotBlank(message = "氏名は必須です")
    @Size(max = 100, message = "氏名は100文字以内です")
    String name,

    @NotBlank(message = "メールアドレスは必須です")
    @Email(message = "メールアドレスの形式が不正です")
    String email,

    @Size(max = 20)
    String phone,

    @Size(max = 500)
    String address
) {}
