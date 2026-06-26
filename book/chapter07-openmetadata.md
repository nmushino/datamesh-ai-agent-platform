# Chapter 7: OpenMetadata 統合

## OpenMetadata の役割

本プラットフォームにおける OpenMetadata は **データ資産の単一情報源 (Single Source of Truth)** です。

```
┌─────────────────────────────────────────┐
│           OpenMetadata                  │
│                                         │
│  ┌─────────┐  ┌─────────┐  ┌────────┐  │
│  │ Tables  │  │ Topics  │  │  APIs  │  │
│  └─────────┘  └─────────┘  └────────┘  │
│                                         │
│  ┌─────────┐  ┌─────────┐  ┌────────┐  │
│  │Lineage  │  │ Quality │  │ Glossary│  │
│  └─────────┘  └─────────┘  └────────┘  │
└─────────────────────────────────────────┘
        ▲               ▲
        │               │
  AI Agent          Quarkus API
  (自動登録)         (ビジネスAPI経由)
```

## OpenShift へのデプロイ

```yaml
# deployment/openshift/openmetadata.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: openmetadata
  namespace: ai-agent-platform
spec:
  replicas: 1
  selector:
    matchLabels:
      app: openmetadata
  template:
    metadata:
      labels:
        app: openmetadata
    spec:
      containers:
      - name: openmetadata
        image: docker.getcollate.io/openmetadata/server:1.3.0
        ports:
        - containerPort: 8585
        env:
        - name: OPENMETADATA_CLUSTER_NAME
          value: "enterprise-ai-agent"
        - name: DB_HOST
          valueFrom:
            secretKeyRef:
              name: openmetadata-db-secret
              key: host
        - name: DB_USER_NAME
          valueFrom:
            secretKeyRef:
              name: openmetadata-db-secret
              key: username
        - name: DB_USER_PASSWORD
          valueFrom:
            secretKeyRef:
              name: openmetadata-db-secret
              key: password
        - name: AIRFLOW_HOST
          value: "http://airflow:8080"
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
```

## OpenMetadata Python クライアント

```python
# backend/openmetadata-client/src/client.py

from metadata.ingestion.ometa.ometa_api import OpenMetadata
from metadata.generated.schema.entity.services.connections.metadata.openMetadataConnection import (
    OpenMetadataConnection,
    AuthProvider,
)
from metadata.generated.schema.security.client.openMetadataJWTClientConfig import (
    OpenMetadataJWTClientConfig,
)

class OpenMetadataClientWrapper:
    def __init__(self, host: str, jwt_token: str):
        server_config = OpenMetadataConnection(
            hostPort=host,
            authProvider=AuthProvider.openmetadata,
            securityConfig=OpenMetadataJWTClientConfig(jwtToken=jwt_token),
        )
        self.client = OpenMetadata(server_config)

    def get_table(self, fqn: str) -> dict:
        from metadata.generated.schema.entity.data.table import Table
        table = self.client.get_by_name(entity=Table, fqn=fqn)
        return table.dict() if table else None

    def search_assets(self, query: str, asset_type: str = "all", limit: int = 10) -> list:
        results = self.client.es_search_from_fqn(
            entity_type=asset_type,
            fqn_search_string=query,
            size=limit,
        )
        return [r.dict() for r in results]

    def create_or_update_table(self, table_request: dict) -> dict:
        from metadata.generated.schema.api.data.createTable import CreateTableRequest
        request = CreateTableRequest(**table_request)
        result = self.client.create_or_update(data=request)
        return result.dict()
```

## Kafka 連携トピック

OpenMetadata の変更イベントは Kafka に発行します。

```yaml
# deployment/openshift/kafka-topics.yaml
topics:
  - name: openmetadata-schema-changes
    partitions: 3
    replicationFactor: 3
    config:
      retention.ms: "604800000"  # 7日

  - name: openmetadata-quality-alerts
    partitions: 3
    replicationFactor: 3

  - name: agent-approval-requests
    partitions: 1
    replicationFactor: 3
```

## メタデータ品質ルール

```python
# tools/openmetadata/quality_tools.py

@tool
def create_quality_rule(
    table_fqn: str,
    column_name: str,
    rule_type: str,
    params: dict
) -> dict:
    """
    データ品質ルールを作成します。

    rule_type の例:
      - "columnNotNull": NULL 禁止
      - "columnValuesToBeUnique": ユニーク制約
      - "columnValuesToBeBetween": 範囲チェック
      - "columnValuesToMatchRegex": 正規表現チェック
    """
    test_case = {
        "name": f"{table_fqn}.{column_name}.{rule_type}",
        "entityLink": f"<#E::table::{table_fqn}::columns::{column_name}>",
        "testDefinition": rule_type,
        "parameterValues": [
            {"name": k, "value": str(v)} for k, v in params.items()
        ],
    }
    return openmetadata_client.create_test_case(test_case)
```
