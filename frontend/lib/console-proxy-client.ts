export type ConsoleProxyMethod = "GET" | "POST" | "PUT" | "DELETE"

type QueryValue = string | number | boolean | null | undefined

export type ConsoleProxyPayload = {
  path: string
  method?: ConsoleProxyMethod
  query?: Record<string, QueryValue>
  body?: unknown
  includeAdminKey?: boolean
}

export type ConsoleProxyResponse<T> = {
  ok: boolean
  status: number
  data: T | null
  error: string | null
}

export async function consoleProxy<T>(payload: ConsoleProxyPayload): Promise<ConsoleProxyResponse<T>> {
  try {
    const response = await fetch("/api/console/proxy", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    })

    const contentType = response.headers.get("content-type") ?? ""
    if (contentType.includes("application/json")) {
      const parsed = (await response.json()) as ConsoleProxyResponse<T>
      return parsed
    }

    return {
      ok: response.ok,
      status: response.status,
      data: null,
      error: await response.text(),
    }
  } catch (error) {
    return {
      ok: false,
      status: 0,
      data: null,
      error: error instanceof Error ? error.message : "Network error",
    }
  }
}
