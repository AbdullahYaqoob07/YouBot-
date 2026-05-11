import { NextRequest, NextResponse } from "next/server"

import { getFrontendRuntimeConfig } from "@/lib/runtime-config"
import { createClient } from "@/lib/supabase/server"

function stringifyErrorPayload(payload: unknown): string {
  if (!payload) {
    return "Unknown error"
  }
  if (typeof payload === "string") {
    return payload
  }
  if (typeof payload === "object" && payload !== null) {
    const detail = (payload as { detail?: unknown }).detail
    if (typeof detail === "string") {
      return detail
    }
    if (detail !== undefined) {
      return JSON.stringify(detail)
    }
  }
  return "Unknown error"
}

export async function POST(request: NextRequest) {
  const config = getFrontendRuntimeConfig()

  // Resolve workspace from the authenticated user
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  const { data: { session } } = user ? await supabase.auth.getSession() : { data: { session: null } }
  const workspaceId = user?.id ?? config.workspaceId
  const tenantId = user?.id ?? config.tenantId

  let formData: FormData
  try {
    formData = await request.formData()
  } catch {
    return NextResponse.json(
      {
        ok: false,
        status: 400,
        data: null,
        error: "Invalid multipart form payload",
      },
      { status: 400 },
    )
  }

  const sourceName = formData.get("source_name")
  const file = formData.get("file")
  if (!sourceName || !file) {
    return NextResponse.json(
      {
        ok: false,
        status: 400,
        data: null,
        error: "Both source_name and file are required",
      },
      { status: 400 },
    )
  }

  const targetUrl = `${config.baseUrl}/admin/workspaces/${workspaceId}/knowledge-sources/upload`

  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Tenant-Id": tenantId,
    "X-Workspace-Id": workspaceId,
  }

  if (session?.access_token) {
    headers["Authorization"] = `Bearer ${session.access_token}`
  } else if (config.adminKey) {
    headers["X-Admin-Key"] = config.adminKey
  }

  const maybeApiKey =
    process.env.YOUBOT_PUBLIC_API_KEY ??
    process.env.API_KEY ??
    process.env.NEXT_PUBLIC_API_KEY ??
    ""

  if (maybeApiKey) {
    headers["X-API-Key"] = maybeApiKey
  }

  try {
    const response = await fetch(targetUrl, {
      method: "POST",
      headers,
      body: formData,
      cache: "no-store",
    })

    const contentType = response.headers.get("content-type") ?? ""
    const data = contentType.includes("application/json") ? await response.json() : await response.text()

    return NextResponse.json(
      {
        ok: response.ok,
        status: response.status,
        data,
        error: response.ok ? null : stringifyErrorPayload(data),
      },
      { status: response.status },
    )
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        status: 502,
        data: null,
        error: error instanceof Error ? error.message : "Upload proxy request failed",
      },
      { status: 502 },
    )
  }
}
