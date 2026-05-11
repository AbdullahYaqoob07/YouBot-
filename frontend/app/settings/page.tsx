import { Cog, Shield } from "lucide-react"

import { AssistantProfileForm, type AssistantProfile } from "@/components/assistant-profile-form"
import { RetrievalProfileForm, type RetrievalProfile } from "@/components/retrieval-profile-form"
import { fetchJson } from "@/lib/runtime-config"
import { createClient } from "@/lib/supabase/server"

type HealthResponse = {
  status?: string
}

type SupervisionResponse = {
  total?: number
  conversations?: unknown[]
}

type WorkspaceLLMConfig = {
  provider?: string
  model?: string
}

type RetrievalProfileResponse = {
  status?: string
  profile?: RetrievalProfile | null
}

type AssistantProfileResponse = {
  status?: string
  profile?: AssistantProfile | null
}

export default async function SettingsPage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  const { data: { session } } = user ? await supabase.auth.getSession() : { data: { session: null } }
  const workspaceId = user?.id ?? "default"
  const authOptions = { tenantId: user?.id, accessToken: session?.access_token }

  const [health, supervision, llmConfig, retrievalProfile, assistantProfile] = await Promise.all([
    fetchJson<HealthResponse>("/health", { includeAdminKey: false }),
    fetchJson<SupervisionResponse>("/admin/supervision/conversations", authOptions),
    fetchJson<WorkspaceLLMConfig>(`/admin/workspaces/${workspaceId}/llm-config`, authOptions),
    fetchJson<RetrievalProfileResponse>("/admin/retrieval/profile", authOptions),
    fetchJson<AssistantProfileResponse>(`/admin/workspaces/${workspaceId}/assistant-profile`, authOptions),
  ])

  const initialProfile = retrievalProfile.data?.profile ?? null
  const initialAssistantProfile = assistantProfile.data?.profile ?? null

  return (
    <div className="futuristic-bg h-full overflow-auto p-3 sm:p-5 lg:p-7">
      <div className="relative z-10 mx-auto max-w-6xl space-y-5">
        <section className="apex-panel rounded-2xl border border-lime-500/15 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-500">User</p>
              <h1 className="mt-2 text-3xl font-semibold text-lime-50">Experience Settings</h1>
              <p className="mt-2 text-sm text-slate-400">
                Personalize the support experience without exposing backend configuration.
              </p>
            </div>
            <span className="rounded-lg border border-lime-500/30 bg-lime-500/10 px-3 py-2 text-xs text-lime-400">
              <Cog className="mr-1 inline size-3.5" /> Support Settings
            </span>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-lime-500/15 bg-black/60 p-5">
            <h2 className="flex items-center gap-2 text-lg font-semibold text-lime-50"><Shield className="size-4" /> Privacy & Safety</h2>
            <div className="mt-4 space-y-2 text-sm text-lime-50/90">
              <p>Only user-relevant settings are shown here.</p>
              <p>The assistant handles technical routing behind the scenes.</p>
            </div>
          </div>

          <div className="rounded-xl border border-lime-500/15 bg-black/60 p-5">
            <h2 className="text-lg font-semibold text-lime-50">Recommended Preferences</h2>
            <ul className="mt-4 space-y-2 text-sm text-lime-50/88">
              <li>1. Keep the assistant tone consistent with your brand.</li>
              <li>2. Choose concise responses for mobile visitors.</li>
              <li>3. Enable human handoff when a question needs support.</li>
              <li>4. Keep the interface focused on the visitor experience.</li>
            </ul>
          </div>
        </section>

        <AssistantProfileForm
          workspaceId={workspaceId}
          initialProfile={initialAssistantProfile}
        />

        <RetrievalProfileForm initialProfile={initialProfile} />

        <section className="rounded-2xl border border-lime-500/15 bg-black/60 p-5">
          <h2 className="text-lg font-semibold text-lime-50">Validation API Checks</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="rounded-xl border border-lime-500/15 bg-lime-500/10 p-3 text-sm text-lime-50">
              <p className="font-semibold">Health API</p>
              <p className="mt-1 text-xs text-slate-400">System status</p>
              <p className="mt-2 text-xs text-slate-400">{health.ok ? `status=${health.data?.status ?? "unknown"}` : (health.error ?? "failed")}</p>
            </div>
            <div className="rounded-xl border border-lime-500/15 bg-lime-500/10 p-3 text-sm text-lime-50">
              <p className="font-semibold">Supervision API</p>
              <p className="mt-1 text-xs text-slate-400">Conversation monitoring</p>
              <p className="mt-2 text-xs text-slate-400">{supervision.ok ? "available" : (supervision.error ?? "failed")}</p>
            </div>
            <div className="rounded-xl border border-lime-500/15 bg-lime-500/10 p-3 text-sm text-lime-50">
              <p className="font-semibold">LLM Config API</p>
              <p className="mt-1 text-xs text-slate-400">Model configuration</p>
              <p className="mt-2 text-xs text-slate-400">{llmConfig.ok ? "available" : (llmConfig.error ?? "failed")}</p>
            </div>
          </div>
          <p className="mt-4 text-xs text-slate-500">Settings stay focused on the visitor experience.</p>
        </section>
      </div>
    </div>
  )
}
