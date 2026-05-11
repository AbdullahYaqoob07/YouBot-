import { Cable, KeyRound, MessageCircleMore, Webhook } from "lucide-react"

import { fetchJson } from "@/lib/runtime-config"
import { createClient } from "@/lib/supabase/server"

type ClientApiKey = {
  id: number
  name: string
  key_type: string
  api_key: string
  is_active: boolean
  created_at?: string
}

type SocialConnection = {
  id: number
  name: string
  provider: string
  channel: string
  connection_key: string
  is_active: boolean
}

type SocialConnectionResponse = {
  status?: string
  connections?: SocialConnection[]
}

export default async function ChannelsPage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  const { data: { session } } = user ? await supabase.auth.getSession() : { data: { session: null } }
  const workspaceId = user?.id ?? "default"
  const authOptions = { tenantId: user?.id, accessToken: session?.access_token }

  const [keysResult, socialResult] = await Promise.all([
    fetchJson<ClientApiKey[]>(`/admin/workspaces/${workspaceId}/client-keys`, authOptions),
    fetchJson<SocialConnectionResponse>(`/admin/workspaces/${workspaceId}/social-connections`, authOptions),
  ])

  const keys = keysResult.data ?? []
  const socialConnections = socialResult.data?.connections ?? []

  return (
    <div className="futuristic-bg h-full overflow-auto p-3 sm:p-5 lg:p-7">
      <div className="relative z-10 mx-auto max-w-6xl space-y-5">
        <section className="apex-panel rounded-2xl border border-lime-500/15 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-500">User</p>
              <h1 className="mt-2 text-3xl font-semibold text-lime-50">Channels & Connections</h1>
              <p className="mt-2 text-sm text-slate-400">
                Manage external connections without showing internal keys or backend paths.
              </p>
            </div>
            <span className="rounded-lg border border-lime-500/30 bg-lime-500/10 px-3 py-2 text-xs text-lime-400">
              Secure connections
            </span>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-4">
          <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
            <div className="flex items-center gap-2 text-lime-400"><KeyRound className="size-4" /> Client Keys</div>
            <p className="mt-2 text-2xl font-semibold text-lime-50">{keys.length}</p>
            <p className="mt-1 text-xs text-slate-500">Stored securely</p>
          </div>
          <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
            <div className="flex items-center gap-2 text-lime-400"><Cable className="size-4" /> Social Connections</div>
            <p className="mt-2 text-2xl font-semibold text-lime-50">{socialConnections.length}</p>
            <p className="mt-1 text-xs text-slate-500">Ready for messaging</p>
          </div>
          <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
            <div className="flex items-center gap-2 text-lime-400"><Webhook className="size-4" /> Generic Inbound</div>
            <p className="mt-2 text-xs text-lime-50">Configured behind the scenes</p>
          </div>
          <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
            <div className="flex items-center gap-2 text-lime-400"><MessageCircleMore className="size-4" /> Meta Webhook</div>
            <p className="mt-2 text-xs text-lime-50">Configured behind the scenes</p>
          </div>
        </section>

        <section className="rounded-2xl border border-lime-500/15 bg-black/60 p-5">
          <h2 className="text-lg font-semibold text-lime-50">Client API Keys</h2>
          <p className="mt-1 text-xs text-slate-500">
            {keysResult.error ? keysResult.error : "Keys are visible on this admin-only page for implementation and support."}
          </p>
          <div className="mt-4 space-y-2">
            {keys.slice(0, 8).map((key) => (
              <div key={key.id} className="rounded-lg border border-lime-500/15 bg-black/55 p-3 text-sm text-lime-50/90">
                <p className="font-medium">{key.name} <span className="text-xs text-slate-500">({key.key_type})</span></p>
                <p className="mt-1 text-xs text-slate-400">Stored securely</p>
                <p className="mt-1 break-all text-xs text-slate-500">API key: {key.api_key}</p>
              </div>
            ))}
            {keys.length === 0 && <p className="text-sm text-slate-500">No client keys found for this workspace.</p>}
          </div>
        </section>

        <section className="rounded-2xl border border-lime-500/15 bg-black/60 p-5">
          <h2 className="text-lg font-semibold text-lime-50">Social Connectors</h2>
          <p className="mt-1 text-xs text-slate-500">
            {socialResult.error ? socialResult.error : "Connector details are visible to admins for support and implementation."}
          </p>
          <div className="mt-4 space-y-2">
            {socialConnections.slice(0, 10).map((connection) => (
              <div key={connection.id} className="rounded-lg border border-lime-500/15 bg-black/55 p-3 text-sm text-lime-50/90">
                <p className="font-medium">{connection.name}</p>
                <p className="mt-1 text-xs text-slate-400">{connection.provider}/{connection.channel}</p>
                <p className="mt-1 break-all text-xs text-slate-500">Connection key: {connection.connection_key}</p>
              </div>
            ))}
            {socialConnections.length === 0 && <p className="text-sm text-slate-500">No social connections configured yet.</p>}
          </div>
        </section>
      </div>
    </div>
  )
}
