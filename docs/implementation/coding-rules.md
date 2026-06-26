# Coding Rules

## 共通ルール

### 命名規則

| 対象 | 規則 | 例 |
|---|---|---|
| Python モジュール | snake_case | `schema_tools.py` |
| Python クラス | PascalCase | `SchemaAgent` |
| Python 関数 | snake_case | `get_table_schema` |
| Tool 名 | snake_case (動詞_名詞) | `register_customer`, `search_assets` |
| Java クラス | PascalCase | `CustomerResource` |
| Java メソッド | camelCase | `registerCustomer` |
| Kubernetes リソース | kebab-case | `ai-agent-orchestrator` |
| Kafka トピック | kebab-case | `openmetadata-schema-changes` |
| 環境変数 | UPPER_SNAKE_CASE | `OPENMETADATA_HOST` |

### Tool 実装ルール

```python
# ✅ 正しい実装
@tool
def register_customer(
    customer_id: str,
    name: str,
    email: str,
) -> dict:
    """
    顧客を登録します。

    Args:
        customer_id: 顧客 ID (形式: CUST-XXXXXXXX)
        name: 顧客名
        email: メールアドレス

    Returns:
        登録された顧客情報の辞書

    Raises:
        DuplicateCustomerError: customer_id が既に存在する場合
        ValidationError: 入力値が不正な場合
    """
    # 実装
    ...

# ❌ 避けるべき実装
@tool
def register(data):  # 引数が不明確
    """顧客登録"""  # 説明が不十分
    ...
```

### エージェント実装ルール

- システムプロンプトは `prompts/` ディレクトリに外部ファイルとして管理する
- エージェントは自身のドメイン外の操作をしない（Schema Agent はスキーマのみ操作）
- 破壊的操作（DELETE, DROP等）は必ず `requires_approval: True` を設定する
- エラーはすべてログに記録し、ユーザーに分かりやすいメッセージを返す

```python
# ✅ 正しいエラーハンドリング
try:
    result = openmetadata_client.delete_table(fqn)
except OpenMetadataNotFoundError:
    return {"error": f"テーブルが見つかりません: {fqn}", "success": False}
except Exception as e:
    logger.exception(f"テーブル削除中にエラーが発生しました: {fqn}")
    return {"error": "内部エラーが発生しました。管理者に連絡してください。", "success": False}
```

### Quarkus API ルール

- すべての API は `/api/v1/` プレフィックスを使用する
- レスポンスは統一フォーマットを使用する
- バリデーションは Bean Validation アノテーションで行う
- 認証は Keycloak OIDC を必須とする（ヘルスチェックエンドポイントを除く）

```java
// ✅ 統一レスポンスフォーマット
public record ApiResponse<T>(
    boolean success,
    T data,
    String message,
    String requestId
) {}

// ✅ バリデーション
public record CustomerRequest(
    @NotBlank @Pattern(regexp = "CUST-[A-Z0-9]{8}") String customerId,
    @NotBlank @Size(max = 100) String name,
    @NotBlank @Email String email
) {}
```

## Git ルール

- ブランチ名: `feature/`, `fix/`, `docs/`, `chore/` プレフィックス
- コミットメッセージ: Conventional Commits 形式
  - `feat: Schema Agent に lineage 取得機能を追加`
  - `fix: OpenMetadata 接続タイムアウトを修正`
  - `docs: chapter07-openmetadata を追加`
- PR は必ずレビュー 1 名以上の承認を必要とする
- main ブランチへの直接 push 禁止
