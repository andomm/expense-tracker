import { writeJson } from "@/lib/api"
import type { AppUrls } from "@/Shell"

export type BulkSelection =
  | { mode: "explicit"; ids: ReadonlySet<number> }
  | { mode: "matching"; count: number; token: string; stale?: boolean }

export const emptySelection: BulkSelection = { mode: "explicit", ids: new Set() }
export type BulkAction = "recategorize" | "delete"
export type Confirmation = { count: number; token: string | null }

export function bulkWriter(urls: AppUrls, userId: number, csrfToken: string, signal: AbortSignal) {
  const base = urls.expensesApi.replace(/\/?$/, "/")
  return function send<T>(action: BulkAction | "confirm", body: object) {
    return writeJson<T>(`${base}bulk/${action}/`, {
      method: "POST", csrfToken, userId, body, signal,
    })
  }
}

export function expensesLabel(count: number) {
  return `${count} expense${count === 1 ? "" : "s"}`
}
