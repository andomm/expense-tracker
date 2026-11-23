import { ChevronLeft, ChevronRight, Search } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"

import { displayDate, listHref, type ExpenseList } from "./read"

const orders = [
  ["-date", "Newest first"],
  ["date", "Oldest first"],
  ["amount", "Amount (low to high)"],
  ["-amount", "Amount (high to low)"],
  ["category_obj__name", "Category (A–Z)"],
  ["-category_obj__name", "Category (Z–A)"],
  ["receiver", "Receiver (A–Z)"],
  ["-receiver", "Receiver (Z–A)"],
]

export function ExpenseFilters({ path, list }: { path: string; list: ExpenseList }) {
  const { filters, months, categories } = list
  const allDates = filters.month === "all"
  const selectedMonth = allDates ? months.current : filters.month
  const monthHref = (month: string) => listHref(path, { ...filters, month })
  const monthLabel = allDates ? "All dates" : displayDate(`${filters.month}-01`, { month: "long", year: "numeric" })

  return (
    <div className="filters">
      <div className="period">
        <div className="period-navigation" aria-label="Date navigation" role="group">
          {months.previous && (
            <Button asChild variant="outline" size="icon-lg">
              <a href={monthHref(months.previous)} aria-label="Previous month"><ChevronLeft aria-hidden="true" /></a>
            </Button>
          )}
          <p className="font-bold">{monthLabel}</p>
          {months.next && (
            <Button asChild variant="outline" size="icon-lg">
              <a href={monthHref(months.next)} aria-label="Next month"><ChevronRight aria-hidden="true" /></a>
            </Button>
          )}
        </div>
        <Button asChild variant="outline" className="h-10"><a href={monthHref(allDates ? months.current : "all")}>
          {allDates ? "Current month" : "All dates"}
        </a></Button>
      </div>

      <form action={path} method="get" aria-label="Choose a month" className="month-picker">
        <input type="hidden" name="category_filter" value={filters.category_filter} />
        <input type="hidden" name="order_by" value={filters.order_by} />
        <input type="hidden" name="search" value={filters.search} />
        <label htmlFor="chosen-month">Jump to month</label>
        <Input id="chosen-month" name="month" type="month" className="h-10 max-w-48" required
          min={`${Math.min(months.min_year, Number(selectedMonth.slice(0, 4))).toString().padStart(4, "0")}-01`}
          max={`${Math.max(months.max_year, Number(selectedMonth.slice(0, 4)))}-12`}
          defaultValue={selectedMonth} />
        <Button type="submit" variant="outline" className="h-10">Go</Button>
      </form>

      <form action={path} method="get" aria-label="Filter and sort expenses" className="filter-form">
        <input type="hidden" name="month" value={filters.month} />
        <div className="filter-search">
          <label htmlFor="search">Search</label>
          <div className="relative">
            <Search className="pointer-events-none absolute top-3 left-3 size-4 text-muted-foreground" aria-hidden="true" />
            <Input name="search" id="search" type="search" placeholder="Receiver, description or category"
              className="h-10 pl-9" defaultValue={filters.search} maxLength={100} />
          </div>
        </div>
        <div>
          <label htmlFor="category-filter">Category</label>
          <NativeSelect id="category-filter" name="category_filter" className="h-10" defaultValue={filters.category_filter}>
            {categories.map(({ value, label }) => (
              <NativeSelectOption key={value} value={value}>{label}</NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
        <div>
          <label htmlFor="order-by">Sort by</label>
          <NativeSelect id="order-by" name="order_by" className="h-10" defaultValue={filters.order_by}>
            {orders.map(([value, label]) => <NativeSelectOption key={value} value={value}>{label}</NativeSelectOption>)}
          </NativeSelect>
        </div>
        <Button type="submit" className="h-10">Apply filters</Button>
      </form>
    </div>
  )
}
