import { useState, type ReactNode } from "react"
import { BarChart3, Layers3, Moon, Sun, Tags, Upload, WalletCards } from "lucide-react"

import { Button } from "@/components/ui/button"
import type { SessionUrls } from "@/auth/AuthPage"

export type FormRoutes = {
  detailApi: string | null
  optionsApi: string
  previewApi: string
  returnUrl: string
  deleteUrl: string | null
}

export type DeletionRoutes = { api: string; returnUrl: string }

export type AppUrls = SessionUrls & Record<"expenses" | "addExpense" | "deleteAllExpenses" | "analytics" | "categories" | "upload"
  | "expensesApi", string>

export type AppConfig = { urls: AppUrls; userId: number } & (
  | { screen: "expenses"; notices: string[] }
  | { screen: "analytics"; analyticsApi: string }
  | { screen: "expense-add" | "expense-edit"; form: FormRoutes }
  | { screen: "expense-delete" | "expense-delete-all"; deletion: DeletionRoutes }
  | { screen: "categories"; categoryList: CategoryListRoutes }
  | { screen: "category-add" | "category-edit" | "category-delete"; categoryAction: CategoryActionRoutes }
  | { screen: "category-sync" | "category-sync-result"; categorySync: CategorySyncRoutes }
  | { screen: "csv-upload" | "csv-import-result"; csvImport: CsvImportRoutes }
)

export type CategoryListRoutes = { api: string; addUrl: string; syncUrl: string; syncResultUrl: string; notices: string[] }
export type CategoryActionRoutes = { readApi: string; writeApi: string }
export type CategorySyncRoutes = { startUrl: string; resultUrl: string; startApi: string; latestApi: string }
export type CsvImportRoutes = { resultUrl: string; startApi: string; latestApi: string }

const titles = {
  expenses: "Expenses",
  analytics: "Analytics",
  "expense-add": "Add expense",
  "expense-edit": "Edit expense",
  "expense-delete": "Delete expense",
  "expense-delete-all": "Delete all expenses",
  categories: "Categories",
  "category-add": "Add category",
  "category-edit": "Edit category",
  "category-delete": "Delete category",
  "category-sync": "Sync existing expenses",
  "category-sync-result": "Category sync results",
  "csv-upload": "Upload CSV",
  "csv-import-result": "CSV import results",
}

export function AppHeader({ config, onSignOut }: { config?: AppConfig; onSignOut?: () => void }) {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"))
  const links = [
    { label: "Expenses", route: "expenses", icon: WalletCards },
    { label: "Analytics", route: "analytics", icon: BarChart3 },
    { label: "Categories", route: "categories", icon: Tags },
    { label: "Import", route: "upload", icon: Upload },
  ] as const

  function toggleTheme() {
    document.documentElement.classList.toggle("dark", !dark)
    localStorage.setItem("theme", dark ? "light" : "dark")
    setDark(!dark)
  }

  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="app-header">
        <div className={config ? "frame header-inner" : "frame flex min-h-16 items-center justify-between gap-2 py-2"}>
          {config ? <a className="brand" href={config.urls.expenses}>
            <Layers3 size={23} aria-hidden="true" />
            <span>Expense <strong>Tracker</strong></span>
          </a> : <span className="brand">
            <Layers3 size={23} aria-hidden="true" />
            <span>Expense <strong>Tracker</strong></span>
          </span>}
          {config && <nav aria-label="Main navigation">
            {links.map(({ label, route, icon: Icon }) => (
              <a key={route} href={config.urls[route]}
                aria-current={config.screen === route || (route === "upload" && "csvImport" in config) ? "page" : undefined}>
                <Icon className="hidden sm:block" size={16} aria-hidden="true" />
                {label}
              </a>
            ))}
          </nav>}
          <div className="header-actions">
            <Button type="button" variant="ghost" size="icon-lg" onClick={toggleTheme}
              aria-label="Dark mode" aria-pressed={dark}>
              {dark ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
            </Button>
            {onSignOut && <Button type="button" variant="ghost" onClick={onSignOut}>Sign out</Button>}
          </div>
        </div>
      </header>
    </>
  )
}

export function PageTitle({ screen }: { screen: AppConfig["screen"] }) {
  return <div className="page-title">
    <div>
      <p className="eyebrow">Personal ledger</p>
      <h1>{titles[screen]}</h1>
    </div>
  </div>
}

export function ReadFailure({ message, retry, reset, title = "Could not load expenses" }: {
  message: string; retry: () => void; reset?: string; title?: string
}) {
  return (
    <div className="notice" role="alert">
      <h2>{title}</h2>
      <p>{message || "Check your connection and try again."}</p>
      <div className="flex flex-wrap gap-2">
        <Button onClick={retry}>Retry</Button>
        {reset && <Button asChild variant="outline"><a href={reset}>Reset filters</a></Button>}
      </div>
    </div>
  )
}
