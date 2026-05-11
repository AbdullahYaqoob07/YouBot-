export type FrontendRuntimeConfig = {
  baseUrl: string
  proxyPrefix: string
  tenantId: string
  workspaceId: string
  adminKey: string
}

export type FetchJsonResult<T> = {
  ok: boolean
  status: number
  data: T | null
  error: string | null
  config: FrontendRuntimeConfig
}

export function getFrontendRuntimeConfig(): FrontendRuntimeConfig {
  const baseUrlRaw =
    process.env.YOUBOT_API_BASE_URL ??
    process.env.NEXT_PUBLIC_YOUBOT_API_BASE_URL ??
    "http://127.0.0.1:8000"

  const adminKey =
    process.env.YOUBOT_ADMIN_API_KEY ??
    process.env.ADMIN_API_KEY ??
    process.env.NEXT_PUBLIC_ADMIN_API_KEY ??
    ""

  return {
    baseUrl: baseUrlRaw.replace(/\/+$/, ""),
    proxyPrefix: (process.env.NEXT_PUBLIC_BACKEND_PROXY_PREFIX ?? "/backend").replace(/\/+$/, ""),
    tenantId: process.env.YOUBOT_TENANT_ID ?? "public",
    workspaceId: process.env.YOUBOT_WORKSPACE_ID ?? "default",
    adminKey,
  }
}

function normalizePath(path: string): string {
  return path.startsWith("/") ? path : `/${path}`
}

export function backendSurfaceHref(path: string): string {
  const config = getFrontendRuntimeConfig()
  return `${config.proxyPrefix}${normalizePath(path)}`
}

export function backendApiHref(path: string): string {
  const config = getFrontendRuntimeConfig()
  return `${config.baseUrl}${normalizePath(path)}`
}

function buildHeaders(config: FrontendRuntimeConfig, includeAdminKey: boolean, customTenantId?: string): Record<string, string> {
  const tId = customTenantId ?? config.tenantId
  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Tenant-Id": tId,
    "X-Workspace-Id": tId,
  }

  const apiKey =
    process.env.YOUBOT_PUBLIC_API_KEY ??
    process.env.API_KEY ??
    process.env.NEXT_PUBLIC_API_KEY ??
    ""

  if (apiKey) {
    headers["X-API-Key"] = apiKey
  }

  if (includeAdminKey && (customTenantId || config.adminKey)) {
    headers["X-Admin-Key"] = customTenantId ?? config.adminKey
  }

  return headers
}

export async function fetchJson<T>(
  path: string,
  options?: {
    includeAdminKey?: boolean
    tenantId?: string
    accessToken?: string
  },
): Promise<FetchJsonResult<T>> {
  const config = getFrontendRuntimeConfig()
  const normalizedPath = normalizePath(path)
  const includeAdminKey = options?.includeAdminKey ?? true

  const headers = buildHeaders(config, includeAdminKey, options?.tenantId)
  if (options?.accessToken) {
    headers["Authorization"] = `Bearer ${options.accessToken}`
  }

  try {
    const response = await fetch(`${config.baseUrl}${normalizedPath}`, {
      method: "GET",
      headers,
      cache: "no-store",
    })

    const contentType = response.headers.get("content-type") ?? ""
    const isJson = contentType.includes("application/json")
    const payload = isJson ? ((await response.json()) as T) : null

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        data: payload,
        error: `${normalizedPath} returned ${response.status} ${response.statusText}`,
        config,
      }
    }

    return {
      ok: true,
      status: response.status,
      data: payload,
      error: null,
      config,
    }
  } catch (error) {
    return {
      ok: false,
      status: 0,
      data: null,
      error: `${normalizedPath} request failed: ${error instanceof Error ? error.message : "Unknown error"}`,
      config,
    }
  }
}
