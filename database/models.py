"""
Database Models using SQLAlchemy
"""
import asyncio
import sys
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, Boolean, Float, DateTime, ForeignKey, JSON, UniqueConstraint, inspect, LargeBinary
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, mapped_column
from sqlalchemy.schema import CreateIndex, CreateTable
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, TypeVar
from loguru import logger
from config import settings

# Psycopg async requires a selector loop on Windows. This makes standalone
# commands like `python -c "asyncio.run(...)"` work consistently.
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

Base = declarative_base()
T = TypeVar("T")


class Organization(Base):
    """Tenant organization table."""
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    plan = Column(String(50), nullable=False, default="starter")
    status = Column(String(50), nullable=False, default="active")
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime)


class Workspace(Base):
    """Tenant workspace table."""
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String(80), nullable=False, unique=True, index=True)
    tenant_id = Column(String(80), ForeignKey("organizations.tenant_id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="active")
    default_provider = Column(String(50), nullable=True)
    default_model = Column(String(120), nullable=True)
    default_retrieval_mode = Column(String(50), nullable=False, default="rag")
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime)


class WorkspaceMember(Base):
    """Workspace memberships and role mapping."""
    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String(80), ForeignKey("workspaces.workspace_id"), nullable=False, index=True)
    tenant_id = Column(String(80), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    email = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False, default="member")
    status = Column(String(50), nullable=False, default="active")
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime)


class LLMProviderConfig(Base):
    """Workspace-level provider/model/API-key configuration."""
    __tablename__ = "llm_provider_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "workspace_id", name="uq_llm_provider_config_tenant_workspace"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=False, index=True)
    workspace_id = Column(String(80), nullable=False, index=True)
    provider = Column(String(50), nullable=False)
    model_name = Column(String(120), nullable=False)
    encrypted_api_key = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime)


class ClientApiKey(Base):
    """API Keys for external client integrations (Widgets, Custom Apps, SDKs)."""
    __tablename__ = "client_api_keys"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=False, index=True)
    workspace_id = Column(String(80), nullable=False, index=True)
    key_type = Column(String(50), nullable=False, default="public_widget") # 'public_widget' or 'secret_api'
    api_key = Column(String(120), nullable=False, unique=True, index=True) # e.g. youbot_pub_xxxyyyzzz
    name = Column(String(255), nullable=False) # e.g. "Main Website Widget"
    allowed_domains = Column(JSON, nullable=True) # CORS allowed origins for public keys
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, index=True)
    last_used_at = Column(DateTime, nullable=True)


class SocialChannelConnection(Base):
    """Tenant-managed social media connector configuration and secrets."""
    __tablename__ = "social_channel_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=False, index=True)
    workspace_id = Column(String(80), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    provider = Column(String(50), nullable=False, index=True)  # meta, generic
    channel = Column(String(50), nullable=False, index=True)  # whatsapp, instagram, facebook, custom
    connection_key = Column(String(128), nullable=False, unique=True, index=True)
    verify_token_encrypted = Column(Text, nullable=True)
    access_token_encrypted = Column(Text, nullable=True)
    app_secret_encrypted = Column(Text, nullable=True)
    outbound_webhook_url = Column(Text, nullable=True)
    outbound_auth_headers_encrypted = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime, nullable=True)
    last_event_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)


class KnowledgeSource(Base):
    """Tenant workspace knowledge source configuration."""
    __tablename__ = "knowledge_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=False, index=True)
    workspace_id = Column(String(80), nullable=False, index=True)
    source_name = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False)  # csv, web
    source_uri = Column(Text, nullable=True)
    source_config = Column(JSON, nullable=True)
    status = Column(String(50), nullable=False, default="active", index=True)
    last_sync_at = Column(DateTime, nullable=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime)


class IngestionJob(Base):
    """Knowledge ingestion job tracking."""
    __tablename__ = "ingestion_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=False, index=True)
    workspace_id = Column(String(80), nullable=False, index=True)
    source_id = Column(Integer, ForeignKey("knowledge_sources.id"), nullable=True, index=True)
    source_type = Column(String(50), nullable=False)
    trigger_type = Column(String(50), nullable=False, default="manual")
    status = Column(String(50), nullable=False, default="queued", index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    total_records = Column(Integer, nullable=False, default=0)
    processed_records = Column(Integer, nullable=False, default=0)
    success_records = Column(Integer, nullable=False, default=0)
    failed_records = Column(Integer, nullable=False, default=0)
    error_summary = Column(Text, nullable=True)
    details_json = Column(JSON, nullable=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime)


class RetrievalProfile(Base):
    """Workspace retrieval policy and recommendation signals."""
    __tablename__ = "retrieval_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "workspace_id", name="uq_retrieval_profile_tenant_workspace"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=False, index=True)
    workspace_id = Column(String(80), nullable=False, index=True)
    default_mode = Column(String(50), nullable=False, default="rag")
    allowed_modes = Column(JSON, nullable=False, default=["rag"])
    page_window_limit = Column(Integer, nullable=False, default=4)
    compliance_criticality = Column(Float, nullable=False, default=0.5)
    average_document_pages = Column(Integer, nullable=False, default=10)
    query_complexity = Column(Float, nullable=False, default=0.5)
    latency_budget_ms = Column(Integer, nullable=False, default=2500)
    cost_sensitivity = Column(Float, nullable=False, default=0.5)
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime)


class RetrievalRecommendationEvent(Base):
    """Recommendation and selection audit trail for retrieval mode routing."""
    __tablename__ = "retrieval_recommendation_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=False, index=True)
    workspace_id = Column(String(80), nullable=False, index=True)
    query_hash = Column(String(64), nullable=False, index=True)
    query_preview = Column(String(500), nullable=True)
    recommended_mode = Column(String(50), nullable=False)
    selected_mode = Column(String(50), nullable=False)
    reason_summary = Column(Text, nullable=True)
    expected_latency_band = Column(String(50), nullable=True)
    expected_cost_band = Column(String(50), nullable=True)
    override_applied = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, index=True)


class DocumentPage(Base):
    """Page-level extracted document content for page-index retrieval mode."""
    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("workspace_id", "document_id", "page_number", name="uq_document_page_workspace_doc_page"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=False, index=True)
    workspace_id = Column(String(80), nullable=False, index=True)
    source_id = Column(Integer, ForeignKey("knowledge_sources.id"), nullable=True, index=True)
    document_id = Column(String(255), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    page_text = Column(Text, nullable=False)
    section_headings = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, index=True)


class PageIndexEntry(Base):
    """Page index pointer metadata for retrieval routing."""
    __tablename__ = "page_index_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=False, index=True)
    workspace_id = Column(String(80), nullable=False, index=True)
    source_id = Column(Integer, ForeignKey("knowledge_sources.id"), nullable=True, index=True)
    document_id = Column(String(255), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    embedding_vector_ref = Column(String(255), nullable=False)
    keyword_vector_ref = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, index=True)


class ConversationLog(Base):
    """Conversation logs table"""
    __tablename__ = "conversation_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=True, index=True)
    workspace_id = Column(String(80), nullable=True, index=True)
    session_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    user_message = Column(Text, nullable=False)
    assistant_response = Column(Text, nullable=False)
    language = Column(String(50))
    channel = Column(String(50))
    sentiment = Column(String(50), default="neutral")
    resolved = Column(Boolean, default=False)
    handed_to_human = Column(Boolean, default=False)
    model_used = Column(String(100))
    knowledge_base_used = Column(Boolean, default=False)
    action_items = Column(Text)
    handoff_reason = Column(Text)
    unsolved_score = Column(Float)
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime)


class AdminAvailability(Base):
    """Admin availability table"""
    __tablename__ = "admin_availability"
    
    admin_id = Column(String(255), primary_key=True)
    tenant_id = Column(String(80), nullable=True, index=True)
    workspace_id = Column(String(80), nullable=True, index=True)
    admin_name = Column(String(255), nullable=False)
    admin_email = Column(String(255), nullable=False)
    role = Column(String(50), default="admin", index=True)  # 'admin' or 'super_admin'
    status = Column(String(50), nullable=False, default="offline", index=True)
    current_queue_count = Column(Integer, default=0)
    max_queue_size = Column(Integer, default=10)
    last_assigned_at = Column(DateTime)
    total_queries_handled = Column(Integer, default=0)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime)


class AdminQueue(Base):
    """Admin queue table"""
    __tablename__ = "admin_queue"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=True, index=True)
    workspace_id = Column(String(80), nullable=True, index=True)
    session_id = Column(String(255), nullable=False)
    user_id = Column(String(255), nullable=False)
    admin_id = Column(String(255), ForeignKey("admin_availability.admin_id"))
    user_message = Column(Text, nullable=False)
    ai_response = Column(Text)
    status = Column(String(50), default="pending", index=True)
    priority = Column(String(50), default="normal")
    language = Column(String(50))
    channel = Column(String(50))
    handoff_reason = Column(Text)
    unsolved_score = Column(Float)
    assigned_at = Column(DateTime)
    resolved_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime)


class AnalyticsEvent(Base):
    """Analytics events table"""
    __tablename__ = "analytics_events"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=True, index=True)
    workspace_id = Column(String(80), nullable=True, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    session_id = Column(String(255))
    user_id = Column(String(255))
    language = Column(String(50))
    channel = Column(String(50))
    sentiment = Column(String(50))
    model_used = Column(String(100))
    response_time_ms = Column(Integer)
    knowledge_base_used = Column(Boolean, default=False)
    resolved_by_ai = Column(Boolean, default=False)
    handed_to_human = Column(Boolean, default=False)
    unsolved_score = Column(Float)
    timestamp = Column(DateTime, nullable=False, index=True)


class ConversationMetric(Base):
    """Session-level metrics for analytics aggregation and KPI auditing."""
    __tablename__ = "conversation_metrics"
    __table_args__ = (
        UniqueConstraint("tenant_id", "workspace_id", "session_id", name="uq_conversation_metrics_session"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=False, index=True)
    workspace_id = Column(String(80), nullable=False, index=True)
    session_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=True, index=True)
    channel = Column(String(50), nullable=True)
    language = Column(String(50), nullable=True)
    total_messages = Column(Integer, nullable=False, default=0)
    ai_messages = Column(Integer, nullable=False, default=0)
    human_messages = Column(Integer, nullable=False, default=0)
    first_response_time_ms = Column(Integer, nullable=True)
    retrieval_hit = Column(Boolean, nullable=False, default=False)
    citation_coverage = Column(Float, nullable=False, default=0.0)
    fallback_count = Column(Integer, nullable=False, default=0)
    low_confidence_count = Column(Integer, nullable=False, default=0)
    unresolved = Column(Boolean, nullable=False, default=False)
    started_at = Column(DateTime, nullable=False, index=True)
    resolved_at = Column(DateTime, nullable=True, index=True)
    aggregated_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class SessionOutcome(Base):
    """Canonical per-session outcome record used by user/team KPI domains."""
    __tablename__ = "session_outcomes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "workspace_id", "session_id", name="uq_session_outcomes_session"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=False, index=True)
    workspace_id = Column(String(80), nullable=False, index=True)
    session_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=True, index=True)
    channel = Column(String(50), nullable=True)
    language = Column(String(50), nullable=True)
    sentiment = Column(String(50), nullable=True)
    outcome_status = Column(String(50), nullable=False, default="open", index=True)
    resolved_by = Column(String(50), nullable=False, default="none", index=True)
    first_meaningful_response_ms = Column(Integer, nullable=True)
    total_duration_ms = Column(Integer, nullable=True)
    repeat_contact_24h = Column(Boolean, nullable=False, default=False)
    repeat_contact_7d = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=True)


class SLAEvent(Base):
    """SLA tracking events for queue, takeover, and response-time governance."""
    __tablename__ = "sla_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=False, index=True)
    workspace_id = Column(String(80), nullable=False, index=True)
    session_id = Column(String(255), nullable=True, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    channel = Column(String(50), nullable=True)
    severity = Column(String(50), nullable=True)
    target_ms = Column(Integer, nullable=True)
    actual_ms = Column(Integer, nullable=True)
    breached = Column(Boolean, nullable=False, default=False, index=True)
    metadata_json = Column(JSON, nullable=True)
    event_time = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class TenantAnalyticsHourly(Base):
    """Hourly phase 5 analytics aggregation."""
    __tablename__ = "tenant_analytics_hourly"

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id = mapped_column(String(80), nullable=False, index=True)
    workspace_id = mapped_column(String(80), nullable=False, index=True)
    hour_timestamp = mapped_column(DateTime, nullable=False, index=True)
    total_conversations = mapped_column(Integer, default=0)
    ai_resolved_conversations = mapped_column(Integer, default=0)
    handed_to_human = mapped_column(Integer, default=0)
    avg_human_response_time_ms = mapped_column(Integer, default=0)
    created_at = mapped_column(DateTime, default=datetime.utcnow)


class TenantAnalyticsDaily(Base):
    """Daily phase 5 analytics aggregation."""
    __tablename__ = "tenant_analytics_daily"

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id = mapped_column(String(80), nullable=False, index=True)
    workspace_id = mapped_column(String(80), nullable=False, index=True)
    date = mapped_column(DateTime, nullable=False, index=True)
    total_conversations = mapped_column(Integer, default=0)
    ai_resolved_conversations = mapped_column(Integer, default=0)
    handed_to_human = mapped_column(Integer, default=0)
    avg_human_response_time_ms = mapped_column(Integer, default=0)
    created_at = mapped_column(DateTime, default=datetime.utcnow)


class AnalyticsAlertRule(Base):
    """Alert rules for Phase 5 analytics."""
    __tablename__ = "analytics_alert_rules"

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id = mapped_column(String(80), nullable=False, index=True)
    workspace_id = mapped_column(String(80), nullable=False, index=True)
    rule_name = mapped_column(String(255), index=True)
    metric_name = mapped_column(String(100))
    threshold_value = mapped_column(Float)
    condition = mapped_column(String(50))
    is_active = mapped_column(Boolean, default=True)
    created_at = mapped_column(DateTime, default=datetime.utcnow)


class AnalyticsAlertEvent(Base):
    """Alert events produced by Phase 5 rules."""
    __tablename__ = "analytics_alert_events"

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id = mapped_column(String(80), nullable=False, index=True)
    workspace_id = mapped_column(String(80), nullable=False, index=True)
    rule_id = mapped_column(Integer, index=True)
    event_time = mapped_column(DateTime, default=datetime.utcnow, index=True)
    metric_value = mapped_column(Float)
    message = mapped_column(Text)
    status = mapped_column(String(50), default="new")


class ActiveConversation(Base):
    """
    Track all active conversations for admin supervision.
    Every conversation is logged here for real-time monitoring.
    """
    __tablename__ = "active_conversations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=True, index=True)
    workspace_id = Column(String(80), nullable=True, index=True)
    session_id = Column(String(255), nullable=False, unique=True, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    channel = Column(String(50))
    language = Column(String(50))
    
    # Conversation status
    status = Column(String(50), default="active", index=True)  # active, admin_watching, admin_takeover, ended
    is_supervised = Column(Boolean, default=True)  # All conversations supervised by default
    
    # Admin intervention
    admin_id = Column(String(255), ForeignKey("admin_availability.admin_id"), nullable=True)
    admin_takeover = Column(Boolean, default=False)  # True if admin has taken over
    takeover_reason = Column(Text, nullable=True)
    takeover_at = Column(DateTime, nullable=True)
    
    # Super admin intervention (NEW)
    super_admin_id = Column(String(255), ForeignKey("admin_availability.admin_id"), nullable=True)
    previous_admin_id = Column(String(255), nullable=True)
    super_admin_takeover = Column(Boolean, default=False)
    super_admin_takeover_at = Column(DateTime, nullable=True)
    
    # AI handoff (when AI triggers handoff)
    ai_triggered_handoff = Column(Boolean, default=False)
    handoff_reason = Column(Text, nullable=True)
    
    # Message counts
    message_count = Column(Integer, default=0)
    last_message = Column(Text)
    last_ai_response = Column(Text)
    
    # Timestamps
    started_at = Column(DateTime, nullable=False)
    last_activity = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)


class AdminMessage(Base):
    """
    Messages sent by admin during intervention.
    Separate from AI responses so we can track admin vs AI messages.
    """
    __tablename__ = "admin_messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=True, index=True)
    workspace_id = Column(String(80), nullable=True, index=True)
    session_id = Column(String(255), nullable=False, index=True)
    admin_id = Column(String(255), ForeignKey("admin_availability.admin_id"), nullable=False)
    message = Column(Text, nullable=False)
    is_super_admin = Column(Boolean, default=False)  # Track if message from super admin
    created_at = Column(DateTime, nullable=False)


class TenantCustomAction(Base):
    """Tenant-defined external API actions for the AI to utilize as tools."""
    __tablename__ = "tenant_custom_actions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "workspace_id", "name", name="uq_tenant_custom_action_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=False, index=True)
    workspace_id = Column(String(80), nullable=False, index=True)
    name = Column(String(100), nullable=False) # e.g. "check_order_status"
    description = Column(Text, nullable=False) # Important for LLM tool selection
    api_endpoint = Column(Text, nullable=False)
    method = Column(String(10), nullable=False, default="GET")
    auth_headers_encrypted = Column(Text, nullable=True) # Configured headers securely encrypted
    payload_schema_json = Column(JSON, nullable=True) # Expected parameter schema
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=True)


class TenantMCPServer(Base):
    """Tenant-defined MCP servers for dynamic tool resolution."""
    __tablename__ = "tenant_mcp_servers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "workspace_id", "name", name="uq_tenant_mcp_server_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=False, index=True)
    workspace_id = Column(String(80), nullable=False, index=True)
    name = Column(String(100), nullable=False) # e.g. "social_media_integrator"
    connection_type = Column(String(20), nullable=False, default="sse") # "stdio" or "sse"
    connection_url = Column(Text, nullable=False) # The URL for SSE or binary command for stdio
    config_json_encrypted = Column(Text, nullable=True) # Encrypted JSON of ENV vars / tokens for MCP Auth
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=True)

class AssistantProfile(Base):
    """
    Per-workspace assistant identity & behavioural profile.

    Drives the dynamic system prompt for the bot so the same backend can
    serve different industries/companies without code changes. The bot's
    persona, scope, and tone come from this row; the KB still grounds the
    facts.
    """
    __tablename__ = "assistant_profiles"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "workspace_id",
            name="uq_assistant_profile_tenant_workspace",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(80), nullable=False, index=True)
    workspace_id = Column(String(80), nullable=False, index=True)
    business_name = Column(String(255), nullable=False, default="our team")
    business_description = Column(Text, nullable=True)  # one-line "what we do"
    service_topics = Column(JSON, nullable=False, default=list)  # ["payroll", "tax compliance", ...]
    tone = Column(String(40), nullable=False, default="warm")  # warm | professional | casual | formal
    website_url = Column(String(500), nullable=True)
    contact_email = Column(String(255), nullable=True)
    handoff_message = Column(Text, nullable=True)  # custom no-info response
    forbidden_topics = Column(JSON, nullable=False, default=list)  # things bot must never claim to handle
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=True)


class LangGraphCheckpoint(Base):
    """Distributed persistence for LangGraph Thread State."""
    __tablename__ = "langgraph_checkpoints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(String(255), nullable=False, index=True)
    checkpoint_id = Column(String(255), nullable=False)
    parent_checkpoint_id = Column(String(255), nullable=True)
    checkpoint_blob = Column(LargeBinary, nullable=False)
    metadata_blob = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class LangGraphCheckpointWrite(Base):
    """Intermediate LangGraph writes linked to a checkpoint."""
    __tablename__ = "langgraph_checkpoint_writes"
    __table_args__ = (
        UniqueConstraint("thread_id", "checkpoint_id", "task_id", "idx", name="uq_langgraph_checkpoint_write"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(String(255), nullable=False, index=True)
    checkpoint_id = Column(String(255), nullable=False, index=True)
    task_id = Column(String(255), nullable=False, index=True)
    idx = Column(Integer, nullable=False)
    channel = Column(String(255), nullable=False)
    value_type = Column(String(50), nullable=False)
    value_blob = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

# Phase 3 tables required by retrieval and ingestion endpoints.
PHASE3_TABLES = [
    KnowledgeSource.__table__,
    IngestionJob.__table__,
    RetrievalProfile.__table__,
    RetrievalRecommendationEvent.__table__,
    DocumentPage.__table__,
    PageIndexEntry.__table__,
]

# Runtime tables required by the current SaaS backend API.
#
# Important: Do not auto-bootstrap tenant foundation tables that can conflict with
# pre-existing Supabase schemas (e.g. workspaces with different column naming).
# We bootstrap only the tables actively used by current runtime endpoints.
RUNTIME_BOOTSTRAP_TABLE_NAMES = {
    "conversation_logs",
    "conversation_metrics",
    "session_outcomes",
    "sla_events",
    "admin_availability",
    "admin_queue",
    "analytics_events",
    "active_conversations",
    "admin_messages",
    "llm_provider_configs",
    "client_api_keys",
    "social_channel_connections",
    "knowledge_sources",
    "ingestion_jobs",
    "retrieval_profiles",
    "retrieval_recommendation_events",
    "document_pages",
    "page_index_entries",
    "tenant_analytics_hourly",
    "tenant_analytics_daily",
    "analytics_alert_rules",
    "analytics_alert_events",
    "tenant_custom_actions",
    "tenant_mcp_servers",
    "assistant_profiles",
    "langgraph_checkpoints",
    "langgraph_checkpoint_writes",
}

RUNTIME_TABLES = [
    table for table in Base.metadata.sorted_tables if table.name in RUNTIME_BOOTSTRAP_TABLE_NAMES
]


def _engine_connect_args() -> dict:
    """
    Build driver-specific connection args.

    Supabase pooler (PgBouncer in transaction mode) is not compatible with
    psycopg server-side prepared statements. Disable preparation to avoid
    DuplicatePreparedStatement startup/runtime errors.
    """
    database_url = settings.DATABASE_URL_RUNTIME.lower()
    if database_url.startswith("postgresql+psycopg://"):
        return {"prepare_threshold": None}
    return {}


def _existing_columns(sync_conn, table_name: str) -> set[str]:
    try:
        inspector = inspect(sync_conn)
        return {str(col["name"]) for col in inspector.get_columns(table_name)}
    except Exception:
        return set()


def _create_table_if_not_exists(sync_conn, table) -> None:
    sync_conn.execute(CreateTable(table, if_not_exists=True))


def _ensure_llm_provider_column(sync_conn, column_name: str, default_value: str) -> None:
    sync_conn.exec_driver_sql(
        f"ALTER TABLE llm_provider_configs ADD COLUMN IF NOT EXISTS {column_name} VARCHAR(80)"
    )
    sync_conn.exec_driver_sql(
        f"UPDATE llm_provider_configs SET {column_name} = '{default_value}' WHERE {column_name} IS NULL"
    )


def _create_index_if_not_exists(sync_conn, index) -> None:
    sync_conn.execute(CreateIndex(index, if_not_exists=True))


async def _run_bootstrap_step(step_name: str, sync_action: Callable[[object], T]) -> T | None:
    """Run a single DDL step in its own transaction so a failure cannot poison later steps."""
    try:
        async with engine.begin() as conn:
            return await conn.run_sync(sync_action)
    except Exception as exc:
        logger.warning("Skipping {} due to compatibility error: {}", step_name, exc)
        return None


async def _bootstrap_table(table) -> set[str]:
    await _run_bootstrap_step(
        f"table bootstrap for {table.name}",
        lambda sync_conn: _create_table_if_not_exists(sync_conn, table),
    )

    db_columns = await _run_bootstrap_step(
        f"column inspection for {table.name}",
        lambda sync_conn: _existing_columns(sync_conn, table.name),
    )
    if db_columns is None:
        db_columns = set()

    if table.name == "llm_provider_configs" and db_columns:
        if "tenant_id" not in db_columns:
            await _run_bootstrap_step(
                "llm_provider_configs tenant_id compatibility migration",
                lambda sync_conn: _ensure_llm_provider_column(sync_conn, "tenant_id", "public"),
            )

        if "workspace_id" not in db_columns:
            await _run_bootstrap_step(
                "llm_provider_configs workspace_id compatibility migration",
                lambda sync_conn: _ensure_llm_provider_column(sync_conn, "workspace_id", "default"),
            )

        refreshed_columns = await _run_bootstrap_step(
            f"column inspection for {table.name}",
            lambda sync_conn: _existing_columns(sync_conn, table.name),
        )
        if refreshed_columns is not None:
            db_columns = refreshed_columns

    return db_columns


async def _bootstrap_table_indexes(table, db_columns: set[str]) -> None:
    for index in table.indexes:
        required_columns = {
            str(expr.name)
            for expr in index.expressions
            if getattr(expr, "name", None)
        }

        if required_columns and not required_columns.issubset(db_columns):
            logger.warning(
                "Skipping index bootstrap for {} on {} because required columns are missing. required={}, existing={}",
                index.name,
                table.name,
                sorted(required_columns),
                sorted(db_columns),
            )
            continue

        await _run_bootstrap_step(
            f"index bootstrap for {index.name} on {table.name}",
            lambda sync_conn, index=index: _create_index_if_not_exists(sync_conn, index),
        )


async def _bootstrap_tables(tables) -> list[str]:
    for table in tables:
        db_columns = await _bootstrap_table(table)
        await _bootstrap_table_indexes(table, db_columns)

    return [table.name for table in tables]


# Create async engine with production optimizations
engine = create_async_engine(
    settings.DATABASE_URL_RUNTIME,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,  # Detect stale connections before use
    pool_recycle=3600,   # Recycle connections after 1 hour
    connect_args=_engine_connect_args(),
    echo=settings.DEBUG
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def bootstrap_phase3_tables() -> list[str]:
    """Create missing Phase 3 retrieval/ingestion tables if they do not exist."""
    return await _bootstrap_tables(PHASE3_TABLES)


async def bootstrap_runtime_tables() -> list[str]:
    """Create all ORM-backed runtime tables if they do not exist."""
    return await _bootstrap_tables(RUNTIME_TABLES)


@asynccontextmanager
async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Get async database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
