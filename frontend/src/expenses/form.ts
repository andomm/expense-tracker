import { useEffect, useEffectEvent, useState } from "react"

import { writeJson } from "@/lib/api"

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

export function useAmountPreview(draft: Draft, url: string, csrfToken: string, userId: number, paused: boolean): PreviewResult {
  const body = draft.amount.trim() ? JSON.stringify(amountFields(draft)) : ""
  const [last, setLast] = useState<{ body: string; result: PreviewResult }>()

  // A refreshed token must not resend even the read-only preview POST.
  const requestPreview = useEffectEvent(async (value: string, signal: AbortSignal) => {
    if (paused) {
      setLast({ body: value, result: { state: "error" } })
      return
    }
    try {
      const data = await writeJson<AmountPreview>(url, {
        method: "POST", csrfToken, userId, body: JSON.parse(value), signal,
      })
      if (!signal.aborted) setLast({ body: value, result: { state: "ready", data } })
    } catch {
      if (!signal.aborted) setLast({ body: value, result: { state: "error" } })
    }
  })

  useEffect(() => {
    if (!body) return
    const controller = new AbortController()
    const timer = window.setTimeout(() => void requestPreview(body, controller.signal), 250)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [body, url, userId])

  if (!body) return { state: "idle" }
  return last?.body === body ? last.result : { state: "loading" }
}
