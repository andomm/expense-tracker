import { useEffect, useRef, useState, type FormEvent } from "react"
import { AlertTriangle } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ApiError, useRead, writeJson, type Session } from "@/lib/api"
import { ReadFailure, type DeletionRoutes } from "@/Shell"

import type { ExpenseDetail } from "./form"
import { displayDate, euro } from "./read"

type Preview = ExpenseDetail | { count: number }
type Props = {
  routes: DeletionRoutes
  allExpenses: boolean
  userId: number
  session: Session
}

export function LoadingExpenseDeletion() {
  return <div className="notice" role="status"><p>Loading deletion details…</p></div>
}

export function ExpenseDeletePage(props: Props) {
  const { routes, userId } = props
  const { result, retry } = useRead<Preview>(routes.api, userId)
  if (result.state === "loading") return <LoadingExpenseDeletion />
  if (result.state === "error") {
    return <div className="grid justify-items-start gap-3">
      {result.status === 404 ? <p className="notice" role="alert">This expense is no longer available.</p> :
        <ReadFailure title="Could not load deletion details" message={result.message} retry={retry} />}
      <Button asChild variant="outline"><a href={routes.returnUrl}>Back to expenses</a></Button>
    </div>
  }
  return <DeleteConfirmation {...props} preview={result.data} />
}

type Failure = { kind: "rejected" | "unknown" | "missing"; message: string }

function DeleteConfirmation({ routes, allExpenses, userId, session, preview }: Props & {
  preview: Preview
}) {
  const [confirmation, setConfirmation] = useState("")
  const [pending, setPending] = useState(false)
  const [failure, setFailure] = useState<Failure | null>(null)
  const request = useRef<AbortController | null>(null)
  const feedback = useRef<HTMLParagraphElement>(null)
  useEffect(() => () => request.current?.abort(), [])
  useEffect(() => { if (failure) feedback.current?.focus() }, [failure])

  const count = "count" in preview ? preview.count : null
  const label = allExpenses ? "Delete all expenses" : "Delete expense"
  const mustLeave = failure?.kind === "unknown" || failure?.kind === "missing"
  const canDelete = !pending && !mustLeave &&
    (allExpenses ? count !== null && count > 0 && confirmation === "DELETE" : count === null)

  async function run() {
    if (request.current) return
    const controller = new AbortController()
    const { signal } = controller
    request.current = controller
    setPending(true)
    setFailure(null)
    let navigating = false
    try {
      const options = { csrfToken: session.csrf_token, userId, signal }
      await writeJson(routes.api, allExpenses
        ? { ...options, method: "POST", body: { confirmation } }
        : { ...options, method: "DELETE" })
      if (!signal.aborted) {
        window.location.replace(routes.returnUrl)
        navigating = true
      }
    } catch (error) {
      if (signal.aborted) return
      if (error instanceof ApiError && error.needsSessionCheck) {
        setConfirmation("")
        setFailure({ kind: "rejected", message: "The deletion was blocked. Review and confirm again if you still want to delete." })
      } else if (error instanceof ApiError && error.status === 404) {
        setFailure({ kind: "missing", message: "This expense is no longer available. Check your expenses." })
      } else if (error instanceof ApiError && error.status < 500) {
        setFailure({ kind: "rejected", message: error.message || "The deletion was rejected. Review and try again." })
      } else {
        setFailure({ kind: "unknown", message: "The deletion result is unknown. Check Expenses before trying again. Nothing will be sent automatically." })
      }
    } finally {
      if (!signal.aborted && !navigating) {
        request.current = null
        setPending(false)
      }
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (canDelete) void run()
  }

  return (
    <Card className="max-w-xl gap-4 py-4 shadow-none sm:py-5">
      <CardHeader className="gap-2 px-4 sm:px-5">
        <h2 className="flex items-start gap-2 font-extrabold">
          <AlertTriangle className="size-5 shrink-0 text-destructive" aria-hidden="true" />
          {allExpenses ? "Across all months and filters" : "Review this expense"}
        </h2>
        {count !== null ? <>
          <p className="font-bold" aria-live="polite">{count} {count === 1 ? "expense" : "expenses"} in your account</p>
          <p id="delete-warning" className="text-sm text-muted-foreground">{count === 0
            ? "There are no expenses to delete."
            : "This permanently deletes every expense in your account, even expenses hidden by your current filters. You cannot undo this."}</p>
        </> : "receiver" in preview && <>
          <div className="wrap-anywhere rounded-lg border p-3">
            <p className="font-bold">{preview.receiver || "Expense without a receiver"}</p>
            {preview.description && <p className="whitespace-pre-wrap text-sm">{preview.description}</p>}
            <p className="mt-2 text-sm text-muted-foreground">
              <time dateTime={preview.date}>{displayDate(preview.date, { dateStyle: "long" })}</time>
              {" · Full amount "}<span className="money whitespace-nowrap">{euro(preview.amount)}</span>
            </p>
          </div>
          <p id="delete-warning" className="text-sm text-muted-foreground">Only this expense will be permanently deleted. You cannot undo this.</p>
        </>}
      </CardHeader>
      <CardContent className="px-4 sm:px-5">
        <form onSubmit={submit} aria-label="Confirm deletion" aria-describedby="delete-warning" className="grid gap-4">
          {allExpenses && count !== null && count > 0 && <div className="grid gap-1.5">
            <label htmlFor="delete-confirmation" className="text-sm font-bold">Type DELETE to confirm</label>
            <Input id="delete-confirmation" name="confirmation" autoComplete="off" autoCapitalize="off" spellCheck={false}
              className="h-11" value={confirmation} disabled={pending || mustLeave}
              onChange={(event) => setConfirmation(event.target.value)} />
          </div>}
          {failure && <p ref={feedback} tabIndex={-1} role="alert" className="text-sm font-bold text-destructive">{failure.message}</p>}
          <div className="flex flex-wrap gap-2">
            {pending ? <Button type="button" variant="outline" className="h-11" disabled>Cancel</Button> :
              <Button asChild variant="outline" className="h-11">
                <a href={routes.returnUrl}>{mustLeave ? "Check expenses" : "Cancel"}</a>
              </Button>}
            {!mustLeave && count !== 0 && <Button type="submit" variant="destructive" disabled={!canDelete}
              className="h-11 dark:bg-destructive dark:text-background dark:hover:bg-destructive/90">
              {pending ? "Deleting…" : label}
            </Button>}
          </div>
          {pending && <span role="status" className="sr-only">Deleting expenses</span>}
        </form>
      </CardContent>
    </Card>
  )
}
