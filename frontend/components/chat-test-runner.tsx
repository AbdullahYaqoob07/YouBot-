"use client"

import { Bot, BookmarkCheck, Loader2, RotateCcw, Send, Sparkles, User } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { consoleProxy } from "@/lib/console-proxy-client"

type RetrievalMode = "auto" | "rag" | "hybrid" | "page_index"

type TestChatResponse = {
  ok: boolean
  sessionId: string
  userId: string
  response: string
  language?: string | null
  modelUsed?: string | null
  knowledgeBaseUsed: boolean
  cacheHit: boolean
  requiresHuman: boolean
  handoffReason?: string | null
  retrieval: {
    requestedOverride?: string | null
    selectedMode?: string | null
    recommendedMode?: string | null
    reason?: string | null
  }
  elapsedMs: number
}

type ChatTurn = {
  id: string
  who: "user" | "bot" | "system"
  text: string
  diagnostics?: TestChatResponse
  error?: string
}

type ModeOption = {
  value: RetrievalMode
  label: string
  technical: string
  description: string
  bestFor: string
  recommended?: boolean
}

const MODE_OPTIONS: ModeOption[] = [
  {
    value: "auto",
    label: "Smart Auto",
    technical: "Workspace default + per-query routing",
    description: "Lets the system pick the best mode for each question.",
    bestFor: "Mixed customer support — when you're not sure.",
    recommended: true,
  },
  {
    value: "rag",
    label: "Quick Answer",
    technical: "RAG · vector search over chunks",
    description: "Fastest and cheapest. Pulls short, focused snippets.",
    bestFor: "FAQ-style questions, short policies, simple lookups.",
  },
  {
    value: "hybrid",
    label: "Balanced Search",
    technical: "Hybrid · vector + keyword rerank",
    description: "Combines meaning with exact-word matching.",
    bestFor: "Product names, version numbers, named policies, rare terms.",
  },
  {
    value: "page_index",
    label: "Deep Context",
    technical: "Page Index · full pages + neighbours",
    description: "Loads whole pages around each match so context isn't cut off.",
    bestFor: "Legal documents, contracts, case files, long policies.",
  },
]

const SAMPLE_PROMPTS = [
  "What services do you offer?",
  "How much does it cost?",
  "How can I get in touch with someone?",
  "Can you do something completely unrelated to your business?",
]

type ChatTestRunnerProps = {
  workspaceId: string
}

function shortMode(mode?: string | null): string {
  if (!mode) return "—"
  return mode.replace("_", " ")
}

export function ChatTestRunner({ workspaceId }: ChatTestRunnerProps) {
  const [mode, setMode] = useState<RetrievalMode>("auto")
  const [input, setInput] = useState("")
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [savingDefault, setSavingDefault] = useState(false)
  const [savedDefault, setSavedDefault] = useState<RetrievalMode | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [turns])

  const sendMessage = async (rawText?: string) => {
    const text = (rawText ?? input).trim()
    if (!text || busy) return

    setTurns((prev) => [...prev, { id: `u-${Date.now()}`, who: "user", text }])
    setInput("")
    setBusy(true)

    const result = await consoleProxy<TestChatResponse>({
      path: `/admin/workspaces/${workspaceId}/test-chat`,
      method: "POST",
      body: {
        message: text,
        retrievalMode: mode === "auto" ? null : mode,
        sessionId,
        channel: "admin_test",
      },
    })

    if (!result.ok || !result.data) {
      setTurns((prev) => [
        ...prev,
        {
          id: `e-${Date.now()}`,
          who: "system",
          text: "Test failed",
          error: result.error ?? `HTTP ${result.status}`,
        },
      ])
      setBusy(false)
      return
    }

    const data = result.data
    if (data.sessionId && data.sessionId !== sessionId) {
      setSessionId(data.sessionId)
    }

    setTurns((prev) => [
      ...prev,
      {
        id: `b-${Date.now()}`,
        who: "bot",
        text:
          data.response ||
          (data.requiresHuman ? "(handed off to a human admin)" : "(empty response)"),
        diagnostics: data,
      },
    ])
    setBusy(false)
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault()
      void sendMessage()
    }
  }

  const reset = () => {
    setTurns([])
    setSessionId(null)
  }

  const saveAsDefault = async () => {
    if (mode === "auto" || savingDefault) return
    setSavingDefault(true)
    setSaveError(null)

    // Read current profile so we don't clobber other knobs.
    const current = await consoleProxy<{
      status?: string
      profile?: {
        default_mode?: string
        allowed_modes?: string[]
        page_window_limit?: number
        average_document_pages?: number
        latency_budget_ms?: number
      } | null
    }>({ path: "/admin/retrieval/profile", method: "GET" })

    const profile = current.data?.profile ?? null
    const allowed = new Set<string>(profile?.allowed_modes ?? [])
    allowed.add(mode)

    const result = await consoleProxy<unknown>({
      path: "/admin/retrieval/profile",
      method: "POST",
      body: {
        defaultMode: mode,
        allowedModes: Array.from(allowed),
        pageWindowLimit: profile?.page_window_limit ?? 4,
        averageDocumentPages: profile?.average_document_pages ?? 10,
        latencyBudgetMs: profile?.latency_budget_ms ?? 2500,
      },
    })

    if (result.ok) {
      setSavedDefault(mode)
    } else {
      setSaveError(result.error ?? `HTTP ${result.status}`)
    }
    setSavingDefault(false)
  }

  const lastDiagnostics = [...turns].reverse().find((t) => t.diagnostics)?.diagnostics

  return (
    <section className="rounded-2xl border border-lime-500/20 bg-black/40 p-4 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-semibold text-lime-50">
            <Sparkles className="h-5 w-5 text-lime-400" />
            Try your bot
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Send messages as a customer would, switch how the bot looks things up, and see
            exactly what it answers and why.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void saveAsDefault()}
            disabled={mode === "auto" || savingDefault || savedDefault === mode}
            title={
              mode === "auto"
                ? "Pick a specific mode to save it"
                : savedDefault === mode
                  ? "Already the workspace default"
                  : "Save the current mode as the workspace default"
            }
            className="flex items-center gap-2 rounded-lg border border-lime-500/30 bg-lime-500/15 px-3 py-1.5 text-xs font-medium text-lime-400 transition hover:border-lime-500/50 hover:bg-lime-500/25 disabled:opacity-40"
          >
            {savingDefault ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <BookmarkCheck className="h-3.5 w-3.5" />
            )}
            {savedDefault === mode ? "Saved as default" : "Save as workspace default"}
          </button>
          <button
            type="button"
            onClick={reset}
            disabled={turns.length === 0 || busy}
            className="flex items-center gap-2 rounded-lg border border-lime-500/15 bg-black/50 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:border-lime-500/30 hover:bg-lime-500/5 disabled:opacity-40"
          >
            <RotateCcw className="h-3.5 w-3.5" /> Reset session
          </button>
        </div>
      </div>

      {(saveError || savedDefault) && (
        <div
          className={
            "mt-3 rounded-lg border px-3 py-2 text-xs " +
            (saveError
              ? "border-rose-500/30 bg-rose-500/10 text-rose-300"
              : "border-emerald-500/30 bg-emerald-500/10 text-emerald-300")
          }
        >
          {saveError
            ? `Could not save: ${saveError}`
            : `New customer messages will use ${savedDefault?.replace("_", " ")} from now on. You can fine-tune in Settings.`}
        </div>
      )}

      <p className="mt-3 text-xs text-slate-500">
        Try modes here, then commit the one that fits your docs as the workspace default. Per-query
        override is mainly an escape hatch — production traffic uses whatever is set in{" "}
        <a className="text-lime-400 underline-offset-2 hover:underline" href="/settings">
          Settings
        </a>
        .
      </p>

      {/* Mode selector */}
      <div className="mt-4">
        <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-slate-500">
          How should the bot look things up?
        </p>
        <fieldset className="grid gap-2 md:grid-cols-2 lg:grid-cols-4">
          <legend className="sr-only">Retrieval mode</legend>
          {MODE_OPTIONS.map((option) => {
            const active = mode === option.value
            return (
              <label
                key={option.value}
                className={
                  "cursor-pointer rounded-xl border p-3 transition " +
                  (active
                    ? "border-lime-500/50 bg-lime-500/10"
                    : "border-lime-500/15 bg-black/50 hover:border-lime-500/30 hover:bg-lime-500/5")
                }
              >
                <input
                  type="radio"
                  name="retrieval-mode"
                  value={option.value}
                  checked={active}
                  onChange={() => {
                    setMode(option.value)
                    setSavedDefault(null)
                    setSaveError(null)
                  }}
                  className="sr-only"
                />
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-lime-50">{option.label}</p>
                  {option.recommended && (
                    <span className="rounded-full border border-lime-500/30 bg-lime-500/10 px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-lime-400">
                      Recommended
                    </span>
                  )}
                </div>
                <p className="mt-1 text-[11px] leading-snug text-slate-400">
                  {option.description}
                </p>
                <p className="mt-2 text-[10px] leading-snug text-slate-500">
                  <span className="text-slate-400">Best for:</span> {option.bestFor}
                </p>
                <p className="mt-2 text-[9px] uppercase tracking-wider text-slate-600">
                  {option.technical}
                </p>
              </label>
            )
          })}
        </fieldset>
      </div>

      {/* Sample prompts */}
      {turns.length === 0 && (
        <div className="mt-4">
          <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-slate-500">
            Or try a sample question
          </p>
          <div className="flex flex-wrap gap-2">
            {SAMPLE_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => void sendMessage(prompt)}
                disabled={busy}
                className="rounded-full border border-lime-500/20 bg-black/50 px-3 py-1 text-xs text-slate-300 transition hover:border-lime-500/40 hover:bg-lime-500/10 hover:text-lime-50 disabled:opacity-40"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Chat transcript */}
      <div
        ref={scrollRef}
        className="mt-4 max-h-[460px] min-h-[280px] space-y-3 overflow-y-auto rounded-xl border border-lime-500/15 bg-black/50 p-3"
      >
        {turns.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-lime-500/10">
              <Bot className="h-5 w-5 text-lime-400/60" />
            </div>
            <p className="text-sm font-medium text-lime-50">Ready when you are</p>
            <p className="mt-1 text-xs text-slate-500">
              Pick a mode and send a test message — or click a sample above.
            </p>
          </div>
        )}
        {turns.map((turn) => (
          <div key={turn.id} className="flex gap-2.5">
            <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-lime-500/20 bg-lime-500/10 text-lime-400">
              {turn.who === "user" ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
            </div>
            <div className="min-w-0 flex-1">
              <div
                className={
                  "rounded-xl border p-3 text-sm text-lime-50 " +
                  (turn.who === "user"
                    ? "border-lime-500/15 bg-black/60"
                    : turn.error
                      ? "border-rose-500/30 bg-rose-500/10"
                      : turn.diagnostics?.requiresHuman
                        ? "border-amber-500/30 bg-amber-500/10"
                        : turn.diagnostics?.cacheHit
                          ? "border-sky-500/25 bg-sky-500/5"
                          : "border-lime-500/15 bg-lime-500/5")
                }
              >
                <p className="whitespace-pre-wrap leading-relaxed">{turn.text}</p>
                {turn.error && (
                  <p className="mt-2 text-xs text-rose-300">Error: {turn.error}</p>
                )}
              </div>
              {turn.diagnostics && (
                <div className="mt-1.5 flex flex-wrap gap-1.5 text-[10px]">
                  <span className="rounded-md border border-lime-500/20 bg-black/50 px-1.5 py-0.5 uppercase tracking-wider text-slate-300">
                    mode: {shortMode(turn.diagnostics.retrieval.selectedMode)}
                  </span>
                  {turn.diagnostics.retrieval.recommendedMode &&
                    turn.diagnostics.retrieval.recommendedMode !==
                      turn.diagnostics.retrieval.selectedMode && (
                      <span className="rounded-md border border-lime-500/15 bg-black/50 px-1.5 py-0.5 uppercase tracking-wider text-slate-500">
                        rec: {shortMode(turn.diagnostics.retrieval.recommendedMode)}
                      </span>
                    )}
                  <span className="rounded-md border border-lime-500/15 bg-black/50 px-1.5 py-0.5 text-slate-400">
                    {turn.diagnostics.elapsedMs} ms
                  </span>
                  <span
                    className={
                      "rounded-md border px-1.5 py-0.5 " +
                      (turn.diagnostics.knowledgeBaseUsed
                        ? "border-lime-500/30 bg-lime-500/10 text-lime-400"
                        : "border-amber-500/30 bg-amber-500/10 text-amber-300")
                    }
                  >
                    KB: {turn.diagnostics.knowledgeBaseUsed ? "used" : "no match"}
                  </span>
                  {turn.diagnostics.cacheHit && (
                    <span className="rounded-md border border-sky-500/30 bg-sky-500/10 px-1.5 py-0.5 text-sky-300">
                      cache hit
                    </span>
                  )}
                  {turn.diagnostics.requiresHuman && (
                    <span className="rounded-md border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-amber-300">
                      handoff
                    </span>
                  )}
                  {turn.diagnostics.language && (
                    <span className="rounded-md border border-lime-500/15 bg-black/50 px-1.5 py-0.5 text-slate-500">
                      {turn.diagnostics.language}
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-lime-400" />
            Bot is thinking…
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="mt-3 flex items-end gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
          placeholder="Type a customer question…  (Shift+Enter for newline)"
          disabled={busy}
          className="flex-1 resize-none rounded-lg border border-lime-500/20 bg-black/60 px-3 py-2 text-sm text-lime-50 placeholder:text-slate-600 outline-none transition focus:border-lime-500/50 disabled:opacity-50"
        />
        <button
          type="button"
          onClick={() => void sendMessage()}
          disabled={busy || !input.trim()}
          className="flex h-[44px] shrink-0 items-center gap-2 rounded-lg border border-lime-500/30 bg-lime-500/15 px-4 text-sm font-medium text-lime-400 transition hover:border-lime-500/50 hover:bg-lime-500/25 disabled:opacity-40"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          Send
        </button>
      </div>

      {/* Diagnostic detail for the most recent answer */}
      {lastDiagnostics && (
        <div className="mt-4 rounded-xl border border-lime-500/15 bg-black/50 p-3">
          <p className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
            Last response details
          </p>
          <div className="mt-2 grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <p className="text-slate-500">Lookup mode used</p>
              <p className="text-lime-50 capitalize">
                {shortMode(lastDiagnostics.retrieval.selectedMode)}
              </p>
            </div>
            <div>
              <p className="text-slate-500">Auto recommendation</p>
              <p className="text-lime-50 capitalize">
                {shortMode(lastDiagnostics.retrieval.recommendedMode)}
              </p>
            </div>
            <div>
              <p className="text-slate-500">Latency</p>
              <p className="text-lime-50">{lastDiagnostics.elapsedMs} ms</p>
            </div>
            <div>
              <p className="text-slate-500">Model</p>
              <p className="break-all text-lime-50">{lastDiagnostics.modelUsed ?? "—"}</p>
            </div>
            <div>
              <p className="text-slate-500">Session</p>
              <p className="break-all text-slate-400">{lastDiagnostics.sessionId}</p>
            </div>
            <div>
              <p className="text-slate-500">Routing reason</p>
              <p className="text-slate-300">{lastDiagnostics.retrieval.reason ?? "—"}</p>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
