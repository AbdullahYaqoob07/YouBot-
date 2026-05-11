type ApiEnvelope<T> = {
  status: string
  data: T
}

type QuotaStatus = "healthy" | "warning" | "breached" | string

type UtilizationValue = number | null

export type OverviewMetrics = {
  window_days: number
  health_score: number
  total_events: number
  total_conversations: number
  ai_resolved_count: number
  handoff_count: number
  auto_resolution_rate: number
  fallback_rate: number
  kb_hit_rate: number
  avg_response_time_ms: number
}

export type UserPerformanceMetrics = {
  window_days: number
  total_users: number
  total_conversations: number
  resolved_sessions: number
  completion_rate: number
  repeat_contact_rate_24h: number
  repeat_contact_rate_7d: number
  dropoff_rate: number
  time_to_first_meaningful_response_ms: number
  sentiment_distribution: Record<string, number>
  outcomes_distribution: Record<string, number>
}

export type AiModelMetric = {
  model: string
  events: number
  avg_response_time_ms: number
  auto_resolution_rate: number
  handoff_rate: number
}

export type AiPerformanceMetrics = {
  window_days: number
  total_events: number
  auto_resolution_rate: number
  fallback_rate: number
  kb_hit_rate: number
  low_confidence_response_ratio: number
  hallucination_risk_proxy_rate: number
  avg_unsolved_score: number
  avg_response_time_ms: number
  models: AiModelMetric[]
}

export type TeamPerformanceMetrics = {
  window_days: number
  handoffs: number
  queue_status_counts: Record<string, number>
  avg_queue_wait_minutes: number
  first_takeover_response_time_minutes: number
  avg_handling_time_minutes: number
  sla_breach_rate: number
  resolved_count: number
}

export type KbTrendPoint = {
  day: string
  unanswered: number
}

export type KbSourceQuality = {
  source_type: string
  total_jobs: number
  success_rate: number
  failure_rate: number
}

export type KbPerformanceMetrics = {
  window_days: number
  total_events: number
  retrieval_hit_rate: number
  citation_coverage_rate: number
  unanswered_questions: number
  unanswered_question_trend: KbTrendPoint[]
  knowledge_freshness_score: number
  source_volume: Record<string, number>
  source_quality: KbSourceQuality[]
}

export type ChannelMetric = {
  channel: string
  events: number
  avg_response_time_ms: number
  auto_resolution_rate: number
  handoff_rate: number
  p50_response_latency_ms: number
  p95_response_latency_ms: number
}

export type ChannelPerformanceMetrics = {
  window_days: number
  total_events: number
  channels: ChannelMetric[]
}

export type UsageGovernanceMetrics = {
  tenant_plan: string
  usage: {
    window_days: number
    events: number
    conversations: number
    active_users: number
    rolling_30d_events: number
    rolling_30d_conversations: number
    active_alert_rules: number
  }
  quota: {
    monthly_events: number | null
    monthly_conversations: number | null
    active_alert_rules: number | null
  }
  utilization: {
    monthly_events_pct: UtilizationValue
    monthly_conversations_pct: UtilizationValue
    active_alert_rules_pct: UtilizationValue
  }
  status: QuotaStatus
  near_limit: string[]
  exceeded: string[]
}

export type QuotaGovernanceMetrics = {
  tenant_plan: string
  status: QuotaStatus
  usage: UsageGovernanceMetrics["usage"]
  quota: UsageGovernanceMetrics["quota"]
  utilization: UsageGovernanceMetrics["utilization"]
  forecast: {
    avg_daily_events: number
    avg_daily_conversations: number
    events_days_until_quota: number | null
    conversations_days_until_quota: number | null
    alert_rule_slots_remaining: number | null
  }
  recommendations: string[]
}

export type AlertEvent = {
  id: number
  rule_id: number | null
  rule_name: string | null
  metric_value: number
  message: string
  status: string
  event_time: string | null
}

export type AlertEventsMetrics = {
  window_days: number
  count: number
  events: AlertEvent[]
}

export type DashboardAnalyticsData = {
  overview: OverviewMetrics
  user: UserPerformanceMetrics
  ai: AiPerformanceMetrics
  team: TeamPerformanceMetrics
  kb: KbPerformanceMetrics
  channel: ChannelPerformanceMetrics
  usage: UsageGovernanceMetrics
  quota: QuotaGovernanceMetrics
  alerts: AlertEventsMetrics
  meta: {
    baseUrl: string
    tenantId: string
    workspaceId: string
    windowDays: number
    live: boolean
    partial: boolean
    issues: string[]
    generatedAt: string
  }
}

function getRuntimeConfig() {
  const baseUrlRaw =
    process.env.YOUBOT_API_BASE_URL ??
    process.env.NEXT_PUBLIC_YOUBOT_API_BASE_URL ??
    "http://127.0.0.1:8000"

  const adminKey =
    process.env.YOUBOT_ADMIN_API_KEY ??
    process.env.ADMIN_API_KEY ??
    process.env.NEXT_PUBLIC_ADMIN_API_KEY ??
    ""

  return {
    baseUrl: baseUrlRaw.replace(/\/+$/, ""),
    adminKey,
    tenantId: process.env.YOUBOT_TENANT_ID ?? "public",
    workspaceId: process.env.YOUBOT_WORKSPACE_ID ?? "default",
  }
}

function defaultAnalytics(days: number): Omit<DashboardAnalyticsData, "meta"> {
  return {
    overview: {
      window_days: days,
      health_score: 0,
      total_events: 0,
      total_conversations: 0,
      ai_resolved_count: 0,
      handoff_count: 0,
      auto_resolution_rate: 0,
      fallback_rate: 0,
      kb_hit_rate: 0,
      avg_response_time_ms: 0,
    },
    user: {
      window_days: days,
      total_users: 0,
      total_conversations: 0,
      resolved_sessions: 0,
      completion_rate: 0,
      repeat_contact_rate_24h: 0,
      repeat_contact_rate_7d: 0,
      dropoff_rate: 0,
      time_to_first_meaningful_response_ms: 0,
      sentiment_distribution: {},
      outcomes_distribution: {},
    },
    ai: {
      window_days: days,
      total_events: 0,
      auto_resolution_rate: 0,
      fallback_rate: 0,
      kb_hit_rate: 0,
      low_confidence_response_ratio: 0,
      hallucination_risk_proxy_rate: 0,
      avg_unsolved_score: 0,
      avg_response_time_ms: 0,
      models: [],
    },
    team: {
      window_days: days,
      handoffs: 0,
      queue_status_counts: {},
      avg_queue_wait_minutes: 0,
      first_takeover_response_time_minutes: 0,
      avg_handling_time_minutes: 0,
      sla_breach_rate: 0,
      resolved_count: 0,
    },
    kb: {
      window_days: days,
      total_events: 0,
      retrieval_hit_rate: 0,
      citation_coverage_rate: 0,
      unanswered_questions: 0,
      unanswered_question_trend: [],
      knowledge_freshness_score: 0,
      source_volume: {},
      source_quality: [],
    },
    channel: {
      window_days: days,
      total_events: 0,
      channels: [],
    },
    usage: {
      tenant_plan: "starter",
      usage: {
        window_days: days,
        events: 0,
        conversations: 0,
        active_users: 0,
        rolling_30d_events: 0,
        rolling_30d_conversations: 0,
        active_alert_rules: 0,
      },
      quota: {
        monthly_events: 10000,
        monthly_conversations: 2000,
        active_alert_rules: 5,
      },
      utilization: {
        monthly_events_pct: 0,
        monthly_conversations_pct: 0,
        active_alert_rules_pct: 0,
      },
      status: "healthy",
      near_limit: [],
      exceeded: [],
    },
    quota: {
      tenant_plan: "starter",
      status: "healthy",
      usage: {
        window_days: days,
        events: 0,
        conversations: 0,
        active_users: 0,
        rolling_30d_events: 0,
        rolling_30d_conversations: 0,
        active_alert_rules: 0,
      },
      quota: {
        monthly_events: 10000,
        monthly_conversations: 2000,
        active_alert_rules: 5,
      },
      utilization: {
        monthly_events_pct: 0,
        monthly_conversations_pct: 0,
        active_alert_rules_pct: 0,
      },
      forecast: {
        avg_daily_events: 0,
        avg_daily_conversations: 0,
        events_days_until_quota: null,
        conversations_days_until_quota: null,
        alert_rule_slots_remaining: 5,
      },
      recommendations: ["Connect backend analytics to view plan forecasts."],
    },
    alerts: {
      window_days: days,
      count: 0,
      events: [],
    },
  }
}

async function fetchDomain<T>(
  baseUrl: string,
  path: string,
  headers: Record<string, string>,
): Promise<{ data: T | null; error: string | null }> {
  const url = `${baseUrl}${path}`

  try {
    const response = await fetch(url, {
      method: "GET",
      headers,
      cache: "no-store",
    })

    if (!response.ok) {
      return {
        data: null,
        error: `${path} returned ${response.status} ${response.statusText}`,
      }
    }

    const payload = (await response.json()) as ApiEnvelope<T>
    if (!payload || typeof payload !== "object" || payload.data === undefined) {
      return {
        data: null,
        error: `${path} returned an unexpected payload shape`,
      }
    }

    return {
      data: payload.data,
      error: null,
    }
  } catch (error) {
    return {
      data: null,
      error: `${path} fetch failed: ${error instanceof Error ? error.message : "Unknown error"}`,
    }
  }
}

type DashboardFetchOptions = {
  tenantId?: string
  workspaceId?: string
  accessToken?: string
}

export async function getDashboardAnalytics(
  days = 30,
  fetchOptions?: DashboardFetchOptions,
): Promise<DashboardAnalyticsData> {
  const config = getRuntimeConfig()
  const defaults = defaultAnalytics(days)
  const issues: string[] = []

  const tenantId = fetchOptions?.tenantId ?? config.tenantId
  const workspaceId = fetchOptions?.workspaceId ?? config.workspaceId

  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Tenant-Id": tenantId,
    "X-Workspace-Id": workspaceId,
  }

  if (fetchOptions?.accessToken) {
    headers["Authorization"] = `Bearer ${fetchOptions.accessToken}`
  } else if (config.adminKey) {
    headers["X-Admin-Key"] = config.adminKey
  } else {
    issues.push("Missing admin key. Set YOUBOT_ADMIN_API_KEY or ADMIN_API_KEY for live analytics.")
  }

  const [
    overviewRes,
    userRes,
    aiRes,
    teamRes,
    kbRes,
    channelRes,
    usageRes,
    quotaRes,
    alertsRes,
  ] = await Promise.all([
    fetchDomain<OverviewMetrics>(config.baseUrl, `/tenant-analytics/overview?days=${days}`, headers),
    fetchDomain<UserPerformanceMetrics>(config.baseUrl, `/tenant-analytics/user-performance?days=${days}`, headers),
    fetchDomain<AiPerformanceMetrics>(config.baseUrl, `/tenant-analytics/ai-performance?days=${days}`, headers),
    fetchDomain<TeamPerformanceMetrics>(config.baseUrl, `/tenant-analytics/team-performance?days=${days}`, headers),
    fetchDomain<KbPerformanceMetrics>(config.baseUrl, `/tenant-analytics/kb-performance?days=${days}`, headers),
    fetchDomain<ChannelPerformanceMetrics>(config.baseUrl, `/tenant-analytics/channel-performance?days=${days}`, headers),
    fetchDomain<UsageGovernanceMetrics>(config.baseUrl, `/tenant-analytics/governance/usage?days=${days}`, headers),
    fetchDomain<QuotaGovernanceMetrics>(config.baseUrl, `/tenant-analytics/governance/quota?days=${days}`, headers),
    fetchDomain<AlertEventsMetrics>(config.baseUrl, `/tenant-analytics/alerts/events?days=${days}&limit=5`, headers),
  ])

  const fetchErrors = [
    overviewRes.error,
    userRes.error,
    aiRes.error,
    teamRes.error,
    kbRes.error,
    channelRes.error,
    usageRes.error,
    quotaRes.error,
    alertsRes.error,
  ].filter((value): value is string => Boolean(value))

  issues.push(...fetchErrors)

  const liveDomainCount = [
    overviewRes,
    userRes,
    aiRes,
    teamRes,
    kbRes,
    channelRes,
    usageRes,
    quotaRes,
    alertsRes,
  ].filter((domain) => domain.data !== null).length

  const totalDomains = 9
  const live = liveDomainCount > 0
  const partial = liveDomainCount > 0 && liveDomainCount < totalDomains

  return {
    overview: overviewRes.data ?? defaults.overview,
    user: userRes.data ?? defaults.user,
    ai: aiRes.data ?? defaults.ai,
    team: teamRes.data ?? defaults.team,
    kb: kbRes.data ?? defaults.kb,
    channel: channelRes.data ?? defaults.channel,
    usage: usageRes.data ?? defaults.usage,
    quota: quotaRes.data ?? defaults.quota,
    alerts: alertsRes.data ?? defaults.alerts,
    meta: {
      baseUrl: config.baseUrl,
      tenantId: tenantId,
      workspaceId: workspaceId,
      windowDays: days,
      live,
      partial,
      issues,
      generatedAt: new Date().toISOString(),
    },
  }
}
