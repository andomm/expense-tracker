import { useEffect, useRef, useState, type FormEvent } from "react"

import { Button } from "@/components/ui/button"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { ApiError } from "@/lib/api"
import type { AppUrls } from "@/Shell"

import { bulkWriter, emptySelection, expensesLabel,
  type BulkAction, type BulkSelection, type Confirmation } from "./bulk"
import type { ExpenseList } from "./read"

type Failure = { message: string; next?: "check" | "reconfirm"; field?: string }

type Props = {
  urls: AppUrls
  userId: number
  csrfToken: string
  list: ExpenseList
  selection: BulkSelection
  onSelection: (selection: BulkSelection) => void
  onSuccess: (message: string) => void
  onRefresh: () => void
}

export function BulkExpenseActions({
  urls, userId, csrfToken, list, selection, onSelection, onSuccess, onRefresh,
}: Props) {
  const [action, setAction] = useState<BulkAction | null>(null)
  const [pending, setPending] = useState(false)
  const [failure, setFailure] = useState<Failure | null>(null)
  const [notice, setNotice] = useState("")
  const [needsCheck, setNeedsCheck] = useState(false)
  const inFlight = useRef<AbortController | null>(null)
  useEffect(() => () => inFlight.current?.abort(), [])

  const matching = selection.mode === "matching"
  const count = matching ? selection.count : selection.ids.size
  const stale = matching && selection.stale
  const categories = list.categories.filter(({ value }) => /^\d+$/.test(value))

  async function run(
    work: (signal: AbortSignal) => Promise<void>,
    onError: (error: unknown) => void,
  ) {
    if (inFlight.current) return
    const controller = new AbortController()
    inFlight.current = controller
    setPending(true)
    try {
      await work(controller.signal)
    } catch (error) {
      if (controller.signal.aborted) return
      onError(error)
    } finally {
      if (!controller.signal.aborted) setPending(false)
      inFlight.current = null
    }
  }

  function selectMatches() {
    setNotice("")
    void run(async (signal) => {
      const send = bulkWriter(urls, userId, csrfToken, signal)
      const result = await send<Confirmation>("confirm", { filters: list.filters })
      if (signal.aborted) return
      onSelection(result.token
        ? { mode: "matching", count: result.count, token: result.token }
        : emptySelection)
      onRefresh()
    }, (error) => {
      setNotice(error instanceof ApiError && error.status === 409
        ? "These filters changed. Refresh the results before selecting matches."
        : "Could not select all matches. Try again.")
    })
  }

  function submit(categoryId: string) {
    if (!action || !count || stale || failure?.next) return
    setFailure(null)
    let applying = false
    void run(async (signal) => {
      const send = bulkWriter(urls, userId, csrfToken, signal)
      const ids = matching ? undefined : [...selection.ids]
      const token = matching ? selection.token : (await send<Confirmation>("confirm", { ids })).token
      applying = true
      const result = await send<{ affected_count: number }>(action, {
        token, ...(ids && { ids }), ...(action === "recategorize" && { category_id: Number(categoryId) }),
      })
      if (!signal.aborted) {
        onSuccess(`${action === "delete" ? "Deleted" : "Recategorized"} ${expensesLabel(result.affected_count)}.`)
      }
    }, (error) => {
      if (error instanceof ApiError && error.status === 409 && matching) {
        onSelection({ ...selection, stale: true })
        setFailure({ message: "The confirmed matches changed or expired. Nothing was changed. Confirm the matches again.", next: "reconfirm" })
      } else if (error instanceof ApiError && error.status < 500) {
        setFailure({
          message: error.status === 404 ? "Some selected expenses are unavailable. Check expenses, then clear or adjust your selection." :
            error.message || "Could not apply this action. Check your selection and try again.",
          next: error.status === 404 ? "check" : undefined,
          field: error.body?.fields?.category_id?.[0],
        })
      } else if (applying) {
        if (matching) onSelection({ ...selection, stale: true })
        const message = "The outcome is unknown. Check expenses before trying again."
        setNeedsCheck(true)
        setNotice(message)
        setFailure({ message, next: "check" })
      } else {
        setFailure({ message: "Could not confirm the selection. Try again." })
      }
    })
  }

  function open(next: BulkAction) {
    setFailure(null)
    setAction(next)
  }

  return (
    <section aria-label="Expense selection" className="mb-3 space-y-2 rounded-xl border bg-card p-3 sm:p-4">
      <div role="status" className="text-sm">
        <p className="font-bold">{count} selected</p>
        {matching && <p className="small-note">{stale
          ? "Confirm the matches again to use this selection."
          : "All confirmed matches in this view, across pages. Clear selection to pick individual expenses."}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {(!matching || stale) && <Button type="button" variant="outline" className="min-h-11"
          disabled={pending || needsCheck || (!stale && list.pagination.count === 0)} onClick={selectMatches}>
          {pending && !action ? "Checking matches…" : stale ? "Reconfirm matches" : "Select all in this view"}
        </Button>}
        {count > 0 && <>
          <Button type="button" variant="outline" className="min-h-11" disabled={pending || needsCheck || stale || !categories.length}
            onClick={() => open("recategorize")}>Change category</Button>
          <Button type="button" variant="outline" className="min-h-11" disabled={pending || needsCheck || stale}
            onClick={() => open("delete")}>Delete selected</Button>
          <Button type="button" variant="ghost" className="min-h-11" disabled={pending}
            onClick={() => { if (!needsCheck) setNotice(""); onSelection(emptySelection) }}>Clear selection</Button>
        </>}
      </div>
      {count > 0 && !categories.length && <p className="small-note">Create a category before moving expenses.</p>}
      {notice && !action && <div className="flex flex-wrap items-center gap-2">
        <p role="alert" className="text-sm text-destructive">{notice}</p>
        <Button type="button" variant="outline" className="min-h-11" onClick={onRefresh}>
          {needsCheck ? "Check expenses" : "Refresh results"}
        </Button>
      </div>}
      {action && <BulkDialog action={action} count={count} categories={categories} pending={pending}
        failure={failure} onClose={() => setAction(null)} onSubmit={submit} onRefresh={onRefresh} />}
    </section>
  )
}

function BulkDialog({ action, count, categories, pending, failure, onClose, onSubmit, onRefresh }: {
  action: BulkAction; count: number; categories: ExpenseList["categories"]; pending: boolean
  failure: Failure | null; onClose: () => void; onSubmit: (categoryId: string) => void; onRefresh: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const cancel = useRef<HTMLButtonElement>(null)
  const [categoryId, setCategoryId] = useState("")
  const deleting = action === "delete"
  useEffect(() => { dialog.current?.showModal() }, [])
  useEffect(() => { if (!pending) cancel.current?.focus() }, [pending])
  function submit(event: FormEvent) {
    event.preventDefault()
    onSubmit(categoryId)
  }

  return (
    <dialog ref={dialog} aria-labelledby="bulk-title" aria-describedby="bulk-description"
      className="fixed inset-0 m-auto max-h-[calc(100%-1.5rem)] w-[calc(100%-1.5rem)] max-w-md overflow-auto rounded-xl border bg-card p-4 text-card-foreground shadow-lg backdrop:bg-black/55 sm:p-6"
      onClose={onClose} onCancel={(event) => { if (pending) event.preventDefault() }}>
      <form className="space-y-4" onSubmit={submit}>
        <h3 id="bulk-title" className="text-lg font-bold">{deleting ? "Delete" : "Change category for"} {expensesLabel(count)}?</h3>
        <p id="bulk-description" className="text-sm text-muted-foreground">{deleting
          ? "This permanently deletes the selected expenses across pages. This cannot be undone."
          : "Choose the new category for the selected expenses across pages. Amounts and personal shares stay the same."}</p>
        {!deleting && <div className="space-y-1">
          <label htmlFor="bulk-category" className="text-sm font-bold">Destination category</label>
          <NativeSelect id="bulk-category" value={categoryId} onChange={(event) => setCategoryId(event.target.value)}
            className="min-h-11" required disabled={pending || !!failure?.next}
            aria-invalid={!!failure?.field} aria-describedby={failure?.field ? "bulk-category-error" : undefined}>
            <NativeSelectOption value="">Choose a category</NativeSelectOption>
            {categories.map(({ value, label }) => <NativeSelectOption key={value} value={value}>{label}</NativeSelectOption>)}
          </NativeSelect>
          {failure?.field && <p id="bulk-category-error" className="text-sm text-destructive">{failure.field}</p>}
        </div>}
        {failure && <p role="alert" className="text-sm text-destructive">{failure.message}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <Button ref={cancel} type="button" variant="outline" className="min-h-11" disabled={pending}
            onClick={() => dialog.current?.close()}>{failure?.next ? "Close" : "Cancel"}</Button>
          {failure?.next === "check" && <Button type="button" className="min-h-11" onClick={onRefresh}>Check expenses</Button>}
          {!failure?.next && <Button type="submit" variant={deleting ? "destructive" : "default"} className="min-h-11"
            disabled={pending || (!deleting && !categoryId)}>
            {pending ? "Working…" : deleting ? "Delete permanently" : "Change category"}
          </Button>}
        </div>
      </form>
    </dialog>
  )
}
