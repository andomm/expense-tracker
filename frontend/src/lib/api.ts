import { useContext, useEffect, useState } from "react"

import { ProtectedAccess } from "@/auth/access"

export type Session = {
  user: { id: number; username: string } | null
  csrf_token: string
  logout_marker: string | null
}

export type AuthResult = Session & { next: string }
export const PROTECTED_SESSION_REJECTED = "expense:session-rejected"

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

async function requestJson<T>(url: string, options: RequestInit, protectedRequest = false): Promise<T> {
  const response = await fetch(url, {
    ...options,
    mode: "same-origin",
    credentials: "same-origin",
    cache: "no-store",
    redirect: "error",
  })
  if (!response.ok) {
    const error = new ApiError(response.status, await response.json().catch(() => null) as ErrorBody | null)
    if (protectedRequest && !options.signal?.aborted && error.needsSessionCheck) {
      window.dispatchEvent(new CustomEvent(PROTECTED_SESSION_REJECTED, { detail: error }))
    }
    throw error
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function readJson<T>(url: string, signal?: AbortSignal, userId?: number): Promise<T> {
  const headers = new Headers({ Accept: "application/json" })
  if (userId !== undefined) headers.set("X-Expense-Pilot-User", String(userId))
  return requestJson<T>(url, { headers, signal }, userId !== undefined)
}

function writeHeaders(csrfToken: string, userId: number | "anonymous") {
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
  }, true)
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
  }, true)
}

export function submitAuth(url: string, session: Session, body: object, signal: AbortSignal) {
  return requestJson<AuthResult>(url, {
    method: "POST",
    headers: { ...writeHeaders(session.csrf_token, session.user?.id ?? "anonymous"), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  })
}

type ReadState<T> =
  | { state: "loading" }
  | { state: "ready"; data: T }
  | { state: "error"; status?: number; message: string }

export function useRead<T>(url: string | null, userId?: number) {
  const [result, setResult] = useState<ReadState<T>>({ state: "loading" })
  const [attempt, setAttempt] = useState(0)
  const { readVersion } = useContext(ProtectedAccess)

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
  }, [url, attempt, userId, readVersion])

  return {
    result,
    retry() {
      setResult({ state: "loading" })
      setAttempt((value) => value + 1)
    },
  }
}
