"""
Configuration management for LangGraph AI Agent
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Application
    APP_NAME: str = "Sweden Relocators AI Agent"
    DEBUG: bool = False
    API_VERSION: str = "v1"
    
    # LLM Configuration (from n8n workflow)
    # n8n used: llama3-70b-8192 with temp=0.3 for main LLM
    GROQ_API_KEY: str
    GROQ_MODEL: str  # Will read from .env
    GROQ_TEMPERATURE: float = 0.4  # Slightly higher for more natural responses
    GROQ_MAX_TOKENS: int = 500  # Reduced for faster responses
    
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4-turbo-preview"
    
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
    
    # Embeddings
    EMBEDDING_MODEL_NAME: str = "intfloat/multilingual-e5-base"
    VECTOR_TOP_K: int = 3  # Reduced for speed
    
    # Qdrant (if used)
    QDRANT_URL: Optional[str] = None
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION: str = "sweden_relocators"
    
    # Redis (optional, for distributed caching)
    REDIS_URL: Optional[str] = None
    REDIS_TTL: int = 3600  # 1 hour
    
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
    RATE_LIMIT_PER_MINUTE: int = 100
    ALLOWED_ORIGINS: list[str] = ["https://swedenrelocators.se", "https://admin.swedenrelocators.se", "http://localhost:5678", "http://127.0.0.1:5678"]
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
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Export settings instance
settings = get_settings()
