import json
from functools import lru_cache
from uuid import UUID
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict  # pyright: ignore[reportMissingImports]


class Settings(BaseSettings):
    """
    Configuração via variáveis de ambiente (``.env``). Nomes: maiúsculas + underscore,
    ex. ``OPENAI_API_KEY`` → ``openai_api_key``. Ver também ``.env.example``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(
        default="",
        description=(
            "Bearer token OpenAI; usado por OpenAIProvider, arranque MCP (sampling) e orquestrador."
        ),
    )
    openai_model: str = Field(
        default="",
        description=(
            "Modelo por omissão; sobrescrito por ``ORCHESTRATOR_MODEL_*`` quando esse valor não está "
            "vazio (``resolve_orchestrator_model_for_agent``)."
        ),
    )

    mysql_host: str = Field(
        default="localhost",
        description=(
            "Host MySQL; copiado para ``os.environ`` no arranque (``sync_mysql_env_from_settings``) "
            "para o subprocesso MCP e glossário."
        ),
    )
    mysql_port: int = Field(default=3306, description="Porta TCP do MySQL.")
    mysql_user: str = Field(default="", description="Utilizador da ligação MySQL.")
    mysql_password: str = Field(
        default="",
        description="Senha MySQL (analytics MCP + queries do glossário na API).",
    )
    mysql_database: str = Field(default="", description="Nome da base de dados de negócio.")

    postgres_host: str = Field(
        default="",
        description=(
            "Se vazio (junto com user/database necessários), ``postgres_enabled`` é false: "
            "sem persistência de sessões/transcript."
        ),
    )
    postgres_port: int = Field(default=5432, description="Porta do PostgreSQL.")
    postgres_user: str = Field(default="", description="Utilizador da base de sessões.")
    postgres_password: str = Field(default="", description="Senha PostgreSQL.")
    postgres_database: str = Field(
        default="maestro_sessions",
        description="Nome da base onde vivem sessions/messages/metadata.",
    )
    postgres_maintenance_database: str = Field(
        default="postgres",
        description=(
            "Base onde ligar para ``CREATE DATABASE`` quando ``postgres_database`` ainda não existe."
        ),
    )
    postgres_auto_migrate: bool = Field(
        default=True,
        description="Se true, SessionStore corre migrações SQL ao arranque quando PostgreSQL está activo.",
    )

    cors_origins: str = Field(
        default="http://localhost:5173",
        description=(
            "Origens permitidas pelo FastAPI CORSMiddleware, separadas por vírgula "
            "(ex.: frontend Vite em http://localhost:5173)."
        ),
    )

    orchestrator_max_tool_rounds: int = Field(
        default=24,
        description=(
            "Tecto de voltas do loop LLM↔tools no maestro e no especialista; exceder gera erro."
        ),
    )
    orchestrator_max_history_messages: int = Field(
        default=20,
        description=(
            "Após podagem por idade e orçamento, o histórico não excede este número de mensagens."
        ),
    )
    orchestrator_max_message_age_seconds: float = Field(
        default=7200.0,
        description=(
            "Mensagens com timestamp implícito mais antigo que agora−N segundos são removidas "
            "antes de enviar ao modelo."
        ),
    )
    orchestrator_tool_result_preview_max: int = Field(
        default=500,
        description=(
            "Caracteres da prévia do resultado da tool em ``tools_used`` (resposta HTTP / observador); "
            "não o texto completo enviado ao LLM."
        ),
    )
    orchestrator_context_budget_safety_margin: int = Field(
        default=768,
        description=(
            "Caracteres reservados ao lado da estimativa de contexto ao calcular quanto histórico cabe."
        ),
    )
    orchestrator_chars_per_token_estimate: int = Field(
        default=3,
        description=(
            "Divide caracteres para estimar tokens na podagem de contexto (heurística, não tokenizer oficial)."
        ),
    )
    orchestrator_agent_types: str = Field(
        default=(
            "maestro,analise_os,clusterizacao,visualizador,agregador,projecoes,"
            "verificador,compositor_layout"
        ),
        description=(
            "Agentes permitidos em handoff e validação de sessão PostgreSQL; vírgula, sem espaços nos nomes."
        ),
    )
    orchestrator_glossary_cache_anonymous_uuid: str = Field(
        default="00000000-0000-0000-0000-000000000001",
        description=(
            "UUID válido usado como chave do LRU do glossário quando não há session_id (sessão só em memória)."
        ),
    )
    orchestrator_model_maestro: str = Field(
        default="",
        description="Override do modelo só na fase de roteamento / maestro (llm_phase orchestrator:maestro).",
    )
    orchestrator_model_analise_os: str = Field(
        default="",
        description="Override para o agente analise_os (queries MCP, OS).",
    )
    orchestrator_model_clusterizacao: str = Field(
        default="",
        description="Override para clusterização.",
    )
    orchestrator_model_visualizador: str = Field(
        default="",
        description="Override para o agente visualizador.",
    )
    orchestrator_model_agregador: str = Field(
        default="",
        description="Override para agregador.",
    )
    orchestrator_model_projecoes: str = Field(
        default="",
        description="Override para projeções.",
    )
    orchestrator_model_verificador: str = Field(
        default="",
        description=(
            "Override para o skill verificador na pipeline F3 (além do agente homónimo se usado)."
        ),
    )
    orchestrator_model_compositor_layout: str = Field(
        default="",
        description="Override para o compositor JSON de layout na pipeline F3.",
    )

    entity_glossary_enabled: bool = Field(
        default=True,
        description="Se false, desliga a injecção do glossário no system (orquestrador).",
    )
    entity_glossary_mcp_tool: str = Field(
        default="get_entity_glossary_markdown",
        description=(
            "Nome da tool no servidor MCP cujo resultado markdown é fundido no system "
            "(deve coincidir com o registo no MCP)."
        ),
    )
    entity_glossary_max_chars: int = Field(
        default=24_000,
        description="Truncagem do markdown do glossário antes de fundir no system.",
    )
    entity_glossary_on_handoff: bool = Field(
        default=True,
        description=(
            "Se true, o orquestrador pode refrescar o glossário após handoff do Maestro para o especialista."
        ),
    )
    entity_glossary_include_demais_registos: bool = Field(
        default=True,
        description=(
            "Inclui no glossário pessoas via JOIN funcionario_cargos / cargos (ver entity_glossary.py)."
        ),
    )
    entity_glossary_sql_fun_extra: str = Field(
        default="",
        description=(
            "Sufixo SQL injectado na query de funcionários do glossário (começar por espaço + AND …); "
            "ver entity_glossary.py."
        ),
    )
    entity_glossary_sql_concessionarias_extra: str = Field(
        default="",
        description="Idem para o ramo concessionárias no markdown do glossário.",
    )
    entity_glossary_sql_servicos_extra: str = Field(
        default="",
        description="Idem para o ramo serviços no glossário.",
    )
    entity_glossary_session_cache_enabled: bool = Field(
        default=True,
        description=(
            "Se false, desliga o LRU em RAM do markdown do glossário por session_id "
            "(sempre refresh via MCP/MySQL quando aplicável)."
        ),
    )
    entity_glossary_session_cache_max: int = Field(
        default=256,
        description="Máximo de entradas no LRU do glossário por processo (orquestrador).",
    )

    tool_message_content_max_chars: int = Field(
        default=600_000,
        description=(
            "Teto ao serializar conteúdo de mensagens role=tool para o LLM (~200k tokens com CHARS_PER_TOKEN≈3)."
        ),
    )

    agent_trace_enabled: bool = Field(
        default=True,
        description="Se false, desliga a pasta de trace (``resolve_agent_trace_dir`` retorna None).",
    )
    agent_trace_dir: str = Field(
        default="",
        description=(
            "Caminho para ``{run_id}_app.jsonl`` / ``_server.jsonl``; vazio → projecto/logs/agent_trace."
        ),
    )
    agent_trace_max_field_chars: int = Field(
        default=600_000,
        description=(
            "Truncagem por campo JSON no trace; ≤0 desactiva truncagem (ficheiros grandes; cuidado com PII). "
            "Com trace activo, cada POST /api/chat pode gravar ``openai.chat_completions.summary`` no fim do run."
        ),
    )

    memory_prompts_enabled: bool = Field(
        default=True,
        description="Se false, ``maybe_update_*`` e extração de memória são no-op (memory_prompts.py).",
    )
    memory_conversation_summary_enabled: bool = Field(
        default=True,
        description=(
            "Activa resumo rolling do transcript em metadata.conversation_summary (conversation-summary.md)."
        ),
    )
    memory_session_notes_enabled: bool = Field(
        default=True,
        description="Activa notas estruturadas JSON em metadata.session_notes (session-notes.md).",
    )
    memory_extraction_enabled: bool = Field(
        default=True,
        description="Activa extração incremental para metadata.extracted_memory (memory-extraction.md).",
    )
    memory_consolidation_enabled: bool = Field(
        default=True,
        description="Reservada para consolidação de memória (sem uso activo noutros módulos no estado actual do repo).",
    )

    mcp_cache_entry_max_chars: int = Field(
        default=200_000,
        description=(
            "Teto de caracteres guardados por resultado de tool em sessions.metadata.mcp_tool_cache.entries."
        ),
    )
    mcp_cache_digest_max_chars: int = Field(
        default=12_000,
        description="Tamanho máximo do bloco markdown digest de cache MCP injectado no system.",
    )
    mcp_cache_digest_max_entries: int = Field(
        default=24,
        description="Quantas entradas recentes do cache entram no digest (mais recentes primeiro).",
    )
    mcp_cache_digest_max_chars_per_entry: int = Field(
        default=1800,
        description="Truncagem por entrada antes de compor o digest.",
    )

    mcp_cache_digest_llm_enabled: bool = Field(
        default=True,
        description="Se true, pode chamar um LLM para condensar o digest base (mcp_digest_editor.md).",
    )
    mcp_cache_digest_llm_trigger: str = Field(
        default="when_base_too_long",
        description=(
            "``when_base_too_long``: só corre o editor LLM se o digest base tiver ≥ "
            "``mcp_cache_digest_llm_min_chars_to_run`` caracteres."
        ),
    )
    mcp_cache_digest_llm_model: str = Field(
        default="",
        description=(
            "Modelo OpenAI para o editor do digest; vazio → ``openai_model`` no fluxo do orquestrador."
        ),
    )
    mcp_cache_digest_llm_timeout_seconds: float = Field(
        default=45.0,
        description="``asyncio.wait_for`` à volta da chamada ao modelo do digest (evita pendura indefinida).",
    )
    mcp_cache_digest_llm_max_output_chars: int = Field(
        default=4000,
        description="Truncagem da saída do editor LLM antes de gravar em mcp_digest_llm_cache.",
    )
    mcp_cache_digest_llm_min_chars_to_run: int = Field(
        default=2500,
        description="Com trigger when_base_too_long, digest base mais curto que isto não dispara o LLM.",
    )
    mcp_cache_digest_llm_reuse_hash: bool = Field(
        default=True,
        description="Se true, reutiliza digest LLM em cache quando o fingerprint das entradas MCP não mudou.",
    )

    analytics_session_datasets_enabled: bool = Field(
        default=True,
        description=(
            "Se true, regista spill + session_dataset_id após run_analytics_query com dados tabulares."
        ),
    )
    analytics_dataset_spill_dir: str = Field(
        default="",
        description=(
            "Directório para JSON de datasets por sessão; vazio → ``<projecto>/logs/analytics_datasets``."
        ),
    )
    analytics_dataset_spill_threshold_chars: int = Field(
        default=50_000,
        ge=1024,
        description=(
            "Se o JSON completo do resultado exceder este tamanho, grava spill (sempre recomendado; "
            "também usado como limiar para aviso de ficheiro grande)."
        ),
    )
    analytics_datasets_max_registered: int = Field(
        default=48,
        ge=4,
        description="Máximo de handles `session_dataset_id` mantidos em metadata por sessão (FIFO).",
    )

    analytics_aggregate_session_enabled: bool = Field(
        default=True,
        description="Se true, expõe a tool virtual host-only `analytics_aggregate_session` aos especialistas.",
    )
    analytics_aggregate_max_rows: int = Field(
        default=100_000,
        ge=100,
        description="Máximo de linhas carregadas do spill para agregação (protecção memória).",
    )
    analytics_aggregate_timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        description="Timeout da agregação determinística (thread pool + wait_for).",
    )
    analytics_aggregate_rate_limit_per_session: int = Field(
        default=80,
        ge=1,
        description="Máximo de chamadas `analytics_aggregate_session` por sessão (metadata).",
    )
    analytics_aggregate_top_k_max: int = Field(
        default=500,
        ge=1,
        description="Teto de `top_k` aceite pela tool virtual.",
    )

    pipeline_verifier_enabled: bool = Field(
        default=True,
        description=(
            "Após o especialista, chama o verificador contra o digest; grava verification_status em metadata."
        ),
    )
    pipeline_compositor_enabled: bool = Field(
        default=True,
        description="Se activo e não bloqueado por REPROVADO, gera layout_blocks JSON via compositor_layout.",
    )
    verification_depth: str = Field(
        default="smoke",
        description="Passado no user message ao verificador (texto livre consumido pelo skill).",
    )

    pipeline_critical_evaluator_enabled: bool = Field(
        default=True,
        description=(
            "Após o especialista, avaliador crítico (APROVAR/DEVOLVER) com voltas limitadas "
            "e preservação do transcript de tools."
        ),
    )
    orchestrator_max_critique_rounds: int = Field(
        default=3,
        ge=1,
        description="Máximo de devoluções do avaliador ao mesmo especialista por pedido HTTP.",
    )
    orchestrator_model_avaliador_critico: str = Field(
        default="",
        description="Override OpenAI para o passo avaliador_critico; vazio → openai_model.",
    )

    pipeline_formatador_ui_enabled: bool = Field(
        default=True,
        description="Após APROVAR, formatador_ui anexa bloco JSON content_blocks à mensagem final.",
    )
    orchestrator_model_formatador_ui: str = Field(
        default="",
        description="Override OpenAI para formatador_ui; vazio → openai_model.",
    )
    pipeline_skip_compositor_when_formatador_succeeds: bool = Field(
        default=True,
        description="Se o formatador produzir JSON válido com blocks, não chamar compositor_layout na F3.",
    )

    serpapi_api_key: str = Field(
        default="",
        description="Chave SerpApi; exportada para SERPAPI_API_KEY no arranque (subprocesso MCP).",
    )
    serpapi_enabled: bool = Field(
        default=True,
        description="Se false, SERPAPI_ENABLED=false no ambiente e o servidor MCP omite google_search_serpapi.",
    )

    orchestrator_tool_allowlist_json: str = Field(
        default="",
        description=(
            'JSON {"analise_os":["run_analytics_query",...]} — allowlist de nomes de tools MCP por agente. '
            "Vazio = sem filtro (todas as tools do servidor para cada especialista)."
        ),
    )

    observer_agent_enabled: bool = Field(
        default=True,
        description=(
            "Se true, no fim do run gera narrativa técnica do turno (observer.md) e acrescenta a observer_log/metadata."
        ),
    )
    observer_agent_model: str = Field(
        default="",
        description="Modelo para a narrativa do observador; vazio usa ``openai_model``.",
    )
    observer_log_max_entries: int = Field(
        default=500,
        description="Máximo de eventos estruturados mantidos em observer_log.entries antes de podar.",
    )
    observer_narratives_max: int = Field(
        default=50,
        description="Quantas narrativas completas (texto do observador) guardar em metadata.",
    )
    observer_narrative_max_chars: int = Field(
        default=8000,
        description="Truncagem de cada narrativa persistida.",
    )

    def resolve_analytics_dataset_spill_dir(self) -> Path:
        raw = (self.analytics_dataset_spill_dir or "").strip()
        if raw:
            return Path(raw).expanduser().resolve()
        return Path(__file__).resolve().parent.parent / "logs" / "analytics_datasets"

    def specialist_mcp_tool_allowlist(self) -> dict[str, frozenset[str]]:
        """
        Mapa agente → conjunto de nomes de tool MCP permitidos.
        Dicionário vazio = sem filtro por agente.
        """
        raw = (self.orchestrator_tool_allowlist_json or "").strip()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}
        out: dict[str, frozenset[str]] = {}
        for k, v in data.items():
            if isinstance(v, list):
                names = frozenset(str(x).strip() for x in v if str(x).strip())
                if names:
                    out[str(k).strip()] = names
        return out

    @property
    def postgres_enabled(self) -> bool:
        return bool(self.postgres_host and self.postgres_user and self.postgres_database)

    @property
    def orchestrator_agent_types_frozenset(self) -> frozenset[str]:
        parts = [p.strip() for p in self.orchestrator_agent_types.split(",") if p.strip()]
        return frozenset(parts)

    @field_validator("orchestrator_glossary_cache_anonymous_uuid")
    @classmethod
    def _valid_anon_glossary_uuid(cls, v: str) -> str:
        UUID(v.strip())
        return v.strip()

    def orchestrator_glossary_cache_anonymous_key(self) -> UUID:
        return UUID(self.orchestrator_glossary_cache_anonymous_uuid)

    def resolve_orchestrator_model_for_agent(self, agent_type: str) -> str | None:
        """Modelo da API OpenAI para o agente; ``None`` se deve usar ``openai_model``."""
        m = {
            "maestro": self.orchestrator_model_maestro,
            "analise_os": self.orchestrator_model_analise_os,
            "clusterizacao": self.orchestrator_model_clusterizacao,
            "visualizador": self.orchestrator_model_visualizador,
            "agregador": self.orchestrator_model_agregador,
            "projecoes": self.orchestrator_model_projecoes,
            "verificador": self.orchestrator_model_verificador,
            "compositor_layout": self.orchestrator_model_compositor_layout,
            "avaliador_critico": self.orchestrator_model_avaliador_critico,
            "formatador_ui": self.orchestrator_model_formatador_ui,
        }
        raw = (m.get(agent_type) or "").strip()
        return raw if raw else None

    def effective_model_for_agent(self, agent_type: str) -> str:
        """Modelo final (override por agente ou ``openai_model`` ou fallback)."""
        o = self.resolve_orchestrator_model_for_agent(agent_type)
        if o:
            return o
        base = (self.openai_model or "").strip()
        return base if base else "gpt-4o-mini"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def sync_mysql_env_from_settings(settings: Settings) -> None:
    """
    Escreve MYSQL_* em ``os.environ`` a partir do ``Settings`` (``.env`` / Pydantic).

    ``mcp_server.db`` usa ``os.environ``; o glossário corre no processo da API (uvicorn).
    Sem isto, valores herdados do shell (ex.: ``MYSQL_HOST=127.0.0.1``) podem prevalecer
    sobre o ``.env`` lido só pelo Pydantic — enquanto o subprocesso MCP arranca com outro ambiente.
    """
    import os

    host = (settings.mysql_host or "localhost").strip() or "localhost"
    os.environ["MYSQL_HOST"] = host
    os.environ["MYSQL_PORT"] = str(int(settings.mysql_port or 3306))
    os.environ["MYSQL_USER"] = settings.mysql_user or ""
    os.environ["MYSQL_PASSWORD"] = settings.mysql_password or ""
    os.environ["MYSQL_DATABASE"] = settings.mysql_database or ""

    if (settings.serpapi_api_key or "").strip():
        os.environ["SERPAPI_API_KEY"] = settings.serpapi_api_key.strip()
    os.environ["SERPAPI_ENABLED"] = "true" if settings.serpapi_enabled else "false"


def resolve_agent_trace_dir(settings: Settings) -> Path | None:
    """Directório onde são gravados ``{run_id}_app.jsonl`` e ``{run_id}_server.jsonl``."""

    if not settings.agent_trace_enabled:
        return None
    raw = (settings.agent_trace_dir or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parent.parent / "logs" / "agent_trace"
