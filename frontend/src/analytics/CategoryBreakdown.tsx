import { ChevronLeft, ChevronRight } from "lucide-react"
import { useState } from "react"
import { Pie, PieChart, Sector, type PieLabelRenderProps } from "recharts"

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

function SliceNumber({ cx, cy, midAngle, middleRadius, index }: PieLabelRenderProps) {
  if (midAngle === undefined || middleRadius === undefined) return null
  const angle = -midAngle * Math.PI / 180
  const x = cx + middleRadius * Math.cos(angle)
  const y = cy + middleRadius * Math.sin(angle)
  return (
    <g aria-hidden="true" pointerEvents="none">
      <circle cx={x} cy={y} r={12} fill="var(--card)" />
      <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fill="var(--foreground)"
        className="text-xs font-extrabold">{index + 1}</text>
    </g>
  )
}

export function CategoryBreakdown({ period }: { period: CategoryPeriod }) {
  const [selected, setSelected] = useState<number | null>(null)
  const { rows, label, total } = period
  if (!rows.length) return <ChartEmpty>No category data for {label}.</ChartEmpty>
  const hasSlices = total !== "0.00"
  const data = rows.map((row, index) => ({ ...row, size: Number(row.amount), fill: sliceColor(index) }))
  const active = selected === null ? null : data[selected]
  function toggle(index: number) {
    if (data[index].size > 0) setSelected((prior) => prior === index ? null : index)
  }

  return (
    <>
      <div className="relative mt-2 flex h-48 items-center justify-center sm:h-52">
        {hasSlices ? (
          <ChartContainer config={{}} className="h-full w-full">
            <PieChart aria-label={`Category spending chart for ${label}`}>
              <Pie data={data} dataKey="size" nameKey="name" innerRadius="64%" outerRadius="94%"
                isAnimationActive={false} onClick={(_, index) => toggle(index)}
                shape={({ index, cx, cy, innerRadius, outerRadius, startAngle, endAngle, fill }) => (
                  <Sector cx={cx} cy={cy} innerRadius={innerRadius} outerRadius={outerRadius}
                    startAngle={startAngle} endAngle={endAngle} fill={fill}
                    data-slice={index + 1} data-highlighted={selected === index}
                    opacity={selected === null || selected === index ? 1 : 0.28}
                    stroke={selected === index ? "var(--foreground)" : "var(--card)"}
                    strokeWidth={selected === index ? 3 : 2} />
                )}
                labelLine={false} label={(props) => {
                  const arcLength = Math.abs(props.startAngle - props.endAngle) * Math.PI / 180 * (props.middleRadius ?? 0)
                  const show = selected === null ? arcLength >= 26 : selected === props.index
                  return show ? <SliceNumber {...props} /> : null
                }} />
              <ChartTooltip active={active ? false : undefined} isAnimationActive={false}
                content={<ChartTooltipContent formatValue={(item) => {
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
      {hasSlices && <p role="status" className="mb-1 text-center text-sm text-muted-foreground wrap-anywhere">
        {active && selected !== null ? <><strong>{selected + 1}. {active.name}</strong> · {euro(active.amount)} · {active.percent}%</>
          : "Select a category below to highlight its slice."}
      </p>}
      <ValuesTable caption={`Exact category spending for ${label}`} columns={["Category", "Amount", "Share"]}
        rows={rows.map((row) => [row.name, euro(row.amount), `${row.percent}%`])}
        renderLabel={(name, index) => data[index].size === 0 ? name : (
          <button type="button" aria-pressed={selected === index} onClick={() => toggle(index)}
            className="flex min-h-11 w-full cursor-pointer items-center gap-1.5 rounded text-left outline-ring
              hover:bg-accent focus-visible:outline-2 aria-pressed:bg-accent aria-pressed:font-bold">
            <span aria-hidden="true" className="inline-grid min-w-6 shrink-0 place-items-center rounded border border-current px-0.5 tabular-nums">
              {index + 1}
            </span>
            <span className="min-w-0 wrap-anywhere">{name}</span>
          </button>
        )} />
    </>
  )
}
