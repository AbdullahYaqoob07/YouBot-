import { KeyRound, Plug, ShieldCheck, Sparkles } from "lucide-react"

import { ProviderConfigForm } from "@/components/provider-config-form"
import { fetchJson } from "@/lib/runtime-config"
import { createClient } from "@/lib/supabase/server"

type WorkspaceLLMConfig = {
  tenantId?: string
  workspaceId?: string
  provider?: string
  model?: string
  hasApiKey?: boolean
  maskedApiKey?: string
  updatedAt?: string | null
}

export default async function ProvidersPage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  const { data: { session } } = user ? await supabase.auth.getSession() : { data: { session: null } }
  const workspaceId = user?.id ?? "default"
  const authOptions = { tenantId: user?.id, accessToken: session?.access_token }

  const llmConfig = await fetchJson<WorkspaceLLMConfig>(
    `/admin/workspaces/${workspaceId}/llm-config`,
    authOptions,
  )

  const provider = llmConfig.data?.provider ?? "not-set"
  const model = llmConfig.data?.model ?? "not-set"
  const masked = llmConfig.data?.maskedApiKey ?? "not-set"

  return (
    <div className="futuristic-bg h-full overflow-auto p-3 sm:p-5 lg:p-7">
      <div className="relative z-10 mx-auto max-w-6xl space-y-5">
        <section className="apex-panel rounded-2xl border border-lime-500/15 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-500">User</p>
              <h1 className="mt-2 text-3xl font-semibold text-lime-50">Assistant Preferences</h1>
              <p className="mt-2 text-sm text-slate-400">
                Manage how the assistant behaves without exposing provider URLs or secrets in the UI.
              </p>
            </div>
            <span className="rounded-lg border border-lime-500/30 bg-lime-500/10 px-3 py-2 text-xs text-lime-400">
              Preferences saved securely
            </span>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-4">
          <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
            <div className="flex items-center gap-2 text-lime-400"><Plug className="size-4" /> Provider</div>
            <p className="mt-2 text-lg font-semibold text-lime-50">{provider}</p>
          </div>
          <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
            <div className="flex items-center gap-2 text-lime-400"><Sparkles className="size-4" /> Model</div>
            <p className="mt-2 text-lg font-semibold text-lime-50">{model}</p>
          </div>
          <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
            <div className="flex items-center gap-2 text-lime-400"><KeyRound className="size-4" /> API Key</div>
            <p className="mt-2 text-sm text-lime-50">Stored securely</p>
          </div>
          <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
            <div className="flex items-center gap-2 text-lime-400"><ShieldCheck className="size-4" /> Status</div>
            <p className="mt-2 text-sm text-lime-50">{llmConfig.error ? "Needs setup" : "Configured"}</p>
          </div>
        </section>

        <section className="rounded-2xl border border-lime-500/15 bg-black/60 p-5">
          <h2 className="text-lg font-semibold text-lime-50">Model Catalog</h2>
          <p className="mt-1 text-xs text-slate-500">
            {llmConfig.error ? llmConfig.error : "Your assistant is ready to use."}
          </p>

          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { key: "groq" },
              { key: "openai" },
              { key: "anthropic" },
              { key: "gemini" },
            ].map((item) => (
              <div key={item.key} className="rounded-xl border border-lime-500/15 bg-lime-500/10 p-3">
                <p className="text-sm font-semibold text-lime-50 uppercase">{item.key}</p>
                <p className="mt-1 text-xs text-slate-400">Available for the assistant experience.</p>
              </div>
            ))}
          </div>
        </section>

        <ProviderConfigForm workspaceId={workspaceId} initialConfig={llmConfig.data} />
      </div>
    </div>
  )
}
