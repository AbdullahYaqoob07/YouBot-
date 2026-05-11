"use client"

import { useEffect, useMemo, useState, useRef } from "react"
import {
  RefreshCw,
  Send,
  Sparkles,
  Bot,
  User,
  Shield,
  MessageSquare,
  Clock,
  Eye,
  PowerOff,
  Filter,
  AlertTriangle,
  CheckCircle2
} from "lucide-react"

import { consoleProxy } from "@/lib/console-proxy-client"

type ConversationSummary = {
  session_id?: string
  status?: string
  admin_takeover?: boolean
  user_id?: string
  channel?: string
  assigned_admin_name?: string
  queue_status?: string
  updated_at?: string
  admin_id?: string
  ai_triggered_handoff?: boolean
  handoff_reason?: string
  last_message?: string
  last_ai_response?: string
  message_count?: number
  takeover_at?: string
}

type ConversationListResponse = {
  status?: string
  total?: number
  conversations?: ConversationSummary[]
}

type ConversationMessage = {
  type?: string
  role?: string
  sender_type?: string
  sender?: string
  content?: string
  message?: string
  text?: string
  timestamp?: string
  created_at?: string
  original_content?: string
  translated?: boolean
  language?: string
  admin_id?: string
  _session_id?: string
  _session_index?: number
}

type ConversationDetail = {
  session_id?: string
  status?: string
  admin_takeover?: boolean
  channel?: string
  user_id?: string
  handoff_reason?: string
  messages?: ConversationMessage[]
}

type GroupedConversation = {
  user_id: string
  sessions: ConversationSummary[]
  primary: ConversationSummary
  total_message_count: number
}

type ConversationDetailResponse = {
  status?: string
  conversation?: ConversationDetail
}

type ActionResponse = {
  success?: boolean
  session_id?: string
  action?: string
  message?: string
  error?: string
  corrected?: string
  suggestions?: string[]
  enhanced?: string
  output?: string
}

const ENHANCEMENT_ACTIONS = ["shorten", "extend", "summarize", "rephrase", "formal", "friendly", "bullets", "grammar"] as const

function getSessionId(item: ConversationSummary): string {
  return item.session_id ?? ""
}

function getUserKey(item: ConversationSummary): string {
  const id = item.user_id?.trim()
  if (id) return id
  return `__session_${item.session_id ?? "unknown"}`
}

function timestampOf(value?: string): number {
  if (!value) return 0
  const t = new Date(value).getTime()
  return isNaN(t) ? 0 : t
}

function groupConversationsByUser(items: ConversationSummary[]): GroupedConversation[] {
  const map = new Map<string, ConversationSummary[]>()
  for (const item of items) {
    const key = getUserKey(item)
    const arr = map.get(key) ?? []
    arr.push(item)
    map.set(key, arr)
  }

  const groups: GroupedConversation[] = []
  for (const [user_id, sessions] of map) {
    sessions.sort((a, b) => timestampOf(b.updated_at) - timestampOf(a.updated_at))
    groups.push({
      user_id,
      sessions,
      primary: sessions[0],
      total_message_count: sessions.reduce((sum, s) => sum + (s.message_count ?? 0), 0),
    })
  }

  groups.sort((a, b) => timestampOf(b.primary.updated_at) - timestampOf(a.primary.updated_at))
  return groups
}

function getMessageText(message: ConversationMessage): string {
  return message.content ?? message.message ?? message.text ?? ""
}

function getMessageRole(message: ConversationMessage): string {
  return message.type ?? message.role ?? message.sender_type ?? "message"
}

function truncateText(value: string | undefined, limit = 84): string {
  if (!value) {
    return ""
  }

  const normalized = value.replace(/\s+/g, " ").trim()
  if (normalized.length <= limit) {
    return normalized
  }

  return `${normalized.slice(0, limit - 1)}…`
}

function isDelegatedConversation(conversation: ConversationSummary): boolean {
  return Boolean(conversation.admin_takeover || conversation.status === "admin_takeover")
}

function isHandoffConversation(conversation: ConversationSummary): boolean {
  return Boolean(conversation.ai_triggered_handoff || conversation.status === "pending_handoff")
}

function getConversationStateLabel(conversation: ConversationSummary): string {
  if (isDelegatedConversation(conversation)) {
    return "Delegated"
  }
  if (isHandoffConversation(conversation)) {
    return "Pending Handoff"
  }
  return "AI Handling"
}

function getConversationBadgeClass(conversation: ConversationSummary): string {
  if (isDelegatedConversation(conversation)) {
    return "border-amber-500/40 bg-amber-500/10 text-amber-400"
  }
  if (isHandoffConversation(conversation)) {
    return "border-cyan-500/40 bg-cyan-500/10 text-cyan-400"
  }
  return "border-lime-500/40 bg-lime-500/10 text-lime-400"
}

function getConversationCardClass(conversation: ConversationSummary, isSelected: boolean): string {
  const baseClass = isDelegatedConversation(conversation)
    ? "border-amber-500/20 bg-amber-950/20 hover:bg-amber-900/30"
    : isHandoffConversation(conversation)
      ? "border-cyan-500/20 bg-cyan-950/20 hover:bg-cyan-900/30"
      : "border-white/10 bg-white/5 hover:bg-white/10"

  if (isSelected) {
    return `${baseClass} ring-1 ring-lime-400 border-lime-400/50 bg-lime-950/30 hover:bg-lime-950/30`
  }

  return baseClass
}

function formatRelativeTime(dateString?: string): string {
  if (!dateString) return ""
  const date = new Date(dateString)
  if (isNaN(date.getTime())) return ""
  
  const diffInMs = new Date().getTime() - date.getTime()
  const diffInMins = Math.floor(diffInMs / 60000)
  
  if (diffInMins < 1) return "Just now"
  if (diffInMins < 60) return `${diffInMins}m ago`
  if (diffInMins < 1440) return `${Math.floor(diffInMins / 60)}h ago`
  return `${Math.floor(diffInMins / 1440)}d ago`
}

function getMessageLabel(message: ConversationMessage): string {
  const role = getMessageRole(message).toLowerCase()
  if (role === "user" || role === "customer" || role === "visitor") {
    return "User"
  }
  if (role === "ai" || role === "assistant" || role === "bot") {
    return "AI Assistant"
  }
  if (role === "admin" || role === "agent" || role === "human") {
    return "Support Agent"
  }
  return getMessageRole(message)
}

function getMessageRoleIcon(message: ConversationMessage) {
  const role = getMessageRole(message).toLowerCase()
  if (role === "admin" || role === "agent" || role === "human") return <Shield className="h-3 w-3" />
  if (role === "ai" || role === "assistant" || role === "bot") return <Bot className="h-3 w-3" />
  return <User className="h-3 w-3" />
}

function getMessageCardClass(message: ConversationMessage): string {
  const role = getMessageRole(message).toLowerCase()

  if (role === "admin" || role === "agent" || role === "human") {
    return "border-amber-500/20 bg-amber-500/10 text-amber-50"
  }

  if (role === "ai" || role === "assistant" || role === "bot") {
    return "border-white/10 bg-white/5 text-slate-100"
  }

  return "border-cyan-500/20 bg-cyan-500/10 text-cyan-50"
}

function getMessageAlignment(message: ConversationMessage): string {
  const role = getMessageRole(message).toLowerCase()
  if (role === "admin" || role === "agent" || role === "human") {
    return "justify-end"
  }

  return "justify-start"
}

type AdminChatHandlerProps = {
  defaultAdminId?: string
}

export function AdminChatHandler({ defaultAdminId = "admin_console" }: AdminChatHandlerProps) {
  const [adminId, setAdminId] = useState(defaultAdminId)
  const [statusFilter, setStatusFilter] = useState("")
  const [draftMessage, setDraftMessage] = useState("")
  const [enhanceAction, setEnhanceAction] = useState<(typeof ENHANCEMENT_ACTIONS)[number]>("grammar")
  const [takeoverReason, setTakeoverReason] = useState("Manual intervention")

  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [selectedConversation, setSelectedConversation] = useState<ConversationDetail | null>(null)
  const [isLoadingDetail, setIsLoadingDetail] = useState(false)

  const [previewText, setPreviewText] = useState<string | null>(null)
  const [enhancedText, setEnhancedText] = useState<string | null>(null)

  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  
  const scrollAreaRef = useRef<HTMLDivElement>(null)

  const groupedConversations = useMemo(
    () => groupConversationsByUser(conversations),
    [conversations],
  )

  const selectedGroup = useMemo(
    () => groupedConversations.find((group) => group.user_id === selectedUserId) ?? null,
    [groupedConversations, selectedUserId],
  )

  const selectedSummary = useMemo(() => {
    if (selectedGroup) return selectedGroup.primary
    return conversations.find((conversation) => getSessionId(conversation) === selectedSessionId) ?? null
  }, [selectedGroup, conversations, selectedSessionId])

  async function loadConversations() {
    setIsRefreshing(true)
    setError(null)

    const response = await consoleProxy<ConversationListResponse>({
      path: "/admin/supervision/conversations",
      method: "GET",
      query: {
        status: statusFilter || undefined,
        include_ended: false,
      },
    })

    if (!response.ok) {
      setError(response.error ?? "Failed to load conversations")
      setIsRefreshing(false)
      return
    }

    const nextConversations = response.data?.conversations ?? []
    setConversations(nextConversations)

    const groups = groupConversationsByUser(nextConversations)

    if (!selectedUserId && groups[0]) {
      await loadGroupDetail(groups[0])
    } else if (selectedUserId) {
      const stillPresent = groups.find((g) => g.user_id === selectedUserId)
      if (!stillPresent) {
        setSelectedUserId(null)
        setSelectedSessionId(null)
        setSelectedConversation(null)
      } else {
        // Refresh the merged view in case new messages arrived
        await loadGroupDetail(stillPresent)
      }
    }

    setIsRefreshing(false)
  }

  async function loadGroupDetail(group: GroupedConversation) {
    setError(null)
    setIsLoadingDetail(true)
    setSelectedUserId(group.user_id)
    setSelectedSessionId(group.primary.session_id ?? null)

    const validSessions = group.sessions.filter((s) => Boolean(s.session_id))

    const results = await Promise.all(
      validSessions.map((s) =>
        consoleProxy<ConversationDetailResponse>({
          path: `/admin/supervision/conversations/${encodeURIComponent(s.session_id ?? "")}`,
          method: "GET",
        }),
      ),
    )

    const failed = results.find((r) => !r.ok)
    if (failed && results.every((r) => !r.ok)) {
      setError(failed.error ?? "Failed to load conversation detail")
      setIsLoadingDetail(false)
      return
    }

    const merged: ConversationMessage[] = []
    let primaryDetail: ConversationDetail | null = null
    const lastSessionIndex = validSessions.length - 1

    results.forEach((r, idx) => {
      if (!r.ok || !r.data?.conversation) return
      const sessionId = validSessions[idx].session_id
      // Session index numbered oldest=1 ... newest=N for display
      const displayIndex = lastSessionIndex - idx + 1
      if (idx === 0) primaryDetail = r.data.conversation

      const msgs = r.data.conversation.messages ?? []
      for (const m of msgs) {
        merged.push({ ...m, _session_id: sessionId, _session_index: displayIndex })
      }
    })

    merged.sort((a, b) => {
      const at = timestampOf(a.timestamp ?? a.created_at)
      const bt = timestampOf(b.timestamp ?? b.created_at)
      if (at !== bt) return at - bt
      // Fall back to session ordering when timestamps tie
      return (a._session_index ?? 0) - (b._session_index ?? 0)
    })

    setSelectedConversation({
      ...(primaryDetail ?? {}),
      session_id: group.primary.session_id,
      user_id: group.user_id,
      messages: merged,
    } as ConversationDetail)
    setIsLoadingDetail(false)
  }

  async function loadConversationDetail(sessionId: string) {
    // Backward-compat shim: find the group containing this session and load the merged view
    const group = groupedConversations.find((g) =>
      g.sessions.some((s) => s.session_id === sessionId),
    )
    if (group) {
      await loadGroupDetail(group)
      return
    }

    // Fallback: load just the single session if grouping data isn't available
    setError(null)
    setIsLoadingDetail(true)
    const response = await consoleProxy<ConversationDetailResponse>({
      path: `/admin/supervision/conversations/${encodeURIComponent(sessionId)}`,
      method: "GET",
    })
    setIsLoadingDetail(false)

    if (!response.ok) {
      setError(response.error ?? "Failed to load conversation detail")
      return
    }

    setSelectedSessionId(sessionId)
    setSelectedConversation(response.data?.conversation ?? null)
  }

  useEffect(() => {
    void loadConversations()
  }, [])
  
  // Auto-scroll chat area to bottom when messages update
  useEffect(() => {
    const timer = setTimeout(() => {
      if (scrollAreaRef.current) {
        scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight
      }
    }, 10)
    return () => clearTimeout(timer)
  }, [selectedConversation?.messages, previewText, enhancedText])

  async function runSessionAction(pathSuffix: string, body: Record<string, unknown>, actionLabel: string) {
    if (!selectedSessionId) {
      setError("Select a conversation first.")
      return null
    }

    setBusyAction(actionLabel)
    setError(null)
    setStatus(null)

    const response = await consoleProxy<ActionResponse>({
      path: `/admin/supervision/conversations/${encodeURIComponent(selectedSessionId)}${pathSuffix}`,
      method: "POST",
      body,
    })

    setBusyAction(null)

    if (!response.ok) {
      setError(response.error ?? `Failed to ${actionLabel.toLowerCase()}`)
      return null
    }

    // loadConversations will refresh the merged group view automatically if a user is selected
    await loadConversations()
    return response.data
  }

  async function takeoverConversation() {
    const result = await runSessionAction(
      "/takeover",
      { admin_id: adminId, reason: takeoverReason },
      "Taking Over",
    )
    if (result) {
      setStatus("Conversation takeover successful.")
    }
  }

  async function sendMessage() {
    if (!draftMessage.trim()) {
      setError("Write a message before sending.")
      return
    }

    const result = await runSessionAction(
      "/message",
      { admin_id: adminId, message: draftMessage },
      "Sending Message",
    )
    if (result) {
      setStatus("Admin message sent.")
      setDraftMessage("")
      setPreviewText(null)
      setEnhancedText(null)
    }
  }

  async function previewMessage() {
    if (!draftMessage.trim()) {
      setError("Write a message before previewing.")
      return
    }

    const result = await runSessionAction(
      "/message/preview",
      { admin_id: adminId, message: draftMessage },
      "Previewing",
    )

    if (result) {
      setPreviewText(result.corrected ?? "No correction returned")
      setStatus("Preview generated.")
    }
  }

  async function enhanceMessage() {
    if (!draftMessage.trim()) {
      setError("Write a message before enhancing.")
      return
    }

    const result = await runSessionAction(
      "/message/enhance",
      { admin_id: adminId, message: draftMessage, action: enhanceAction },
      "Enhancing",
    )

    if (result) {
      const nextText = result.enhanced ?? result.output ?? result.message ?? null
      if (nextText) {
        setEnhancedText(nextText)
        setDraftMessage(nextText)
      }
      setStatus(`Enhancement '${enhanceAction}' completed.`)
    }
  }

  async function releaseConversation(endConversation: boolean) {
    const result = await runSessionAction(
      "/release",
      { admin_id: adminId, end_conversation: endConversation },
      endConversation ? "Ending Conversation" : "Releasing Conversation",
    )
    if (result) {
      setStatus(endConversation ? "Conversation ended." : "Conversation released back to AI.")
    }
  }

  const messages = selectedConversation?.messages ?? []

  return (
    <section className="h-[92vh] min-h-[850px] rounded-2xl border border-lime-500/20 bg-black/40 p-4 md:p-6 flex flex-col overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 shrink-0 mb-4 sm:mb-6">
        <div>
          <h2 className="text-xl font-semibold text-lime-50 flex items-center gap-2">
            <MessageSquare className="h-5 w-5 text-lime-400" />
            Admin Chat Handler
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Monitor live conversations, take over manually, and release back to AI.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="hidden sm:flex items-center gap-2 mr-2">
            <div className="relative">
              <Shield className="h-4 w-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={adminId}
                onChange={(event) => setAdminId(event.target.value)}
                placeholder="Admin ID"
                className="w-32 rounded-lg border border-lime-500/20 bg-black/60 pl-8 pr-3 py-1.5 text-xs text-lime-50 outline-none focus:border-lime-500/50"
              />
            </div>
            <div className="relative">
              <Filter className="h-4 w-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
                placeholder="Filter status..."
                className="w-32 rounded-lg border border-lime-500/20 bg-black/60 pl-8 pr-3 py-1.5 text-xs text-lime-50 outline-none focus:border-lime-500/50"
              />
            </div>
          </div>
          <button
            type="button"
            onClick={loadConversations}
            disabled={isRefreshing}
            className="flex items-center gap-2 rounded-lg border border-lime-500/30 bg-lime-500/10 px-3 py-1.5 text-xs font-medium text-lime-400 transition hover:bg-lime-500/20 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {(status || error) && (
        <div className={`shrink-0 mb-4 rounded-lg border px-3 py-2 text-xs flex items-center gap-2 ${error ? "border-rose-500/30 bg-rose-500/10 text-rose-300" : "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"}`}>
          {error ? <AlertTriangle className="h-4 w-4" /> : <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />}
          {error ?? status}
        </div>
      )}

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-4 lg:gap-6 min-h-0">
        {/* LEFT PANEL: Conversation List */}
        <div className="flex flex-col lg:col-span-4 rounded-xl border border-lime-500/15 bg-black/50 overflow-hidden min-h-0">
          <div className="p-3 border-b border-lime-500/15 bg-lime-950/20 shrink-0 flex justify-between items-center">

            <h3 className="text-sm font-semibold text-lime-50">Active Users</h3>
            <span className="rounded-full bg-lime-500/20 px-2 py-0.5 text-[10px] text-lime-400">{groupedConversations.length}</span>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-2">
            {groupedConversations.map((group, index) => {
              const primary = group.primary
              const isSelected = group.user_id === selectedUserId
              const isDelegated = isDelegatedConversation(primary)
              const sessionCount = group.sessions.length

              return (
                <button
                  type="button"
                  key={group.user_id || `group-${index}`}
                  onClick={() => void loadGroupDetail(group)}
                  className={`w-full group flex flex-col rounded-lg p-3 text-left transition ${getConversationCardClass(primary, isSelected)}`}
                >
                  <div className="flex w-full items-center justify-between mb-1">
                    <span className="font-medium text-sm truncate pr-2 text-slate-200">
                      {primary.user_id ?? "unknown-user"}
                    </span>
                    <span className="shrink-0 text-[10px] text-slate-500">
                      {formatRelativeTime(primary.updated_at) || <Clock className="h-3 w-3" />}
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5 mb-2">
                    <span className={`px-1.5 py-0.5 rounded text-[9px] uppercase tracking-wider font-medium border ${getConversationBadgeClass(primary)}`}>
                      {getConversationStateLabel(primary)}
                    </span>
                    <span className="text-[10px] text-slate-500 truncate">{primary.channel ?? "web"}</span>
                    {sessionCount > 1 && (
                      <span className="rounded bg-white/5 border border-white/10 px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-slate-400">
                        {sessionCount} sessions
                      </span>
                    )}
                    {group.total_message_count > 0 && (
                      <span className="text-[10px] text-slate-500">
                        {group.total_message_count} msg{group.total_message_count === 1 ? "" : "s"}
                      </span>
                    )}
                  </div>

                  {primary.last_message && (
                    <p className="text-xs text-slate-400 line-clamp-1 group-hover:text-slate-300 transition-colors">
                      <span className="font-medium text-slate-500 mr-1">U:</span>
                      {primary.last_message}
                    </p>
                  )}
                  {primary.last_ai_response && !isDelegated && (
                    <p className="mt-1 text-[11px] text-slate-500 line-clamp-1">
                      <span className="font-medium text-slate-600 mr-1">AI:</span>
                      {primary.last_ai_response}
                    </p>
                  )}
                </button>
              )
            })}

            {groupedConversations.length === 0 && (
              <div className="flex flex-col items-center justify-center py-10 text-center px-4">
                <div className="h-10 w-10 rounded-full bg-lime-500/10 flex items-center justify-center mb-3">
                  <CheckCircle2 className="h-5 w-5 text-lime-400/50" />
                </div>
                <p className="text-sm font-medium text-lime-50">Inbox Zero</p>
                <p className="text-xs text-slate-500 mt-1">No active conversations require your attention.</p>
              </div>
            )}
          </div>
        </div>

        {/* RIGHT PANEL: Chat Detail */}
        <div className="flex flex-col lg:col-span-8 rounded-xl border border-lime-500/15 bg-black/50 overflow-hidden relative min-h-0">
          {!selectedSessionId ? (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-gradient-to-b from-black/0 to-lime-950/5">
              <MessageSquare className="h-12 w-12 text-slate-700 mb-4" strokeWidth={1} />
              <h3 className="text-lg font-medium text-slate-300">No Chat Selected</h3>
              <p className="text-sm text-slate-500 max-w-[250px] mt-2">Select a conversation from the left to view details and assist.</p>
            </div>
          ) : (
            <>
              {/* Chat Header */}
              <div className="p-3 sm:px-4 border-b border-lime-500/15 bg-lime-950/20 shrink-0 flex flex-wrap items-center justify-between gap-3 shadow-sm z-10">
                <div className="flex flex-col min-w-0">
                  <h3 className="text-sm font-bold text-lime-50 truncate flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-lime-400 inline-block shrink-0" />
                    {selectedConversation?.user_id ?? selectedSummary?.user_id ?? "Unknown User"}
                  </h3>
                  <div className="flex flex-wrap items-center gap-3 mt-1 text-[11px] text-slate-400">
                    {selectedGroup && selectedGroup.sessions.length > 1 ? (
                      <span title={selectedGroup.sessions.map((s) => s.session_id).join("\n")}>
                        {selectedGroup.sessions.length} sessions · latest {selectedSummary?.session_id?.slice(0, 8)}…
                      </span>
                    ) : (
                      <span>{selectedSummary?.session_id}</span>
                    )}
                    {selectedConversation?.channel && <span className="bg-black/50 px-1.5 py-0.5 rounded text-[10px] uppercase border border-white/5">{selectedConversation.channel}</span>}
                    {isLoadingDetail && <span className="text-slate-500">loading…</span>}
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={takeoverConversation}
                    disabled={busyAction !== null}
                    className="flex items-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/10 hover:bg-amber-500/20 px-3 py-1.5 text-xs font-medium text-amber-400 transition disabled:opacity-50"
                  >
                    <Shield className="h-3.5 w-3.5" />
                    <span className="hidden sm:inline">{busyAction === "Taking Over" ? "Taking Over..." : "Take Over"}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => releaseConversation(false)}
                    disabled={busyAction !== null}
                    className="flex items-center gap-1.5 rounded-lg border border-cyan-500/40 bg-cyan-500/10 hover:bg-cyan-500/20 px-3 py-1.5 text-xs font-medium text-cyan-400 transition disabled:opacity-50"
                  >
                    <Bot className="h-3.5 w-3.5" />
                    <span className="hidden sm:inline">{busyAction === "Releasing Conversation" ? "Releasing..." : "Release to AI"}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => releaseConversation(true)}
                    disabled={busyAction !== null}
                    className="flex items-center gap-1.5 rounded-lg border border-rose-500/40 bg-rose-500/10 hover:bg-rose-500/20 px-3 py-1.5 text-xs font-medium text-rose-400 transition disabled:opacity-50"
                  >
                    <PowerOff className="h-3.5 w-3.5" />
                    <span className="hidden sm:inline">{busyAction === "Ending Conversation" ? "Ending..." : "End"}</span>
                  </button>
                </div>
              </div>

              {selectedConversation?.handoff_reason && (
                <div className="bg-amber-500/10 border-b border-amber-500/20 px-4 py-2 text-[11px] text-amber-200/80 flex items-start gap-2 shrink-0">
                  <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                  <p><strong className="text-amber-400">Handoff reason:</strong> {selectedConversation.handoff_reason}</p>
                </div>
              )}

              {/* Chat Message Area */}
              <div 
                ref={scrollAreaRef}
                className="flex-1 overflow-y-auto overflow-x-hidden p-4 space-y-4 scroll-smooth min-h-0 w-full"
              >
                {messages.map((message, index) => {
                  const role = getMessageRole(message).toLowerCase()
                  const isUser = role === "user" || role === "customer" || role === "visitor"
                  const isAI = role === "ai" || role === "assistant" || role === "bot"
                  const prevSession = index > 0 ? messages[index - 1]._session_id : undefined
                  const showSessionDivider =
                    message._session_id !== undefined &&
                    message._session_id !== prevSession &&
                    (selectedGroup?.sessions.length ?? 0) > 1

                  return (
                    <div key={`${index}-${message.timestamp ?? message.created_at ?? "msg"}`}>
                    {showSessionDivider && (
                      <div className="flex items-center gap-2 my-3 text-[10px] uppercase tracking-wider text-slate-500">
                        <div className="h-px flex-1 bg-white/10" />
                        <span>
                          Session {message._session_index}
                          {message._session_id && <span className="ml-1 normal-case text-slate-600">· {message._session_id.slice(0, 8)}…</span>}
                        </span>
                        <div className="h-px flex-1 bg-white/10" />
                      </div>
                    )}
                    <div className={`flex ${isUser ? "justify-end" : "justify-start"} group`}>
                      <div className={`flex gap-2 max-w-[85%] ${isUser ? "flex-row-reverse" : "flex-row"}`}>
                        <div className={`h-6 w-6 shrink-0 rounded-full flex items-center justify-center mt-1 outline outline-1 outline-offset-1 ${isUser ? 'bg-cyan-500/20 text-cyan-400 outline-cyan-500/30' : isAI ? 'bg-lime-500/20 text-lime-400 outline-lime-500/30' : 'bg-amber-500/20 text-amber-400 outline-amber-500/30'}`}>
                           {getMessageRoleIcon(message)}
                        </div>
                        <div className={`flex flex-col ${isUser ? "items-end" : "items-start"}`}>
                          <div className={`flex items-baseline gap-2 mb-1 px-1 opacity-0 group-hover:opacity-100 transition-opacity ${isUser ? "flex-row-reverse" : "flex-row"}`}>
                            <span className="text-[10px] font-medium text-slate-400">{getMessageLabel(message)}</span>
                            {(message.timestamp || message.created_at) && (
                              <span className="text-[9px] text-slate-500">{new Date(message.timestamp ?? message.created_at!).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                            )}
                          </div>
                          
                          <div className={`px-4 py-2.5 rounded-2xl text-[13px] leading-relaxed shadow-sm break-words relative max-w-full ${
                            isUser 
                              ? "bg-cyan-500/10 border border-cyan-500/20 text-cyan-50 rounded-tr-sm" 
                              : isAI 
                                ? "bg-white/5 border border-white/10 text-slate-200 rounded-tl-sm"
                                : "bg-amber-500/10 border border-amber-500/20 text-amber-50 rounded-tl-sm"
                          }`}>
                            <p className="whitespace-pre-wrap">{getMessageText(message) || "(empty message)"}</p>
                            
                            {message.language && message.language !== "English" && (
                              <span className="absolute -bottom-2 -right-2 bg-black border border-white/10 text-[9px] px-1.5 rounded uppercase font-medium text-slate-400">
                                {message.language}
                              </span>
                            )}
                          </div>
                          
                          {message.translated && message.original_content && message.original_content !== getMessageText(message) && (
                            <div className="mt-1 text-[10px] text-slate-500 bg-black/40 px-2 py-1 rounded border border-white/5 max-w-full">
                              <span className="block font-medium text-slate-400 mb-0.5">Original ({message.language}):</span>
                              <p className="truncate">{message.original_content}</p>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                    </div>
                  )
                })}
                
                {messages.length === 0 && (
                  <div className="h-full flex items-center justify-center text-slate-500 text-sm">
                    No message history in this session yet.
                  </div>
                )}
              </div>

              {/* Chat Input Area */}
              <div className="p-3 sm:p-4 border-t border-lime-500/15 bg-black/60 shrink-0">
                {(previewText || enhancedText) && (
                  <div className="mb-3 rounded-xl border border-indigo-500/30 bg-indigo-500/5 p-3 text-xs flex gap-3 relative group">
                    <Sparkles className="h-4 w-4 text-indigo-400 shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="text-indigo-100 font-medium mb-1">{enhancedText ? "AI Enhanced Form:" : "AI Preview Response:"}</p>
                      <p className="text-indigo-200/80 italic">"{enhancedText || previewText}"</p>
                    </div>
                    <button 
                      onClick={() => { setEnhancedText(null); setPreviewText(null); }}
                      className="absolute top-2 right-2 text-indigo-400/50 hover:text-indigo-300 p-1"
                    >
                      &times;
                    </button>
                  </div>
                )}

                <div className="relative rounded-xl border border-lime-500/30 bg-black overflow-hidden focus-within:ring-1 focus-within:ring-lime-500/50 focus-within:border-lime-500/50 transition-all">
                  <textarea
                    value={draftMessage}
                    onChange={(event) => setDraftMessage(event.target.value)}
                    placeholder={selectedSummary && isDelegatedConversation(selectedSummary) ? "Type a reply to the user..." : "Take over the conversation to reply..."}
                    rows={Math.min(5, Math.max(1, draftMessage.split('\n').length))}
                    className="w-full bg-transparent px-4 py-3 text-[13px] text-lime-50 outline-none placeholder:text-slate-600 resize-none min-h-[44px] max-h-40"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        if (draftMessage.trim()) void sendMessage();
                      }
                    }}
                  />
                  
                  <div className="flex items-center justify-between px-3 py-2 bg-lime-950/10 border-t border-lime-500/10">
                    <div className="flex items-center gap-1.5">
                      <select
                        value={enhanceAction}
                        onChange={(event) => setEnhanceAction(event.target.value as (typeof ENHANCEMENT_ACTIONS)[number])}
                        className="bg-black border border-lime-500/20 text-slate-400 text-[10px] sm:text-xs rounded-md px-1.5 py-1 lg:px-2 lg:py-1.5 outline-none hover:bg-lime-900/30 focus:border-lime-500/50 cursor-pointer"
                      >
                        {ENHANCEMENT_ACTIONS.map((action) => (
                          <option key={action} value={action}>{action}</option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={enhanceMessage}
                        disabled={busyAction !== null || !draftMessage.trim()}
                        className="text-indigo-400 hover:text-indigo-300 hover:bg-indigo-500/10 p-1 lg:px-2 lg:py-1 rounded-md text-[10px] sm:text-xs font-medium transition disabled:opacity-50 flex items-center gap-1"
                      >
                        <Sparkles className="h-3.5 w-3.5" />
                        <span className="hidden sm:inline">Enhance</span>
                      </button>
                      <button
                        type="button"
                        onClick={previewMessage}
                        disabled={busyAction !== null || !draftMessage.trim()}
                        className="text-teal-400 hover:text-teal-300 hover:bg-teal-500/10 p-1 lg:px-2 lg:py-1 rounded-md text-[10px] sm:text-xs font-medium transition disabled:opacity-50 flex items-center gap-1"
                      >
                        <Eye className="h-3.5 w-3.5" />
                        <span className="hidden sm:inline">Preview</span>
                      </button>
                    </div>

                    <button
                      type="button"
                      onClick={sendMessage}
                      disabled={busyAction !== null || !draftMessage.trim()}
                      className="rounded-lg bg-lime-500 hover:bg-lime-400 px-4 py-1.5 text-xs font-semibold text-black transition disabled:opacity-50 flex items-center gap-2"
                    >
                      {busyAction === "Sending Message" ? "..." : "Send"}
                      <Send className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
                <div className="mt-2 flex items-center justify-between text-[10px] text-slate-500 px-1">
                  <span>Press <kbd className="px-1 py-0.5 rounded bg-white/5 border border-white/10 font-sans">Enter</kbd> to send</span>
                  {selectedSummary && !isDelegatedConversation(selectedSummary) && (
                    <span className="text-amber-500/70 flex items-center gap-1">
                      <AlertTriangle className="h-3 w-3" />
                      Must Take Over to send directly
                    </span>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  )
}
