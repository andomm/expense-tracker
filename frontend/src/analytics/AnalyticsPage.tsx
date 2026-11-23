import { useEffect, useState } from "react"

import { euro } from "@/expenses/read"
import { readJson } from "@/lib/api"
import { ReadFailure } from "@/Shell"

import { CategoryBreakdown, MonthNavigation } from "./CategoryBreakdown"
import { ChartCard, ChartEmpty, ValuesTable } from "./ChartCard"
import { LoadingAnalytics } from "./LoadingAnalytics"
import { CashFlow, DailySpending, MonthlySpending } from "./SeriesCharts"
import type { AnalyticsData } from "./data"

function selectedMonth() {
  return new URLSearchParams(location.search).getAll("month").at(-1) ?? ""
}

type Selection = { month: string }
type Snapshot = {
  selection: Selection
  data?: AnalyticsData
  failed?: boolean
}

export default function AnalyticsPage({ api, userId }: { api: string; userId: number }) {
  const [selection, select] = useState<Selection>(() => ({ month: selectedMonth() }))
  const [snapshot, setSnapshot] = useState<Snapshot>()

  useEffect(() => {
    const restoreMonth = () => select({ month: selectedMonth() })
    window.addEventListener("popstate", restoreMonth)
    return () => window.removeEventListener("popstate", restoreMonth)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    const url = `${api}?${new URLSearchParams({ month: selection.month })}`
    void readJson<AnalyticsData>(url, controller.signal, userId).then((data) => {
      if (controller.signal.aborted) return
      // Month navigation updates only the selected breakdown. Reload the page
      // to refresh the all-time report as a whole.
      setSnapshot((old) => ({ selection, data: old?.data ? { ...old.data, category: data.category } : data }))
    }).catch(() => {
      if (controller.signal.aborted) return
      setSnapshot((old) => ({ selection, data: old?.data, failed: true }))
    })
    return () => controller.abort()
  }, [api, selection, userId])

  function changeMonth(month: string) {
    const url = new URL(location.href)
    url.searchParams.set("month", month)
    history.pushState(null, "", url)
    select({ month })
  }

  const busy = snapshot?.selection !== selection
  const retry = () => select({ ...selection })
  const data = snapshot?.data
  if (!data) {
    return busy ? <LoadingAnalytics /> : <ReadFailure title="Could not load Analytics" message="" retry={retry} />
  }
  const categoryError = !busy && snapshot.failed === true

  return (
    <div className="analytics grid gap-4 sm:gap-5 lg:grid-cols-2">
      <DailySpending rows={data.daily} />
      <MonthlySpending rows={data.monthly} />
      <ChartCard title="Spending by category" caption="Root categories for the selected month, after refunds.">
        <MonthNavigation period={data.category} pending={busy} changeMonth={changeMonth} failed={categoryError} />
        {busy ? <div className="mt-2"><ChartEmpty>Loading category data…</ChartEmpty></div> : categoryError ? (
          <div className="mt-2"><ReadFailure title="Could not load the selected month" message="" retry={retry} /></div>
        ) : <div className="mt-2"><CategoryBreakdown period={data.category} /></div>}
      </ChartCard>
      <CashFlow rows={data.cash_flow} />
      <div className="min-w-0 lg:col-span-2">
        <ChartCard title="Yearly summary" caption="Net spending by calendar year.">
          {!data.yearly.length ? <ChartEmpty>No yearly spending data yet.</ChartEmpty> : (
            <ValuesTable caption="Yearly spending totals" columns={["Year", "Total spent"]}
              rows={data.yearly.map((row) => [String(row.year), euro(row.total_spent)])} />
          )}
        </ChartCard>
      </div>
    </div>
  )
}
