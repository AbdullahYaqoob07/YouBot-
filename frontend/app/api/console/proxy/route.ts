import { NextRequest, NextResponse } from "next/server"
import { createClient } from "@/lib/supabase/server"

import { getFrontendRuntimeConfig } from "@/lib/runtime-config"

type QueryValue = string | number | boolean | null | undefined

type ProxyMethod = "GET" | "POST" | "PUT" | "DELETE"

type ConsoleProxyPayload = {
  path: string
  method?: ProxyMethod
  query?: Record<string, QueryValue>
  body?: unknown
  includeAdminKey?: boolean
}

const ALLOWED_PREFIXES = ["/admin/", "/kb-curation/", "/integrations/", "/health"]

function normalizePath(rawPath: string): string {
  return rawPath.startsWith("/") ? rawPath : `/${rawPath}`
}

function isAllowedPath(path: string): boolean {
  if (path === "/health") {
    return true
  }
  return ALLOWED_PREFIXES.some((prefix) => path.startsWith(prefix))
}

function buildQueryString(query?: Record<string, QueryValue>): string {
  if (!query) {
    return ""
  }

  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") {
      continue
    }
    search.set(key, String(value))
  }

  const rendered = search.toString()
  return rendered ? `?${rendered}` : ""
}

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
  let payload: ConsoleProxyPayload
  try {
    payload = (await request.json()) as ConsoleProxyPayload
  } catch {
    return NextResponse.json(
      {
        ok: false,
        status: 400,
        data: null,
        error: "Invalid JSON payload",
      },
      { status: 400 },
    )
  }

  const method = (payload.method ?? "GET").toUpperCase() as ProxyMethod
  if (!["GET", "POST", "PUT", "DELETE"].includes(method)) {
    return NextResponse.json(
      {
        ok: false,
        status: 400,
        data: null,
        error: `Unsupported method '${payload.method}'`,
      },
      { status: 400 },
    )
  }

  const path = normalizePath(payload.path)
  if (!isAllowedPath(path)) {
    return NextResponse.json(
      {
        ok: false,
        status: 400,
        data: null,
        error: `Path '${path}' is not allowed by console proxy`,
      },
      { status: 400 },
    )
  }

  const config = getFrontendRuntimeConfig()
  const url = `${config.baseUrl}${path}${buildQueryString(payload.query)}`

  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Tenant-Id": config.tenantId,
    "X-Workspace-Id": config.workspaceId,
  }

  // Validate the user against Supabase Auth, then read the access token from the session.
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  const { data: { session } } = user ? await supabase.auth.getSession() : { data: { session: null } }

  if (session?.access_token) {
    headers["Authorization"] = `Bearer ${session.access_token}`
  }

  // Force tenant/workspace segregation using the authenticated user ID
  if (user?.id) {
    headers["X-Tenant-Id"] = user.id
    headers["X-Workspace-Id"] = user.id
    if (payload.includeAdminKey ?? true) {
      headers["X-Admin-Key"] = user.id
    }
  } else if ((payload.includeAdminKey ?? true) && config.adminKey) {
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

  const init: RequestInit = {
    method,
    headers,
    cache: "no-store",
  }

  if (payload.body !== undefined && method !== "GET" && method !== "DELETE") {
    headers["Content-Type"] = "application/json"
    init.body = JSON.stringify(payload.body)
  }

  try {
    const response = await fetch(url, init)
    const contentType = response.headers.get("content-type") ?? ""

    let upstreamPayload: unknown = null
    if (contentType.includes("application/json")) {
      upstreamPayload = await response.json()
    } else {
      upstreamPayload = await response.text()
    }

    return NextResponse.json(
      {
        ok: response.ok,
        status: response.status,
        data: upstreamPayload,
        error: response.ok ? null : stringifyErrorPayload(upstreamPayload),
      },
      { status: response.status },
    )
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        status: 502,
        data: null,
        error: error instanceof Error ? error.message : "Proxy request failed",
      },
      { status: 502 },
    )
  }
}
