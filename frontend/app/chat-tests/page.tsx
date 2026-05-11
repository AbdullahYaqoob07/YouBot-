import { FlaskConical, ShieldCheck, Stethoscope } from "lucide-react"

import { ChatTestRunner } from "@/components/chat-test-runner"
import { fetchJson } from "@/lib/runtime-config"
import { createClient } from "@/lib/supabase/server"

type HealthResponse = {
  status?: string
  version?: string
  components?: Record<string, { status?: string }>
}

type SupervisionResponse = {
  total?: number
  conversations?: unknown[]
}

type WorkspaceLLMConfig = {
  provider?: string
  model?: string
  updatedAt?: string | null
}

type KBItemsResponse = {
  count?: number
  items?: unknown[]
}

type SocialConnectionResponse = {
  connections?: unknown[]
}

type ClientKey = {
  id: number
}

type ApiCheck = {
  label: string
  endpoint: string
  ok: boolean
  detail: string
}

export default async function ChatTestsPage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  const { data: { session } } = user ? await supabase.auth.getSession() : { data: { session: null } }
  const workspaceId = user?.id ?? "default"
  const authOptions = { tenantId: user?.id, accessToken: session?.access_token }

  const [
    health,
    supervision,
    llmConfig,
    kbItems,
    socialConnections,
    clientKeys,
  ] = await Promise.all([
    fetchJson<HealthResponse>("/health", { includeAdminKey: false }),
    fetchJson<SupervisionResponse>("/admin/supervision/conversations", authOptions),
    fetchJson<WorkspaceLLMConfig>(`/admin/workspaces/${workspaceId}/llm-config`, authOptions),
    fetchJson<KBItemsResponse>("/kb-curation/items?limit=1", authOptions),
    fetchJson<SocialConnectionResponse>(`/admin/workspaces/${workspaceId}/social-connections`, authOptions),
    fetchJson<ClientKey[]>(`/admin/workspaces/${workspaceId}/client-keys`, authOptions),
  ])

  const healthStatus = health.data?.status ?? "unknown"
  const apiChecks: ApiCheck[] = [
    {
      label: "Health",
      endpoint: "/health",
      ok: health.ok,
      detail: health.ok ? `status=${healthStatus}` : (health.error ?? "unreachable"),
    },
    {
      label: "Supervision",
      endpoint: "/admin/supervision/conversations",
      ok: supervision.ok,
      detail: supervision.ok
        ? `conversations=${supervision.data?.total ?? supervision.data?.conversations?.length ?? 0}`
        : (supervision.error ?? "failed"),
    },
    {
      label: "LLM Config",
      endpoint: `/admin/workspaces/${workspaceId}/llm-config`,
      ok: llmConfig.ok,
      detail: llmConfig.ok
        ? `${llmConfig.data?.provider ?? "unknown"} / ${llmConfig.data?.model ?? "unknown"}`
        : (llmConfig.error ?? "failed"),
    },
    {
      label: "KB Curation",
      endpoint: "/kb-curation/items?limit=1",
      ok: kbItems.ok,
      detail: kbItems.ok
        ? `items=${kbItems.data?.count ?? kbItems.data?.items?.length ?? 0}`
        : (kbItems.error ?? "failed"),
    },
    {
      label: "Social Connections",
      endpoint: `/admin/workspaces/${workspaceId}/social-connections`,
      ok: socialConnections.ok,
      detail: socialConnections.ok
        ? `connections=${socialConnections.data?.connections?.length ?? 0}`
        : (socialConnections.error ?? "failed"),
    },
    {
      label: "Client Keys",
      endpoint: `/admin/workspaces/${workspaceId}/client-keys`,
      ok: clientKeys.ok,
      detail: clientKeys.ok
        ? `keys=${clientKeys.data?.length ?? 0}`
        : (clientKeys.error ?? "failed"),
    },
  ]

  return (
    <div className="futuristic-bg h-full overflow-auto p-3 sm:p-5 lg:p-7">
      <div className="relative z-10 mx-auto max-w-6xl space-y-5">
        <section className="apex-panel rounded-2xl border border-lime-500/20 bg-black/40 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
                Operations
              </p>
              <h1 className="mt-1.5 text-2xl font-semibold text-lime-50">Bot Testing Sandbox</h1>
              <p className="mt-1.5 max-w-2xl text-sm text-slate-400">
                Make sure the bot answers your customers the way you want. Try real questions,
                switch retrieval modes, and inspect every response.
              </p>
            </div>
            <span className="rounded-lg border border-lime-500/30 bg-lime-500/10 px-3 py-1.5 text-xs font-medium text-lime-400">
              Live workspace
            </span>
          </div>
        </section>

        <section className="grid gap-3 md:grid-cols-3">
          <div className="rounded-xl border border-lime-500/15 bg-black/50 p-4">
            <div className="flex items-center gap-2 text-slate-400">
              <Stethoscope className="h-4 w-4 text-lime-400" />
              <p className="text-xs font-medium uppercase tracking-wider">Backend</p>
            </div>
            <p className="mt-2 text-2xl font-semibold text-lime-50">
              {healthStatus.toUpperCase()}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              {health.error ? health.error : "Health endpoint reachable."}
            </p>
          </div>

          <div className="rounded-xl border border-lime-500/15 bg-black/50 p-4">
            <div className="flex items-center gap-2 text-slate-400">
              <ShieldCheck className="h-4 w-4 text-lime-400" />
              <p className="text-xs font-medium uppercase tracking-wider">Workspace</p>
            </div>
            <p className="mt-2 text-sm text-lime-50">Connected</p>
            <p className="mt-1 text-xs text-slate-500">Scoped to your account.</p>
          </div>

          <div className="rounded-xl border border-lime-500/15 bg-black/50 p-4">
            <div className="flex items-center gap-2 text-slate-400">
              <FlaskConical className="h-4 w-4 text-lime-400" />
              <p className="text-xs font-medium uppercase tracking-wider">Access</p>
            </div>
            <p className="mt-2 text-sm text-lime-50">{user ? "Ready" : "Sign in"}</p>
            <p className="mt-1 text-xs text-slate-500">Authenticated session.</p>
          </div>
        </section>

        <section className="rounded-2xl border border-lime-500/20 bg-black/40 p-5">
          <h2 className="text-base font-semibold text-lime-50">Connection checks</h2>
          <p className="mt-1 text-xs text-slate-500">
            Each piece your bot needs to work end-to-end.
          </p>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {apiChecks.map((check) => (
              <div
                key={check.label}
                className="rounded-xl border border-lime-500/15 bg-black/50 p-3"
              >
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-lime-50">{check.label}</p>
                  <span
                    className={
                      "rounded-full px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider " +
                      (check.ok
                        ? "border border-lime-500/30 bg-lime-500/10 text-lime-400"
                        : "border border-amber-500/30 bg-amber-500/10 text-amber-300")
                    }
                  >
                    {check.ok ? "OK" : "Attention"}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-400">{check.detail}</p>
              </div>
            ))}
          </div>
        </section>

        <ChatTestRunner workspaceId={workspaceId} />

        <section className="rounded-2xl border border-lime-500/20 bg-black/40 p-5">
          <h2 className="text-base font-semibold text-lime-50">Picking the right mode</h2>
          <p className="mt-1 text-xs text-slate-500">
            Plain-English version of the four lookup modes.
          </p>
          <ul className="mt-4 space-y-3 text-sm text-slate-300">
            <li className="rounded-xl border border-lime-500/15 bg-black/50 p-3">
              <p className="font-medium text-lime-50">
                Smart Auto <span className="text-xs font-normal text-slate-500">— recommended</span>
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Lets the system choose for each question. Good default for most workspaces.
              </p>
            </li>
            <li className="rounded-xl border border-lime-500/15 bg-black/50 p-3">
              <p className="font-medium text-lime-50">Quick Answer (RAG)</p>
              <p className="mt-1 text-xs text-slate-400">
                Fastest, cheapest. Use when answers fit in a few sentences — typical FAQ
                support.
              </p>
            </li>
            <li className="rounded-xl border border-lime-500/15 bg-black/50 p-3">
              <p className="font-medium text-lime-50">Balanced Search (Hybrid)</p>
              <p className="mt-1 text-xs text-slate-400">
                Mixes meaning with exact-word matching. Use when product names, version
                numbers, or named policies must match exactly.
              </p>
            </li>
            <li className="rounded-xl border border-lime-500/15 bg-black/50 p-3">
              <p className="font-medium text-lime-50">Deep Context (Page Index)</p>
              <p className="mt-1 text-xs text-slate-400">
                Loads whole pages around each match. Use for legal documents, contracts, or
                long policies where one paragraph isn&apos;t enough.
              </p>
            </li>
          </ul>
          <p className="mt-4 text-xs text-slate-500">
            All four options above run on the same indexed data — the difference is the
            algorithm used to look things up at query time, not how documents were stored.
            Use this sandbox to compare modes on real customer questions, then commit the
            winner from{" "}
            <a className="text-lime-400 underline-offset-2 hover:underline" href="/settings">
              Settings → Bot behaviour
            </a>{" "}
            so production traffic uses it.
          </p>
        </section>
      </div>
    </div>
  )
}
