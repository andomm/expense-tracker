import { ArrowDownLeft, ArrowUpRight, Bookmark, CheckCircle2, Plus, Receipt } from "lucide-react"
import { useContext, useEffect, useRef, useState, type MouseEvent } from "react"

import { ProtectedAccess } from "@/auth/access"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useRead, type Session } from "@/lib/api"
import { ReadFailure, type AppUrls } from "@/Shell"

import { BulkExpenseActions } from "./BulkExpenseActions"
import { ExpenseFilters } from "./ExpenseFilters"
import { emptySelection, type BulkSelection } from "./bulk"
import { displayDate, euro, expenseContextHref, listHref, listRequestUrl, type Expense, type ExpenseList } from "./read"

function Balance({ summary, allDates }: { summary: ExpenseList["summary"]; allDates: boolean }) {
  return (
    <Card role="region" aria-labelledby="balance-title"
      className="balance-card gap-3 rounded-2xl border-transparent bg-[var(--balance)] py-5 text-[var(--balance-text)] shadow-none sm:gap-4 sm:py-6">
      <CardHeader className="px-4 sm:px-6">
        <h2 id="balance-title" className="eyebrow">{allDates ? "All dates" : "Monthly"} balance</h2>
        <p className="balance-amount money">{euro(summary.balance)}</p>
        <p className="balance-note">Income plus net spending. Savings and transfers excluded.</p>
      </CardHeader>
      <CardContent className="px-4 sm:px-6">
        <dl>
          {([
            ["Net spending", summary.total_spent, ArrowUpRight],
            ["Income", summary.income, ArrowDownLeft],
            ["Savings", summary.savings_total, Bookmark],
          ] as const).map(([label, amount, Icon]) => (
            <div key={label}>
              <dt><Icon size={15} aria-hidden="true" />{label}</dt>
              <dd className="money">{euro(amount)}</dd>
            </div>
          ))}
        </dl>
        <p className="balance-foot">Your share · All matching expenses</p>
      </CardContent>
    </Card>
  )
}

function TopExpenses({ rows }: { rows: Expense[] }) {
  return (
    <Card role="region" className="top-card gap-3 shadow-none" aria-labelledby="top-title">
      <CardHeader>
        <h2 id="top-title">Top expenses</h2>
        <p className="small-note">Largest outflows by your share, across all matching expenses.</p>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? <p className="small-note">No spending to rank.</p> : (
          <ol>
            {rows.map((row) => (
              <li key={row.id}>
                <div>
                  <p>{row.receiver || row.description || "No receiver or description"}</p>
                  <p className="small-note">{row.category?.name ?? "Uncategorized"}</p>
                </div>
                <span className="money">{euro(row.personal_share)}</span>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  )
}

type RowSelection = { ids: ReadonlySet<number>; toggle: (id: number) => void }

function ExpenseRow({ row, showDate, context, selection }: {
  row: Expense; showDate: boolean; context: (path: string) => string; selection?: RowSelection
}) {
  const name = row.receiver || row.description || "No receiver or description"
  return (
    <li className={selection ? "expense-row grid-cols-[auto_minmax(0,1fr)_auto]" : "expense-row"}>
      {selection ? <label className="grid size-8 cursor-pointer place-items-center rounded-md hover:bg-accent has-focus-visible:ring-2 has-focus-visible:ring-ring sm:size-9">
        <input type="checkbox" className="size-4 cursor-pointer accent-primary" aria-label={`Select expense: ${name}`}
          checked={selection.ids.has(row.id)} onChange={() => selection.toggle(row.id)} />
      </label> : <span className="receipt-icon"><Receipt size={17} aria-hidden="true" /></span>}
      <div className="row-description">
        <p className="row-name">{name}</p>
        <p className="small-note">{row.category?.name ?? "Uncategorized"}</p>
        {row.receiver && row.description && <p className="small-note row-note">{row.description}</p>}
        {showDate && <time className="small-note" dateTime={row.date}>
          {displayDate(row.date, { month: "short", day: "numeric", year: "numeric" })}
        </time>}
        <div className="pt-1">
          <Button asChild size="sm" variant="outline">
            <a href={context(row.edit_url)} aria-label={`Edit expense: ${name}`}>Edit</a>
          </Button>
        </div>
      </div>
      <dl className="row-amounts money">
        <div><dt>Your share</dt><dd>{euro(row.personal_share)}</dd></div>
        <div><dt>Full amount</dt><dd>{euro(row.amount)}</dd></div>
      </dl>
    </li>
  )
}

function ExpenseRows({ list, context, selection }: {
  list: ExpenseList; context: (path: string) => string; selection?: RowSelection
}) {
  if (list.filters.order_by.replace(/^-/, "") !== "date") {
    return <ul className="expense-rows" aria-label="Expenses on this page">
      {list.rows.map((row) => <ExpenseRow key={row.id} row={row} context={context} selection={selection} showDate />)}
    </ul>
  }

  const groups = new Map<string, Expense[]>()
  for (const row of list.rows) {
    const group = groups.get(row.date)
    if (group) {
      group.push(row)
    } else {
      groups.set(row.date, [row])
    }
  }

  return <div className="date-groups">
    {[...groups].map(([day, rows]) => (
      <section className="date-group" key={day} aria-labelledby={`date-${day}`}>
        <h3 id={`date-${day}`}>
          <time dateTime={day}>{displayDate(day, { day: "numeric", month: "short", year: "numeric" })}</time>
        </h3>
        <ul className="expense-rows">
          {rows.map((row) => <ExpenseRow key={row.id} row={row} context={context} selection={selection} showDate={false} />)}
        </ul>
      </section>
    ))}
  </div>
}

function Pagination({ path, list, navigate }: {
  path: string; list: ExpenseList; navigate: (event: MouseEvent<HTMLAnchorElement>) => void
}) {
  const { page, pages } = list.pagination
  if (pages < 2) {
    return null
  }

  return (
    <nav className="pager" aria-label="Expense pages">
      {page > 1
        ? <Button asChild variant="outline"><a href={listHref(path, list.filters, page - 1)} onClick={navigate}>Previous page</a></Button>
        : <span />}
      <span>Page {page} of {pages}</span>
      {page < pages
        ? <Button asChild variant="outline"><a href={listHref(path, list.filters, page + 1)} onClick={navigate}>Next page</a></Button>
        : <span />}
    </nav>
  )
}

export function LoadingExpenses() {
  return (
    <div className="ledger">
      <Skeleton className="h-64 w-full" aria-hidden="true" />
      <div className="notice" role="status">
        <p>Loading expenses…</p>
        <Skeleton className="h-12 w-full" aria-hidden="true" />
        <Skeleton className="h-12 w-full" aria-hidden="true" />
      </div>
    </div>
  )
}

type PageProps = { urls: AppUrls; notices: string[]; userId: number; session: Session }
type ScopedSelection = { key: string; value: BulkSelection; readVersion: number }

export function ExpensesPage({ urls, notices, userId, session, expired }: PageProps & { expired: boolean }) {
  const { readVersion } = useContext(ProtectedAccess)
  const [search, setSearch] = useState(window.location.search)
  const [selected, setSelected] = useState<ScopedSelection | null>(null)
  const [success, setSuccess] = useState("")
  const [restores, setRestores] = useState(0)
  const request = listRequestUrl(urls.expensesApi, search)

  useEffect(() => {
    const sync = () => setSearch(window.location.search)
    const restore = (event: PageTransitionEvent) => {
      if (!event.persisted) return
      // Returning from a different document must not restore a selection draft.
      setSelected(null)
      setSuccess("")
      setRestores((value) => value + 1)
      sync()
    }
    window.addEventListener("popstate", sync)
    window.addEventListener("pageshow", restore)
    return () => {
      window.removeEventListener("popstate", sync)
      window.removeEventListener("pageshow", restore)
    }
  }, [])

  useEffect(() => {
    // Only manually selected IDs can survive an expired session. A match token
    // belongs to the old session and must never become actionable again.
    setSelected((previous) => previous?.value.mode === "matching" &&
      (expired || previous.readVersion !== readVersion) ? null : previous)
    if (expired) setSuccess("")
  }, [expired, readVersion])

  if (expired) return null

  function navigate(event: MouseEvent<HTMLAnchorElement>) {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    window.history.pushState(null, "", event.currentTarget.href)
    setSearch(window.location.search)
  }

  return <ExpensesResults key={`${userId}:${restores}:${readVersion}:${request}`} request={request} urls={urls}
    notices={success ? [...notices, success] : notices} userId={userId} navigate={navigate}
    selected={selected} setSelected={setSelected} onSuccess={setSuccess} session={session} />
}

function ExpensesResults({ urls, notices, userId, request, navigate, selected, setSelected,
  onSuccess, session }: PageProps & {
  request: string; navigate: (event: MouseEvent<HTMLAnchorElement>) => void
  selected: ScopedSelection | null; setSelected: (value: ScopedSelection | null) => void
  onSuccess: (message: string) => void
}) {
  const { readVersion } = useContext(ProtectedAccess)
  const { result, retry } = useRead<ExpenseList>(request, userId)
  const focusAfterRefresh = useRef(false)
  function refresh() {
    focusAfterRefresh.current = true
    retry()
  }
  const scope = result.state === "ready" ? `${userId}:${expenseContextHref(urls.expenses, result.data.filters)}` : null
  useEffect(() => {
    if (!scope) return
    if (selected && selected.key !== scope) setSelected(null)
  }, [scope, selected, setSelected])
  useEffect(() => {
    if (result.state === "ready" && (location.hash === "#activity" || focusAfterRefresh.current)) {
      focusAfterRefresh.current = false
      document.getElementById("activity")?.focus()
    }
  }, [result.state])
  if (result.state === "loading") {
    return <LoadingExpenses />
  }
  if (result.state === "error") {
    return <ReadFailure message={result.message} retry={retry} reset={urls.expenses} />
  }

  const list = result.data
  const selection = selected?.key === scope && (selected.value.mode === "explicit" || selected.readVersion === readVersion)
    ? selected.value : emptySelection
  const setSelection = (value: BulkSelection) => setSelected(scope ? { key: scope, value, readVersion } : null)
  const rowSelection: RowSelection | undefined = selection.mode === "explicit" ? {
    ids: selection.ids,
    toggle(id) {
      const ids = new Set(selection.ids)
      if (!ids.delete(id)) ids.add(id)
      setSelection({ mode: "explicit", ids })
    },
  } : undefined
  const { page, page_size: pageSize, count } = list.pagination
  const context = (path: string) => expenseContextHref(path, list.filters, page > 1 ? page : undefined)
  const firstRow = (page - 1) * pageSize + 1
  const resultLabel = count <= 1
    ? `${count} matching expense${count === 0 ? "s" : ""}`
    : `Showing ${firstRow}–${firstRow + list.rows.length - 1} of ${count} expenses`
  return (
    <>
      <div className="ledger">
        <Balance summary={list.summary} allDates={list.filters.month === "all"} />
        <section className="activity" aria-labelledby="activity-title">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 id="activity-title" className="mb-0">Activity</h2>
            <Button asChild><a href={context(urls.addExpense)}><Plus aria-hidden="true" /> Add expense</a></Button>
          </div>
          {notices.length > 0 && (
            <div role="status" className="mb-3 flex items-start gap-2 rounded-lg border bg-accent px-3 py-2 text-sm font-bold">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
              <div>{notices.map((notice, index) => <p key={index}>{notice}</p>)}</div>
            </div>
          )}
          <ExpenseFilters path={urls.expenses} list={list} />
          <div id="activity" className="results-header" tabIndex={-1}>
            <p role="status">{resultLabel}</p>
          </div>
          <BulkExpenseActions urls={urls} userId={userId} csrfToken={session.csrf_token} list={list} selection={selection}
            onSelection={setSelection} onRefresh={refresh}
            onSuccess={(message) => { setSelected(null); onSuccess(message); refresh() }} />
          {count ? <ExpenseRows list={list} context={context} selection={rowSelection} /> : (
            <div className="notice">
              <h3>No matching expenses</h3>
              <p>Try changing the month or clearing your filters.</p>
              <Button asChild variant="outline"><a href={urls.expenses}>Reset filters</a></Button>
            </div>
          )}
          <Pagination path={urls.expenses} list={list} navigate={navigate} />
        </section>
        <TopExpenses rows={list.top_expenses} />
      </div>
      <section aria-labelledby="account-actions-title" className="mt-8 grid justify-items-start gap-2 border-t pt-4">
        <h2 id="account-actions-title" className="font-extrabold">Account actions</h2>
        <p className="text-sm text-muted-foreground">This action applies to all months, regardless of your filters.</p>
        <Button asChild variant="outline" className="h-11 text-destructive hover:text-destructive">
          <a href={context(urls.deleteAllExpenses)}>Delete all expenses</a>
        </Button>
      </section>
    </>
  )
}
