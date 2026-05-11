"use client"

import { Building2, Loader2, Plus, Save, X } from "lucide-react"
import { useState } from "react"

import { consoleProxy } from "@/lib/console-proxy-client"

type Tone = "warm" | "professional" | "casual" | "formal"

export type AssistantProfile = {
  business_name?: string
  business_description?: string
  service_topics?: string[]
  tone?: string
  website_url?: string
  contact_email?: string
  handoff_message?: string
  forbidden_topics?: string[]
}

type Props = {
  workspaceId: string
  initialProfile: AssistantProfile | null
}

const TONE_OPTIONS: Array<{ value: Tone; label: string; description: string }> = [
  { value: "warm",         label: "Warm",         description: "Friendly, empathetic, encouraging." },
  { value: "professional", label: "Professional", description: "Polished, factual, no slang." },
  { value: "casual",       label: "Casual",       description: "Conversational, contractions OK." },
  { value: "formal",       label: "Formal",       description: "Precise, deferential, full sentences." },
]

function normalizeTone(value: string | undefined): Tone {
  if (value === "professional" || value === "casual" || value === "formal") return value
  return "warm"
}

export function AssistantProfileForm({ workspaceId, initialProfile }: Props) {
  const [businessName, setBusinessName] = useState(initialProfile?.business_name ?? "")
  const [businessDescription, setBusinessDescription] = useState(initialProfile?.business_description ?? "")
  const [topics, setTopics] = useState<string[]>(initialProfile?.service_topics ?? [])
  const [topicInput, setTopicInput] = useState("")
  const [forbidden, setForbidden] = useState<string[]>(initialProfile?.forbidden_topics ?? [])
  const [forbiddenInput, setForbiddenInput] = useState("")
  const [tone, setTone] = useState<Tone>(normalizeTone(initialProfile?.tone))
  const [websiteUrl, setWebsiteUrl] = useState(initialProfile?.website_url ?? "")
  const [contactEmail, setContactEmail] = useState(initialProfile?.contact_email ?? "")
  const [handoffMessage, setHandoffMessage] = useState(initialProfile?.handoff_message ?? "")
  const [busy, setBusy] = useState(false)
  const [statusMsg, setStatusMsg] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const addTopic = (
    value: string,
    list: string[],
    setList: (v: string[]) => void,
    setInput: (v: string) => void,
  ) => {
    const cleaned = value.trim()
    if (!cleaned) return
    if (list.some((t) => t.toLowerCase() === cleaned.toLowerCase())) {
      setInput("")
      return
    }
    setList([...list, cleaned])
    setInput("")
  }

  const removeAt = <T,>(list: T[], setList: (v: T[]) => void, idx: number) => {
    setList(list.filter((_, i) => i !== idx))
  }

  const save = async () => {
    if (!businessName.trim()) {
      setErrorMsg("Please enter your business name.")
      return
    }
    setBusy(true)
    setStatusMsg(null)
    setErrorMsg(null)

    const result = await consoleProxy<{ status?: string; profile?: AssistantProfile }>({
      path: `/admin/workspaces/${workspaceId}/assistant-profile`,
      method: "POST",
      body: {
        businessName: businessName.trim(),
        businessDescription: businessDescription.trim() || null,
        serviceTopics: topics,
        tone,
        websiteUrl: websiteUrl.trim() || null,
        contactEmail: contactEmail.trim() || null,
        handoffMessage: handoffMessage.trim() || null,
        forbiddenTopics: forbidden,
      },
    })

    if (result.ok) {
      setStatusMsg("Saved. New customer messages will use this identity.")
    } else {
      setErrorMsg(result.error ?? `HTTP ${result.status}`)
    }
    setBusy(false)
  }

  return (
    <section className="rounded-2xl border border-lime-500/20 bg-black/40 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold text-lime-50">
            <Building2 className="h-4 w-4 text-lime-400" />
            Bot identity
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Tell the bot who it works for. This shapes its tone, scope, and how it
            introduces itself — without changing any code.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void save()}
          disabled={busy}
          className="flex items-center gap-2 rounded-lg border border-lime-500/30 bg-lime-500/15 px-3 py-1.5 text-xs font-medium text-lime-400 transition hover:border-lime-500/50 hover:bg-lime-500/25 disabled:opacity-40"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
          Save identity
        </button>
      </div>

      {(statusMsg || errorMsg) && (
        <div
          className={
            "mt-3 rounded-lg border px-3 py-2 text-xs " +
            (errorMsg
              ? "border-rose-500/30 bg-rose-500/10 text-rose-300"
              : "border-emerald-500/30 bg-emerald-500/10 text-emerald-300")
          }
        >
          {errorMsg ?? statusMsg}
        </div>
      )}

      {/* Business name + description */}
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <label className="rounded-xl border border-lime-500/15 bg-black/50 p-3">
          <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
            Business name
          </span>
          <input
            type="text"
            value={businessName}
            onChange={(e) => setBusinessName(e.target.value)}
            placeholder="Acme Logistics"
            className="mt-2 w-full rounded-lg border border-lime-500/20 bg-black/60 px-3 py-2 text-sm text-lime-50 outline-none focus:border-lime-500/50"
          />
          <span className="mt-1 block text-[10px] text-slate-500">
            Used when the bot introduces itself.
          </span>
        </label>
        <label className="rounded-xl border border-lime-500/15 bg-black/50 p-3">
          <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
            What does your business do?
          </span>
          <input
            type="text"
            value={businessDescription}
            onChange={(e) => setBusinessDescription(e.target.value)}
            placeholder="Same-day parcel delivery for SMBs"
            maxLength={200}
            className="mt-2 w-full rounded-lg border border-lime-500/20 bg-black/60 px-3 py-2 text-sm text-lime-50 outline-none focus:border-lime-500/50"
          />
          <span className="mt-1 block text-[10px] text-slate-500">
            One short line. Helps the bot stay on-topic.
          </span>
        </label>
      </div>

      {/* Service topics */}
      <div className="mt-3 rounded-xl border border-lime-500/15 bg-black/50 p-3">
        <p className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
          Topics the bot should help with
        </p>
        <p className="mt-1 text-xs text-slate-500">
          Add the categories of questions you expect — e.g. <em>shipping</em>,{" "}
          <em>returns</em>, <em>billing</em>, <em>tracking</em>. The bot uses these to know
          what&apos;s in scope.
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {topics.map((topic, idx) => (
            <span
              key={`${topic}-${idx}`}
              className="inline-flex items-center gap-1.5 rounded-full border border-lime-500/30 bg-lime-500/10 px-2.5 py-1 text-xs text-lime-300"
            >
              {topic}
              <button
                type="button"
                onClick={() => removeAt(topics, setTopics, idx)}
                className="text-lime-300/70 hover:text-rose-300"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
          {topics.length === 0 && (
            <span className="text-xs text-slate-500">No topics yet — add a few below.</span>
          )}
        </div>
        <div className="mt-3 flex gap-2">
          <input
            type="text"
            value={topicInput}
            onChange={(e) => setTopicInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault()
                addTopic(topicInput, topics, setTopics, setTopicInput)
              }
            }}
            placeholder="Add a topic and press Enter"
            className="flex-1 rounded-lg border border-lime-500/20 bg-black/60 px-3 py-2 text-sm text-lime-50 placeholder:text-slate-600 outline-none focus:border-lime-500/50"
          />
          <button
            type="button"
            onClick={() => addTopic(topicInput, topics, setTopics, setTopicInput)}
            className="flex items-center gap-1.5 rounded-lg border border-lime-500/30 bg-lime-500/10 px-3 py-1.5 text-xs text-lime-400 hover:bg-lime-500/20"
          >
            <Plus className="h-3.5 w-3.5" /> Add
          </button>
        </div>
      </div>

      {/* Tone picker */}
      <div className="mt-3">
        <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-slate-500">
          Tone of voice
        </p>
        <fieldset className="grid gap-2 md:grid-cols-4">
          <legend className="sr-only">Tone</legend>
          {TONE_OPTIONS.map((option) => {
            const active = tone === option.value
            return (
              <label
                key={option.value}
                className={
                  "cursor-pointer rounded-xl border p-3 transition " +
                  (active
                    ? "border-lime-500/50 bg-lime-500/10"
                    : "border-lime-500/15 bg-black/50 hover:border-lime-500/30 hover:bg-lime-500/5")
                }
              >
                <input
                  type="radio"
                  name="tone"
                  value={option.value}
                  checked={active}
                  onChange={() => setTone(option.value)}
                  className="sr-only"
                />
                <p className="text-sm font-semibold text-lime-50">{option.label}</p>
                <p className="mt-1 text-[11px] leading-snug text-slate-400">
                  {option.description}
                </p>
              </label>
            )
          })}
        </fieldset>
      </div>

      {/* Contact info */}
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <label className="rounded-xl border border-lime-500/15 bg-black/50 p-3">
          <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
            Website (optional)
          </span>
          <input
            type="url"
            value={websiteUrl}
            onChange={(e) => setWebsiteUrl(e.target.value)}
            placeholder="https://your-site.com"
            className="mt-2 w-full rounded-lg border border-lime-500/20 bg-black/60 px-3 py-2 text-sm text-lime-50 outline-none focus:border-lime-500/50"
          />
          <span className="mt-1 block text-[10px] text-slate-500">
            Used as a closing link on social channels.
          </span>
        </label>
        <label className="rounded-xl border border-lime-500/15 bg-black/50 p-3">
          <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
            Support email (optional)
          </span>
          <input
            type="email"
            value={contactEmail}
            onChange={(e) => setContactEmail(e.target.value)}
            placeholder="support@your-site.com"
            className="mt-2 w-full rounded-lg border border-lime-500/20 bg-black/60 px-3 py-2 text-sm text-lime-50 outline-none focus:border-lime-500/50"
          />
          <span className="mt-1 block text-[10px] text-slate-500">
            Shared only when a user explicitly asks how to reach a human.
          </span>
        </label>
      </div>

      {/* Custom handoff */}
      <label className="mt-3 block rounded-xl border border-lime-500/15 bg-black/50 p-3">
        <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
          Custom handoff message (optional)
        </span>
        <textarea
          value={handoffMessage}
          onChange={(e) => setHandoffMessage(e.target.value)}
          rows={2}
          placeholder="Thanks for reaching out — our team will get back to you within one business day."
          className="mt-2 w-full resize-none rounded-lg border border-lime-500/20 bg-black/60 px-3 py-2 text-sm text-lime-50 placeholder:text-slate-600 outline-none focus:border-lime-500/50"
        />
        <span className="mt-1 block text-[10px] text-slate-500">
          What the bot says when the knowledge base can&apos;t answer. Translated automatically.
        </span>
      </label>

      {/* Forbidden topics */}
      <div className="mt-3 rounded-xl border border-amber-500/20 bg-amber-500/5 p-3">
        <p className="text-[10px] font-medium uppercase tracking-wider text-amber-300/80">
          Topics the bot must refuse
        </p>
        <p className="mt-1 text-xs text-slate-400">
          Optional. Add anything the bot must never claim to handle (e.g. <em>medical advice</em>,{" "}
          <em>legal guarantees</em>). It will politely redirect.
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {forbidden.map((topic, idx) => (
            <span
              key={`${topic}-${idx}`}
              className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs text-amber-300"
            >
              {topic}
              <button
                type="button"
                onClick={() => removeAt(forbidden, setForbidden, idx)}
                className="text-amber-300/70 hover:text-rose-300"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
        <div className="mt-2 flex gap-2">
          <input
            type="text"
            value={forbiddenInput}
            onChange={(e) => setForbiddenInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault()
                addTopic(forbiddenInput, forbidden, setForbidden, setForbiddenInput)
              }
            }}
            placeholder="Add a forbidden topic and press Enter"
            className="flex-1 rounded-lg border border-amber-500/20 bg-black/60 px-3 py-2 text-sm text-lime-50 placeholder:text-slate-600 outline-none focus:border-amber-500/50"
          />
          <button
            type="button"
            onClick={() => addTopic(forbiddenInput, forbidden, setForbidden, setForbiddenInput)}
            className="flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-300 hover:bg-amber-500/20"
          >
            <Plus className="h-3.5 w-3.5" /> Add
          </button>
        </div>
      </div>

      <p className="mt-4 text-xs text-slate-500">
        These settings shape the bot&apos;s persona and scope. The knowledge base still grounds
        every answer with facts — this layer just controls who the bot says it is and what it
        will or won&apos;t engage with.
      </p>
    </section>
  )
}
