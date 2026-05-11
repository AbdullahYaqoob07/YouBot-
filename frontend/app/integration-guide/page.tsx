import {
  BookOpen,
  Cable,
  Code2,
  Globe,
  KeyRound,
  MessageCircleMore,
  ShieldCheck,
  Webhook,
} from "lucide-react"

import { CopySnippet, CopyValue } from "@/components/copy-snippet"
import { fetchJson } from "@/lib/runtime-config"
import { createClient } from "@/lib/supabase/server"

type ClientApiKey = {
  id: number
  name: string
  key_type: string
  api_key: string
  is_active: boolean
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

function getPublicApiBaseUrl(): string {
  const raw =
    process.env.NEXT_PUBLIC_YOUBOT_API_BASE_URL ??
    process.env.YOUBOT_API_BASE_URL ??
    "http://127.0.0.1:8000"
  return raw.replace(/\/+$/, "")
}

export default async function IntegrationGuidePage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  const { data: { session } } = user ? await supabase.auth.getSession() : { data: { session: null } }
  const workspaceId = user?.id ?? "default"
  const authOptions = { tenantId: user?.id, accessToken: session?.access_token }

  const apiBaseUrl = getPublicApiBaseUrl()

  const [keysResult, socialResult] = await Promise.all([
    fetchJson<ClientApiKey[]>(`/admin/workspaces/${workspaceId}/client-keys`, authOptions),
    fetchJson<SocialConnectionResponse>(`/admin/workspaces/${workspaceId}/social-connections`, authOptions),
  ])

  const clientKeys = (keysResult.data ?? []).filter((k) => k.is_active)
  const socialConnections = (socialResult.data?.connections ?? []).filter((c) => c.is_active)

  const publicWidgetKey = clientKeys.find((k) => k.key_type === "public_widget")
  const secretApiKey = clientKeys.find((k) => k.key_type === "secret_api")
  const sampleClientKey = publicWidgetKey?.api_key ?? secretApiKey?.api_key ?? "<your-client-api-key>"

  const chatEndpoint = `${apiBaseUrl}/v1/chat`
  const historyEndpointTemplate = `${apiBaseUrl}/chat/{session_id}/history`

  const widgetSnippet = `<!-- YouBot Chat Widget -->
<script>
  window.YOUBOT_CONFIG = {
    apiBaseUrl: "${apiBaseUrl}",
    apiKey: "${sampleClientKey}",
    workspaceId: "${workspaceId}",
    channel: "web",
  };
</script>
<script async src="${apiBaseUrl}/widget/youbot-widget.js"></script>`

  const fetchSnippet = `// Send a message from your web app
const response = await fetch("${chatEndpoint}", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-API-Key": "${sampleClientKey}",
  },
  body: JSON.stringify({
    message: "Hi, I have a question about your services.",
    userId: "user-123",                 // your stable user id
    sessionId: "optional-session-id",   // omit to start a new session
    channel: "web",
    language: "en",
  }),
});

const data = await response.json();
console.log(data.response, data.sessionId);`

  const curlSnippet = `curl -X POST "${chatEndpoint}" \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: ${sampleClientKey}" \\
  -d '{
    "message": "Hello",
    "userId": "user-123",
    "channel": "web"
  }'`

  const pythonSnippet = `import requests

resp = requests.post(
    "${chatEndpoint}",
    headers={
        "Content-Type": "application/json",
        "X-API-Key": "${sampleClientKey}",
    },
    json={
        "message": "Hello",
        "userId": "user-123",
        "channel": "web",
    },
    timeout=30,
)
data = resp.json()
print(data["response"], data["sessionId"])`

  return (
    <div className="futuristic-bg h-full overflow-auto p-3 sm:p-5 lg:p-7">
      <div className="relative z-10 mx-auto max-w-6xl space-y-6">
        {/* Hero */}
        <section className="apex-panel rounded-2xl border border-lime-500/15 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-500">User Guide</p>
              <h1 className="mt-2 text-3xl font-semibold text-lime-50">Integration Guide</h1>
              <p className="mt-2 max-w-2xl text-sm text-slate-400">
                Connect the YouBot assistant to your website, mobile app, or social channels.
                Every snippet below is pre-filled with your workspace ID and active API keys.
              </p>
            </div>
            <span className="rounded-lg border border-lime-500/30 bg-lime-500/10 px-3 py-2 text-xs text-lime-400">
              Personalised for your workspace
            </span>
          </div>
        </section>

        {/* Quick reference card */}
        <section className="rounded-2xl border border-lime-500/15 bg-black/40 p-5">
          <div className="flex items-center gap-2 text-lime-400">
            <KeyRound className="size-4" />
            <h2 className="text-lg font-semibold text-lime-50">Your workspace credentials</h2>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            These values identify your tenant. Treat secret keys (`sk_…`) like passwords.
          </p>

          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <CopyValue label="API Base URL" value={apiBaseUrl} />
            <CopyValue label="Workspace ID" value={workspaceId} />
          </div>

          <div className="mt-4 space-y-2">
            <p className="text-xs uppercase tracking-wider text-slate-500">
              Active client API keys
            </p>
            {clientKeys.length === 0 && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-300">
                No active client keys yet. Visit{" "}
                <a href="/integrations" className="underline">
                  Integration Selection
                </a>{" "}
                to create one before integrating.
              </div>
            )}
            {clientKeys.map((key) => (
              <div
                key={key.id}
                className="rounded-lg border border-lime-500/15 bg-black/50 p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-lime-50">
                    {key.name}{" "}
                    <span className="text-xs text-slate-500">({key.key_type})</span>
                  </p>
                  <span
                    className={
                      key.key_type === "secret_api"
                        ? "rounded-md border border-rose-500/30 bg-rose-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-rose-300"
                        : "rounded-md border border-lime-500/30 bg-lime-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-lime-400"
                    }
                  >
                    {key.key_type === "secret_api" ? "Server-side only" : "Browser-safe"}
                  </span>
                </div>
                <div className="mt-2">
                  <CopyValue value={key.api_key} label="X-API-Key" />
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* 1. Web Widget */}
        <section className="rounded-2xl border border-lime-500/15 bg-black/40 p-5">
          <div className="flex items-center gap-2 text-lime-400">
            <Globe className="size-4" />
            <h2 className="text-lg font-semibold text-lime-50">1. Embed on your website</h2>
          </div>
          <p className="mt-1 text-sm text-slate-400">
            Drop this snippet right before <code className="text-lime-400">{"</body>"}</code> on
            any page where you want the assistant to appear. Use a <em>public_widget</em> key —
            never paste a <em>secret_api</em> key into client-side code.
          </p>
          <div className="mt-4">
            <CopySnippet value={widgetSnippet} language="HTML" label="HTML embed" />
          </div>
          <p className="mt-3 text-xs text-slate-500">
            The widget will create user sessions, persist them in `localStorage`, and stream
            replies through the same endpoint shown below.
          </p>
        </section>

        {/* 2. REST API */}
        <section className="rounded-2xl border border-lime-500/15 bg-black/40 p-5">
          <div className="flex items-center gap-2 text-lime-400">
            <Code2 className="size-4" />
            <h2 className="text-lg font-semibold text-lime-50">2. Call the chat API directly</h2>
          </div>
          <p className="mt-1 text-sm text-slate-400">
            For mobile apps, custom UIs, or backend automations. Authenticate with the{" "}
            <code className="text-lime-400">X-API-Key</code> header.
          </p>

          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <CopyValue label="POST endpoint" value={chatEndpoint} />
            <CopyValue label="History (GET)" value={historyEndpointTemplate} />
          </div>

          <div className="mt-4 space-y-3">
            <CopySnippet value={curlSnippet} language="bash" label="cURL" />
            <CopySnippet value={fetchSnippet} language="javascript" label="JavaScript (fetch)" />
            <CopySnippet value={pythonSnippet} language="python" label="Python (requests)" />
          </div>

          <div className="mt-4 rounded-lg border border-lime-500/15 bg-black/50 p-3 text-xs text-slate-400">
            <p className="font-medium text-slate-300">Required body fields</p>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              <li>
                <code className="text-lime-50">message</code> — the user&apos;s text
              </li>
              <li>
                <code className="text-lime-50">userId</code> — a stable id you control (used for
                routing & analytics)
              </li>
              <li>
                <code className="text-lime-50">channel</code> — e.g. <code>web</code>,{" "}
                <code>mobile</code>, <code>custom</code>
              </li>
              <li>
                <code className="text-lime-50">sessionId</code> — optional; omit on the first
                message and reuse the value the API returns
              </li>
              <li>
                <code className="text-lime-50">language</code> — optional ISO code, auto-detected
                if omitted
              </li>
            </ul>
          </div>
        </section>

        {/* 3. Social channels */}
        <section className="rounded-2xl border border-lime-500/15 bg-black/40 p-5">
          <div className="flex items-center gap-2 text-lime-400">
            <MessageCircleMore className="size-4" />
            <h2 className="text-lg font-semibold text-lime-50">
              3. Social channels (WhatsApp, Instagram, Facebook)
            </h2>
          </div>
          <p className="mt-1 text-sm text-slate-400">
            Each connector you create on the{" "}
            <a className="underline" href="/channels">
              Channels page
            </a>{" "}
            gets its own <code className="text-lime-400">connection_key</code>. Plug the URLs
            below into the matching field of the provider&apos;s developer console.
          </p>

          {socialConnections.length === 0 && (
            <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-300">
              No social connectors yet. Create one on the Channels page first; the verification
              and inbound URLs will appear here automatically.
            </div>
          )}

          <div className="mt-4 space-y-4">
            {socialConnections.map((connection) => {
              const verifyUrl = `${apiBaseUrl}/integrations/social/meta/${connection.connection_key}/webhook`
              const sendUrl = `${apiBaseUrl}/integrations/social/${connection.connection_key}/messages`
              const isMeta = connection.provider === "meta"

              return (
                <div
                  key={connection.id}
                  className="rounded-xl border border-lime-500/15 bg-black/50 p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-lime-50">{connection.name}</p>
                      <p className="text-xs text-slate-500">
                        {connection.provider} / {connection.channel}
                      </p>
                    </div>
                    <span className="rounded-md border border-lime-500/30 bg-lime-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-lime-400">
                      {isMeta ? "Meta webhook" : "Generic inbound"}
                    </span>
                  </div>

                  <div className="mt-3 space-y-2">
                    <CopyValue label="Connection key" value={connection.connection_key} />
                    {isMeta ? (
                      <>
                        <CopyValue
                          label="Callback URL (verify + receive)"
                          value={verifyUrl}
                        />
                        <p className="text-xs text-slate-500">
                          Paste this into the Meta App Dashboard → Webhooks → Callback URL. The
                          Verify Token you set on the Channels page must match the one you enter
                          in Meta.
                        </p>
                      </>
                    ) : (
                      <>
                        <CopyValue label="Outbound dispatch URL" value={sendUrl} />
                        <p className="text-xs text-slate-500">
                          POST a JSON body{" "}
                          <code>{`{ "userId": "...", "message": "...", "channel": "${connection.channel}" }`}</code>{" "}
                          to dispatch a message into the assistant from any system you control.
                        </p>
                      </>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        {/* 4. Custom webhook */}
        <section className="rounded-2xl border border-lime-500/15 bg-black/40 p-5">
          <div className="flex items-center gap-2 text-lime-400">
            <Webhook className="size-4" />
            <h2 className="text-lg font-semibold text-lime-50">
              4. Custom outbound webhooks
            </h2>
          </div>
          <p className="mt-1 text-sm text-slate-400">
            When the assistant produces a reply for a social connector with an{" "}
            <code className="text-lime-400">outboundWebhookUrl</code> configured, we POST the
            payload to your URL with the headers and signature you set on the Channels page.
            Use this for custom CRMs, helpdesks, or in-house chat backends.
          </p>
          <div className="mt-4">
            <CopySnippet
              language="json"
              label="Outbound payload"
              value={`{
  "connectionKey": "sc_...",
  "channel": "whatsapp",
  "userId": "1555550123",
  "sessionId": "sess_...",
  "message": "Hello! I'm here to help.",
  "language": "en",
  "timestamp": "2026-05-09T11:00:00Z"
}`}
            />
          </div>
        </section>

        {/* Security notes */}
        <section className="rounded-2xl border border-lime-500/15 bg-black/40 p-5">
          <div className="flex items-center gap-2 text-lime-400">
            <ShieldCheck className="size-4" />
            <h2 className="text-lg font-semibold text-lime-50">Security checklist</h2>
          </div>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-300">
            <li>
              Use a <strong>public_widget</strong> key (<code>pk_…</code>) for browser-side
              embeds; restrict it to your domains on the Integrations page.
            </li>
            <li>
              Use a <strong>secret_api</strong> key (<code>sk_…</code>) only from your own
              servers — never ship it to the browser.
            </li>
            <li>
              Rotate keys from the Integrations page if you suspect a leak — old keys stop
              working immediately.
            </li>
            <li>
              The <code>workspace_id</code> shown above is unique to your account; every request
              you make is automatically scoped to it.
            </li>
            <li>
              Meta webhooks are signature-verified using the App Secret you provide on the
              Channels page; payloads with mismatched signatures are rejected.
            </li>
          </ul>
        </section>

        {/* Help */}
        <section className="apex-panel rounded-2xl border border-lime-500/15 p-5">
          <div className="flex items-center gap-2 text-lime-400">
            <BookOpen className="size-4" />
            <h2 className="text-lg font-semibold text-lime-50">Where to next</h2>
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <a
              href="/integrations"
              className="group rounded-xl border border-lime-500/15 bg-lime-500/5 p-3 transition hover:border-lime-500/30 hover:bg-lime-500/10"
            >
              <div className="flex items-center gap-2 text-lime-400">
                <Cable className="size-4" /> Integrations
              </div>
              <p className="mt-1 text-xs text-slate-400">Create &amp; rotate API keys.</p>
            </a>
            <a
              href="/channels"
              className="group rounded-xl border border-lime-500/15 bg-lime-500/5 p-3 transition hover:border-lime-500/30 hover:bg-lime-500/10"
            >
              <div className="flex items-center gap-2 text-lime-400">
                <MessageCircleMore className="size-4" /> Channels
              </div>
              <p className="mt-1 text-xs text-slate-400">Wire up Meta &amp; custom webhooks.</p>
            </a>
            <a
              href="/knowledge"
              className="group rounded-xl border border-lime-500/15 bg-lime-500/5 p-3 transition hover:border-lime-500/30 hover:bg-lime-500/10"
            >
              <div className="flex items-center gap-2 text-lime-400">
                <BookOpen className="size-4" /> Knowledge
              </div>
              <p className="mt-1 text-xs text-slate-400">Feed the assistant your docs.</p>
            </a>
            <a
              href="/chat-tests"
              className="group rounded-xl border border-lime-500/15 bg-lime-500/5 p-3 transition hover:border-lime-500/30 hover:bg-lime-500/10"
            >
              <div className="flex items-center gap-2 text-lime-400">
                <Code2 className="size-4" /> Sandbox
              </div>
              <p className="mt-1 text-xs text-slate-400">Test before going live.</p>
            </a>
          </div>
        </section>
      </div>
    </div>
  )
}
