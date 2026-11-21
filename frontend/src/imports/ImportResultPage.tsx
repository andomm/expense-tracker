import { ArrowLeft } from "lucide-react"

import { Button } from "@/components/ui/button"
import { displayDate, euro } from "@/expenses/read"
import { useRead } from "@/lib/api"
import { ReadFailure, SignInNotice, type AppUrls, type CsvImportRoutes } from "@/Shell"
import { LoadingImport } from "./UploadPage"

const totals = [
  { key: "total", label: "Imported" },
  { key: "categorized", label: "Categorized" },
  { key: "uncategorized", label: "Uncategorized" },
] as const

const completedAt = new Intl.DateTimeFormat("en-FI", {
  dateStyle: "medium", timeStyle: "short", timeZone: "Europe/Helsinki",
})

type PreviewRow = {
  id: number; edit_url: string | null; date: string; receiver: string; description: string; amount: string
}

type Report = {
  completed_at: string
  counts: Record<(typeof totals)[number]["key"], number>
  uncategorized_preview: { rows: PreviewRow[]; omitted: number }
}

function ImportReport({ report }: { report: Report }) {
  const { rows, omitted } = report.uncategorized_preview
  return (
    <>
      <p className="text-sm text-muted-foreground">
        <strong className="text-foreground">Import complete.</strong> Latest successful import in this session: {" "}
        <time dateTime={report.completed_at}>{completedAt.format(new Date(report.completed_at))} (Helsinki)</time>.
      </p>
      <dl aria-label="Import totals" className="grid grid-cols-[minmax(0,.85fr)_minmax(0,1fr)_minmax(0,1.15fr)] gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-3">
        {totals.map(({ key, label }) => (
          <div key={key} className="flex min-w-0 flex-col justify-between gap-1 bg-card p-2.5 sm:p-5">
            <dt className="text-xs font-semibold text-muted-foreground wrap-anywhere sm:text-sm">{label}</dt>
            <dd className="text-2xl font-extrabold text-primary tabular-nums wrap-anywhere sm:text-3xl">{report.counts[key]}</dd>
          </div>
        ))}
      </dl>
      {rows.length ? (
        <section aria-labelledby="unmatched-title" className="min-w-0 rounded-xl border bg-card">
          <div className="space-y-1 border-b px-4 py-4 sm:px-6">
            <h2 id="unmatched-title" className="text-lg font-extrabold tracking-tight">Uncategorized at import</h2>
            <p className="text-sm text-muted-foreground">No keyword matched these expenses. Edit them to choose a category.</p>
            {omitted > 0 && <p className="text-sm font-bold">Showing {rows.length} of {report.counts.uncategorized} expenses. {omitted} more not shown.</p>}
          </div>
          <ul role="list" className="divide-y">
            {rows.map((row) => {
              const name = row.receiver || row.description || "Unnamed expense"
              return (
                <li key={row.id} className="grid min-w-0 gap-x-4 gap-y-2 px-4 py-3 text-sm sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:px-6">
                  <div className="min-w-0 space-y-0.5 wrap-anywhere">
                    <time dateTime={row.date} className="text-xs font-semibold text-muted-foreground">
                      {displayDate(row.date, { day: "numeric", month: "short", year: "numeric" })}
                    </time>
                    <p className="font-extrabold">{name}</p>
                    {row.receiver && row.description && <p className="whitespace-pre-wrap text-muted-foreground">{row.description}</p>}
                  </div>
                  <div className="flex flex-wrap items-center gap-x-3 sm:justify-end">
                    <span className="font-bold tabular-nums">{euro(row.amount)}</span>
                    {row.edit_url ? <Button asChild variant="link" className="h-11 px-1">
                      <a href={row.edit_url} aria-label={`Edit expense: ${name}`}>Edit expense</a>
                    </Button> : <span className="text-muted-foreground">No longer available</span>}
                  </div>
                </li>
              )
            })}
          </ul>
        </section>
      ) : <div className="notice"><p>All imported expenses were categorized.</p></div>}
    </>
  )
}

export function ImportResultPage({ routes, urls, userId }: {
  routes: CsvImportRoutes; urls: AppUrls; userId: number
}) {
  const { result, retry } = useRead<{ result: Report | null }>(routes.latestApi, userId)
  if (result.state === "loading") return <LoadingImport result />
  if (result.state === "error" && result.status === 401) return <SignInNotice login={urls.login} csvImport />
  return (
    <div className="max-w-4xl space-y-4 sm:space-y-5">
      <div className="flex flex-wrap gap-2">
        <Button asChild variant="outline" className="h-11"><a href={urls.upload}><ArrowLeft aria-hidden="true" /> Upload CSV</a></Button>
        <Button asChild variant="outline" className="h-11"><a href={`${urls.expenses}?month=all`}>View Expenses</a></Button>
        <Button asChild variant="link" className="h-11"><a href={urls.categories}>Manage Categories</a></Button>
      </div>
      {result.state === "error" ? <ReadFailure title="Could not load the latest import result" message={result.message} retry={retry} /> :
        result.data.result ? <ImportReport report={result.data.result} /> : <div className="notice">
          <h2>No import result in this session</h2>
          <p>After a successful upload, its results will appear here. Opening this page never imports a file.</p>
        </div>}
    </div>
  )
}
