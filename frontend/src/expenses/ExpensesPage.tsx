import { ArrowDownLeft, ArrowUpRight, Bookmark, Receipt } from "lucide-react"
import { useEffect } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useRead } from "@/lib/api"
import { ReadFailure, SignInNotice, type AppConfig } from "@/Shell"

import { ExpenseFilters } from "./ExpenseFilters"
import { displayDate, euro, listHref, listRequestUrl, type Expense, type ExpenseList } from "./read"

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

function ExpenseRow({ row, showDate }: { row: Expense; showDate: boolean }) {
  return (
    <li className="expense-row">
      <span className="receipt-icon"><Receipt size={17} aria-hidden="true" /></span>
      <div className="row-description">
        <p className="row-name">{row.receiver || row.description || "No receiver or description"}</p>
        <p className="small-note">{row.category?.name ?? "Uncategorized"}</p>
        {row.receiver && row.description && <p className="small-note row-note">{row.description}</p>}
        {showDate && <time className="small-note" dateTime={row.date}>
          {displayDate(row.date, { month: "short", day: "numeric", year: "numeric" })}
        </time>}
      </div>
      <dl className="row-amounts money">
        <div><dt>Your share</dt><dd>{euro(row.personal_share)}</dd></div>
        <div><dt>Full amount</dt><dd>{euro(row.amount)}</dd></div>
      </dl>
    </li>
  )
}

function ExpenseRows({ list }: { list: ExpenseList }) {
  if (list.filters.order_by.replace(/^-/, "") !== "date") {
    return <ul className="expense-rows" aria-label="Expenses on this page">
      {list.rows.map((row) => <ExpenseRow key={row.id} row={row} showDate />)}
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
          {rows.map((row) => <ExpenseRow key={row.id} row={row} showDate={false} />)}
        </ul>
      </section>
    ))}
  </div>
}

function Pagination({ path, list }: { path: string; list: ExpenseList }) {
  const { page, pages } = list.pagination
  if (pages < 2) {
    return null
  }

  return (
    <nav className="pager" aria-label="Expense pages">
      {page > 1
        ? <Button asChild variant="outline"><a href={listHref(path, list.filters, page - 1)}>Previous page</a></Button>
        : <span />}
      <span>Page {page} of {pages}</span>
      {page < pages
        ? <Button asChild variant="outline"><a href={listHref(path, list.filters, page + 1)}>Next page</a></Button>
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

export function ExpensesPage({ urls }: { urls: AppConfig["urls"] }) {
  const { result, retry } = useRead<ExpenseList>(listRequestUrl(urls.expensesApi))
  useEffect(() => {
    if (result.state === "ready" && location.hash === "#activity") {
      document.getElementById("activity")?.focus()
    }
  }, [result.state])
  if (result.state === "loading") {
    return <LoadingExpenses />
  }
  if (result.state === "error") {
    return result.expired
      ? <SignInNotice login={urls.login} />
      : <ReadFailure message={result.message} retry={retry} reset={urls.expenses} />
  }

  const list = result.data
  const { page, page_size: pageSize, count } = list.pagination
  const firstRow = (page - 1) * pageSize + 1
  const resultLabel = count <= 1
    ? `${count} matching expense${count === 0 ? "s" : ""}`
    : `Showing ${firstRow}–${firstRow + list.rows.length - 1} of ${count} expenses`
  return (
    <div className="ledger">
      <Balance summary={list.summary} allDates={list.filters.month === "all"} />
      <section className="activity" aria-labelledby="activity-title">
        <h2 id="activity-title">Activity</h2>
        <ExpenseFilters path={urls.expenses} list={list} />
        <div id="activity" className="results-header" tabIndex={-1}>
          <p role="status">{resultLabel}</p>
        </div>
        {count ? <ExpenseRows list={list} /> : (
          <div className="notice">
            <h3>No matching expenses</h3>
            <p>Try changing the month or clearing your filters.</p>
            <Button asChild variant="outline"><a href={urls.expenses}>Reset filters</a></Button>
          </div>
        )}
        <Pagination path={urls.expenses} list={list} />
      </section>
      <TopExpenses rows={list.top_expenses} />
    </div>
  )
}
