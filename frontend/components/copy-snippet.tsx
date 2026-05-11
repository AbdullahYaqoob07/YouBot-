"use client"

import { Check, Copy } from "lucide-react"
import { useState } from "react"

type CopySnippetProps = {
  value: string
  language?: string
  label?: string
}

export function CopySnippet({ value, language = "text", label }: CopySnippetProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <div className="rounded-xl border border-lime-500/15 bg-black/60">
      <div className="flex items-center justify-between border-b border-lime-500/15 bg-lime-950/20 px-3 py-1.5">
        <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
          {label ?? language}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1.5 rounded-md border border-lime-500/30 bg-lime-500/10 px-2 py-1 text-[11px] font-medium text-lime-400 transition hover:bg-lime-500/20"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto px-3 py-3 text-[12.5px] leading-relaxed text-lime-50">
        <code>{value}</code>
      </pre>
    </div>
  )
}

type CopyValueProps = {
  value: string
  label?: string
}

export function CopyValue({ value, label }: CopyValueProps) {
  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <div className="flex items-center gap-2 rounded-lg border border-lime-500/15 bg-black/50 px-3 py-2">
      {label && (
        <span className="shrink-0 text-[10px] font-medium uppercase tracking-wider text-slate-500">
          {label}
        </span>
      )}
      <code className="flex-1 truncate text-[12.5px] text-lime-50">{value}</code>
      <button
        type="button"
        onClick={handleCopy}
        className="flex items-center gap-1.5 rounded-md border border-lime-500/30 bg-lime-500/10 px-2 py-1 text-[11px] font-medium text-lime-400 transition hover:bg-lime-500/20"
      >
        {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  )
}
