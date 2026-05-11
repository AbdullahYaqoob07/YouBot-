"use client"

import { useCallback, useEffect, useMemo, useState } from "react"

import {
  UploadCloud,
  Database,
  FileText,
  Settings2,
  Trash2,
  RefreshCw,
  Activity,
  PlayCircle,
  AlertTriangle,
  CheckCircle2
} from "lucide-react"

import { consoleProxy } from "@/lib/console-proxy-client"

type KnowledgeSource = {
  id: number
  source_name?: string
  source_type?: string
  source_uri?: string
  status?: string
  created_at?: string
}

type IngestionJob = {
  id: number
  source_id?: number
  source_type?: string
  trigger_type?: string
  status?: string
  total_records?: number
  processed_records?: number
  success_records?: number
  failed_records?: number
  created_at?: string
  started_at?: string
  finished_at?: string
}

type SourceResponse = {
  status?: string
  count?: number
  sources?: KnowledgeSource[]
}

type JobResponse = {
  status?: string
  count?: number
  jobs?: IngestionJob[]
}

type UploadResponse = {
  status?: string
  source?: KnowledgeSource
  job?: IngestionJob
}

type CreateJobResponse = {
  status?: string
  started?: boolean
  job?: IngestionJob
}

type DeleteSourceResponse = {
  status?: string
  deleted_source_id?: number
  detached_jobs?: number
  removed_page_records?: number
  removed_index_records?: number
}

type KnowledgeIngestionFormProps = {
  workspaceId: string
}

export function KnowledgeIngestionForm({ workspaceId }: KnowledgeIngestionFormProps) {
  const [file, setFile] = useState<File | null>(null)
  const [sourceName, setSourceName] = useState("")
  const [category, setCategory] = useState("document")
  const [language, setLanguage] = useState("English")
  const [manualSourceId, setManualSourceId] = useState("")

  const [sources, setSources] = useState<KnowledgeSource[]>([])
  const [jobs, setJobs] = useState<IngestionJob[]>([])

  const [isUploading, setIsUploading] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isCreatingJob, setIsCreatingJob] = useState(false)
  const [deletingSourceId, setDeletingSourceId] = useState<number | null>(null)

  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const uploadName = useMemo(() => {
    if (sourceName.trim()) {
      return sourceName.trim()
    }
    if (file?.name) {
      return file.name
    }
    return ""
  }, [file, sourceName])

  const refreshLists = useCallback(async () => {
    setIsRefreshing(true)
    setError(null)

    const [sourcesResponse, jobsResponse] = await Promise.all([
      consoleProxy<SourceResponse>({
        path: `/admin/workspaces/${workspaceId}/knowledge-sources`,
        method: "GET",
        query: { limit: 100 },
      }),
      consoleProxy<JobResponse>({
        path: `/admin/workspaces/${workspaceId}/ingestion-jobs`,
        method: "GET",
        query: { limit: 50 },
      }),
    ])

    if (!sourcesResponse.ok) {
      setError(sourcesResponse.error ?? "Failed to load knowledge sources")
    } else {
      setSources(sourcesResponse.data?.sources ?? [])
    }

    if (!jobsResponse.ok) {
      setError(jobsResponse.error ?? "Failed to load ingestion jobs")
    } else {
      setJobs(jobsResponse.data?.jobs ?? [])
    }

    setIsRefreshing(false)
  }, [workspaceId])

  const hasActiveJob = useMemo(() => {
    return jobs.some((job) => {
      const normalized = (job.status ?? "").toLowerCase()
      return normalized === "queued" || normalized === "running"
    })
  }, [jobs])

  const highlightedJobProgress = useMemo(() => {
    const targetJob =
      jobs.find((job) => {
        const normalized = (job.status ?? "").toLowerCase()
        return normalized === "running" || normalized === "queued"
      }) ?? jobs[0]

    if (!targetJob) {
      return null
    }

    const total = Math.max(
      targetJob.total_records ?? 0,
      targetJob.processed_records ?? 0,
      targetJob.success_records ?? 0,
      targetJob.failed_records ?? 0,
    )
    const processed = Math.max(targetJob.processed_records ?? 0, targetJob.success_records ?? 0)
    const left = total > 0 ? Math.max(total - processed, 0) : null
    const percent = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0

    return {
      id: targetJob.id,
      status: targetJob.status ?? "unknown",
      total,
      processed,
      left,
      percent,
    }
  }, [jobs])

  useEffect(() => {
    void refreshLists()
  }, [refreshLists])

  useEffect(() => {
    if (!hasActiveJob) {
      return
    }

    const pollTimer = window.setInterval(() => {
      void refreshLists()
    }, 2500)

    return () => window.clearInterval(pollTimer)
  }, [hasActiveJob, refreshLists])

  async function uploadDocument() {
    if (!file) {
      setError("Select a .pdf or .docx file before uploading.")
      return
    }

    if (!uploadName) {
      setError("Source name is required.")
      return
    }

    setIsUploading(true)
    setError(null)
    setStatus(null)

    const formData = new FormData()
    formData.append("file", file)
    formData.append("source_name", uploadName)
    formData.append("category", category)
    formData.append("language", language)

    try {
      const response = await fetch("/api/console/knowledge/upload", {
        method: "POST",
        body: formData,
      })

      const payload = (await response.json()) as {
        ok: boolean
        status: number
        data: UploadResponse | null
        error: string | null
      }

      if (!payload.ok) {
        setError(payload.error ?? "Upload failed")
        setIsUploading(false)
        return
      }

      const sourceId = payload.data?.source?.id
      const jobId = payload.data?.job?.id
      setStatus(`Document queued successfully${sourceId ? ` (source #${sourceId})` : ""}${jobId ? `, job #${jobId}` : ""}.`)
      setFile(null)
      setSourceName("")
      await refreshLists()
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Upload failed")
    } finally {
      setIsUploading(false)
    }
  }

  async function createManualJob() {
    const parsedId = Number(manualSourceId)
    if (!Number.isFinite(parsedId) || parsedId <= 0) {
      setError("Enter a valid numeric source ID before creating a job.")
      return
    }

    setIsCreatingJob(true)
    setError(null)
    setStatus(null)

    const response = await consoleProxy<CreateJobResponse>({
      path: "/admin/ingestion-jobs",
      method: "POST",
      body: {
        sourceId: parsedId,
        triggerType: "manual",
        createdBy: "frontend_console",
        runNow: true,
      },
    })

    if (!response.ok) {
      setError(response.error ?? "Failed to create ingestion job")
      setIsCreatingJob(false)
      return
    }

    setStatus(`Manual ingestion job created${response.data?.job?.id ? ` (#${response.data.job.id})` : ""}.`)
    setManualSourceId("")
    setIsCreatingJob(false)
    await refreshLists()
  }

  async function deleteSource(sourceId: number) {
    const isConfirmed = window.confirm(
      `Delete source #${sourceId}? This also removes related page index records for this document.`,
    )
    if (!isConfirmed) {
      return
    }

    setDeletingSourceId(sourceId)
    setError(null)
    setStatus(null)

    const response = await consoleProxy<DeleteSourceResponse>({
      path: `/admin/workspaces/${workspaceId}/knowledge-sources/${sourceId}`,
      method: "DELETE",
    })

    if (!response.ok || !response.data) {
      setError(response.error ?? "Failed to delete source")
      setDeletingSourceId(null)
      return
    }

    setStatus(
      `Source #${sourceId} removed (pages=${response.data.removed_page_records ?? 0}, index=${response.data.removed_index_records ?? 0}).`,
    )
    setDeletingSourceId(null)
    await refreshLists()
  }

  return (
    <section className="rounded-2xl border border-lime-500/20 bg-black/40 p-4 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h2 className="text-lg font-semibold text-lime-50">Ingest Documents</h2>
          <p className="mt-1 text-xs text-slate-400">
            Upload PDF/DOCX files, then monitor ingestion jobs and re-run jobs manually when needed.
          </p>
        </div>
        <button
          type="button"
          onClick={refreshLists}
          disabled={isRefreshing}
          className="flex items-center gap-2 rounded-lg border border-lime-500/30 bg-lime-500/10 px-3 py-1.5 text-xs font-medium text-lime-400 transition hover:bg-lime-500/20 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
          Refresh Sources
        </button>
      </div>

      <div className="grid gap-6 mt-6 lg:grid-cols-2">
        {/* File Upload Area */}
        <div className="rounded-xl border border-lime-500/15 bg-black/50 p-4">
          <h3 className="text-sm font-semibold text-lime-50 flex items-center gap-2 mb-4">
            <UploadCloud className="h-4 w-4 text-cyan-400" />
            Upload Document
          </h3>
          
          <div className="space-y-4">
            <label className="block space-y-1.5 text-sm text-slate-300">
              <span className="font-medium text-xs">Document File (.pdf or .docx)</span>
              <div className="relative group">
                <input
                  type="file"
                  accept=".pdf,.docx"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  className="w-full rounded-lg border border-lime-500/20 bg-black/60 px-3 py-2.5 text-sm text-lime-50 outline-none file:mr-3 file:rounded-md file:border-0 file:bg-cyan-500/10 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-cyan-400 hover:border-lime-500/40 focus:border-lime-500/50 transition-colors"
                />
              </div>
            </label>

            <label className="block space-y-1.5 text-sm text-slate-300">
              <span className="font-medium text-xs">Source Name</span>
              <input
                value={sourceName}
                onChange={(event) => setSourceName(event.target.value)}
                placeholder="Give this document a readable title"
                className="w-full rounded-lg border border-lime-500/20 bg-black/60 px-3 py-2.5 text-sm text-lime-50 outline-none placeholder:text-slate-600 focus:border-lime-500/50 transition-colors"
              />
            </label>

            <div className="grid grid-cols-2 gap-4">
              <label className="space-y-1.5 text-sm text-slate-300">
                <span className="font-medium text-xs">Category</span>
                <input
                  value={category}
                  onChange={(event) => setCategory(event.target.value)}
                  className="w-full rounded-lg border border-lime-500/20 bg-black/60 px-3 py-2.5 text-sm text-lime-50 outline-none focus:border-lime-500/50 transition-colors"
                />
              </label>

              <label className="space-y-1.5 text-sm text-slate-300">
                <span className="font-medium text-xs">Language</span>
                <input
                  value={language}
                  onChange={(event) => setLanguage(event.target.value)}
                  className="w-full rounded-lg border border-lime-500/20 bg-black/60 px-3 py-2.5 text-sm text-lime-50 outline-none focus:border-lime-500/50 transition-colors"
                />
              </label>
            </div>

            <button
              type="button"
              onClick={uploadDocument}
              disabled={isUploading}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-cyan-600/20 border border-cyan-500/30 hover:bg-cyan-500/30 hover:border-cyan-500/50 px-4 py-2.5 text-sm font-semibold text-cyan-50 transition disabled:opacity-50 mt-2"
            >
              {isUploading ? <RefreshCw className="h-4 w-4 animate-spin text-cyan-400" /> : <UploadCloud className="h-4 w-4 text-cyan-400" />}
              {isUploading ? "Uploading & Queuing..." : "Upload & Parse"}
            </button>
          </div>
        </div>

        {/* Manual Job Area */}
        <div className="rounded-xl border border-lime-500/15 bg-black/50 p-4 flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-semibold text-lime-50 flex items-center gap-2 mb-4">
              <Settings2 className="h-4 w-4 text-emerald-400" />
              Manual Trigger
            </h3>
            <p className="text-xs text-slate-400 mb-4 leading-relaxed">
              If an ingestion job stalled or you need to re-index an existing source, enter the source ID below to queue a fresh parsing job.
            </p>
            <label className="block space-y-1.5 text-sm text-slate-300">
              <span className="font-medium text-xs">Source ID</span>
              <input
                value={manualSourceId}
                onChange={(event) => setManualSourceId(event.target.value)}
                placeholder="e.g. 12"
                className="w-full rounded-lg border border-lime-500/20 bg-black/60 px-3 py-2.5 text-sm text-lime-50 outline-none placeholder:text-slate-600 focus:border-lime-500/50 transition-colors"
              />
            </label>
          </div>

          <button
            type="button"
            onClick={createManualJob}
            disabled={isCreatingJob || !manualSourceId}
            className="w-full flex items-center justify-center gap-2 rounded-lg bg-emerald-600/20 border border-emerald-500/30 hover:bg-emerald-500/30 hover:border-emerald-500/50 px-4 py-2.5 text-sm font-semibold text-emerald-50 transition disabled:opacity-50 mt-4"
          >
            {isCreatingJob ? <RefreshCw className="h-4 w-4 animate-spin text-emerald-400" /> : <PlayCircle className="h-4 w-4 text-emerald-400" />}
            {isCreatingJob ? "Scheduling..." : "Trigger Manual Job"}
          </button>
        </div>
      </div>

      {status && (
        <div className="mt-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3 flex items-center gap-2 text-sm text-emerald-300">
          <RefreshCw className="h-4 w-4" />
          {status}
        </div>
      )}
      {error && (
        <div className="mt-4 rounded-lg bg-rose-500/10 border border-rose-500/20 p-3 flex items-center gap-2 text-sm text-rose-300">
          <PlayCircle className="h-4 w-4" />
          {error}
        </div>
      )}

      {highlightedJobProgress && (
        <div className="mt-6 rounded-xl border border-lime-500/20 bg-black/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <h3 className="text-sm font-semibold text-lime-50 flex items-center gap-2">
              <RefreshCw className="h-4 w-4 text-emerald-400 animate-spin" />
              Ingestion Progress (Job #{highlightedJobProgress.id})
            </h3>
            <span className="text-xs font-medium px-2 py-1 rounded bg-black/40 border border-lime-500/20 text-lime-400 uppercase tracking-wider">
              {highlightedJobProgress.status}
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-black/60 border border-lime-500/20">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-cyan-500 transition-all duration-500 relative"
              style={{ width: `${highlightedJobProgress.percent}%` }}
            >
              <div className="absolute inset-0 bg-white/20 animate-pulse" />
            </div>
          </div>
          <p className="mt-2.5 text-xs font-medium text-slate-400 flex items-center justify-between">
            <span>
              {highlightedJobProgress.total > 0
                ? `${highlightedJobProgress.processed} / ${highlightedJobProgress.total} processed`
                : "Waiting for record count..."}
            </span>
            {highlightedJobProgress.left !== null && highlightedJobProgress.left > 0 && (
              <span className="text-emerald-400/80">{highlightedJobProgress.left} remaining</span>
            )}
          </p>
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        {/* Knowledge Sources List */}
        <div className="rounded-xl border border-lime-500/15 bg-black/50 p-4 flex flex-col max-h-[400px]">
          <div className="flex items-center justify-between mb-4 pb-3 border-b border-lime-500/10 shrink-0">
            <h3 className="text-sm font-semibold text-lime-50 flex items-center gap-2">
              <Settings2 className="h-4 w-4 text-slate-400" />
              Knowledge Sources
            </h3>
            <span className="text-xs px-2 py-0.5 rounded-full bg-lime-500/10 text-lime-400 font-medium">
              {sources.length} Total
            </span>
          </div>
          
          <div className="space-y-3 overflow-y-auto pr-2 custom-scrollbar">
            {sources.map((source) => (
              <div key={source.id} className="rounded-lg border border-lime-500/10 bg-black/40 p-3 hover:border-lime-500/30 transition-colors group">
                <div className="flex justify-between items-start gap-4">
                  <div className="min-w-0">
                    <p className="font-medium text-sm text-lime-50 truncate pb-1">
                      <span className="text-lime-500/50 mr-1.5 font-mono">#{source.id}</span>
                      {source.source_name ?? "Unnamed source"}
                    </p>
                    <div className="flex items-center gap-3 mt-1.5 text-[11px] text-slate-400 font-mono">
                      <span className="bg-black/60 px-1.5 py-0.5 rounded border border-lime-500/10 truncate max-w-[120px]">
                        {source.source_type ?? "unknown"}
                      </span>
                      <span className="flex items-center gap-1.5">
                        <div className={`w-1.5 h-1.5 rounded-full ${
                          source.status === 'completed' ? 'bg-emerald-500' : 
                          source.status === 'failed' ? 'bg-rose-500' : 'bg-amber-500'
                        }`} />
                        {source.status ?? "unknown"}
                      </span>
                    </div>
                  </div>
                  
                  <button
                    type="button"
                    onClick={() => void deleteSource(source.id)}
                    disabled={deletingSourceId === source.id}
                    className="shrink-0 flex items-center justify-center h-8 w-8 rounded-md bg-rose-500/10 border border-rose-500/20 text-rose-400 hover:bg-rose-500/20 transition-all disabled:opacity-50 md:opacity-0 md:group-hover:opacity-100"
                    title="Delete Source"
                  >
                    {deletingSourceId === source.id ? (
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                       <span>&times;</span>
                    )}
                  </button>
                </div>
              </div>
            ))}
            {sources.length === 0 && (
              <div className="text-center py-8 text-slate-500 text-sm border border-dashed border-lime-500/20 rounded-lg">
                No sources loaded yet.
              </div>
            )}
          </div>
        </div>

        {/* Ingestion Jobs List */}
        <div className="rounded-xl border border-lime-500/15 bg-black/50 p-4 flex flex-col max-h-[400px]">
          <div className="flex items-center justify-between mb-4 pb-3 border-b border-lime-500/10 shrink-0">
            <h3 className="text-sm font-semibold text-lime-50 flex items-center gap-2">
              <PlayCircle className="h-4 w-4 text-slate-400" />
              Ingestion Jobs
            </h3>
            <span className="text-xs px-2 py-0.5 rounded-full bg-lime-500/10 text-lime-400 font-medium">
              {jobs.length} Queued/Done
            </span>
          </div>

          <div className="space-y-3 overflow-y-auto pr-2 custom-scrollbar">
            {jobs.map((job) => {
              const totalRecords = Math.max(
                job.total_records ?? 0,
                job.processed_records ?? 0,
                job.success_records ?? 0,
                job.failed_records ?? 0,
              )
              const processedRecords = Math.max(job.processed_records ?? 0, job.success_records ?? 0)
              const progressPercent = totalRecords > 0 ? Math.min(100, Math.round((processedRecords / totalRecords) * 100)) : 0
              const isRunning = job.status === "running" || job.status === "queued"

              return (
                <div key={job.id} className="rounded-lg border border-lime-500/10 bg-black/40 p-3 hover:border-lime-500/30 transition-colors">
                  <div className="flex justify-between items-center mb-2">
                    <p className="font-medium text-sm text-lime-50 font-mono">
                      <span className="text-lime-500/50 mr-1">#{job.id}</span>
                      <span className="text-slate-400 text-xs ml-2">src: {job.source_id ?? "-"}</span>
                    </p>
                    <span className={`text-[10px] px-2 py-0.5 rounded uppercase tracking-wider font-semibold border ${
                      isRunning ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400' :
                      job.status === 'failed' ? 'bg-rose-500/10 border-rose-500/30 text-rose-400' :
                      'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                    }`}>
                      {job.status ?? "unknown"}
                    </span>
                  </div>

                  <div className="mt-3">
                    <div className="flex justify-between text-[11px] font-mono text-slate-400 mb-1">
                      <span>{processedRecords} / {totalRecords > 0 ? totalRecords : '?'}</span>
                      <span>{progressPercent}%</span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-black/60 border border-lime-500/20">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${isRunning ? 'bg-gradient-to-r from-cyan-500 to-emerald-500' : job.status === 'failed' ? 'bg-rose-500' : 'bg-emerald-500'}`}
                        style={{ width: `${progressPercent}%` }}
                      />
                    </div>
                    <p className="mt-2 text-[10px] text-slate-500 font-mono text-right">
                      Trigger: {job.trigger_type ?? "manual"}
                    </p>
                  </div>
                </div>
              )
            })}
            {jobs.length === 0 && (
              <div className="text-center py-8 text-slate-500 text-sm border border-dashed border-lime-500/20 rounded-lg">
                No jobs loaded.
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
