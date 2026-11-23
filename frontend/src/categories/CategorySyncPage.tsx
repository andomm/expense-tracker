import { ArrowLeft, RefreshCw } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { ApiError, useRead, writeJson, type Session } from "@/lib/api"
import { displayDate, euro } from "@/expenses/read"
import { ReadFailure, type AppUrls, type CategorySyncRoutes } from "@/Shell"

const groups = [
  { key: "newly_categorized", title: "Newly categorized", description: "These expenses had no category before this run." },
  { key: "upgraded", title: "Moved to a more specific category", description: "Each move stayed within the same top-level category." },
  { key: "still_uncategorized", title: "Still uncategorized", description: "No keyword matched. You can categorize these expenses by hand." },
] as const

type Group = (typeof groups)[number]["key"]
type PreviewRow = {
  id: number
  edit_url: string | null
  date: string
  receiver: string
  description: string
  amount: string
  category?: string
  old_category?: string
  new_category?: string
  matched_keyword?: string
  matched_from?: "receiver" | "description" | "category"
}
type Preview = { rows: PreviewRow[]; omitted: number }
type Report = {
  completed_at: string
  counts: Record<Group | "uncategorized_before", number>
  previews: Record<Group, Preview>
}

const completedAt = new Intl.DateTimeFormat("en-FI", {
  dateStyle: "medium", timeStyle: "medium", timeZone: "Europe/Helsinki",
})
const sources = { receiver: "Receiver", description: "Description", category: "Previous category text" }

export function LoadingSync({ result = false }: { result?: boolean }) {
  return <div className="notice" role="status"><p>{result ? "Loading latest sync result…" : "Loading sync review…"}</p></div>
}

export function CategorySyncPage({ routes, urls, userId, session }: {
  routes: CategorySyncRoutes; urls: AppUrls; userId: number; session: Session
}) {
  const [state, setState] = useState<"ready" | "pending" | "rejected" | "unknown">("ready")
  const inFlight = useRef<AbortController | null>(null)
  useEffect(() => () => inFlight.current?.abort(), [])

  async function start() {
    if (inFlight.current || (state !== "ready" && state !== "rejected")) return
    const controller = new AbortController()
    const { signal } = controller
    inFlight.current = controller
    setState("pending")
    try {
      const outcome = await writeJson<{ result_url: string }>(routes.startApi, {
        method: "POST", body: {}, csrfToken: session.csrf_token, userId, signal,
      })
      if (!signal.aborted) window.location.replace(outcome.result_url)
    } catch (error) {
      if (signal.aborted) return
      // A CSRF rejection is known not to have written. All other uncertain
      // failures stop here; the results link is read-only.
      if (error instanceof ApiError && error.needsSessionCheck) {
        setState("rejected")
      } else {
        setState("unknown")
      }
    } finally {
      inFlight.current = null
    }
  }

  const pending = state === "pending"
  return (
    <div className="max-w-2xl space-y-4">
      <Card aria-labelledby="sync-scope-title" className="gap-0 overflow-hidden py-0 shadow-none">
        <CardHeader className="gap-3 border-b px-4 py-5 sm:px-6 sm:py-6">
          <div className="flex items-center gap-3">
            <RefreshCw className="size-5 shrink-0 text-primary" aria-hidden="true" />
            <h2 id="sync-scope-title" className="text-lg font-extrabold tracking-tight">Review what sync will change</h2>
          </div>
          <p id="sync-scope" className="max-w-prose text-sm leading-relaxed text-muted-foreground">
            Sync checks your expenses across all dates, regardless of filters, using your saved category keywords.
          </p>
        </CardHeader>
        <CardContent className="space-y-4 px-4 py-5 text-sm sm:px-6 sm:py-6">
          <ul role="list" className="list-disc space-y-2 pl-5 marker:text-primary">
            <li>Assigns a category to uncategorized expenses when a keyword matches.</li>
            <li>Moves categorized expenses only to a deeper category within the same top-level category.</li>
            <li>Leaves amounts, unmatched expenses, and other accounts untouched.</li>
          </ul>
          {pending && <p role="status" className="font-semibold">Syncing expenses… Keep this page open to see the result.</p>}
          {state === "rejected" && <p role="alert" className="font-semibold text-destructive">
            Sync did not start because the request could not be verified. Review and select Start sync to try again.
          </p>}
          {state === "unknown" && <div role="alert" className="space-y-1 rounded-lg border bg-background p-3">
            <p className="font-extrabold">Could not confirm whether sync finished</p>
            <p>Sync was not retried. Check your expenses and the time of the latest result before starting another run.</p>
          </div>}
          <div className="flex flex-wrap gap-2">
            {!pending && <Button asChild variant="outline" className="h-11">
              <a href={urls.categories}>{state === "unknown" ? "Back to Categories" : "Cancel"}</a>
            </Button>}
            {state !== "unknown" && <Button type="button" onClick={start} disabled={pending} className="h-11" aria-describedby="sync-scope">
              <RefreshCw aria-hidden="true" /> {pending ? "Syncing…" : "Start sync"}
            </Button>}
          </div>
        </CardContent>
      </Card>
      {!pending && <Button asChild variant="link" className="h-11 px-0">
        <a href={routes.resultUrl}>View latest result</a>
      </Button>}
    </div>
  )
}

function PreviewSection({ group, count, preview }: { group: (typeof groups)[number]; count: number; preview: Preview }) {
  if (!count) return null
  return (
    <section aria-labelledby={`sync-${group.key}`} className="min-w-0 overflow-hidden rounded-xl border bg-card">
      <div className="space-y-1 border-b px-4 py-4 sm:px-6">
        <h2 id={`sync-${group.key}`} className="text-lg font-extrabold tracking-tight">{group.title}</h2>
        <p className="text-sm text-muted-foreground">{group.description}</p>
        {preview.omitted > 0 && <p className="text-sm font-bold">
          Showing {preview.rows.length} of {count} expenses. {preview.omitted} more not shown.
        </p>}
      </div>
      <ul role="list" className="divide-y">
        {preview.rows.map((row) => (
          <li key={row.id} className="grid min-w-0 gap-x-6 gap-y-2 px-4 py-3 text-sm sm:px-6 md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_auto] md:items-center">
            <div className="min-w-0 space-y-0.5 wrap-anywhere">
              <time dateTime={row.date} className="text-xs font-semibold text-muted-foreground">
                {displayDate(row.date, { day: "numeric", month: "short", year: "numeric" })}
              </time>
              <p className="font-extrabold">{row.receiver || row.description || "Unnamed expense"}</p>
              {row.receiver && row.description && <p className="text-muted-foreground">{row.description}</p>}
            </div>
            <div className="min-w-0 space-y-0.5 wrap-anywhere">
              {row.category && <p><span className="text-muted-foreground">Category:</span> <strong>{row.category}</strong></p>}
              {row.old_category && <p><span className="text-muted-foreground">From:</span> {row.old_category}</p>}
              {row.new_category && <p><span className="text-muted-foreground">To:</span> <strong>{row.new_category}</strong></p>}
              {row.matched_keyword !== undefined && <p className="text-muted-foreground">
                Matched: {row.matched_keyword ? `“${row.matched_keyword}”` : "empty keyword"}
                {row.matched_from && ` · ${sources[row.matched_from]}`}
              </p>}
            </div>
            <div className="flex flex-wrap items-center gap-x-3 md:justify-end">
              <span className="font-bold tabular-nums">{euro(row.amount)}</span>
              {row.edit_url && <Button asChild variant="link" className="h-11 px-1">
                <a href={row.edit_url} aria-label={`Edit expense: ${row.receiver || row.description || row.date}`}>Edit expense</a>
              </Button>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function CategorySyncResultPage({ routes, urls, userId }: {
  routes: CategorySyncRoutes; urls: AppUrls; userId: number
}) {
  const { result, retry } = useRead<{ result: Report | null }>(routes.latestApi, userId)
  if (result.state === "loading") return <LoadingSync result />
  const report = result.state === "ready" ? result.data.result : null
  const noChanges = report && !report.counts.newly_categorized && !report.counts.upgraded
  return (
    <div className="space-y-4 sm:space-y-5">
      <div className="flex flex-wrap gap-2">
        <Button asChild variant="outline" className="h-11"><a href={urls.categories}><ArrowLeft aria-hidden="true" /> Back to Categories</a></Button>
        <Button asChild variant="outline" className="h-11"><a href={`${urls.expenses}?month=all`}>View Expenses</a></Button>
        <Button asChild variant="link" className="h-11"><a href={routes.startUrl}>Sync review</a></Button>
      </div>
      {result.state === "error" ? <ReadFailure title="Could not load the latest sync result" message={result.message} retry={retry} /> :
        !report ? <div className="notice">
          <h2>No sync result in this session</h2>
          <p>After you run sync, its results will appear here. Opening this page does not start sync.</p>
        </div> : <>
          <p className="text-sm text-muted-foreground">
            <strong className="text-foreground">{noChanges ? "Sync completed. No categories changed." : "Sync completed."}</strong>
            {" "}Latest successful run in this session:{" "}
            <time dateTime={report.completed_at} className="whitespace-nowrap">{completedAt.format(new Date(report.completed_at))} (Helsinki)</time>.
          </p>
          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-4" aria-label="Sync totals">
            {[{ key: "uncategorized_before", title: "Uncategorized before sync" } as const, ...groups].map(({ key, title }) => (
              <div key={key} className="flex min-w-0 flex-col justify-between gap-1 bg-card p-3 sm:p-5">
                <dt className="text-xs font-semibold text-muted-foreground sm:text-sm">{title}</dt>
                <dd className="text-2xl font-extrabold text-primary tabular-nums sm:text-3xl">{report.counts[key]}</dd>
              </div>
            ))}
          </dl>
          {groups.map((group) => <PreviewSection key={group.key} group={group}
            count={report.counts[group.key]} preview={report.previews[group.key]} />)}
        </>}
    </div>
  )
}
