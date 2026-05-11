"use client"

import { Check, Loader2, Save, Sparkles } from "lucide-react"
import { useState } from "react"

import { consoleProxy } from "@/lib/console-proxy-client"

type RetrievalMode = "rag" | "hybrid" | "page_index"

export type RetrievalProfile = {
  default_mode?: string
  allowed_modes?: string[]
  page_window_limit?: number
  compliance_criticality?: number
  average_document_pages?: number
  query_complexity?: number
  latency_budget_ms?: number
  cost_sensitivity?: number
}

type ProfileResponse = {
  status?: string
  profile?: RetrievalProfile
}

type Props = {
  initialProfile: RetrievalProfile | null
  initialOverride?: RetrievalMode | null
}

const MODES: Array<{
  value: RetrievalMode
  label: string
  description: string
  fits: string
}> = [
  {
    value: "rag",
    label: "Quick Answer",
    description: "Fast, low-cost lookup over short snippets.",
    fits: "FAQs, support replies, simple knowledge.",
  },
  {
    value: "hybrid",
    label: "Balanced Search",
    description: "Combines meaning with exact-word matching.",
    fits: "Product specs, named policies, version numbers.",
  },
  {
    value: "page_index",
    label: "Deep Context",
    description: "Loads whole pages so context isn't cut off.",
    fits: "Legal contracts, case files, long policies.",
  },
]

function normalizeMode(value: string | undefined | null, fallback: RetrievalMode = "rag"): RetrievalMode {
  if (value === "rag" || value === "hybrid" || value === "page_index") return value
  return fallback
}

export function RetrievalProfileForm({ initialProfile, initialOverride }: Props) {
  const startingMode = normalizeMode(
    initialOverride ?? initialProfile?.default_mode,
    "rag",
  )
  const startingAllowed = (() => {
    const allowed = (initialProfile?.allowed_modes ?? ["rag"]) as string[]
    const cleaned = new Set<RetrievalMode>()
    for (const m of allowed) {
      if (m === "rag" || m === "hybrid" || m === "page_index") cleaned.add(m)
    }
    cleaned.add(startingMode)
    return cleaned
  })()

  const [defaultMode, setDefaultMode] = useState<RetrievalMode>(startingMode)
  const [allowedModes, setAllowedModes] = useState<Set<RetrievalMode>>(startingAllowed)
  const [pageWindowLimit, setPageWindowLimit] = useState<number>(
    initialProfile?.page_window_limit ?? 4,
  )
  const [averagePages, setAveragePages] = useState<number>(
    initialProfile?.average_document_pages ?? 10,
  )
  const [latencyBudget, setLatencyBudget] = useState<number>(
    initialProfile?.latency_budget_ms ?? 2500,
  )
  const [busy, setBusy] = useState(false)
  const [statusMsg, setStatusMsg] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const toggleAllowed = (mode: RetrievalMode) => {
    setAllowedModes((prev) => {
      const next = new Set(prev)
      if (next.has(mode)) {
        if (mode !== defaultMode) next.delete(mode)
      } else {
        next.add(mode)
      }
      return next
    })
  }

  const save = async () => {
    setBusy(true)
    setStatusMsg(null)
    setErrorMsg(null)

    const allowed = Array.from(allowedModes)
    if (!allowed.includes(defaultMode)) allowed.push(defaultMode)

    const result = await consoleProxy<ProfileResponse>({
      path: "/admin/retrieval/profile",
      method: "POST",
      body: {
        defaultMode,
        allowedModes: allowed,
        pageWindowLimit: Math.max(1, Math.min(20, pageWindowLimit)),
        averageDocumentPages: Math.max(1, averagePages),
        latencyBudgetMs: Math.max(300, latencyBudget),
      },
    })

    if (result.ok && result.data?.profile) {
      setStatusMsg("Saved. New customer messages will use this style.")
    } else {
      setErrorMsg(result.error ?? `HTTP ${result.status}`)
    }
    setBusy(false)
  }

  return (
    <section className="rounded-2xl border border-lime-500/20 bg-black/40 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold text-lime-50">
            <Sparkles className="h-4 w-4 text-lime-400" />
            Bot behaviour
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Pick how your bot should look up answers in production. The sandbox lets you try
            modes; this is the one that&apos;s actually used when customers chat.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void save()}
          disabled={busy}
          className="flex items-center gap-2 rounded-lg border border-lime-500/30 bg-lime-500/15 px-3 py-1.5 text-xs font-medium text-lime-400 transition hover:border-lime-500/50 hover:bg-lime-500/25 disabled:opacity-40"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
          Save
        </button>
      </div>

      {(statusMsg || errorMsg) && (
        <div
          className={
            "mt-3 rounded-lg border px-3 py-2 text-xs " +
            (errorMsg
              ? "border-rose-500/30 bg-rose-500/10 text-rose-300"
              : "border-emerald-500/30 bg-emerald-500/10 text-emerald-300")
          }
        >
          {errorMsg ?? statusMsg}
        </div>
      )}

      {/* Default mode picker */}
      <div className="mt-4">
        <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-slate-500">
          Default lookup style
        </p>
        <fieldset className="grid gap-2 md:grid-cols-3">
          <legend className="sr-only">Default retrieval mode</legend>
          {MODES.map((m) => {
            const active = defaultMode === m.value
            return (
              <label
                key={m.value}
                className={
                  "cursor-pointer rounded-xl border p-3 transition " +
                  (active
                    ? "border-lime-500/50 bg-lime-500/10"
                    : "border-lime-500/15 bg-black/50 hover:border-lime-500/30 hover:bg-lime-500/5")
                }
              >
                <input
                  type="radio"
                  name="default-mode"
                  value={m.value}
                  checked={active}
                  onChange={() => {
                    setDefaultMode(m.value)
                    setAllowedModes((prev) => {
                      const next = new Set(prev)
                      next.add(m.value)
                      return next
                    })
                  }}
                  className="sr-only"
                />
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-lime-50">{m.label}</p>
                  {active && <Check className="h-3.5 w-3.5 text-lime-400" />}
                </div>
                <p className="mt-1 text-[11px] leading-snug text-slate-400">{m.description}</p>
                <p className="mt-2 text-[10px] leading-snug text-slate-500">
                  <span className="text-slate-400">Best for:</span> {m.fits}
                </p>
              </label>
            )
          })}
        </fieldset>
      </div>

      {/* Allowed modes */}
      <div className="mt-4">
        <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-slate-500">
          Also allow the auto-router to pick from
        </p>
        <p className="mb-2 text-xs text-slate-500">
          When &quot;Smart Auto&quot; is on, the bot can fall back to these modes for tricky
          queries. The default above is always allowed.
        </p>
        <div className="flex flex-wrap gap-2">
          {MODES.map((m) => {
            const checked = allowedModes.has(m.value)
            const isDefault = m.value === defaultMode
            return (
              <button
                key={m.value}
                type="button"
                onClick={() => !isDefault && toggleAllowed(m.value)}
                disabled={isDefault}
                className={
                  "rounded-lg border px-3 py-1.5 text-xs transition " +
                  (checked
                    ? "border-lime-500/40 bg-lime-500/15 text-lime-300"
                    : "border-lime-500/15 bg-black/50 text-slate-400 hover:border-lime-500/30") +
                  (isDefault ? " opacity-90 cursor-default" : "")
                }
              >
                {m.label}
                {isDefault && <span className="ml-1 text-slate-500">(default)</span>}
              </button>
            )
          })}
        </div>
      </div>

      {/* Tuning knobs */}
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <label className="rounded-xl border border-lime-500/15 bg-black/50 p-3">
          <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
            Pages of context (Deep Context only)
          </span>
          <input
            type="number"
            min={1}
            max={20}
            value={pageWindowLimit}
            onChange={(e) => setPageWindowLimit(Number(e.target.value) || 4)}
            className="mt-2 w-full rounded-lg border border-lime-500/20 bg-black/60 px-2 py-1.5 text-sm text-lime-50 outline-none focus:border-lime-500/50"
          />
          <span className="mt-1 block text-[10px] text-slate-500">
            How many full pages to send the model per question. 4 is balanced.
          </span>
        </label>
        <label className="rounded-xl border border-lime-500/15 bg-black/50 p-3">
          <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
            Typical doc length
          </span>
          <input
            type="number"
            min={1}
            value={averagePages}
            onChange={(e) => setAveragePages(Number(e.target.value) || 10)}
            className="mt-2 w-full rounded-lg border border-lime-500/20 bg-black/60 px-2 py-1.5 text-sm text-lime-50 outline-none focus:border-lime-500/50"
          />
          <span className="mt-1 block text-[10px] text-slate-500">
            Average pages per source document. Helps Smart Auto pick the right mode.
          </span>
        </label>
        <label className="rounded-xl border border-lime-500/15 bg-black/50 p-3">
          <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
            Speed budget (ms)
          </span>
          <input
            type="number"
            min={300}
            step={100}
            value={latencyBudget}
            onChange={(e) => setLatencyBudget(Number(e.target.value) || 2500)}
            className="mt-2 w-full rounded-lg border border-lime-500/20 bg-black/60 px-2 py-1.5 text-sm text-lime-50 outline-none focus:border-lime-500/50"
          />
          <span className="mt-1 block text-[10px] text-slate-500">
            How fast the bot should answer. Tighter budget biases Smart Auto toward Quick Answer.
          </span>
        </label>
      </div>

      <p className="mt-4 text-xs text-slate-500">
        These settings affect the live bot. Use the{" "}
        <a className="text-lime-400 underline-offset-2 hover:underline" href="/chat-tests">
          Bot Testing Sandbox
        </a>{" "}
        to compare modes on real questions before committing.
      </p>
    </section>
  )
}
