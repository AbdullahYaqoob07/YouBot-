import { BookOpenText, Database, FileClock } from "lucide-react"

import { KnowledgeIngestionForm } from "@/components/knowledge-ingestion-form"
import { fetchJson } from "@/lib/runtime-config"
import { createClient } from "@/lib/supabase/server"

type KBItem = {
  id: number
  user_question?: string
  category?: string
  user_language?: string
  added_to_kb_at?: string | null
  kb_document_id?: string | null
}

type KBItemsResponse = {
  success?: boolean
  items?: KBItem[]
  count?: number
}

type KnowledgeSource = {
  id: number
}

type IngestionJob = {
  id: number
}

type KnowledgeSourceResponse = {
  status?: string
  count?: number
  sources?: KnowledgeSource[]
}

type IngestionJobsResponse = {
  status?: string
  count?: number
  jobs?: IngestionJob[]
}

export default async function KnowledgePage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  const { data: { session } } = user ? await supabase.auth.getSession() : { data: { session: null } }
  const workspaceId = user?.id ?? "default"
  const authOptions = { tenantId: user?.id, accessToken: session?.access_token }

  const [itemsResponse, sourcesResponse, jobsResponse] = await Promise.all([
    fetchJson<KBItemsResponse>("/kb-curation/items?limit=30", authOptions),
    fetchJson<KnowledgeSourceResponse>(`/admin/workspaces/${workspaceId}/knowledge-sources`, authOptions),
    fetchJson<IngestionJobsResponse>(`/admin/workspaces/${workspaceId}/ingestion-jobs?limit=20`, authOptions),
  ])

  const items = itemsResponse.data?.items ?? []

  return (
    <div className="futuristic-bg h-full overflow-auto p-3 sm:p-5 lg:p-7">
      <div className="relative z-10 mx-auto max-w-6xl space-y-5">
        <section className="apex-panel rounded-2xl border border-lime-500/15 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-500">Experience</p>
              <h1 className="mt-2 text-3xl font-semibold text-lime-50">Knowledge Sources</h1>
              <p className="mt-2 text-sm text-slate-400">
                Review curated knowledge and ingestion status through a clean user-facing dashboard.
              </p>
            </div>
            <span className="rounded-lg border border-lime-500/30 bg-lime-500/10 px-3 py-2 text-xs text-lime-400">
              Knowledge status
            </span>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-3">
          <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
            <div className="flex items-center gap-2 text-lime-400"><Database className="size-4" /> Curated Items</div>
            <p className="mt-2 text-2xl font-semibold text-lime-50">{items.length}</p>
          </div>
          <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
            <div className="flex items-center gap-2 text-lime-400"><BookOpenText className="size-4" /> Scope</div>
            <p className="mt-2 text-sm text-lime-50">Connected</p>
          </div>
          <div className="rounded-xl border border-lime-500/15 bg-black/60 p-4">
            <div className="flex items-center gap-2 text-lime-400"><FileClock className="size-4" /> Source Status</div>
            <p className="mt-2 text-sm text-lime-50">{itemsResponse.error ? "Needs attention" : "Connected"}</p>
          </div>
        </section>

        <section className="rounded-2xl border border-lime-500/15 bg-black/60 p-5">
          <h2 className="text-lg font-semibold text-lime-50">Recent Knowledge Entries</h2>
          <p className="mt-1 text-xs text-slate-500">
            {itemsResponse.error ? itemsResponse.error : "Latest curated knowledge is shown below."}
          </p>

          <div className="mt-4 overflow-x-auto rounded-xl border border-lime-500/15">
            <table className="min-w-full text-sm">
              <thead className="bg-black/55 text-left text-slate-300">
                <tr>
                  <th className="px-3 py-2">ID</th>
                  <th className="px-3 py-2">Question</th>
                  <th className="px-3 py-2">Category</th>
                  <th className="px-3 py-2">Language</th>
                  <th className="px-3 py-2">Document</th>
                </tr>
              </thead>
              <tbody>
                {items.slice(0, 12).map((item) => (
                  <tr key={item.id} className="border-t border-lime-500/10 text-lime-50/88">
                    <td className="px-3 py-2">{item.id}</td>
                    <td className="px-3 py-2">{item.user_question ?? "-"}</td>
                    <td className="px-3 py-2">{item.category ?? "-"}</td>
                    <td className="px-3 py-2">{item.user_language ?? "-"}</td>
                    <td className="px-3 py-2">{item.kb_document_id ?? "-"}</td>
                  </tr>
                ))}
                {items.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-3 py-4 text-center text-slate-500">
                      No curated KB items found for this workspace.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="rounded-xl border border-lime-500/15 bg-lime-500/10 p-3 text-sm text-lime-50">
              <p className="font-semibold">Curation Items API</p>
              <p className="mt-1 text-xs text-slate-400">Latest knowledge entries</p>
              <p className="mt-2 text-xs text-slate-400">{itemsResponse.ok ? `items=${items.length}` : (itemsResponse.error ?? "failed")}</p>
            </div>
            <div className="rounded-xl border border-lime-500/15 bg-lime-500/10 p-3 text-sm text-lime-50">
              <p className="font-semibold">Knowledge Sources API</p>
              <p className="mt-1 text-xs text-slate-400">Configured sources</p>
              <p className="mt-2 text-xs text-slate-400">
                {sourcesResponse.ok ? `sources=${sourcesResponse.data?.sources?.length ?? 0}` : (sourcesResponse.error ?? "failed")}
              </p>
            </div>
            <div className="rounded-xl border border-lime-500/15 bg-lime-500/10 p-3 text-sm text-lime-50">
              <p className="font-semibold">Ingestion Jobs API</p>
              <p className="mt-1 text-xs text-slate-400">Background ingestion</p>
              <p className="mt-2 text-xs text-slate-400">
                {jobsResponse.ok ? `jobs=${jobsResponse.data?.jobs?.length ?? 0}` : (jobsResponse.error ?? "failed")}
              </p>
            </div>
          </div>

          <p className="mt-3 text-xs text-slate-500">
            Knowledge checks stay behind the scenes.
          </p>
        </section>

        <KnowledgeIngestionForm workspaceId={workspaceId} />
      </div>
    </div>
  )
}
