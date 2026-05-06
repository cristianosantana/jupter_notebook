from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class McpGrpcServerSettings(BaseSettings):
    """Configuração do processo `orion-mcp-server` (gRPC). Prefixo ORION_."""

    model_config = SettingsConfigDict(env_prefix="ORION_", env_file=".env", extra="ignore")

    mcp_server_grpc_host: str = Field(default="0.0.0.0")
    mcp_server_grpc_port: int = Field(default=50051, ge=1, le=65535)
    mcp_mysql_url: str | None = Field(
        default=None,
        description="MySQL só no serviço MCP (mysql:// ou mysql+asyncmy://). Opcional em dev/CI.",
    )
    mcp_mysql_pool_minsize: int = Field(default=5, ge=1, le=100)
    mcp_mysql_pool_maxsize: int = Field(default=20, ge=1, le=200)
    mcp_redis_url: str | None = Field(
        default=None,
        description="Redis L2; se vazio, usa ORION_REDIS_URL.",
    )
    mcp_l2_cache_ttl_seconds: int = Field(default=300, ge=1, le=86400)
    mcp_query_concurrency: int = Field(default=50, ge=1, le=5000)
    mcp_http_gateway_enabled: bool = Field(default=False)
    mcp_http_gateway_host: str = Field(default="0.0.0.0")
    mcp_http_gateway_port: int = Field(default=5050, ge=1, le=65535)
    redis_url: str | None = Field(default=None, description="Fallback L2 se mcp_redis_url vazio.")
    tool_llm_preview_rows: int = Field(
        default=10,
        ge=1,
        le=10000,
        description=(
            "Com summarize=true em run_domain_query, número máx. de linhas em rows_sample "
            "(mesmo env ORION_TOOL_LLM_PREVIEW_ROWS que a API usa no DataInterpreter)."
        ),
    )

    def effective_redis_url(self) -> str | None:
        return (self.mcp_redis_url or self.redis_url or "").strip() or None
