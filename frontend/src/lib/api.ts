import { useEffect, useState } from "react"

export type Session = {
  user: { id: number; username: string } | null
  csrf_token: string
}

class ReadError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

async function readJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    mode: "same-origin",
    credentials: "same-origin",
    cache: "no-store",
    signal,
  })
  if (!response.ok) {
    const error = await response.json().catch(() => null) as { message?: string } | null
    throw new ReadError(response.status, error?.message ?? "")
  }
  return response.json() as Promise<T>
}

type ReadState<T> =
  | { state: "loading" }
  | { state: "ready"; data: T }
  | { state: "error"; expired: boolean; message: string }

export function useRead<T>(url: string) {
  const [result, setResult] = useState<ReadState<T>>({ state: "loading" })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    readJson<T>(url, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setResult({ state: "ready", data })
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setResult({
            state: "error",
            expired: error instanceof ReadError && error.status === 401,
            message: error instanceof ReadError && error.status === 400 ? error.message : "",
          })
        }
      })
    return () => controller.abort()
  }, [url, attempt])

  return {
    result,
    retry() {
      setResult({ state: "loading" })
      setAttempt((value) => value + 1)
    },
  }
}
