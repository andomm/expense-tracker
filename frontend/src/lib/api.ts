import { useEffect, useState } from "react"

export type Session = {
  user: { id: number; username: string } | null
  csrf_token: string
}

export type FieldErrors = Record<string, string[]>

type ErrorBody = { code?: string; message?: string; fields?: FieldErrors }

export class ApiError extends Error {
  constructor(readonly status: number, readonly body: ErrorBody | null) {
    super(body?.message ?? "")
  }

  get needsSessionCheck() {
    return this.status === 401 || (this.status === 403 && this.body?.code === "csrf_failed")
  }
}

async function requestJson<T>(url: string, options: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    mode: "same-origin",
    credentials: "same-origin",
    cache: "no-store",
    redirect: "error",
  })
  if (!response.ok) {
    const error = await response.json().catch(() => null) as ErrorBody | null
    throw new ApiError(response.status, error)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function readJson<T>(url: string, signal?: AbortSignal, userId?: number): Promise<T> {
  const headers = new Headers({ Accept: "application/json" })
  if (userId !== undefined) headers.set("X-Expense-Pilot-User", String(userId))
  return requestJson<T>(url, { headers, signal })
}

function writeHeaders(csrfToken: string, userId: number) {
  return { Accept: "application/json", "X-CSRFToken": csrfToken, "X-Expense-Pilot-User": String(userId) }
}

// One attempt only. Callers decide how to handle session changes and uncertain outcomes.
export function writeMultipart<T>(url: string, options: {
  body: FormData; csrfToken: string; userId: number; signal?: AbortSignal
}): Promise<T> {
  return requestJson<T>(url, {
    method: "POST",
    signal: options.signal,
    headers: writeHeaders(options.csrfToken, options.userId),
    body: options.body,
  })
}

export function writeJson<T>(url: string, options: {
  csrfToken: string; userId: number; signal?: AbortSignal
} & ({ method: "POST" | "PUT"; body: object } | { method: "DELETE"; body?: never })): Promise<T> {
  return requestJson<T>(url, {
    method: options.method,
    signal: options.signal,
    headers: {
      ...writeHeaders(options.csrfToken, options.userId),
      ...(options.body && { "Content-Type": "application/json" }),
    },
    body: JSON.stringify(options.body),
  })
}

type ReadState<T> =
  | { state: "loading" }
  | { state: "ready"; data: T }
  | { state: "error"; status?: number; message: string }

export function useRead<T>(url: string | null, userId?: number) {
  const [result, setResult] = useState<ReadState<T>>({ state: "loading" })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!url) return
    const controller = new AbortController()
    readJson<T>(url, controller.signal, userId)
      .then((data) => {
        if (!controller.signal.aborted) {
          setResult({ state: "ready", data })
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setResult({
            state: "error",
            status: error instanceof ApiError ? error.status : undefined,
            message: error instanceof ApiError && error.status < 500 ? error.message : "",
          })
        }
      })
    return () => controller.abort()
  }, [url, attempt, userId])

  return {
    result,
    retry() {
      setResult({ state: "loading" })
      setAttempt((value) => value + 1)
    },
  }
}
