import { MessageSquareWarning, ShieldAlert, UserCheck, Users } from "lucide-react"

import { fetchJson, getFrontendRuntimeConfig } from "@/lib/runtime-config"

type SupervisionConversation = {
  session_id?: string
  user_id?: string
  status?: string
  channel?: string
  language?: string
  updated_at?: string
}

type SupervisionResponse = {
  status?: string
  total?: number
  conversations?: SupervisionConversation[]
}

function countByStatus(conversations: SupervisionConversation[]): Record<string, number> {
  return conversations.reduce<Record<string, number>>((acc, item) => {
    const key = item.status ?? "unknown"
    acc[key] = (acc[key] ?? 0) + 1
    return acc
  }, {})
}

export default async function SupervisionPage() {
  const config = getFrontendRuntimeConfig()
  const response = await fetchJson<SupervisionResponse>("/admin/supervision/conversations")
  const conversations = response.data?.conversations ?? []
  const counters = countByStatus(conversations)

  return (
    <div className="futuristic-bg h-full overflow-auto p-3 sm:p-5 lg:p-7">
      <div className="relative z-10 mx-auto max-w-6xl space-y-5">
        <section className="apex-panel rounded-2xl border border-lime-500/15 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-500">Operations</p>
              <h1 className="mt-2 text-3xl font-semibold text-lime-50">Live Supervision</h1>
              <p className="mt-2 text-sm text-slate-400">
                Monitor active conversations and human handoff states in a clean operations view.
              </p>
            </div>
            <span className="rounded-lg border border-lime-500/30 bg-lime-500/10 px-3 py-2 text-xs text-lime-400">
              Conversation monitoring
            </span>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-4">
          <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
            <div className="flex items-center gap-2 text-lime-400"><Users className="size-4" /> Total</div>
            <p className="mt-2 text-2xl font-semibold text-lime-50">{conversations.length}</p>
          </div>
          <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
            <div className="flex items-center gap-2 text-lime-400"><UserCheck className="size-4" /> Active</div>
            <p className="mt-2 text-2xl font-semibold text-lime-50">{counters.active ?? 0}</p>
          </div>
          <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
            <div className="flex items-center gap-2 text-lime-400"><MessageSquareWarning className="size-4" /> Pending Handoff</div>
            <p className="mt-2 text-2xl font-semibold text-lime-50">{counters.pending_handoff ?? 0}</p>
          </div>
          <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
            <div className="flex items-center gap-2 text-lime-400"><ShieldAlert className="size-4" /> Admin Takeover</div>
            <p className="mt-2 text-2xl font-semibold text-lime-50">{counters.admin_takeover ?? 0}</p>
          </div>
        </section>

        <section className="rounded-2xl border border-lime-500/15 bg-black/60 p-5">
          <h2 className="text-lg font-semibold text-lime-50">Recent Conversations</h2>
          <p className="mt-1 text-xs text-slate-500">
            {response.error ? response.error : "Recent conversation activity is shown below."}
          </p>

          <div className="mt-4 overflow-x-auto rounded-xl border border-lime-500/15">
            <table className="min-w-full text-sm">
              <thead className="bg-black/55 text-left text-slate-300">
                <tr>
                  <th className="px-3 py-2">Session</th>
                  <th className="px-3 py-2">User</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Channel</th>
                  <th className="px-3 py-2">Language</th>
                </tr>
              </thead>
              <tbody>
                {conversations.slice(0, 12).map((item) => (
                  <tr key={item.session_id ?? `${item.user_id}-${item.status}`} className="border-t border-lime-500/10 text-lime-50/88">
                    <td className="px-3 py-2">{item.session_id ?? "-"}</td>
                    <td className="px-3 py-2">{item.user_id ?? "-"}</td>
                    <td className="px-3 py-2">{item.status ?? "unknown"}</td>
                    <td className="px-3 py-2">{item.channel ?? "-"}</td>
                    <td className="px-3 py-2">{item.language ?? "-"}</td>
                  </tr>
                ))}
                {conversations.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-3 py-4 text-center text-slate-500">
                      No conversations returned yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  )
}
