import type { CSSProperties } from "react"
import {
  Activity,
  ArrowUpRight,
  Clock3,
  Gauge,
  MessageSquareWarning,
  Shield,
  Sparkles,
  Zap,
} from "lucide-react"

import { getDashboardAnalytics } from "@/lib/tenant-analytics"
import { createClient } from "@/lib/supabase/server"

function clamp(value: number, min = 0, max = 100): number {
  return Math.min(Math.max(value, min), max)
}

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`
}

function formatMetric(value: number, unit = ""): string {
  const rounded = Number.isInteger(value) ? value.toString() : value.toFixed(1)
  return `${rounded}${unit}`
}

function formatLargeNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value)
}

function formatRelativeIsoTime(value: string | null): string {
  if (!value) {
    return "Unknown timestamp"
  }

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }

  return parsed.toLocaleString()
}

function delay(ms: number): CSSProperties {
  return { animationDelay: `${ms}ms` }
}

function statusTone(status: string): string {
  if (status === "breached") {
    return "border-rose-500/50 bg-rose-500/10 text-rose-200"
  }
  if (status === "warning") {
    return "border-amber-500/50 bg-amber-500/10 text-amber-300"
  }
  return "border-lime-500/30 bg-lime-500/10 text-lime-400"
}

export default async function DashboardPage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  const { data: { session } } = user ? await supabase.auth.getSession() : { data: { session: null } }

  const analytics = await getDashboardAnalytics(30, {
    tenantId: user?.id,
    workspaceId: user?.id,
    accessToken: session?.access_token,
  })

  const healthScore = clamp(analytics.overview.health_score)
  const healthRingStyle: CSSProperties = {
    background: `conic-gradient(rgba(163,230,53,0.95) ${healthScore}%, rgba(163,230,53,0.28) ${healthScore}% 100%)`,
  }

  const primaryCards = [
    {
      label: "Total Events",
      value: formatLargeNumber(analytics.overview.total_events),
      sub: "Rolling 30 days",
      icon: Activity,
    },
    {
      label: "Conversations",
      value: formatLargeNumber(analytics.overview.total_conversations),
      sub: "Customer sessions",
      icon: MessageSquareWarning,
    },
    {
      label: "Auto Resolution",
      value: formatPercent(analytics.ai.auto_resolution_rate),
      sub: `${formatLargeNumber(analytics.overview.ai_resolved_count)} AI-resolved`,
      icon: Zap,
    },
    {
      label: "Avg Latency",
      value: formatMetric(analytics.overview.avg_response_time_ms, "ms"),
      sub: "Cross-channel average",
      icon: Clock3,
    },
  ]

  const channels = analytics.channel.channels.slice(0, 4)
  const alerts = analytics.alerts.events.slice(0, 4)

  return (
    <div className="futuristic-bg h-full overflow-auto p-3 sm:p-5 lg:p-7">
      <div className="relative z-10 mx-auto max-w-420 space-y-5">
        <section className="apex-panel enter-rise relative overflow-hidden rounded-[28px] border border-lime-500/20 p-5 sm:p-6 lg:p-8">
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,transparent,rgba(163,230,53,0.05)_50%,transparent)]" />
          <div className="apex-arc hidden xl:block" />
          <div className="apex-arc-soft hidden xl:block" />

          <div className="relative z-10 flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-500">YouBot Experience Console</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-lime-50 sm:text-4xl">Operations Dashboard</h1>
              <p className="mt-2 text-base text-lime-50/78">
                High-level product health and performance without surfacing internal infrastructure details.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className={`rounded-full border px-3 py-1.5 ${statusTone(analytics.usage.status)}`}>
                {analytics.usage.status.replace(/_/g, " ").toUpperCase()}
              </span>
            </div>
          </div>

          <div className="relative z-10 mt-7 grid gap-4 lg:grid-cols-[1.5fr_1fr]">
              <div className="rounded-2xl border border-lime-500/15 bg-black/60 p-5">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-semibold text-lime-50">System Throughput</h2>
                <Sparkles className="size-4 text-lime-400" />
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {primaryCards.map((card, index) => (
                  <div
                    key={card.label}
                    className="enter-rise rounded-xl border border-lime-500/15 bg-black/60 p-4"
                    style={delay(70 + index * 40)}
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-sm text-slate-400">{card.label}</p>
                      <card.icon className="size-4 text-lime-400" />
                    </div>
                    <p className="mt-2 text-2xl font-semibold text-lime-50">{card.value}</p>
                    <p className="text-xs text-slate-500">{card.sub}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-lime-500/15 bg-black/60 p-5">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-semibold text-lime-50">Health Index</h2>
                <Gauge className="size-4 text-lime-400" />
              </div>
              <div className="mt-5 flex items-center gap-4">
                <div className="grid size-24 place-items-center rounded-full p-2" style={healthRingStyle}>
                  <div className="grid size-full place-items-center rounded-full bg-black/80">
                    <p className="text-2xl font-semibold text-lime-50">{healthScore.toFixed(0)}</p>
                  </div>
                </div>
                <div>
                  <p className="text-sm text-lime-50/76">Composite reliability score</p>
                  <p className="text-xs text-slate-500">Window {analytics.meta.windowDays} days</p>
                </div>
              </div>

              <div className="mt-5 rounded-xl border border-lime-500/15 bg-black/60 p-4">
                <p className="text-xs uppercase tracking-wider text-slate-500">Quota Outlook</p>
                <p className="mt-2 text-sm text-lime-50/76">
                  {formatLargeNumber(analytics.usage.usage.rolling_30d_events)} events / {formatLargeNumber(analytics.usage.quota.monthly_events)} monthly
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-5 xl:grid-cols-12">
          <div className="apex-panel enter-rise rounded-2xl border border-lime-500/15 p-5 xl:col-span-7" style={delay(180)}>
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-lime-50">Platform Updates</h2>
              <button className="inline-flex items-center gap-1 rounded-full border border-lime-500/30 bg-lime-500/5 px-3 py-1 text-xs text-lime-400">
                View all
                <ArrowUpRight className="size-3.5" />
              </button>
            </div>

            <div className="mt-4 space-y-3">
              <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
                <p className="text-sm font-medium text-lime-50">Model policy refresh completed</p>
                <p className="mt-1 text-xs text-slate-500">Core configuration is in sync.</p>
              </div>
              <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
                <p className="text-sm font-medium text-lime-50">Knowledge status updated</p>
                <p className="mt-1 text-xs text-slate-500">Content freshness and retrieval health are being monitored.</p>
              </div>
              <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
                <p className="text-sm font-medium text-lime-50">Supervision watch active</p>
                <p className="mt-1 text-xs text-slate-500">Escalations and response quality are actively monitored.</p>
              </div>
            </div>
          </div>

          <div className="apex-panel enter-rise rounded-2xl border border-lime-500/15 p-5 xl:col-span-5" style={delay(240)}>
            <h2 className="text-lg font-semibold text-lime-50">Channel Split</h2>
            <p className="mt-1 text-sm text-slate-400">Traffic and p95 latency by channel</p>

            <div className="mt-4 space-y-3">
              {channels.length === 0 && (
                <p className="rounded-xl border border-lime-500/15 bg-black/60 p-4 text-sm text-slate-400">
                  No channel data found for this window.
                </p>
              )}

              {channels.map((channel) => {
                const share = analytics.channel.total_events ? (channel.events / analytics.channel.total_events) * 100 : 0

                return (
                  <div key={channel.channel} className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium capitalize text-lime-50">{channel.channel}</p>
                      <p className="text-xs text-slate-400">
                        {formatLargeNumber(channel.events)} events | p95 {formatMetric(channel.p95_response_latency_ms, "ms")}
                      </p>
                    </div>
                    <div className="mt-3 h-2 overflow-hidden rounded-full bg-lime-950/65">
                      <div className="progress-glow h-full rounded-full" style={{ width: `${clamp(share)}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </section>

        <section className="apex-panel enter-rise rounded-2xl border border-lime-500/15 p-5" style={delay(300)}>
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-lime-50">Live Alert Feed</h2>
            <Shield className="size-4 text-lime-400/78" />
          </div>

          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {alerts.length === 0 && (
              <p className="rounded-xl border border-lime-500/15 bg-black/60 p-4 text-sm text-slate-400">
                No alert events generated yet.
              </p>
            )}

            {alerts.map((alert) => (
              <div key={alert.id} className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium text-lime-50">{alert.rule_name ?? "Quota Guard"}</p>
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${statusTone(alert.status)}`}>
                    {alert.status}
                  </span>
                </div>
                <p className="mt-2 text-xs text-slate-400">{alert.message}</p>
                <p className="mt-2 text-[11px] text-slate-500">{formatRelativeIsoTime(alert.event_time)}</p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
