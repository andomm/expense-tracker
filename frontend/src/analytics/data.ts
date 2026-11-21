export type DailyPoint = { date: string; daily: string; cumulative: string }
export type MonthlyPoint = { month: string; total_spent: string }
export type CashFlowPoint = { date: string; income: string; expenses: string; balance: string }
export type YearlyPoint = { year: number; total_spent: string }
export type CategoryRow = { name: string; amount: string; percent: string }
export type CategoryPeriod = {
  month: string
  label: string
  previous: string | null
  next: string | null
  total: string
  rows: CategoryRow[]
}

export type AnalyticsData = {
  daily: DailyPoint[]
  monthly: MonthlyPoint[]
  cash_flow: CashFlowPoint[]
  yearly: YearlyPoint[]
  category: CategoryPeriod
}
