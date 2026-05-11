"""
Configuration management for LangGraph AI Agent
"""
import os
from pydantic import field_validator
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional
from urllib.parse import quote_plus


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Application
    APP_NAME: str = "Sweden Relocators AI Agent"
    DEBUG: bool = False
    API_VERSION: str = "v1"
    
    # LLM Configuration (from n8n workflow)
    # n8n used: llama3-70b-8192 with temp=0.3 for main LLM
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama3-70b-8192"  # Will read from .env
    GROQ_TEMPERATURE: float = 0.2  # Lower for consistent FAQ responses (was 0.4)
    GROQ_MAX_TOKENS: int = 350  # Optimized for typical response length (was 500)
    GROQ_REQUEST_TIMEOUT: int = 15  # Fail fast on slow API calls
    
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4-turbo-preview"
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-latest"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-pro"

    DEFAULT_LLM_PROVIDER: str = "groq"
    DEFAULT_LLM_MODEL: Optional[str] = None
    LLM_CONFIG_ENCRYPTION_KEY: Optional[str] = None
    LLM_PROVIDER_PLUGIN_MODULES: str = ""  # Comma-separated modules that call register_provider(...)
    LLM_MODEL_VALIDATION_REQUIRED: bool = True
    LLM_PROVIDER_CATALOG_TIMEOUT_SECONDS: int = 12
    LLM_PROVIDER_CATALOG_CACHE_TTL_SECONDS: int = 300

    # Supabase (optional)
    SUPABASE_URL: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[str] = None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    SUPABASE_DB_URL: Optional[str] = None  # Direct Postgres URL for schema migrations
    SUPABASE_DB_HOST: Optional[str] = None
    SUPABASE_DB_PORT: int = 5432
    SUPABASE_DB_NAME: str = "postgres"
    SUPABASE_DB_USER: str = "postgres"
    SUPABASE_DB_PASSWORD: Optional[str] = None
    PREFER_SUPABASE_DATABASE: bool = True
    SUPABASE_REQUIRE_SSLMODE: bool = True
    
    # Database
    DATABASE_URL: str = "mysql+asyncmy://root:password@localhost:3306/sweden_relocators_ai"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    
    # Checkpointing (LangGraph state persistence)
    CHECKPOINT_DB: str = "sqlite:///checkpoints.db"
    
    # Vector Store
    VECTOR_STORE_TYPE: str = "pinecone"  # chroma, pinecone, qdrant
    VECTOR_STORE_PATH: str = "./data/chroma_db"  # For local stores
    
    # Pinecone (if used)
    PINECONE_API_KEY: Optional[str] = None
    PINECONE_ENVIRONMENT: str = "gcp-starter"
    PINECONE_INDEX: str = "sweden-relocators-faq"
    PINECONE_TIMEOUT: int = 5  # Vector search timeout in seconds
    
    # Embeddings
    EMBEDDING_MODEL_NAME: str = "intfloat/multilingual-e5-base"
    VECTOR_TOP_K: int = 5  # Top 5 documents for RAG (was 3)
    VECTOR_MIN_SCORE: float = 0.65  # Minimum relevance score to include doc
    
    # Qdrant (if used)
    QDRANT_URL: Optional[str] = None
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION: str = "sweden_relocators"
    
    # Redis (optional, for distributed caching)
    REDIS_URL: Optional[str] = None
    REDIS_TTL: int = 3600  # 1 hour
    REDIS_TIMEOUT: int = 3  # Cache lookup timeout in seconds
    
    # Semantic Caching
    SEMANTIC_CACHE_ENABLED: bool = True  # Enable semantic similarity caching
    SEMANTIC_CACHE_THRESHOLD: float = 0.90  # Minimum similarity for cache hit (0.0-1.0)
    CROSS_LANGUAGE_CACHE_OVERLAP: float = 0.92  # Strict overlap required for cross-language cache hits
    EMBEDDING_BATCH_SIZE: int = 32  # Batch size for embedding generation

    # MCP External Tool Routing (optional)
    MCP_ENABLED: bool = False
    MCP_SERVER_URL: Optional[str] = None
    MCP_API_KEY: Optional[str] = None
    MCP_TIMEOUT_SECONDS: int = 15
    MCP_FAIL_OPEN: bool = False  # Explicitly opt in to direct HTTP fallback when MCP call fails
    MCP_AGENT_STRICT_MODE: bool = False  # Require MCP for agent external HTTP calls
    MCP_HTTP_GET_TOOL: str = "http.get"
    MCP_HTTP_POST_TOOL: str = "http.post"
    
    # Email Configuration
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "noreply@swedenrelocators.com"
    
    # Admin Notifications
    ADMIN_EMAILS: list[str] = ["admin@swedenrelocators.com"]
    
    # Security
    API_KEY_HEADER: str = "X-API-Key"
    API_KEYS: list[str] = []  # Add valid API keys
    ADMIN_API_KEY: str = ""  # Separate admin key for admin endpoints
    REQUIRE_TENANT_CONTEXT: bool = False
    DEFAULT_TENANT_ID: str = "public"
    DEFAULT_WORKSPACE_ID: str = "default"
    TENANT_HEADER_NAME: str = "X-Tenant-Id"
    WORKSPACE_HEADER_NAME: str = "X-Workspace-Id"
    RATE_LIMIT_PER_MINUTE: int = 100
    ALLOWED_ORIGINS: list[str] = ["https://swedenrelocators.se", "https://admin.swedenrelocators.se", "http://localhost:8000", "http://127.0.0.1:8000"]
    MAX_MESSAGE_LENGTH: int = 5000  # Max input message length
    
    # Workflow Configuration
    MAX_CONVERSATION_HISTORY: int = 5  # Reduced for speed
    SPAM_THRESHOLD: float = 1.0
    INTENT_CONFIDENCE_THRESHOLD: float = 0.8
    
    # Knowledge Base
    KNOWLEDGE_BASE_TOP_K: int = 3  # Reduced for speed
    KNOWLEDGE_BASE_SIMILARITY_THRESHOLD: float = 0.5  # Lower threshold for more flexible matching
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/agent.log"
    
    # Performance
    WORKERS: int = 4
    REQUEST_TIMEOUT: int = 30  # seconds
    
    # URLs
    WEBSITE_URL: str = "https://swedenrelocators.com"

    @field_validator("DEBUG", mode="before")
    @classmethod
    def normalize_debug_flag(cls, value):
        """Handle accidental log-level strings in DEBUG env var gracefully."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"debug", "info", "warn", "warning", "error", "critical"}:
                return normalized == "debug"
        return value

    @staticmethod
    def _normalize_postgres_url_scheme(db_url: str) -> str:
        """Normalize Postgres URL scheme for SQLAlchemy async engines."""
        normalized = (db_url or "").strip()
        if normalized.startswith("postgres://"):
            normalized = "postgresql://" + normalized[len("postgres://"):]

        if normalized.startswith("postgresql+asyncpg://"):
            return normalized
        if normalized.startswith("postgresql+psycopg://"):
            return normalized
        if normalized.startswith("postgresql://"):
            return "postgresql+psycopg://" + normalized[len("postgresql://"):]

        return normalized

    @staticmethod
    def _ensure_sslmode_require(db_url: str) -> str:
        """Append sslmode=require if it is not already present."""
        if "sslmode=" in db_url.lower():
            return db_url
        separator = "&" if "?" in db_url else "?"
        return f"{db_url}{separator}sslmode=require"

    def _build_supabase_db_url_from_components(self) -> Optional[str]:
        """Build a Postgres URL from SUPABASE_DB_* component settings."""
        host = (self.SUPABASE_DB_HOST or "").strip()
        password = self.SUPABASE_DB_PASSWORD or ""
        if not host or not password:
            return None

        user = quote_plus((self.SUPABASE_DB_USER or "postgres").strip())
        safe_password = quote_plus(password)
        db_name = (self.SUPABASE_DB_NAME or "postgres").strip()
        port = int(self.SUPABASE_DB_PORT or 5432)
        return f"postgresql+psycopg://{user}:{safe_password}@{host}:{port}/{db_name}"

    def resolve_database_url(self) -> str:
        """Resolve the runtime database URL with Supabase-first precedence."""
        if self.PREFER_SUPABASE_DATABASE:
            supabase_candidate = (self.SUPABASE_DB_URL or "").strip() or self._build_supabase_db_url_from_components()
            if supabase_candidate:
                resolved = self._normalize_postgres_url_scheme(supabase_candidate)
                if self.SUPABASE_REQUIRE_SSLMODE and resolved.startswith("postgresql+"):
                    resolved = self._ensure_sslmode_require(resolved)
                return resolved

        fallback = (self.DATABASE_URL or "").strip()
        if fallback.startswith("postgres://") or fallback.startswith("postgresql://"):
            fallback = self._normalize_postgres_url_scheme(fallback)
        return fallback

    @property
    def DATABASE_URL_RUNTIME(self) -> str:
        """Runtime database URL used by SQLAlchemy engine creation."""
        return self.resolve_database_url()
    
    class Config:
        env_file = os.path.join(os.path.dirname(__file__), ".env")
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Export settings instance
settings = get_settings()
