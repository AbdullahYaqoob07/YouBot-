import Link from "next/link"
import {
  ArrowRight,
  Bot,
  BookOpen,
  Building2,
  CheckCircle2,
  Code2,
  Globe2,
  KeyRound,
  LogIn,
  MessagesSquare,
  Plug,
  Send,
  ShieldCheck,
  Sparkles,
  Users2,
  Workflow,
} from "lucide-react"

import { createClient } from "@/lib/supabase/server"

const valueProps = [
  {
    icon: Building2,
    title: "Your brand, your tone",
    body: "Set the bot's identity in a 60-second form. Same backend, every business sounds like itself.",
  },
  {
    icon: BookOpen,
    title: "Grounded in your docs",
    body: "Upload PDFs, CSVs, web pages. The bot answers only from your knowledge base — no hallucinations.",
  },
  {
    icon: Globe2,
    title: "Speaks any language",
    body: "Replies match the customer's language automatically — across English, Spanish, German, Arabic, Urdu and more.",
  },
  {
    icon: ShieldCheck,
    title: "Smart human handoff",
    body: "When the bot doesn't know, it escalates to a human admin in real time — never a fabricated answer.",
  },
  {
    icon: Plug,
    title: "Connect anywhere",
    body: "REST API, web widget, WhatsApp, Instagram, Facebook, custom webhooks. One bot, every channel.",
  },
  {
    icon: KeyRound,
    title: "Bring your own LLM",
    body: "Pick Groq, OpenAI, Anthropic, or Gemini per workspace. Your keys, your costs, your control.",
  },
]

const steps = [
  {
    n: "01",
    title: "Set up your bot",
    body: "Tell us who you are: business name, tone, supported topics. Takes about a minute.",
  },
  {
    n: "02",
    title: "Add your knowledge",
    body: "Upload docs or point to a website. Pick a retrieval mode — quick, balanced, or deep context.",
  },
  {
    n: "03",
    title: "Embed and ship",
    body: "Drop the widget on your site or hit the API. Track every conversation in the live console.",
  },
]

const useCases = [
  { icon: MessagesSquare, label: "SaaS support" },
  { icon: Building2, label: "Real estate" },
  { icon: ShieldCheck, label: "Legal & compliance" },
  { icon: Users2, label: "HR & onboarding" },
  { icon: Workflow, label: "Logistics" },
  { icon: BookOpen, label: "Education" },
]

const stats = [
  { value: "<2s", label: "Average reply" },
  { value: "30+", label: "Languages" },
  { value: "3", label: "Retrieval modes" },
  { value: "100%", label: "Grounded answers" },
]

function ChatBubble({
  who,
  text,
  meta,
}: {
  who: "user" | "bot"
  text: string
  meta?: string
}) {
  if (who === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[78%] rounded-2xl rounded-br-sm border border-lime-500/15 bg-black/70 px-3 py-2 text-sm text-lime-50">
          {text}
        </div>
      </div>
    )
  }
  return (
    <div className="flex items-start gap-2">
      <span className="mt-1 grid size-6 shrink-0 place-items-center rounded-full border border-lime-500/30 bg-lime-500/10 text-lime-400">
        <Bot className="size-3" />
      </span>
      <div className="min-w-0">
        <div className="max-w-[92%] rounded-2xl rounded-bl-sm border border-lime-500/20 bg-lime-500/5 px-3 py-2 text-sm text-lime-50">
          {text}
        </div>
        {meta && (
          <p className="ml-1 mt-1 text-[10px] uppercase tracking-wider text-slate-500">
            {meta}
          </p>
        )}
      </div>
    </div>
  )
}

export default async function HomePage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  return (
    <div className="futuristic-bg min-h-full overflow-auto">
      {/* Top navigation */}
      <header className="sticky top-0 z-30 border-b border-lime-500/15 bg-black/60 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 md:px-6">
          <Link href="/" className="flex items-center gap-2">
            <span className="grid size-7 place-items-center rounded-full border border-lime-500/30 bg-lime-500/10 text-lime-400">
              <Sparkles className="size-3.5" />
            </span>
            <span className="text-sm font-semibold tracking-wider text-lime-50">YOUBOT</span>
          </Link>
          <nav className="hidden items-center gap-6 text-sm text-slate-300 md:flex">
            <a href="#features" className="transition hover:text-lime-400">Features</a>
            <a href="#how" className="transition hover:text-lime-400">How it works</a>
            <a href="#use-cases" className="transition hover:text-lime-400">Use cases</a>
            <a href="#integrate" className="transition hover:text-lime-400">Integrate</a>
          </nav>
          <div className="flex items-center gap-2">
            {!user && (
              <Link
                href="/login"
                className="hidden items-center gap-1.5 rounded-lg border border-lime-500/15 bg-black/50 px-3 py-1.5 text-xs text-slate-300 transition hover:border-lime-500/30 hover:text-lime-50 sm:inline-flex"
              >
                <LogIn className="size-3.5" /> Log in
              </Link>
            )}
            <Link
              href={user ? "/dashboard" : "/signup"}
              className="inline-flex items-center gap-1.5 rounded-lg border border-lime-500/40 bg-lime-500 px-3 py-1.5 text-xs font-semibold text-black transition hover:bg-lime-300"
            >
              {user ? "Open console" : "Start free"}
              <ArrowRight className="size-3.5" />
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 pb-20 pt-10 md:px-6 md:pt-14 lg:pt-20">
        {/* HERO */}
        <section className="grid items-center gap-10 lg:grid-cols-[1.15fr_1fr]">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-lime-500/30 bg-lime-500/10 px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-lime-400">
              <Sparkles className="size-3" /> Multi-tenant by design
            </span>
            <h1 className="mt-5 text-4xl font-semibold leading-[1.05] tracking-tight text-lime-50 sm:text-5xl lg:text-[3.6rem]">
              Customer support AI that sounds{" "}
              <span className="text-lime-400">like your brand</span>.
            </h1>
            <p className="mt-5 max-w-xl text-base text-slate-300 sm:text-lg">
              Drop in a chat widget, point it at your docs, and let the bot answer in your
              customer&apos;s language — grounded only in the knowledge you give it. No
              hallucinations, no infrastructure to run.
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-3">
              <Link
                href={user ? "/dashboard" : "/signup"}
                className="inline-flex items-center gap-2 rounded-lg border border-lime-500/40 bg-lime-500 px-5 py-2.5 text-sm font-semibold text-black shadow-[0_8px_30px_-8px_rgba(132,204,22,0.5)] transition hover:bg-lime-300"
              >
                {user ? "Open console" : "Start free"}
                <ArrowRight className="size-4" />
              </Link>
              <a
                href="#how"
                className="inline-flex items-center gap-2 rounded-lg border border-lime-500/20 bg-black/50 px-5 py-2.5 text-sm text-slate-200 transition hover:border-lime-500/40 hover:text-lime-50"
              >
                See how it works
              </a>
            </div>
            <div className="mt-7 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-slate-500">
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="size-3.5 text-lime-400" /> No credit card
              </span>
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="size-3.5 text-lime-400" /> Bring your own LLM
              </span>
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="size-3.5 text-lime-400" /> Self-hosted option
              </span>
            </div>
          </div>

          {/* Chat preview mock */}
          <div className="relative">
            <div className="pointer-events-none absolute -inset-4 rounded-[28px] bg-gradient-to-br from-lime-500/15 via-lime-500/5 to-transparent blur-2xl" />
            <div className="relative rounded-2xl border border-lime-500/20 bg-black/60 p-4 shadow-[0_0_60px_-15px_rgba(132,204,22,0.35)]">
              <div className="flex items-center gap-2 border-b border-lime-500/15 pb-3">
                <div className="flex gap-1.5">
                  <span className="size-2.5 rounded-full bg-rose-500/60" />
                  <span className="size-2.5 rounded-full bg-amber-500/60" />
                  <span className="size-2.5 rounded-full bg-lime-500/60" />
                </div>
                <p className="ml-1 truncate text-[11px] text-slate-400">
                  acme-logistics.com → support widget
                </p>
              </div>

              <div className="mt-4 space-y-3">
                <ChatBubble who="user" text="Hi, can I track my parcel from yesterday?" />
                <ChatBubble
                  who="bot"
                  text="Of course! Could you share the tracking number we emailed you when the parcel was picked up?"
                  meta="Quick Answer · 1.2s"
                />
                <ChatBubble who="user" text="ACL-78231" />
                <ChatBubble
                  who="bot"
                  text="Found it — ACL-78231 is in transit, expected delivery tomorrow before 6 PM. Want me to send live updates by email?"
                  meta="Hybrid · 1.8s"
                />
              </div>

              <div className="mt-4 flex items-center gap-2 rounded-lg border border-lime-500/15 bg-black/70 px-3 py-2">
                <input
                  disabled
                  placeholder="Ask anything…"
                  className="flex-1 bg-transparent text-sm text-slate-400 outline-none placeholder:text-slate-600"
                />
                <Send className="size-4 text-lime-400" />
              </div>
            </div>
          </div>
        </section>

        {/* STATS STRIP */}
        <section className="mt-14 grid grid-cols-2 gap-2 rounded-2xl border border-lime-500/15 bg-black/40 p-5 sm:grid-cols-4">
          {stats.map((s) => (
            <div key={s.label} className="text-center">
              <p className="text-2xl font-semibold text-lime-50 sm:text-3xl">{s.value}</p>
              <p className="mt-0.5 text-[11px] uppercase tracking-wider text-slate-500">
                {s.label}
              </p>
            </div>
          ))}
        </section>

        {/* FEATURES */}
        <section id="features" className="mt-20">
          <div className="max-w-2xl">
            <p className="text-[11px] font-medium uppercase tracking-wider text-lime-400">
              Why YouBot
            </p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight text-lime-50 sm:text-4xl">
              Everything you need to launch a real assistant.
            </h2>
            <p className="mt-3 text-base text-slate-400">
              Not a toy. Not a demo. A production-ready customer-support bot that respects
              your brand and grounds every answer in your data.
            </p>
          </div>

          <div className="mt-9 grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {valueProps.map((v) => (
              <article
                key={v.title}
                className="group rounded-2xl border border-lime-500/15 bg-black/40 p-5 transition hover:-translate-y-0.5 hover:border-lime-500/35 hover:bg-lime-500/5"
              >
                <div className="inline-flex rounded-lg border border-lime-500/30 bg-lime-500/10 p-2 text-lime-400 transition group-hover:bg-lime-500/15">
                  <v.icon className="size-4.5" />
                </div>
                <h3 className="mt-4 text-lg font-semibold text-lime-50">{v.title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-slate-400">{v.body}</p>
              </article>
            ))}
          </div>
        </section>

        {/* HOW IT WORKS */}
        <section
          id="how"
          className="mt-20 overflow-hidden rounded-3xl border border-lime-500/15 bg-black/40 p-6 lg:p-10"
        >
          <div className="max-w-2xl">
            <p className="text-[11px] font-medium uppercase tracking-wider text-lime-400">
              How it works
            </p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight text-lime-50 sm:text-4xl">
              From signup to live in under an hour.
            </h2>
            <p className="mt-3 text-base text-slate-400">
              Three short steps. The console walks you through each one.
            </p>
          </div>

          <div className="mt-8 grid gap-3 md:grid-cols-3">
            {steps.map((step, i) => (
              <div
                key={step.n}
                className="relative rounded-2xl border border-lime-500/15 bg-black/50 p-5"
              >
                <span className="text-4xl font-bold text-lime-500/30">{step.n}</span>
                <h3 className="mt-2 text-lg font-semibold text-lime-50">{step.title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-slate-400">{step.body}</p>
                {i < steps.length - 1 && (
                  <ArrowRight className="absolute -right-3 top-1/2 hidden size-5 -translate-y-1/2 text-lime-500/40 md:block" />
                )}
              </div>
            ))}
          </div>
        </section>

        {/* USE CASES */}
        <section id="use-cases" className="mt-20">
          <div className="max-w-2xl">
            <p className="text-[11px] font-medium uppercase tracking-wider text-lime-400">
              Use cases
            </p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight text-lime-50 sm:text-4xl">
              One backend, every industry.
            </h2>
            <p className="mt-3 text-base text-slate-400">
              Each workspace defines its own identity, tone, and scope. The bot adapts to fit.
            </p>
          </div>

          <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {useCases.map((u) => (
              <div
                key={u.label}
                className="flex flex-col items-center gap-2 rounded-xl border border-lime-500/15 bg-black/40 p-4 transition hover:border-lime-500/40 hover:bg-lime-500/5"
              >
                <u.icon className="size-5 text-lime-400" />
                <p className="text-center text-xs text-slate-300">{u.label}</p>
              </div>
            ))}
          </div>
        </section>

        {/* INTEGRATE */}
        <section
          id="integrate"
          className="mt-20 grid gap-8 lg:grid-cols-[1fr_1.1fr] lg:items-center"
        >
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-lime-400">
              Integrate
            </p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight text-lime-50 sm:text-4xl">
              One snippet. Live in minutes.
            </h2>
            <p className="mt-3 text-base text-slate-400">
              Embed the widget on any web page, call the REST API from your mobile app or
              backend, or wire up Meta channels with one webhook URL.
            </p>
            <ul className="mt-6 space-y-2 text-sm text-slate-300">
              <li className="flex items-center gap-2">
                <CheckCircle2 className="size-4 text-lime-400" /> Drop-in JavaScript widget
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle2 className="size-4 text-lime-400" /> REST API for custom UIs
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle2 className="size-4 text-lime-400" /> Meta webhook (WhatsApp, Instagram, Facebook)
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle2 className="size-4 text-lime-400" /> Outbound webhooks to your CRM
              </li>
            </ul>
          </div>

          <div className="overflow-hidden rounded-2xl border border-lime-500/15 bg-black/60">
            <div className="flex items-center justify-between border-b border-lime-500/15 bg-lime-950/20 px-3 py-1.5">
              <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
                html
              </span>
              <Code2 className="size-3.5 text-lime-400" />
            </div>
            <pre className="overflow-x-auto px-4 py-4 text-[12.5px] leading-relaxed text-lime-50">
              <code>{`<!-- YouBot Chat Widget -->
<script>
  window.YOUBOT_CONFIG = {
    apiBaseUrl: "https://api.youbot.io",
    apiKey: "pk_live_…",
    workspaceId: "ws_…",
    channel: "web",
  };
</script>
<script async src="https://cdn.youbot.io/widget.js"></script>`}</code>
            </pre>
          </div>
        </section>

        {/* FINAL CTA */}
        <section className="relative mt-20 overflow-hidden rounded-3xl border border-lime-500/30 bg-gradient-to-br from-lime-500/15 via-lime-500/5 to-black/40 p-8 text-center sm:p-14">
          <div className="pointer-events-none absolute -top-32 left-1/2 h-72 w-[min(82vw,720px)] -translate-x-1/2 rounded-full bg-lime-500/10 blur-3xl" />
          <div className="relative mx-auto max-w-2xl">
            <h2 className="text-3xl font-semibold tracking-tight text-lime-50 sm:text-4xl">
              Ready to give your customers a smarter conversation?
            </h2>
            <p className="mt-3 text-base text-slate-300">
              Spin up a workspace in 60 seconds. No credit card. Bring your own LLM key, or
              start with the included free tier.
            </p>
            <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
              <Link
                href={user ? "/dashboard" : "/signup"}
                className="inline-flex items-center gap-2 rounded-lg bg-lime-500 px-6 py-3 text-sm font-semibold text-black shadow-[0_8px_30px_-8px_rgba(132,204,22,0.5)] transition hover:bg-lime-300"
              >
                {user ? "Go to console" : "Start free"}
                <ArrowRight className="size-4" />
              </Link>
              {!user && (
                <Link
                  href="/login"
                  className="inline-flex items-center gap-2 rounded-lg border border-lime-500/30 bg-black/40 px-6 py-3 text-sm text-lime-50 transition hover:border-lime-500/50"
                >
                  <LogIn className="size-4" /> Sign in
                </Link>
              )}
            </div>
          </div>
        </section>
      </main>

      {/* FOOTER */}
      <footer className="border-t border-lime-500/10 bg-black/40 py-6">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 text-xs text-slate-500 md:px-6">
          <p>© {new Date().getFullYear()} YouBot. Built with care for customer-first teams.</p>
          <div className="flex items-center gap-4">
            <a href="#features" className="hover:text-lime-400">Features</a>
            <a href="#integrate" className="hover:text-lime-400">Integrate</a>
            <Link href="/login" className="hover:text-lime-400">Log in</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
