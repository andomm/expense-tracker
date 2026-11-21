import { ApiError, readJson, writeJson, type Session } from "@/lib/api"
import type { AppUrls } from "@/Shell"

export type BulkSelection =
  | { mode: "explicit"; ids: ReadonlySet<number> }
  | { mode: "matching"; count: number; token: string; stale?: boolean }

export const emptySelection: BulkSelection = { mode: "explicit", ids: new Set() }
export type BulkAction = "recategorize" | "delete"
export type Confirmation = { count: number; token: string | null }

export class BulkSessionChanged extends Error {}

export async function bulkWriter(urls: AppUrls, userId: number, signal: AbortSignal) {
  const current = await readJson<Session>(urls.sessionApi, signal)
  if (current.user?.id !== userId) throw new BulkSessionChanged()

  const base = urls.expensesApi.replace(/\/?$/, "/")
  return async function send<T>(action: BulkAction | "confirm", body: object) {
    try {
      return await writeJson<T>(`${base}bulk/${action}/`, {
        method: "POST", csrfToken: current.csrf_token, userId, body, signal,
      })
    } catch (error) {
      if (error instanceof ApiError && error.needsSessionCheck) {
        if (error.status === 401) throw new BulkSessionChanged()
        const fresh = await readJson<Session>(urls.sessionApi, signal).catch(() => null)
        if (fresh && fresh.user?.id !== userId) throw new BulkSessionChanged()
      }
      throw error
    }
  }
}

export function expensesLabel(count: number) {
  return `${count} expense${count === 1 ? "" : "s"}`
}
