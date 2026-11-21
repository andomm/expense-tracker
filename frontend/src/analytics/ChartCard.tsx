import { useId, type ReactNode } from "react"
import { ChevronDown } from "lucide-react"

import { Card, CardContent, CardHeader } from "@/components/ui/card"

export function ChartCard({ title, caption, children }: {
  title: string; caption: string; children: ReactNode
}) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="min-w-0">
      <Card className="h-full gap-4 py-4 sm:py-5">
        <CardHeader className="gap-1 px-3 sm:px-5">
          <h2 id={id} className="text-lg font-extrabold tracking-tight">{title}</h2>
          <p className="text-sm text-muted-foreground">{caption}</p>
        </CardHeader>
        <CardContent className="min-w-0 px-3 sm:px-5">{children}</CardContent>
      </Card>
    </section>
  )
}

export function ChartEmpty({ children }: { children: ReactNode }) {
  return <p className="rounded-lg bg-background px-3 py-6 text-sm text-muted-foreground">{children}</p>
}

export function ValuesTable({ caption, columns, rows }: {
  caption: string; columns: string[]; rows: [string, ...ReactNode[]][]
}) {
  return (
    <table className="w-full table-fixed text-xs sm:text-sm">
      <caption className="sr-only">{caption}</caption>
      <thead>
        <tr className="border-b text-muted-foreground">
          {columns.map((label, index) => (
            <th key={label} scope="col" className={index === 0
              ? "py-2 pr-1 text-left font-semibold"
              : "py-2 pl-1 text-right font-semibold"}>{label}</th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y">
        {rows.map(([label, ...values]) => (
          <tr key={label}>
            <th scope="row" className="py-2 pr-1 text-left font-medium wrap-anywhere">{label}</th>
            {values.map((value, index) => (
              <td key={columns[index + 1]} className="py-2 pl-1 text-right font-semibold tabular-nums wrap-anywhere">
                {value}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function ExactValues({ label, children }: { label: string; children: ReactNode }) {
  return (
    <details className="group mt-2 rounded-lg border px-2">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-md px-1 text-sm font-bold text-primary outline-ring focus-visible:outline-2 [&::-webkit-details-marker]:hidden">
        <ChevronDown aria-hidden="true" className="size-4 group-open:rotate-180" />
        {label}
      </summary>
      {children}
    </details>
  )
}
