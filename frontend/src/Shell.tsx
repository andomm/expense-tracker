import { useState, type ReactNode } from "react"
import { BarChart3, Layers3, Moon, Sun, Tags, Upload, WalletCards } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { Session } from "@/lib/api"

export type FormRoutes = {
  detailApi: string | null
  optionsApi: string
  previewApi: string
  returnUrl: string
  deleteUrl: string | null
}

export type DeletionRoutes = { api: string; returnUrl: string }

export type AppUrls = Record<"expenses" | "addExpense" | "analytics" | "categories" | "upload"
  | "login" | "logout" | "sessionApi" | "expensesApi", string>

export type AppConfig = { urls: AppUrls; userId: number } & (
  | { screen: "expenses"; notices: string[]; deleteAllUrl: string }
  | { screen: "expense-add" | "expense-edit"; form: FormRoutes }
  | { screen: "expense-delete" | "expense-delete-all"; deletion: DeletionRoutes }
)

const titles = {
  expenses: "Expenses",
  "expense-add": "Add expense",
  "expense-edit": "Edit expense",
  "expense-delete": "Delete expense",
  "expense-delete-all": "Delete all expenses",
}

export function signInHref(login: string) {
  return `${login}?${new URLSearchParams({ next: location.pathname + location.search })}`
}

export function Shell({ config, session, children }: {
  config: AppConfig
  session: Session | null
  children: ReactNode
}) {
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
        <div className="frame header-inner">
          <a className="brand" href={config.urls.expenses}>
            <Layers3 size={23} aria-hidden="true" />
            <span>Expense <strong>Tracker</strong></span>
          </a>
          <nav aria-label="Main navigation">
            {links.map(({ label, route, icon: Icon }) => (
              <a key={route} href={config.urls[route]} aria-current={config.screen === route ? "page" : undefined}>
                <Icon className="hidden sm:block" size={16} aria-hidden="true" />
                {label}
              </a>
            ))}
          </nav>
          <div className="header-actions">
            <Button type="button" variant="ghost" size="icon-lg" onClick={toggleTheme}
              aria-label="Dark mode" aria-pressed={dark}>
              {dark ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
            </Button>
            {session?.user && (
              <form action={config.urls.logout} method="post">
                <input type="hidden" name="csrfmiddlewaretoken" value={session.csrf_token} />
                <Button type="submit" variant="ghost">Sign out</Button>
              </form>
            )}
          </div>
        </div>
      </header>
      <main id="main" className="frame app-main" tabIndex={-1}>
        <div className="page-title">
          <div>
            <p className="eyebrow">Personal ledger</p>
            <h1>{titles[config.screen]}</h1>
          </div>
          <Badge variant="secondary" className="gap-2 px-3 py-1">
            <span className="size-1.5 rounded-full bg-primary" aria-hidden="true" /> Expenses pilot
          </Badge>
        </div>
        {children}
      </main>
    </>
  )
}

export function SignInNotice({ login, form = false, deletion = false }: {
  login: string; form?: boolean; deletion?: boolean
}) {
  return (
    <div className="notice" role="alert">
      <h2>Sign in to see your expenses</h2>
      <p>{deletion
        ? "Your session ended or changed. Sign in to review the deletion again. Nothing will be sent automatically."
        : form
        ? "Your session ended or changed. Sign in again to reopen this page. Unsaved changes will not be restored or sent."
        : "Your session ended or changed. Sign in again to return to these filters."}</p>
      <Button asChild><a href={signInHref(login)}>Sign in</a></Button>
    </div>
  )
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
