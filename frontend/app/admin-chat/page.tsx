import { AdminChatHandler } from "@/components/admin-chat-handler"
import { createClient } from "@/lib/supabase/server"

export default async function AdminChatPage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  const defaultAdminId = user?.email ?? user?.id ?? "admin_console"

  return (
    <div className="futuristic-bg h-full overflow-auto p-3 sm:p-5 lg:p-7">
      <div className="relative z-10 mx-auto max-w-6xl space-y-5">
        <section className="apex-panel rounded-2xl border border-lime-500/15 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-500">Operations</p>
              <h1 className="mt-2 text-3xl font-semibold text-lime-50">Admin Chat Handler</h1>
              <p className="mt-2 text-sm text-slate-400">
                Handle live conversations with takeover, AI-assisted drafting, and release controls.
              </p>
            </div>
            <span className="rounded-lg border border-lime-500/30 bg-lime-500/10 px-3 py-2 text-xs text-lime-400">
              Admin console ready
            </span>
          </div>
        </section>

        <AdminChatHandler defaultAdminId={defaultAdminId} />
      </div>
    </div>
  )
}
