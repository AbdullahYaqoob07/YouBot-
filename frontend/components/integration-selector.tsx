"use client"

import { useState } from "react"

import { consoleProxy } from "@/lib/console-proxy-client"
import { backendSurfaceHref } from "@/lib/runtime-config"

export type ClientApiKey = {
  id: number
  name: string
  key_type: string
  api_key: string
  is_active: boolean
  allowed_domains?: string[] | null
}

export type SocialConnection = {
  id: number
  name: string
  provider: string
  channel: string
  connection_key: string
  is_active: boolean
  integrationPaths?: {
    generic?: string
    metaWebhook?: string
  }
}

type ClientKeysResponse = ClientApiKey[]

type SocialConnectionsResponse = {
  status?: string
  connections?: SocialConnection[]
}

type CreateKeyResponse = {
  id: number
  name: string
  key_type: string
  api_key: string
}

type CreateConnectionResponse = {
  status?: string
  connection?: SocialConnection
}

type WidgetChatResponse = {
  status?: string
  message?: string
  sessionId?: string
  language?: string | null
  handoff?: boolean
  assignedTo?: string | null
  queueStatus?: string | null
  processingTimeMs?: number
  modelUsed?: string | null
  retrievalMode?: string | null
}

type PreviewMessage = {
  id: string
  role: "assistant" | "user"
  content: string
  meta?: string
}

type IntegrationSelectorProps = {
  workspaceId: string
  initialKeys: ClientApiKey[]
  initialConnections: SocialConnection[]
}

export function IntegrationSelector({ workspaceId, initialKeys, initialConnections }: IntegrationSelectorProps) {
  const [enableWebsite, setEnableWebsite] = useState(true)
  const [enableSocial, setEnableSocial] = useState(true)
  const [selectedWidgetKeyId, setSelectedWidgetKeyId] = useState(() => {
    const initialWidgetKey = initialKeys.find((key) => key.key_type === "public_widget" && key.is_active)
    return initialWidgetKey ? String(initialWidgetKey.id) : ""
  })

  const [widgetName, setWidgetName] = useState("Website Widget")
  const [allowedDomainsText, setAllowedDomainsText] = useState("https://example.com")

  const [socialName, setSocialName] = useState("Social Media Connector")
  const [socialProvider, setSocialProvider] = useState("generic")
  const [socialChannel, setSocialChannel] = useState("social")
  const [verifyToken, setVerifyToken] = useState("")
  const [accessToken, setAccessToken] = useState("")
  const [appSecret, setAppSecret] = useState("")
  const [outboundWebhookUrl, setOutboundWebhookUrl] = useState("")
  const [metadataText, setMetadataText] = useState("{}")

  const [keys, setKeys] = useState<ClientApiKey[]>(initialKeys)
  const [connections, setConnections] = useState<SocialConnection[]>(initialConnections)

  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isCreatingWebsite, setIsCreatingWebsite] = useState(false)
  const [isCreatingSocial, setIsCreatingSocial] = useState(false)
  const [isTestingWidget, setIsTestingWidget] = useState(false)
  const [deletingClientKeyId, setDeletingClientKeyId] = useState<number | null>(null)
  const [deletingConnectionId, setDeletingConnectionId] = useState<number | null>(null)

  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [previewStatus, setPreviewStatus] = useState<string | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [previewSessionId, setPreviewSessionId] = useState<string | null>(null)
  const [previewUserId, setPreviewUserId] = useState("preview_user_001")
  const [previewUserName, setPreviewUserName] = useState("Website Visitor")
  const [previewMessage, setPreviewMessage] = useState("How do I get started with the chatbot?")
  const [previewMessages, setPreviewMessages] = useState<PreviewMessage[]>([
    {
      id: "preview-welcome",
      role: "assistant",
      content: "Pick a website widget key and send a test message to see the live chatbot flow before you embed it.",
      meta: "Preview ready",
    },
  ])
  const [previewSummary, setPreviewSummary] = useState<WidgetChatResponse | null>(null)

  const widgetKeys = keys.filter((key) => key.key_type === "public_widget" && key.is_active)
  const selectedWidgetKey = widgetKeys.find((key) => String(key.id) === selectedWidgetKeyId) ?? widgetKeys[0] ?? null
  const widgetKeySelectValue = widgetKeys.some((key) => String(key.id) === selectedWidgetKeyId)
    ? selectedWidgetKeyId
    : (widgetKeys[0] ? String(widgetKeys[0].id) : "")

  function resetWidgetPreview() {
    setPreviewStatus(null)
    setPreviewError(null)
    setPreviewSessionId(null)
    setPreviewSummary(null)
    setPreviewUserId("preview_user_001")
    setPreviewUserName("Website Visitor")
    setPreviewMessage("How do I get started with the chatbot?")
    setPreviewMessages([
      {
        id: "preview-welcome",
        role: "assistant",
        content: "Pick a website widget key and send a test message to see the live chatbot flow before you embed it.",
        meta: "Preview ready",
      },
    ])
  }

  async function sendWidgetPreviewMessage() {
    const trimmedMessage = previewMessage.trim()
    if (!selectedWidgetKey) {
      setPreviewError("Create and enable a website widget key first.")
      return
    }

    if (!trimmedMessage) {
      setPreviewError("Enter a message to test the chatbot integration.")
      return
    }

    setIsTestingWidget(true)
    setPreviewError(null)
    setPreviewStatus("Sending test message through the live chatbot...")
    setPreviewMessages((current) => [
      ...current,
      {
        id: `user-${current.length + 1}`,
        role: "user",
        content: trimmedMessage,
        meta: `Visitor: ${previewUserName.trim() || "Website Visitor"}`,
      },
    ])

    try {
      const response = await fetch(`${backendSurfaceHref("/v1/chat")}`, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-API-Key": selectedWidgetKey.api_key,
        },
        body: JSON.stringify({
          message: trimmedMessage,
          userId: previewUserId.trim() || "preview_user_001",
          sessionId: previewSessionId ?? undefined,
          channel: "web",
          userName: previewUserName.trim() || undefined,
        }),
      })

      const payload = (await response.json()) as WidgetChatResponse & { detail?: string }

      if (!response.ok) {
        throw new Error(payload.detail ?? payload.message ?? `Request failed with status ${response.status}`)
      }

      setPreviewSessionId(payload.sessionId ?? previewSessionId)
      setPreviewSummary(payload)
      setPreviewMessages((current) => [
        ...current,
        {
          id: `assistant-${current.length + 1}`,
          role: "assistant",
          content: payload.message ?? "No chatbot response was returned.",
          meta: payload.handoff ? "Human handoff triggered" : `Status: ${payload.status ?? "success"}`,
        },
      ])
      setPreviewStatus(
        payload.handoff
          ? "Integration successful. The bot responded and handed off to a human when needed."
          : "Integration successful. The bot responded through the widget endpoint.",
      )
      setPreviewMessage("")
    } catch (previewRequestError) {
      setPreviewError(previewRequestError instanceof Error ? previewRequestError.message : "Widget test failed")
      setPreviewStatus(null)
    } finally {
      setIsTestingWidget(false)
    }
  }

  function applySamplePreviewMessage(sample: string) {
    setPreviewMessage(sample)
  }

  async function refreshIntegrations() {
    setIsRefreshing(true)
    setError(null)

    const [keysResponse, socialResponse] = await Promise.all([
      consoleProxy<ClientKeysResponse>({
        path: `/admin/workspaces/${workspaceId}/client-keys`,
        method: "GET",
        includeAdminKey: false,
      }),
      consoleProxy<SocialConnectionsResponse>({
        path: `/admin/workspaces/${workspaceId}/social-connections`,
        method: "GET",
      }),
    ])

    if (!keysResponse.ok) {
      setError(keysResponse.error ?? "Failed to load website integration keys")
    } else {
      setKeys(keysResponse.data ?? [])
    }

    if (!socialResponse.ok) {
      setError(socialResponse.error ?? "Failed to load social connections")
    } else {
      setConnections(socialResponse.data?.connections ?? [])
    }

    setIsRefreshing(false)
  }

  async function deleteClientKey(keyId: number) {
    const confirmed = window.confirm(
      "Delete this client API key? Any widget using it will stop working until you create a replacement.",
    )
    if (!confirmed) {
      return
    }

    setDeletingClientKeyId(keyId)
    setError(null)
    setStatus(null)

    try {
      const response = await consoleProxy<{ deleted_key_id?: number; name?: string }>({
        path: `/admin/workspaces/${workspaceId}/client-keys/${keyId}`,
        method: "DELETE",
      })

      if (!response.ok) {
        setError(response.error ?? "Failed to delete client API key")
        return
      }

      setStatus(`Deleted client API key ${response.data?.name ?? `#${keyId}`}.`)
      await refreshIntegrations()
    } finally {
      setDeletingClientKeyId(null)
    }
  }

  async function createWebsiteIntegration() {
    const domainList = allowedDomainsText
      .split(",")
      .map((entry) => entry.trim())
      .filter(Boolean)

    if (!widgetName.trim()) {
      setError("Widget key name is required.")
      return
    }

    setIsCreatingWebsite(true)
    setError(null)
    setStatus(null)

    const response = await consoleProxy<CreateKeyResponse>({
      path: `/admin/workspaces/${workspaceId}/client-keys`,
      method: "POST",
      includeAdminKey: false,
      body: {
        name: widgetName,
        key_type: "public_widget",
        allowed_domains: domainList,
      },
    })

    if (!response.ok) {
      setError(response.error ?? "Failed to create website widget key")
      setIsCreatingWebsite(false)
      return
    }

    setStatus("Website integration enabled successfully.")
    setIsCreatingWebsite(false)
    await refreshIntegrations()
  }

  async function createSocialIntegration() {
    if (!socialName.trim()) {
      setError("Connection name is required.")
      return
    }

    let parsedMetadata: Record<string, unknown> | undefined
    if (metadataText.trim()) {
      try {
        parsedMetadata = JSON.parse(metadataText) as Record<string, unknown>
      } catch {
        setError("Metadata must be valid JSON.")
        return
      }
    }

    if (socialProvider === "meta" && !verifyToken.trim()) {
      setError("verifyToken is required for Meta connections.")
      return
    }

    setIsCreatingSocial(true)
    setError(null)
    setStatus(null)

    const response = await consoleProxy<CreateConnectionResponse>({
      path: `/admin/workspaces/${workspaceId}/social-connections`,
      method: "POST",
      body: {
        name: socialName,
        provider: socialProvider,
        channel: socialChannel,
        verifyToken: verifyToken.trim() || undefined,
        accessToken: accessToken.trim() || undefined,
        appSecret: appSecret.trim() || undefined,
        outboundWebhookUrl: outboundWebhookUrl.trim() || undefined,
        metadata: parsedMetadata,
        isActive: true,
      },
    })

    if (!response.ok) {
      setError(response.error ?? "Failed to create social integration")
      setIsCreatingSocial(false)
      return
    }

    setStatus("Social integration enabled successfully.")
    setIsCreatingSocial(false)
    await refreshIntegrations()
  }

  async function deleteSocialConnection(connectionId: number) {
    const confirmed = window.confirm(
      "Delete this social connection? Incoming messages will stop reaching the assistant.",
    )
    if (!confirmed) {
      return
    }

    setDeletingConnectionId(connectionId)
    setError(null)
    setStatus(null)

    try {
      const response = await consoleProxy<{ deleted_connection_id?: number; name?: string }>({
        path: `/admin/workspaces/${workspaceId}/social-connections/${connectionId}`,
        method: "DELETE",
      })

      if (!response.ok) {
        setError(response.error ?? "Failed to delete social connection")
        return
      }

      setStatus(`Deleted social connection ${response.data?.name ?? `#${connectionId}`}.`)
      await refreshIntegrations()
    } finally {
      setDeletingConnectionId(null)
    }
  }

  return (
    <section className="rounded-2xl border border-lime-500/15 bg-black/60 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-lime-50">Integration Selection</h2>
          <p className="mt-1 text-xs text-slate-400">
            Choose and configure which channels your assistant should run on: website and social media for now.
          </p>
        </div>
        <button
          type="button"
          onClick={refreshIntegrations}
          disabled={isRefreshing}
          className="rounded-lg border border-lime-500/30 bg-lime-500/10 px-3 py-2 text-xs text-lime-400 transition hover:bg-lime-500/10 disabled:cursor-not-allowed disabled:opacity-55"
        >
          {isRefreshing ? "Refreshing..." : "Refresh Integrations"}
        </button>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <label className="flex items-center gap-2 rounded-lg border border-lime-500/15 bg-black/55 p-3 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={enableWebsite}
            onChange={(event) => setEnableWebsite(event.target.checked)}
          />
          Enable Website Integration
        </label>
        <label className="flex items-center gap-2 rounded-lg border border-lime-500/15 bg-black/55 p-3 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={enableSocial}
            onChange={(event) => setEnableSocial(event.target.checked)}
          />
          Enable Social Media Integration
        </label>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div className={`rounded-xl border p-4 ${enableWebsite ? "border-lime-500/15 bg-black/55" : "border-lime-500/10 bg-black/30 opacity-60"}`}>
          <h3 className="text-sm font-semibold text-lime-50">Website Widget</h3>
          <p className="mt-1 text-xs text-slate-500">Creates a public widget key for website chat embed.</p>

          <div className="mt-3 space-y-2">
            <label className="space-y-1 text-xs text-slate-300">
              <span>Key name</span>
              <input
                value={widgetName}
                onChange={(event) => setWidgetName(event.target.value)}
                disabled={!enableWebsite}
                className="w-full rounded-lg border border-lime-500/20 bg-black/70 px-3 py-2 text-lime-50 outline-none disabled:opacity-55"
              />
            </label>
            <label className="space-y-1 text-xs text-slate-300">
              <span>Allowed domains (comma separated)</span>
              <input
                value={allowedDomainsText}
                onChange={(event) => setAllowedDomainsText(event.target.value)}
                disabled={!enableWebsite}
                className="w-full rounded-lg border border-lime-500/20 bg-black/70 px-3 py-2 text-lime-50 outline-none disabled:opacity-55"
              />
            </label>
            <button
              type="button"
              onClick={createWebsiteIntegration}
              disabled={!enableWebsite || isCreatingWebsite}
              className="rounded-lg border border-emerald-300/35 bg-emerald-300/14 px-3 py-2 text-xs text-emerald-100 transition hover:bg-emerald-300/22 disabled:cursor-not-allowed disabled:opacity-55"
            >
              {isCreatingWebsite ? "Enabling..." : "Enable Website"}
            </button>
          </div>
        </div>

        <div className={`rounded-xl border p-4 ${enableSocial ? "border-lime-500/15 bg-black/55" : "border-lime-500/10 bg-black/30 opacity-60"}`}>
          <h3 className="text-sm font-semibold text-lime-50">Social Media Connector</h3>
          <p className="mt-1 text-xs text-slate-500">Create a generic or Meta social connection.</p>

          <div className="mt-3 grid gap-2">
            <input
              value={socialName}
              onChange={(event) => setSocialName(event.target.value)}
              disabled={!enableSocial}
              placeholder="Connection name"
              className="rounded-lg border border-lime-500/20 bg-black/70 px-3 py-2 text-xs text-lime-50 outline-none disabled:opacity-55"
            />

            <div className="grid gap-2 sm:grid-cols-2">
              <select
                value={socialProvider}
                onChange={(event) => setSocialProvider(event.target.value)}
                disabled={!enableSocial}
                className="rounded-lg border border-lime-500/20 bg-black/70 px-3 py-2 text-xs text-lime-50 outline-none disabled:opacity-55"
              >
                <option value="generic">generic</option>
                <option value="meta">meta</option>
              </select>
              <select
                value={socialChannel}
                onChange={(event) => setSocialChannel(event.target.value)}
                disabled={!enableSocial}
                className="rounded-lg border border-lime-500/20 bg-black/70 px-3 py-2 text-xs text-lime-50 outline-none disabled:opacity-55"
              >
                <option value="social">social</option>
                <option value="whatsapp">whatsapp</option>
                <option value="facebook">facebook</option>
                <option value="instagram">instagram</option>
                <option value="custom">custom</option>
              </select>
            </div>

            <input
              value={verifyToken}
              onChange={(event) => setVerifyToken(event.target.value)}
              disabled={!enableSocial}
              placeholder="verifyToken (required for meta)"
              className="rounded-lg border border-lime-500/20 bg-black/70 px-3 py-2 text-xs text-lime-50 outline-none disabled:opacity-55"
            />
            <input
              value={accessToken}
              onChange={(event) => setAccessToken(event.target.value)}
              disabled={!enableSocial}
              placeholder="accessToken (optional)"
              className="rounded-lg border border-lime-500/20 bg-black/70 px-3 py-2 text-xs text-lime-50 outline-none disabled:opacity-55"
            />
            <input
              value={appSecret}
              onChange={(event) => setAppSecret(event.target.value)}
              disabled={!enableSocial}
              placeholder="appSecret (optional)"
              className="rounded-lg border border-lime-500/20 bg-black/70 px-3 py-2 text-xs text-lime-50 outline-none disabled:opacity-55"
            />
            <input
              value={outboundWebhookUrl}
              onChange={(event) => setOutboundWebhookUrl(event.target.value)}
              disabled={!enableSocial}
              placeholder="outboundWebhookUrl (optional)"
              className="rounded-lg border border-lime-500/20 bg-black/70 px-3 py-2 text-xs text-lime-50 outline-none disabled:opacity-55"
            />
            <textarea
              value={metadataText}
              onChange={(event) => setMetadataText(event.target.value)}
              disabled={!enableSocial}
              rows={2}
              placeholder='metadata JSON, e.g. {"graph_api_version":"v21.0"}'
              className="rounded-lg border border-lime-500/20 bg-black/70 px-3 py-2 text-xs text-lime-50 outline-none disabled:opacity-55"
            />

            <button
              type="button"
              onClick={createSocialIntegration}
              disabled={!enableSocial || isCreatingSocial}
              className="rounded-lg border border-indigo-300/35 bg-indigo-300/14 px-3 py-2 text-xs text-indigo-100 transition hover:bg-indigo-300/22 disabled:cursor-not-allowed disabled:opacity-55"
            >
              {isCreatingSocial ? "Enabling..." : "Enable Social"}
            </button>
          </div>
        </div>
      </div>

      {status && <p className="mt-4 text-sm text-emerald-200">{status}</p>}
      {error && <p className="mt-4 text-sm text-rose-200">{error}</p>}

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-lime-500/15 bg-black/55 p-4">
          <h3 className="text-sm font-semibold text-lime-50">Website Integrations ({keys.length})</h3>
          <div className="mt-3 max-h-64 space-y-2 overflow-auto pr-1">
            {keys.map((key) => (
              <div key={key.id} className="rounded-lg border border-lime-500/15 bg-black/60 p-2 text-xs text-slate-300">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-medium text-lime-50">{key.name}</p>
                    <p className="mt-1">Allowed domains: {key.allowed_domains?.length ? key.allowed_domains.join(", ") : "not set"}</p>
                    <p className="mt-1 break-all text-slate-500">API key: {key.api_key}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void deleteClientKey(key.id)}
                    disabled={deletingClientKeyId === key.id}
                    className="rounded-md border border-rose-300/35 bg-rose-300/12 px-2.5 py-1 text-[11px] text-rose-300 transition hover:bg-rose-300/20 disabled:cursor-not-allowed disabled:opacity-55"
                  >
                    {deletingClientKeyId === key.id ? "Deleting..." : "Delete"}
                  </button>
                </div>
              </div>
            ))}
            {keys.length === 0 && <p className="text-xs text-slate-500">No website integrations configured.</p>}
          </div>
        </div>

        <div className="rounded-xl border border-lime-500/15 bg-black/55 p-4">
          <h3 className="text-sm font-semibold text-lime-50">Social Connections ({connections.length})</h3>
          <div className="mt-3 max-h-64 space-y-2 overflow-auto pr-1">
            {connections.map((connection) => (
              <div key={connection.id} className="rounded-lg border border-lime-500/15 bg-black/60 p-2 text-xs text-slate-300">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-medium text-lime-50">{connection.name}</p>
                    <p className="mt-1">{connection.provider}/{connection.channel}</p>
                    <p className="mt-1 text-slate-500">Connection is configured and ready.</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void deleteSocialConnection(connection.id)}
                    disabled={deletingConnectionId === connection.id}
                    className="rounded-md border border-rose-300/35 bg-rose-300/12 px-2.5 py-1 text-[11px] text-rose-300 transition hover:bg-rose-300/20 disabled:cursor-not-allowed disabled:opacity-55"
                  >
                    {deletingConnectionId === connection.id ? "Deleting..." : "Delete"}
                  </button>
                </div>
              </div>
            ))}
            {connections.length === 0 && <p className="text-xs text-slate-500">No social connections configured.</p>}
          </div>
        </div>
      </div>

      <div className="mt-6 rounded-2xl border border-cyan-300/18 bg-linear-to-br from-black via-slate-950 to-cyan-950/25 p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold text-cyan-50">Test & Preview</h3>
            <p className="mt-1 text-xs text-cyan-100/68">
              Send a real message through the website widget flow before you add the embed to your site.
            </p>
          </div>
          <button
            type="button"
            onClick={resetWidgetPreview}
            className="rounded-lg border border-cyan-300/25 bg-cyan-300/10 px-3 py-2 text-xs text-cyan-100 transition hover:bg-cyan-300/18"
          >
            Reset Preview
          </button>
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-[1.3fr_0.9fr]">
          <div className="rounded-xl border border-cyan-300/20 bg-black/60 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-wider text-cyan-100/55">Live widget preview</p>
                  <h4 className="mt-1 text-sm font-semibold text-cyan-50">See the customer experience before you publish</h4>
                </div>
                <span className="rounded-full border border-cyan-300/25 bg-cyan-300/10 px-3 py-1 text-[11px] text-cyan-100">
                  {selectedWidgetKey ? "Widget ready" : "No widget selected"}
                </span>
              </div>

            <div className="mt-4 max-h-72 space-y-3 overflow-auto pr-1">
              {previewMessages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[88%] rounded-2xl border px-4 py-3 text-sm shadow-sm ${
                      message.role === "user"
                        ? "border-cyan-300/25 bg-cyan-400/15 text-cyan-50"
                        : "border-lime-500/15 bg-black/80 text-lime-50"
                    }`}
                  >
                    <p className="whitespace-pre-wrap leading-6">{message.content}</p>
                    <p className="mt-2 text-[11px] uppercase tracking-wider text-white/45">{message.meta}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto]">
              <label className="space-y-1 text-xs text-cyan-100/80">
                <span>Test message</span>
                <textarea
                  value={previewMessage}
                  onChange={(event) => setPreviewMessage(event.target.value)}
                  rows={3}
                  placeholder="Ask a real question your visitors would ask"
                  className="w-full rounded-xl border border-cyan-300/20 bg-black/70 px-3 py-2 text-sm text-cyan-50 outline-none placeholder:text-cyan-100/35"
                />
              </label>
              <div className="flex flex-col gap-2 sm:justify-end">
                <button
                  type="button"
                  onClick={sendWidgetPreviewMessage}
                  disabled={isTestingWidget || !selectedWidgetKey}
                  className="rounded-xl border border-emerald-300/35 bg-emerald-300/15 px-4 py-3 text-sm font-medium text-emerald-50 transition hover:bg-emerald-300/22 disabled:cursor-not-allowed disabled:opacity-55"
                >
                  {isTestingWidget ? "Sending..." : "Send Test Message"}
                </button>
                <button
                  type="button"
                  onClick={() => applySamplePreviewMessage("What support do you offer for first-time customers?")}
                  className="rounded-xl border border-cyan-300/22 bg-cyan-300/8 px-4 py-2 text-xs text-cyan-100 transition hover:bg-cyan-300/16"
                >
                  Use Sample Question
                </button>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-cyan-100/70">
              <span className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1">Channel: web</span>
              <span className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1">
                Visitor: {previewUserName.trim() || "Website Visitor"}
              </span>
            </div>

            {previewStatus && <p className="mt-3 text-sm text-emerald-200">{previewStatus}</p>}
            {previewError && <p className="mt-3 text-sm text-rose-200">{previewError}</p>}
          </div>

          <div className="space-y-4">
            <div className="rounded-xl border border-cyan-300/20 bg-black/60 p-4">
              <h4 className="text-sm font-semibold text-cyan-50">Connection State</h4>
              {widgetKeys.length > 0 ? (
                <div className="mt-3 space-y-3">
                  <label className="space-y-1 text-xs text-cyan-100/80">
                    <span>Pick a widget integration</span>
                    <select
                      value={widgetKeySelectValue}
                      onChange={(event) => setSelectedWidgetKeyId(event.target.value)}
                      className="w-full rounded-lg border border-cyan-300/20 bg-black/70 px-3 py-2 text-sm text-cyan-50 outline-none"
                    >
                      {widgetKeys.map((key) => (
                        <option key={key.id} value={String(key.id)}>
                          {key.name}
                        </option>
                      ))}
                    </select>
                  </label>

                  <div className="rounded-lg border border-cyan-300/15 bg-black/50 p-3 text-xs text-cyan-100/75">
                    <p className="font-medium text-cyan-50">{selectedWidgetKey?.name ?? "No widget selected"}</p>
                    <p className="mt-1">The widget is configured to talk to the live assistant securely.</p>
                    <p className="mt-1">
                      Allowed domains: {selectedWidgetKey?.allowed_domains?.length ? selectedWidgetKey.allowed_domains.join(", ") : "not set"}
                    </p>
                    <p className="mt-1 break-all text-cyan-100/62">API key: {selectedWidgetKey?.api_key ?? "n/a"}</p>
                  </div>
                </div>
              ) : (
                <p className="mt-3 text-xs text-cyan-100/65">
                  Create a widget integration above to unlock the live preview.
                </p>
              )}
            </div>

            <div className="rounded-xl border border-cyan-300/20 bg-black/60 p-4">
              <h4 className="text-sm font-semibold text-cyan-50">Last Test Result</h4>
              <div className="mt-3 grid gap-2 text-xs text-cyan-100/75 sm:grid-cols-2">
                <div className="rounded-lg border border-cyan-300/12 bg-black/40 p-3">
                  <p className="text-cyan-100/55">Language</p>
                  <p className="mt-1 text-sm text-cyan-50">{previewSummary?.language ?? "n/a"}</p>
                </div>
                <div className="rounded-lg border border-cyan-300/12 bg-black/40 p-3">
                  <p className="text-cyan-100/55">Processing</p>
                  <p className="mt-1 text-sm text-cyan-50">{previewSummary?.processingTimeMs != null ? `${previewSummary.processingTimeMs} ms` : "n/a"}</p>
                </div>
                <div className="rounded-lg border border-cyan-300/12 bg-black/40 p-3">
                  <p className="text-cyan-100/55">Handoff</p>
                  <p className="mt-1 text-sm text-cyan-50">{previewSummary ? (previewSummary.handoff ? "Yes" : "No") : "n/a"}</p>
                </div>
                <div className="rounded-lg border border-cyan-300/12 bg-black/40 p-3">
                  <p className="text-cyan-100/55">Queue</p>
                  <p className="mt-1 text-sm text-cyan-50">{previewSummary?.queueStatus ?? "n/a"}</p>
                </div>
              </div>

              <div className="mt-3 rounded-lg border border-cyan-300/12 bg-black/40 p-3 text-xs text-cyan-100/70">
                <p className="text-cyan-100/55">Conversation</p>
                <p className="mt-1 break-all text-cyan-50">
                  {previewSummary?.handoff ? "Escalated to a human when needed" : "Handled by the assistant"}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
