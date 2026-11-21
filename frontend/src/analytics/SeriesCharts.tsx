import { memo } from "react"
import {
  Bar, BarChart, CartesianGrid, ComposedChart, Line, LineChart, ReferenceLine, XAxis, YAxis,
} from "recharts"

import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { displayDate, euro } from "@/expenses/read"

import { ChartCard, ChartEmpty, ExactValues, ValuesTable } from "./ChartCard"
import type { CashFlowPoint, DailyPoint, MonthlyPoint } from "./data"

const dailyConfig = {
  daily: { label: "Daily spending", color: "var(--chart-spending)" },
  cumulative: { label: "Cumulative spending", color: "var(--chart-cumulative)" },
} satisfies ChartConfig
const monthlyConfig = { total_spent: { label: "Total spent", color: "var(--chart-spending)" } } satisfies ChartConfig
const flowConfig = {
  income: { label: "Income", color: "var(--chart-income)" },
  expenses: { label: "Expenses", color: "var(--chart-expenses)" },
  balance: { label: "Balance", color: "var(--chart-balance)" },
} satisfies ChartConfig
const flowStrokes = { income: undefined, expenses: "8 4", balance: "2 4" }
const flowKeys = ["income", "expenses", "balance"] as const

const tickDay = new Intl.DateTimeFormat("en", { month: "short", day: "numeric", timeZone: "UTC" })
const fullDay = new Intl.DateTimeFormat("en", { dateStyle: "long", timeZone: "UTC" })
const compactNumber = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 })
const axisMoney = (value: number) => `${value < 0 ? "−" : ""}€${compactNumber.format(Math.abs(value))}`
const monthLabel = (value: string) => displayDate(`${value}-01`, { month: "short", year: "numeric" })
const axes = { tick: { fill: "var(--muted-foreground)" }, tickLine: false, axisLine: false, tickMargin: 6 } as const
const yAxis = { ...axes, width: "auto", tickFormatter: axisMoney, tickCount: 5 } as const
const chartHeight = "h-52 sm:h-64"
const grid = <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 3" />

// The original strings stay in each row for exact table/tooltip output.
// Only the coordinates passed to Recharts use floating point.
function plotRows<T extends object>(rows: T[], keys: (keyof T)[]) {
  return rows.map((row) => ({
    ...row,
    plot: Object.fromEntries(keys.map((key) => [key, Number(row[key])])),
  }))
}

function dateAxis(rows: { timestamp: number }[], pad: number) {
  return <XAxis {...axes} dataKey="timestamp" type="number" domain={["dataMin", "dataMax"]}
    ticks={rows.map((row) => row.timestamp)} interval="preserveStartEnd" minTickGap={26} padding={{ left: pad, right: pad }}
    tickFormatter={(value: number) => tickDay.format(value)} />
}

const exactTooltip = (formatLabel: (value: string | number) => string) => (
  <ChartTooltip isAnimationActive={false} cursor={{ stroke: "var(--input)", fill: "var(--accent)" }}
    content={<ChartTooltipContent formatLabel={formatLabel} formatValue={(item, key) => euro(item.payload[key])} />} />
)

export const DailySpending = memo(function DailySpending({ rows }: { rows: DailyPoint[] }) {
  const data = plotRows(rows, ["daily", "cumulative"]).map((row) => ({ ...row, timestamp: Date.parse(row.date) }))
  return (
    <ChartCard title="Daily vs cumulative spending" caption="Net spending by day and running total, on separate scales.">
      {!rows.length ? <ChartEmpty>No daily spending data yet.</ChartEmpty> : <>
        <div className="mb-2 flex justify-between gap-2 text-xs font-bold">
          <span className="flex items-center gap-1.5"><span aria-hidden="true" className="size-2.5 shrink-0 rounded-xs bg-[var(--chart-spending)]" />Daily · left (€)</span>
          <span className="flex items-center gap-1.5"><span aria-hidden="true" className="h-0.5 w-4 shrink-0 bg-[var(--chart-cumulative)]" />Cumulative · right (€)</span>
        </div>
        <ChartContainer config={dailyConfig} className={chartHeight}>
          <ComposedChart data={data} aria-label="Daily and cumulative spending chart" margin={{ top: 6, right: 4, bottom: 2, left: 0 }}>
            {grid}
            {dateAxis(data, 16)}
            <YAxis {...yAxis} yAxisId="daily" />
            <YAxis {...yAxis} yAxisId="cumulative" orientation="right" />
            {exactTooltip((value) => fullDay.format(Number(value)))}
            <Bar yAxisId="daily" name="daily" dataKey="plot.daily" fill="var(--color-daily)" maxBarSize={25}
              radius={[3, 3, 0, 0]} isAnimationActive={false} />
            <Line yAxisId="cumulative" name="cumulative" dataKey="plot.cumulative" type="linear"
              stroke="var(--color-cumulative)" strokeWidth={2.5} dot={rows.length === 1} isAnimationActive={false} />
          </ComposedChart>
        </ChartContainer>
        <ExactValues label="View daily spending data">
          <ValuesTable caption="Exact daily and cumulative spending" columns={["Date", "Daily", "Cumulative"]}
            rows={rows.map((row) => [row.date, euro(row.daily), euro(row.cumulative)])} />
        </ExactValues>
      </>}
    </ChartCard>
  )
})

export const MonthlySpending = memo(function MonthlySpending({ rows }: { rows: MonthlyPoint[] }) {
  const data = plotRows(rows, ["total_spent"])
  return (
    <ChartCard title="Monthly spending" caption="Net spending for each month with recorded expenses.">
      {!rows.length ? <ChartEmpty>No monthly spending data yet.</ChartEmpty> : <>
        <ChartContainer config={monthlyConfig} className="h-59 sm:h-71">
          <BarChart data={data} aria-label="Monthly spending chart" margin={{ top: 6, right: 8, bottom: 2, left: 0 }}>
            {grid}
            <XAxis {...axes} dataKey="month" minTickGap={26} tickFormatter={monthLabel} />
            <YAxis {...yAxis} />
            {exactTooltip((value) => monthLabel(String(value)))}
            <Bar name="total_spent" dataKey="plot.total_spent" fill="var(--color-total_spent)" maxBarSize={44}
              radius={[3, 3, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ChartContainer>
        <ExactValues label="View monthly spending data">
          <ValuesTable caption="Exact monthly spending" columns={["Month", "Total spent"]}
            rows={rows.map((row) => [monthLabel(row.month), euro(row.total_spent)])} />
        </ExactValues>
      </>}
    </ChartCard>
  )
})

export const CashFlow = memo(function CashFlow({ rows }: { rows: CashFlowPoint[] }) {
  const data = plotRows(rows, [...flowKeys]).map((row) => ({ ...row, timestamp: Date.parse(row.date) }))
  return (
    <ChartCard title="Income vs expenses" caption="Cumulative income, cumulative expenses, and signed balance.">
      {!rows.length ? <ChartEmpty>No income or spending data yet.</ChartEmpty> : <>
        <ul aria-label="Cash-flow series" className="mb-2 flex flex-wrap gap-x-4 gap-y-2 text-xs font-bold">
          {flowKeys.map((key) => (
            <li key={key} className="flex items-center gap-1.5">
              <svg aria-hidden="true" width="22" height="5"><path d="M0 2.5H22" stroke={flowConfig[key].color}
                strokeWidth="2.5" strokeDasharray={flowStrokes[key]} /></svg>
              {flowConfig[key].label}
            </li>
          ))}
        </ul>
        <ChartContainer config={flowConfig} className={chartHeight}>
          <LineChart data={data} aria-label="Income, expenses and balance chart" margin={{ top: 6, right: 4, bottom: 2, left: 0 }}>
            {grid}
            {dateAxis(data, 12)}
            <YAxis {...yAxis} />
            <ReferenceLine y={0} stroke="var(--input)" />
            {exactTooltip((value) => fullDay.format(Number(value)))}
            {flowKeys.map((key) => (
              <Line key={key} name={key} dataKey={`plot.${key}`} type="linear" stroke={`var(--color-${key})`}
                strokeWidth={2.5} strokeDasharray={flowStrokes[key]} dot={rows.length === 1} isAnimationActive={false} />
            ))}
          </LineChart>
        </ChartContainer>
        <ExactValues label="View cash-flow data">
          <ValuesTable caption="Exact income, expenses and balance" columns={["Date", "Income", "Expenses", "Balance"]}
            rows={rows.map((row) => [row.date, euro(row.income), euro(row.expenses), euro(row.balance)])} />
        </ExactValues>
      </>}
    </ChartCard>
  )
})
