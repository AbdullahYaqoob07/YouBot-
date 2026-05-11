import { ClientApiKey, IntegrationSelector, SocialConnection } from "@/components/integration-selector"
import { fetchJson } from "@/lib/runtime-config"
import { createClient } from "@/lib/supabase/server"

type SocialConnectionsResponse = {
  status?: string
  connections?: SocialConnection[]
}

export default async function IntegrationsPage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  const { data: { session } } = user ? await supabase.auth.getSession() : { data: { session: null } }
  const workspaceId = user?.id ?? "default"
  const authOptions = { tenantId: user?.id, accessToken: session?.access_token }

  const [keysResponse, socialResponse] = await Promise.all([
    fetchJson<ClientApiKey[]>(`/admin/workspaces/${workspaceId}/client-keys`, { ...authOptions, includeAdminKey: false }),
    fetchJson<SocialConnectionsResponse>(`/admin/workspaces/${workspaceId}/social-connections`, authOptions),
  ])

  const initialKeys = keysResponse.data ?? []
  const initialConnections = socialResponse.data?.connections ?? []

  return (
    <div className="futuristic-bg h-full overflow-auto p-3 sm:p-5 lg:p-7">
      <div className="relative z-10 mx-auto max-w-6xl space-y-5">
        <section className="apex-panel rounded-2xl border border-lime-500/15 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-500">Experience</p>
              <h1 className="mt-2 text-3xl font-semibold text-lime-50">Integration Selection</h1>
              <p className="mt-2 text-sm text-slate-400">
                Choose where your assistant runs next without exposing internal identifiers.
              </p>
            </div>
            <span className="rounded-lg border border-lime-500/30 bg-lime-500/10 px-3 py-2 text-xs text-lime-400">
              Ready for configuration
            </span>
          </div>
        </section>

        <IntegrationSelector
          workspaceId={workspaceId}
          initialKeys={initialKeys}
          initialConnections={initialConnections}
        />
      </div>
    </div>
  )
}
