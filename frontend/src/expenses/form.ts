import { useEffect, useState } from "react"

import { ApiError, writeJson, type Session } from "@/lib/api"

type Split = { amount: string; category_id: number | null }
export type Draft = {
  date: string
  receiver: string
  description: string
  amount: string
  category_id: number | null
  share_rule_id: number | null
  splits: (Split & { key: number })[]
}

export type MainFields = Omit<Draft, "splits">
export type ExpenseDetail = MainFields & { id: number; personal_share: string }
export type Choice = { id: number; label: string }
export type FormOptions = { categories: Choice[]; share_rules: Choice[]; max_splits: number }
export type AmountPreview = Record<"amount" | "personal_share" | "split_total" | "remaining", string | null>

export const emptyDraft: Draft = {
  date: "", receiver: "", description: "", amount: "", category_id: null, share_rule_id: null, splits: [],
}

function amountFields(draft: Draft) {
  return {
    amount: draft.amount,
    category_id: draft.category_id,
    share_rule_id: draft.share_rule_id,
    splits: draft.splits.map(({ amount, category_id }) => ({ amount, category_id })),
  }
}

export function saveFields(draft: Draft) {
  return { date: draft.date, receiver: draft.receiver, description: draft.description, ...amountFields(draft) }
}

type PreviewResult = { state: "idle" | "loading" | "error" } | { state: "ready"; data: AmountPreview }

export function useAmountPreview(draft: Draft, url: string, csrfToken: string, userId: number,
  onSessionChange: (session: Session | null) => void, paused: boolean): PreviewResult {
  const body = draft.amount.trim() ? JSON.stringify(amountFields(draft)) : ""
  const [last, setLast] = useState<{ body: string; token: string; result: PreviewResult }>()

  useEffect(() => {
    if (!body || paused) return
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      try {
        const data = await writeJson<AmountPreview>(url, {
          method: "POST", csrfToken, userId, body: JSON.parse(body), signal: controller.signal,
        })
        if (!controller.signal.aborted) setLast({ body, token: csrfToken, result: { state: "ready", data } })
      } catch (error) {
        if (controller.signal.aborted) return
        if (error instanceof ApiError && error.status === 401) onSessionChange(null)
        else setLast({ body, token: csrfToken, result: { state: "error" } })
      }
    }, 250)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [body, url, csrfToken, userId, onSessionChange, paused])

  if (!body) return { state: "idle" }
  return last?.body === body && last.token === csrfToken ? last.result : { state: "loading" }
}
