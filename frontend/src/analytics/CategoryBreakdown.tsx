import { ChevronLeft, ChevronRight } from "lucide-react"
import { Pie, PieChart } from "recharts"

import { Button } from "@/components/ui/button"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { euro } from "@/expenses/read"

import { ChartEmpty, ValuesTable } from "./ChartCard"
import type { CategoryPeriod, CategoryRow } from "./data"

export function MonthNavigation({ period, pending, failed, changeMonth }: {
  period: CategoryPeriod; pending: boolean; failed: boolean; changeMonth: (month: string) => void
}) {
  const disabled = pending || failed
  return (
    <div role="group" aria-label="Category month" className="flex flex-wrap items-center justify-between gap-x-1 gap-y-2">
      <Button type="button" size="icon-lg" variant="outline" aria-label="Previous month"
        className="size-11 aria-disabled:opacity-50" aria-disabled={disabled || !period.previous}
        onClick={() => { if (!disabled && period.previous) changeMonth(period.previous) }}>
        <ChevronLeft aria-hidden="true" />
      </Button>
      <p aria-live="polite" aria-atomic="true" className="flex-1 text-center text-sm font-extrabold">
        {pending ? "Changing month…" : failed ? "Month unavailable" : period.label}
      </p>
      <Button type="button" size="icon-lg" variant="outline" aria-label="Next month"
        className="size-11 aria-disabled:opacity-50" aria-disabled={disabled || !period.next}
        onClick={() => { if (!disabled && period.next) changeMonth(period.next) }}>
        <ChevronRight aria-hidden="true" />
      </Button>
    </div>
  )
}

const palette = ["spending", "cumulative", "blue", "expenses", "balance", "olive", "income", "ochre"]
const sliceColor = (index: number) => `var(--chart-${palette[index % palette.length]})`

export function CategoryBreakdown({ period }: { period: CategoryPeriod }) {
  const { rows, label, total } = period
  if (!rows.length) return <ChartEmpty>No category data for {label}.</ChartEmpty>
  const hasSlices = total !== "0.00"
  const data = rows.map((row, index) => ({ ...row, size: Number(row.amount), fill: sliceColor(index) }))
  return (
    <>
      <div className="relative mt-2 flex h-48 items-center justify-center sm:h-52">
        {hasSlices ? (
          <ChartContainer config={{}} className="h-full w-full">
            <PieChart aria-label={`Category spending chart for ${label}`}>
              <Pie data={data} dataKey="size" nameKey="name" innerRadius="68%" outerRadius="94%"
                stroke="var(--card)" strokeWidth={2} isAnimationActive={false} />
              <ChartTooltip isAnimationActive={false} content={<ChartTooltipContent formatValue={(item) => {
                const row = item.payload as CategoryRow
                return `${euro(row.amount)} · ${row.percent}%`
              }} />} />
            </PieChart>
          </ChartContainer>
        ) : (
          <span aria-hidden="true" className="size-40 rounded-full border-[18px] border-accent" />
        )}
        <div className="pointer-events-none absolute inset-0 grid place-content-center text-center">
          <span className="text-xs font-semibold text-muted-foreground">Total</span>
          <strong className="money max-w-28 text-base tracking-tight" aria-label={`Total ${euro(total)}`}>{euro(total)}</strong>
        </div>
      </div>
      {!hasSlices && <p className="mb-1 text-center text-sm text-muted-foreground">Spending nets to zero.</p>}
      <ValuesTable caption={`Exact category spending for ${label}`} columns={["Category", "Amount", "Share"]}
        rows={rows.map((row, index) => [row.name, euro(row.amount), <span className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="size-2.5 shrink-0 rounded-xs" style={{ background: sliceColor(index) }} />
          {row.percent}%
        </span>])} />
    </>
  )
}
