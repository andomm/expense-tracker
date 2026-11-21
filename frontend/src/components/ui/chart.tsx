// shadcn/ui Chart, adapted to the ledger's theme and exact-value tooltips.
import { createContext, useContext, type ComponentProps, type CSSProperties, type ReactNode } from "react"
import { ResponsiveContainer, Tooltip, type TooltipContentProps } from "recharts"

import { cn } from "@/lib/utils"

export type ChartConfig = Record<string, { label: string; color: string }>
const ChartContext = createContext<ChartConfig>({})

export function ChartContainer({ config, className, children, style, ...props }: ComponentProps<"div"> & {
  config: ChartConfig
  children: ComponentProps<typeof ResponsiveContainer>["children"]
}) {
  const colors = Object.fromEntries(Object.entries(config).map(([key, { color }]) => [`--color-${key}`, color]))
  return (
    <ChartContext.Provider value={config}>
      <div data-slot="chart" style={{ ...colors, ...style } as CSSProperties} {...props}
        className={cn(
          "min-w-0 text-xs [&_.recharts-layer]:outline-none [&_.recharts-surface:focus-visible]:outline-2 [&_.recharts-surface:focus-visible]:outline-ring",
          className,
        )}>
        <ResponsiveContainer>{children}</ResponsiveContainer>
      </div>
    </ChartContext.Provider>
  )
}

export const ChartTooltip = Tooltip

type TooltipProps = TooltipContentProps<number, string>

export function ChartTooltipContent({ active, payload, label, formatLabel, formatValue }: Partial<TooltipProps> & {
  formatLabel?: (label: string | number) => string
  formatValue: (item: TooltipProps["payload"][number], key: string) => ReactNode
}) {
  const config = useContext(ChartContext)
  if (!active || !payload?.length) return null
  return (
    <div role="status" className="grid max-w-56 gap-1.5 rounded-lg border bg-card px-3 py-2 text-xs text-foreground shadow-lg">
      {label !== undefined && <p className="font-bold">{formatLabel ? formatLabel(label) : label}</p>}
      <dl className="grid gap-1">
        {payload.map((item) => {
          const key = String(item.name ?? item.dataKey)
          return (
            <div key={key} className="flex flex-wrap justify-between gap-x-3 gap-y-1">
              <dt className="wrap-anywhere text-muted-foreground">{config[key]?.label ?? key}</dt>
              <dd className="font-bold tabular-nums">{formatValue(item, key)}</dd>
            </div>
          )
        })}
      </dl>
    </div>
  )
}
