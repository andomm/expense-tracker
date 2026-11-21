export type Filters = {
  month: string
  search: string
  category_filter: string
  order_by: string
}

export type Expense = {
  id: number
  edit_url: string
  date: string
  receiver: string
  description: string
  category: { id: number; name: string } | null
  amount: string
  personal_share: string
}

export type ExpenseList = {
  filters: Filters
  months: { current: string; previous: string | null; next: string | null; min_year: number; max_year: number }
  categories: { value: string; label: string }[]
  pagination: { page: number; page_size: number; pages: number; count: number }
  rows: Expense[]
  summary: Record<"balance" | "total_spent" | "income" | "savings_total", string>
  top_expenses: Expense[]
}

export function listRequestUrl(endpoint: string) {
  const incoming = new URLSearchParams(window.location.search)
  const params = new URLSearchParams()
  for (const name of ["month", "category_filter", "order_by", "search", "page"]) {
    const value = incoming.getAll(name).at(-1)
    if (value !== undefined) {
      params.set(name, value)
    }
  }
  return `${endpoint}?${params}`
}

export function expenseContextHref(path: string, filters: Filters, page?: number) {
  const params = new URLSearchParams(filters)
  if (page !== undefined) {
    params.set("page", String(page))
  }
  return `${path}?${params}`
}

export function listHref(path: string, filters: Filters, page?: number) {
  return expenseContextHref(path, filters, page) + (page === undefined ? "" : "#activity")
}

// Group digits for display only. No conversion to floating point or totals in React.
export function euro(decimal: string) {
  const [whole, cents] = decimal.replace(/^-/, "").split(".")
  return `${decimal.startsWith("-") ? "−" : ""}€${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${cents}`
}

export function displayDate(value: string, options: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat("en", { ...options, timeZone: "UTC" }).format(new Date(value))
}
