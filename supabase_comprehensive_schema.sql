-- Comprehensive Supabase/Postgres schema for multi-tenant conversational AI
-- Focus: persistence, analytics, context windowing (last 3 user messages), and high-scale optimizations.
--
-- Key techniques included:
-- 1) Hash partitioning (shard-like distribution) on high-volume tables.
-- 2) Composite/covering/partial indexes for common access paths.
-- 3) BRIN + GIN indexes for append-heavy + JSON/text search workloads.
-- 4) Trigger-maintained counters and last-3-user-message context persistence.
-- 5) Materialized view + optional pg_cron refresh for client analytics.
-- 6) RLS-ready tenant/workspace isolation policies.

begin;

create extension if not exists pgcrypto;
create extension if not exists pg_trgm;
create extension if not exists btree_gin;

-- Optional: scheduled analytics refresh (may require elevated privileges)
do $$
begin
    begin
        create extension if not exists pg_cron;
    exception when insufficient_privilege then
        raise notice 'pg_cron extension skipped due to insufficient privileges';
    end;
end $$;

-- -----------------------------------------------------------------------------
-- 1) Core tenancy
-- -----------------------------------------------------------------------------
create table if not exists public.organizations (
    id uuid primary key default gen_random_uuid(),
    slug text not null unique,
    name text not null,
    plan text not null default 'starter' check (plan in ('starter', 'growth', 'enterprise')),
    status text not null default 'active' check (status in ('active', 'suspended', 'deleted')),
    settings jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.workspaces (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    workspace_key text not null,
    name text not null,
    region text not null default 'global',
    retention_days integer not null default 365 check (retention_days between 30 and 3650),
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (organization_id, workspace_key)
);

create table if not exists public.client_users (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    external_user_id text not null,
    display_name text,
    email text,
    phone text,
    locale text,
    attributes jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (workspace_id, external_user_id)
);

-- -----------------------------------------------------------------------------
-- 2) Conversation persistence
-- -----------------------------------------------------------------------------
create table if not exists public.conversations (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    client_user_id uuid not null references public.client_users(id) on delete cascade,
    channel text not null check (channel in ('web', 'whatsapp', 'facebook', 'instagram', 'email', 'api', 'other')),
    status text not null default 'active' check (status in ('active', 'resolved', 'closed', 'escalated', 'abandoned')),
    handoff_reason text,
    started_at timestamptz not null default now(),
    last_message_at timestamptz,
    closed_at timestamptz,

    -- persisted counters for fast dashboards
    message_count integer not null default 0,
    user_message_count integer not null default 0,
    assistant_message_count integer not null default 0,
    admin_message_count integer not null default 0,
    handoff_count integer not null default 0,

    -- persisted context window to support next-turn guidance
    last_3_user_messages jsonb not null default '[]'::jsonb,

    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- High-volume messages table partitioned by workspace hash (shard-like distribution)
create table if not exists public.conversation_messages (
    workspace_id uuid not null,
    message_id uuid not null default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    conversation_id uuid not null references public.conversations(id) on delete cascade,

    sender_type text not null check (sender_type in ('user', 'assistant', 'admin', 'system')),
    sender_id text,
    message_text text not null,
    language_code text,
    token_count integer,
    response_time_ms integer,
    model_used text,
    metadata jsonb not null default '{}'::jsonb,

    -- debug/ops field for deterministic shard bucket visibility
    shard_bucket smallint generated always as (
        mod(abs(hashtextextended(workspace_id::text, 0)), 32)
    ) stored,

    created_at timestamptz not null default now(),
    primary key (workspace_id, message_id)
) partition by hash (workspace_id);

-- 8 partitions explicitly defined for Supabase SQL Editor compatibility (avoids % formatting issues)
create table if not exists public.conversation_messages_p0 partition of public.conversation_messages for values with (modulus 8, remainder 0);
create table if not exists public.conversation_messages_p1 partition of public.conversation_messages for values with (modulus 8, remainder 1);
create table if not exists public.conversation_messages_p2 partition of public.conversation_messages for values with (modulus 8, remainder 2);
create table if not exists public.conversation_messages_p3 partition of public.conversation_messages for values with (modulus 8, remainder 3);
create table if not exists public.conversation_messages_p4 partition of public.conversation_messages for values with (modulus 8, remainder 4);
create table if not exists public.conversation_messages_p5 partition of public.conversation_messages for values with (modulus 8, remainder 5);
create table if not exists public.conversation_messages_p6 partition of public.conversation_messages for values with (modulus 8, remainder 6);
create table if not exists public.conversation_messages_p7 partition of public.conversation_messages for values with (modulus 8, remainder 7);

-- Events table for operational + product analytics, also hash partitioned
create table if not exists public.conversation_events (
    workspace_id uuid not null,
    event_id bigint generated always as identity,
    organization_id uuid not null references public.organizations(id) on delete cascade,
    conversation_id uuid not null references public.conversations(id) on delete cascade,
    event_type text not null,
    event_value numeric(14,4),
    payload jsonb not null default '{}'::jsonb,
    event_time timestamptz not null default now(),
    primary key (workspace_id, event_id)
) partition by hash (workspace_id);

-- 8 explicit partitions for conversation events
create table if not exists public.conversation_events_p0 partition of public.conversation_events for values with (modulus 8, remainder 0);
create table if not exists public.conversation_events_p1 partition of public.conversation_events for values with (modulus 8, remainder 1);
create table if not exists public.conversation_events_p2 partition of public.conversation_events for values with (modulus 8, remainder 2);
create table if not exists public.conversation_events_p3 partition of public.conversation_events for values with (modulus 8, remainder 3);
create table if not exists public.conversation_events_p4 partition of public.conversation_events for values with (modulus 8, remainder 4);
create table if not exists public.conversation_events_p5 partition of public.conversation_events for values with (modulus 8, remainder 5);
create table if not exists public.conversation_events_p6 partition of public.conversation_events for values with (modulus 8, remainder 6);
create table if not exists public.conversation_events_p7 partition of public.conversation_events for values with (modulus 8, remainder 7);

-- -----------------------------------------------------------------------------
-- 3) Analytics persistence
-- -----------------------------------------------------------------------------
create table if not exists public.workspace_daily_analytics (
    organization_id uuid not null references public.organizations(id) on delete cascade,
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    metric_date date not null,
    channel text not null default 'all',

    conversations_started integer not null default 0,
    conversations_resolved integer not null default 0,
    escalations integer not null default 0,
    messages_total integer not null default 0,
    avg_first_response_ms numeric(14,2),
    avg_resolution_minutes numeric(14,2),
    csat_avg numeric(5,2),

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (workspace_id, metric_date, channel)
);

-- -----------------------------------------------------------------------------
-- 4) LLM config + validation cache persistence
-- -----------------------------------------------------------------------------
create table if not exists public.llm_provider_configs (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    provider text not null,
    model_name text not null,
    encrypted_api_key text not null,
    is_active boolean not null default true,
    validated_at timestamptz,
    validation_meta jsonb not null default '{}'::jsonb,
    created_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.workspace_model_catalog_cache (
    provider text not null,
    api_key_fingerprint text not null,
    models jsonb not null,
    fetched_at timestamptz not null default now(),
    expires_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (provider, api_key_fingerprint)
);

create table if not exists public.social_channel_connections (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    name text not null,
    provider text not null check (provider in ('meta', 'generic')),
    channel text not null check (channel in ('whatsapp', 'facebook', 'instagram', 'social', 'custom')),
    connection_key text not null unique,
    verify_token_encrypted text,
    access_token_encrypted text,
    app_secret_encrypted text,
    outbound_webhook_url text,
    outbound_auth_headers_encrypted text,
    metadata_json jsonb not null default '{}'::jsonb,
    is_active boolean not null default true,
    created_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    last_event_at timestamptz,
    last_error text
);

-- -----------------------------------------------------------------------------
-- 5) Agent Orchestration (MCP & Checkpoints)
-- -----------------------------------------------------------------------------
create table if not exists public.tenant_mcp_servers (
    id bigint generated always as identity primary key,
    tenant_id text not null,
    workspace_id text not null,
    name text not null,
    connection_type text not null default 'sse',
    connection_url text not null,
    config_json_encrypted text,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.langgraph_checkpoints (
    id bigint generated always as identity primary key,
    thread_id text not null,
    checkpoint_id text not null,
    parent_checkpoint_id text,
    checkpoint_blob bytea not null,
    metadata_blob bytea not null,
    created_at timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- 6) Audit log
-- -----------------------------------------------------------------------------
create table if not exists public.audit_logs (
    id bigint generated always as identity primary key,
    organization_id uuid references public.organizations(id) on delete cascade,
    workspace_id uuid references public.workspaces(id) on delete cascade,
    actor_id text,
    action text not null,
    entity_type text,
    entity_id text,
    before_state jsonb,
    after_state jsonb,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- 7) Index strategy (composite + partial + covering + BRIN + GIN)
-- -----------------------------------------------------------------------------
create index if not exists idx_workspaces_org_active
    on public.workspaces (organization_id, is_active, updated_at desc);

create index if not exists idx_client_users_workspace_external
    on public.client_users (workspace_id, external_user_id);

create index if not exists idx_conversations_workspace_status_last_message
    on public.conversations (workspace_id, status, last_message_at desc);

create index if not exists idx_conversations_user_recent
    on public.conversations (client_user_id, last_message_at desc);

create index if not exists idx_conversations_metadata_gin
    on public.conversations using gin (metadata jsonb_path_ops);

-- Partitioned indexes (applied as local indexes on partitions)
create index if not exists idx_conv_messages_conversation_created
    on public.conversation_messages (conversation_id, created_at desc);

create index if not exists idx_conv_messages_user_context_covering
    on public.conversation_messages (conversation_id, created_at desc)
    include (message_text, language_code)
    where sender_type = 'user';

create index if not exists idx_conv_messages_workspace_created
    on public.conversation_messages (workspace_id, created_at desc);

create index if not exists idx_conv_messages_created_brin
    on public.conversation_messages using brin (created_at);

create index if not exists idx_conv_messages_metadata_gin
    on public.conversation_messages using gin (metadata jsonb_path_ops);

create index if not exists idx_conv_messages_text_trgm
    on public.conversation_messages using gin (message_text gin_trgm_ops);

create index if not exists idx_conv_events_workspace_type_time
    on public.conversation_events (workspace_id, event_type, event_time desc);

create index if not exists idx_conv_events_conversation_time
    on public.conversation_events (conversation_id, event_time desc);

create index if not exists idx_conv_events_payload_gin
    on public.conversation_events using gin (payload jsonb_path_ops);

create index if not exists idx_workspace_daily_analytics_workspace_date
    on public.workspace_daily_analytics (workspace_id, metric_date desc);

create unique index if not exists ux_llm_provider_configs_workspace_active
    on public.llm_provider_configs (workspace_id)
    where is_active = true;

create index if not exists idx_llm_provider_configs_provider_model
    on public.llm_provider_configs (provider, model_name);

create index if not exists idx_model_catalog_cache_expires_at
    on public.workspace_model_catalog_cache (expires_at);

create index if not exists idx_social_connections_workspace_provider_channel
    on public.social_channel_connections (workspace_id, provider, channel, created_at desc);

create index if not exists idx_social_connections_workspace_active
    on public.social_channel_connections (workspace_id, is_active, updated_at desc);

create index if not exists idx_social_connections_metadata_gin
    on public.social_channel_connections using gin (metadata_json jsonb_path_ops);

create index if not exists idx_mcp_servers_tenant_workspace
    on public.tenant_mcp_servers (tenant_id, workspace_id);

create index if not exists idx_langgraph_checkpoints_thread
    on public.langgraph_checkpoints (thread_id);

create index if not exists idx_audit_logs_workspace_created
    on public.audit_logs (workspace_id, created_at desc);

-- -----------------------------------------------------------------------------
-- 7) Trigger helpers
-- -----------------------------------------------------------------------------
create or replace function public.fn_set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_organizations_updated_at on public.organizations;
create trigger trg_organizations_updated_at
before update on public.organizations
for each row execute function public.fn_set_updated_at();

drop trigger if exists trg_workspaces_updated_at on public.workspaces;
create trigger trg_workspaces_updated_at
before update on public.workspaces
for each row execute function public.fn_set_updated_at();

drop trigger if exists trg_client_users_updated_at on public.client_users;
create trigger trg_client_users_updated_at
before update on public.client_users
for each row execute function public.fn_set_updated_at();

drop trigger if exists trg_conversations_updated_at on public.conversations;
create trigger trg_conversations_updated_at
before update on public.conversations
for each row execute function public.fn_set_updated_at();

drop trigger if exists trg_workspace_daily_analytics_updated_at on public.workspace_daily_analytics;
create trigger trg_workspace_daily_analytics_updated_at
before update on public.workspace_daily_analytics
for each row execute function public.fn_set_updated_at();

drop trigger if exists trg_llm_provider_configs_updated_at on public.llm_provider_configs;
create trigger trg_llm_provider_configs_updated_at
before update on public.llm_provider_configs
for each row execute function public.fn_set_updated_at();

drop trigger if exists trg_workspace_model_catalog_cache_updated_at on public.workspace_model_catalog_cache;
create trigger trg_workspace_model_catalog_cache_updated_at
before update on public.workspace_model_catalog_cache
for each row execute function public.fn_set_updated_at();

drop trigger if exists trg_social_channel_connections_updated_at on public.social_channel_connections;
create trigger trg_social_channel_connections_updated_at
before update on public.social_channel_connections
for each row execute function public.fn_set_updated_at();

-- Keep counters + last 3 user messages persisted in conversations for fast runtime context
create or replace function public.fn_sync_conversation_after_message_insert()
returns trigger
language plpgsql
as $$
declare
    v_last_3 jsonb;
begin
    update public.conversations c
    set
        last_message_at = new.created_at,
        message_count = c.message_count + 1,
        user_message_count = c.user_message_count + case when new.sender_type = 'user' then 1 else 0 end,
        assistant_message_count = c.assistant_message_count + case when new.sender_type = 'assistant' then 1 else 0 end,
        admin_message_count = c.admin_message_count + case when new.sender_type = 'admin' then 1 else 0 end,
        updated_at = now()
    where c.id = new.conversation_id;

    if new.sender_type = 'user' then
        v_last_3 := (
            select coalesce(
                jsonb_agg(
                    jsonb_build_object(
                        'text', x.message_text,
                        'at', x.created_at
                    )
                    order by x.created_at desc
                ),
                '[]'::jsonb
            )
            from (
                select m.message_text, m.created_at
                from public.conversation_messages m
                where m.conversation_id = new.conversation_id
                  and m.sender_type = 'user'
                order by m.created_at desc
                limit 3
            ) x
        );

        update public.conversations c
        set last_3_user_messages = v_last_3,
            updated_at = now()
        where c.id = new.conversation_id;
    end if;

    return null;
end;
$$;

drop trigger if exists trg_conversation_messages_after_insert on public.conversation_messages;
create trigger trg_conversation_messages_after_insert
after insert on public.conversation_messages
for each row execute function public.fn_sync_conversation_after_message_insert();

-- -----------------------------------------------------------------------------
-- 9) Analytics materialized view
-- -----------------------------------------------------------------------------
create materialized view if not exists public.mv_workspace_daily_analytics as
select
    c.organization_id,
    c.workspace_id,
    date_trunc('day', m.created_at)::date as metric_date,
    count(distinct c.id) filter (where m.sender_type = 'user') as conversations_with_user_messages,
    count(*) as total_messages,
    count(*) filter (where m.sender_type = 'user') as user_messages,
    count(*) filter (where m.sender_type = 'assistant') as assistant_messages,
    count(*) filter (where c.status = 'escalated') as escalated_rows,
    avg(m.response_time_ms) filter (
        where m.sender_type = 'assistant' and m.response_time_ms is not null
    )::numeric(14,2) as avg_assistant_response_ms
from public.conversations c
join public.conversation_messages m
    on m.conversation_id = c.id
group by c.organization_id, c.workspace_id, date_trunc('day', m.created_at)::date
with no data;

create unique index if not exists ux_mv_workspace_daily_analytics
    on public.mv_workspace_daily_analytics (organization_id, workspace_id, metric_date);

create or replace function public.refresh_workspace_daily_analytics()
returns void
language plpgsql
as $$
begin
    begin
        refresh materialized view concurrently public.mv_workspace_daily_analytics;
    exception when feature_not_supported then
        refresh materialized view public.mv_workspace_daily_analytics;
    end;
end;
$$;

-- Optional scheduler (requires pg_cron access)
do $$
begin
    if exists (select 1 from pg_extension where extname = 'pg_cron') then
        begin
            if not exists (
                select 1 from cron.job where jobname = 'refresh_workspace_daily_analytics_hourly'
            ) then
                perform cron.schedule(
                    'refresh_workspace_daily_analytics_hourly',
                    '15 * * * *',
                    $job$select public.refresh_workspace_daily_analytics();$job$
                );
            end if;
        exception when undefined_table then
            raise notice 'cron.job catalog not accessible; skipping schedule creation';
        end;
    end if;
end $$;

-- -----------------------------------------------------------------------------
-- 10) Access view for runtime context retrieval
-- -----------------------------------------------------------------------------
create or replace view public.v_conversation_runtime_context as
select
    c.id as conversation_id,
    c.organization_id,
    c.workspace_id,
    c.client_user_id,
    c.status,
    c.last_3_user_messages,
    c.last_message_at,
    c.message_count,
    c.user_message_count,
    c.assistant_message_count,
    c.admin_message_count
from public.conversations c;

-- -----------------------------------------------------------------------------
-- 11) RLS helpers + baseline policies (Supabase JWT claims: org_id, workspace_id)
-- -----------------------------------------------------------------------------
create or replace function public.current_org_id()
returns uuid
language plpgsql
stable
as $$
declare
    v_claim text;
begin
    v_claim := coalesce((current_setting('request.jwt.claims', true)::jsonb ->> 'org_id'), '');
    if v_claim = '' then
        return null;
    end if;
    return v_claim::uuid;
exception when others then
    return null;
end;
$$;

create or replace function public.current_workspace_id()
returns uuid
language plpgsql
stable
as $$
declare
    v_claim text;
begin
    v_claim := coalesce((current_setting('request.jwt.claims', true)::jsonb ->> 'workspace_id'), '');
    if v_claim = '' then
        return null;
    end if;
    return v_claim::uuid;
exception when others then
    return null;
end;
$$;

alter table public.organizations enable row level security;
alter table public.workspaces enable row level security;
alter table public.client_users enable row level security;
alter table public.conversations enable row level security;
alter table public.conversation_messages enable row level security;
alter table public.conversation_events enable row level security;
alter table public.workspace_daily_analytics enable row level security;
alter table public.llm_provider_configs enable row level security;
alter table public.social_channel_connections enable row level security;
alter table public.tenant_mcp_servers enable row level security;
alter table public.langgraph_checkpoints enable row level security;

-- Policies are created idempotently.
do $$
begin
    if not exists (
        select 1 from pg_policies
        where schemaname = 'public' and tablename = 'organizations' and policyname = 'organizations_tenant_isolation'
    ) then
        create policy organizations_tenant_isolation on public.organizations
        for all
        using (id = public.current_org_id())
        with check (id = public.current_org_id());
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'public' and tablename = 'workspaces' and policyname = 'workspaces_tenant_isolation'
    ) then
        create policy workspaces_tenant_isolation on public.workspaces
        for all
        using (organization_id = public.current_org_id())
        with check (organization_id = public.current_org_id());
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'public' and tablename = 'client_users' and policyname = 'client_users_scope_isolation'
    ) then
        create policy client_users_scope_isolation on public.client_users
        for all
        using (
            organization_id = public.current_org_id()
            and (public.current_workspace_id() is null or workspace_id = public.current_workspace_id())
        )
        with check (
            organization_id = public.current_org_id()
            and (public.current_workspace_id() is null or workspace_id = public.current_workspace_id())
        );
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'public' and tablename = 'conversations' and policyname = 'conversations_scope_isolation'
    ) then
        create policy conversations_scope_isolation on public.conversations
        for all
        using (
            organization_id = public.current_org_id()
            and (public.current_workspace_id() is null or workspace_id = public.current_workspace_id())
        )
        with check (
            organization_id = public.current_org_id()
            and (public.current_workspace_id() is null or workspace_id = public.current_workspace_id())
        );
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'public' and tablename = 'conversation_messages' and policyname = 'conversation_messages_scope_isolation'
    ) then
        create policy conversation_messages_scope_isolation on public.conversation_messages
        for all
        using (
            organization_id = public.current_org_id()
            and (public.current_workspace_id() is null or workspace_id = public.current_workspace_id())
        )
        with check (
            organization_id = public.current_org_id()
            and (public.current_workspace_id() is null or workspace_id = public.current_workspace_id())
        );
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'public' and tablename = 'conversation_events' and policyname = 'conversation_events_scope_isolation'
    ) then
        create policy conversation_events_scope_isolation on public.conversation_events
        for all
        using (
            organization_id = public.current_org_id()
            and (public.current_workspace_id() is null or workspace_id = public.current_workspace_id())
        )
        with check (
            organization_id = public.current_org_id()
            and (public.current_workspace_id() is null or workspace_id = public.current_workspace_id())
        );
    end if;

    if not exists (
        select 1 from pg_policies
        where schemaname = 'public' and tablename = 'social_channel_connections' and policyname = 'social_channel_connections_scope_isolation'
    ) then
        create policy social_channel_connections_scope_isolation on public.social_channel_connections
        for all
        using (
            organization_id = public.current_org_id()
            and (public.current_workspace_id() is null or workspace_id = public.current_workspace_id())
        )
        with check (
            organization_id = public.current_org_id()
            and (public.current_workspace_id() is null or workspace_id = public.current_workspace_id())
        );
    end if;
end $$;

commit;
