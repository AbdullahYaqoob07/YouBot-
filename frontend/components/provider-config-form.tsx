"use client"

import { useMemo, useState } from "react"
import { Settings2, Key, RefreshCw, Trash2, Cpu, Shield, Server, Box, AlertTriangle, CheckCircle2 } from "lucide-react"

import { consoleProxy } from "@/lib/console-proxy-client"

type WorkspaceLLMConfig = {
  tenantId?: string
  workspaceId?: string
  provider?: string
  model?: string
  hasApiKey?: boolean
  maskedApiKey?: string
  updatedAt?: string | null
}

type ProviderCatalogResponse = {
  provider: string
  models: string[]
  total: number
}

type ProviderConfigFormProps = {
  workspaceId: string
  initialConfig: WorkspaceLLMConfig | null
}

const PROVIDER_OPTIONS = ["groq", "openai", "anthropic", "gemini"] as const

export function ProviderConfigForm({ workspaceId, initialConfig }: ProviderConfigFormProps) {
  const [provider, setProvider] = useState(initialConfig?.provider ?? "groq")
  const [model, setModel] = useState(initialConfig?.model ?? "")
  const [providerApiKey, setProviderApiKey] = useState("")
  const [catalogModels, setCatalogModels] = useState<string[]>([])
  const [savedConfig, setSavedConfig] = useState<WorkspaceLLMConfig | null>(initialConfig)
  const [isFetchingCatalog, setIsFetchingCatalog] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const canFetchCatalog = providerApiKey.trim().length >= 16
  const canSave = provider.trim().length > 0 && model.trim().length > 0 && providerApiKey.trim().length >= 16

  const modelSuggestions = useMemo(() => {
    if (!model.trim()) {
      return catalogModels
    }
    const normalized = model.toLowerCase()
    return catalogModels.filter((entry) => entry.toLowerCase().includes(normalized)).slice(0, 8)
  }, [catalogModels, model])

  async function refreshCurrentConfig() {
    setIsRefreshing(true)
    setError(null)
    setStatus(null)

    const response = await consoleProxy<WorkspaceLLMConfig>({
      path: `/admin/workspaces/${workspaceId}/llm-config`,
      method: "GET",
    })

    if (!response.ok || !response.data) {
      if (response.status === 404) {
        setSavedConfig(null)
        setStatus("No workspace LLM configuration found.")
        setIsRefreshing(false)
        return
      }

      setError(response.error ?? "Failed to refresh workspace LLM config")
      setIsRefreshing(false)
      return
    }

    setSavedConfig(response.data)
    setProvider(response.data.provider ?? provider)
    setModel(response.data.model ?? model)
    setStatus("Workspace provider config refreshed.")
    setIsRefreshing(false)
  }

  async function fetchProviderCatalog() {
    if (!canFetchCatalog) {
      setError("Provider API key must be at least 16 characters before fetching models.")
      return
    }

    setIsFetchingCatalog(true)
    setError(null)
    setStatus(null)

    const response = await consoleProxy<ProviderCatalogResponse>({
      path: `/admin/llm/providers/${provider}/models`,
      method: "POST",
      body: {
        apiKey: providerApiKey,
        forceRefresh: true,
      },
    })

    if (!response.ok || !response.data) {
      setError(response.error ?? "Failed to fetch provider catalog")
      setIsFetchingCatalog(false)
      return
    }

    setCatalogModels(response.data.models ?? [])
    if (!model && response.data.models?.[0]) {
      setModel(response.data.models[0])
    }
    setStatus(`Loaded ${response.data.total} models for ${response.data.provider}.`)
    setIsFetchingCatalog(false)
  }

  async function saveWorkspaceConfig() {
    if (!canSave) {
      setError("Choose a provider/model and enter a valid API key before saving.")
      return
    }

    setIsSaving(true)
    setError(null)
    setStatus(null)

    const response = await consoleProxy<WorkspaceLLMConfig>({
      path: `/admin/workspaces/${workspaceId}/llm-config`,
      method: "POST",
      body: {
        provider,
        model,
        apiKey: providerApiKey,
      },
    })

    if (!response.ok || !response.data) {
      setError(response.error ?? "Failed to save workspace LLM config")
      setIsSaving(false)
      return
    }

    setSavedConfig(response.data)
    setProviderApiKey("")
    setStatus("Workspace provider config saved successfully.")
    setIsSaving(false)
  }

  async function deleteWorkspaceConfig() {
    if (!savedConfig) {
      setError("No workspace LLM configuration exists to delete.")
      return
    }

    const confirmed = window.confirm("Delete the current workspace provider configuration?")
    if (!confirmed) {
      return
    }

    setIsDeleting(true)
    setError(null)
    setStatus(null)

    const response = await consoleProxy<{ deleted?: boolean }>({
      path: `/admin/workspaces/${workspaceId}/llm-config`,
      method: "DELETE",
    })

    if (!response.ok) {
      setError(response.error ?? "Failed to delete workspace LLM config")
      setIsDeleting(false)
      return
    }

    setSavedConfig(null)
    setStatus("Workspace provider config deleted.")
    setIsDeleting(false)
  }

  return (
    <section className="rounded-2xl border border-lime-500/20 bg-black/40 p-4 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h2 className="text-lg font-semibold text-lime-50 flex items-center gap-2">
            <Cpu className="h-5 w-5 text-lime-400" />
            Configure Provider
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Set your AI model provider and securely store an API key for this workspace.
          </p>
        </div>
        <button
          type="button"
          onClick={refreshCurrentConfig}
          disabled={isRefreshing}
          className="flex items-center gap-2 rounded-lg border border-lime-500/30 bg-lime-500/10 px-3 py-1.5 text-xs font-medium text-lime-400 transition hover:bg-lime-500/20 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
          Refresh Config
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-lime-500/15 bg-black/50 p-4">
          <h3 className="text-sm font-semibold text-lime-50 flex items-center gap-2 mb-4">
            <Server className="h-4 w-4 text-cyan-400" />
            Model Selection
          </h3>
          
          <div className="space-y-4">
            <label className="block space-y-1.5 text-sm text-slate-300">
              <span className="font-medium text-xs">Provider</span>
              <div className="relative">
                <Box className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <select
                  value={provider}
                  onChange={(event) => setProvider(event.target.value)}
                  className="w-full appearance-none rounded-lg border border-lime-500/20 bg-black/60 pl-9 pr-3 py-2.5 text-sm text-lime-50 outline-none focus:border-lime-500/50 transition-colors"
                >
                  {PROVIDER_OPTIONS.map((option) => (
                    <option key={option} value={option} className="bg-black text-lime-50">
                      {option.toUpperCase()}
                    </option>
                  ))}
                </select>
              </div>
            </label>

            <label className="block space-y-1.5 text-sm text-slate-300">
              <span className="font-medium text-xs">Model Identifier</span>
              <div className="relative">
                <Cpu className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  value={model}
                  onChange={(event) => setModel(event.target.value)}
                  list="provider-model-options"
                  placeholder="e.g. gpt-4o-mini"
                  className="w-full rounded-lg border border-lime-500/20 bg-black/60 pl-9 pr-3 py-2.5 text-sm text-lime-50 outline-none placeholder:text-slate-600 focus:border-lime-500/50 transition-colors"
                />
              </div>
              <datalist id="provider-model-options">
                {modelSuggestions.map((entry) => (
                  <option key={entry} value={entry} />
                ))}
              </datalist>
            </label>

            <label className="block space-y-1.5 text-sm text-slate-300">
              <span className="font-medium text-xs">API Key</span>
              <div className="relative">
                <Key className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  value={providerApiKey}
                  onChange={(event) => setProviderApiKey(event.target.value)}
                  placeholder="Sk-..."
                  type="password"
                  autoComplete="off"
                  className="w-full rounded-lg border border-lime-500/20 bg-black/60 pl-9 pr-3 py-2.5 text-sm text-lime-50 outline-none placeholder:text-slate-600 focus:border-lime-500/50 transition-colors"
                />
              </div>
            </label>

            <div className="flex gap-2 pt-2">
              <button
                type="button"
                onClick={fetchProviderCatalog}
                disabled={isFetchingCatalog || !canFetchCatalog}
                className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-lime-600/10 border border-lime-500/20 hover:bg-lime-500/20 hover:border-lime-500/30 px-3 py-2.5 text-xs font-medium text-lime-400 transition disabled:opacity-50"
              >
                {isFetchingCatalog ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Server className="h-3.5 w-3.5" />}
                Discover Models
              </button>
              <button
                type="button"
                onClick={saveWorkspaceConfig}
                disabled={isSaving || !canSave}
                className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-emerald-600/20 border border-emerald-500/30 hover:bg-emerald-500/30 hover:border-emerald-500/50 px-3 py-2.5 text-xs font-semibold text-emerald-50 transition disabled:opacity-50"
              >
                {isSaving ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Shield className="h-3.5 w-3.5" />}
                Save Config
              </button>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-4">
          <div className="rounded-xl border border-lime-500/15 bg-black/50 p-4 relative overflow-hidden">
            <div className="absolute top-0 right-0 p-4 opacity-5 pointer-events-none">
                <Settings2 className="h-24 w-24" />
            </div>
            <h3 className="text-sm font-semibold text-lime-50 flex items-center gap-2 mb-4 relative z-10">
              <Settings2 className="h-4 w-4 text-emerald-400" />
              Active Configuration
            </h3>
            
            <div className="space-y-3 relative z-10">
              <div className="flex items-center justify-between p-2 rounded bg-black/40 border border-lime-500/10">
                <span className="text-xs text-slate-400">Provider</span>
                <span className="text-sm font-medium text-lime-50">{savedConfig?.provider ?? <span className="text-slate-500">Not set</span>}</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded bg-black/40 border border-lime-500/10">
                <span className="text-xs text-slate-400">Model</span>
                <span className="text-sm font-medium text-lime-50 max-w-[200px] truncate">{savedConfig?.model ?? <span className="text-slate-500">Not set</span>}</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded bg-black/40 border border-lime-500/10">
                <span className="text-xs text-slate-400">API Key</span>
                <span className="text-sm font-mono text-lime-400">{savedConfig?.maskedApiKey ?? <span className="text-slate-500 font-sans">Not set</span>}</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded bg-black/40 border border-lime-500/10">
                <span className="text-xs text-slate-400">Last Updated</span>
                <span className="text-xs text-slate-400">{savedConfig?.updatedAt ?? "unknown"}</span>
              </div>
            </div>

            <div className="mt-4 pt-4 border-t border-lime-500/10 relative z-10">
              <button
                type="button"
                onClick={deleteWorkspaceConfig}
                disabled={isDeleting || !savedConfig}
                className="w-full flex items-center justify-center gap-2 rounded-lg bg-rose-950/30 border border-rose-500/20 hover:bg-rose-500/20 hover:border-rose-500/40 px-3 py-2 text-xs font-medium text-rose-300 transition disabled:opacity-50"
              >
                {isDeleting ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                Remove Configuration
              </button>
            </div>
          </div>

          {status && (
            <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3 flex items-center gap-2 text-sm text-emerald-300">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <p className="leading-snug">{status}</p>
            </div>
          )}
          
          {error && (
            <div className="rounded-lg bg-rose-500/10 border border-rose-500/20 p-3 flex gap-2 text-sm text-rose-300">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
              <p className="leading-snug">{error}</p>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
