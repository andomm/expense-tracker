import { lazy, Suspense, useEffect, useRef } from "react"

import { LoadingAnalytics } from "./analytics/LoadingAnalytics"
import { ProtectedAccess } from "./auth/access"
import { AuthCard } from "./auth/AuthPage"
import { useSessionGate } from "./auth/useSessionGate"
import { CategoriesPage } from "./categories/CategoriesPage"
import { CategoryActionPage } from "./categories/CategoryActionPage"
import { CategorySyncPage, CategorySyncResultPage } from "./categories/CategorySyncPage"
import { ExpenseDeletePage } from "./expenses/ExpenseDeletePage"
import { ExpenseFormPage } from "./expenses/ExpenseFormPage"
import { ExpensesPage } from "./expenses/ExpensesPage"
import { ImportResultPage } from "./imports/ImportResultPage"
import { UploadPage } from "./imports/UploadPage"
import { AppHeader, PageTitle, ReadFailure, type AppConfig } from "./Shell"
import type { Session } from "./lib/api"

const AnalyticsPage = lazy(() => import("./analytics/AnalyticsPage"))

function ProtectedScreen({ config, session }: { config: AppConfig; session: Session }) {
  const { urls, userId } = config
  if (config.screen === "analytics") {
    return <Suspense fallback={<LoadingAnalytics />}>
      <AnalyticsPage api={config.analyticsApi} userId={userId} />
    </Suspense>
  }
  if (config.screen === "expenses") {
    return <ExpensesPage urls={urls} notices={config.notices} userId={userId} session={session} />
  }
  if ("categoryList" in config) {
    return <CategoriesPage routes={config.categoryList} userId={userId} />
  }
  if ("categoryAction" in config) {
    return <CategoryActionPage routes={config.categoryAction} screen={config.screen} urls={urls} userId={userId} session={session} />
  }
  if ("categorySync" in config) {
    return config.screen === "category-sync" ?
      <CategorySyncPage routes={config.categorySync} urls={urls} userId={userId} session={session} /> :
      <CategorySyncResultPage routes={config.categorySync} urls={urls} userId={userId} />
  }
  if ("csvImport" in config) {
    return config.screen === "csv-upload" ?
      <UploadPage routes={config.csvImport} urls={urls} userId={userId} session={session} /> :
      <ImportResultPage routes={config.csvImport} urls={urls} userId={userId} />
  }
  if ("deletion" in config) {
    return <ExpenseDeletePage routes={config.deletion} allExpenses={config.screen === "expense-delete-all"}
      userId={userId} session={session} />
  }
  return <ExpenseFormPage routes={config.form} urls={urls} userId={userId} session={session} />
}

export function App({ config }: { config: AppConfig }) {
  const keepsDraft = "form" in config || ["category-add", "category-edit", "csv-upload"].includes(config.screen)
  const { gate, ownerSession, readVersion, resumed, logoutError, revalidate, accept, signOut } = useSessionGate(config, keepsDraft)
  const active = gate.kind === "active"
  const main = useRef<HTMLElement>(null)
  useEffect(() => {
    if (active && resumed) main.current?.focus()
  }, [active, resumed])

  return <>
    <AppHeader config={active ? config : undefined} onSignOut={active ? signOut : undefined} />
    <main id="main" ref={main} className="frame app-main" tabIndex={-1}>
      {gate.kind === "expired" ?
        <AuthCard urls={config.urls} next={location.pathname + location.search} session={gate.session} inline
          retained={Boolean(ownerSession)} onSuccess={accept} onRefresh={accept} /> :
        gate.kind === "unavailable" ? <ReadFailure title="Could not verify your session" message="Your ledger is hidden until we can check your session."
          retry={revalidate} /> : !active &&
          <p className="notice" role="status">{gate.kind === "signing-out" ? "Signing out…" : "Checking your session…"}</p>}
      <div hidden={!active} inert={!active}>
        {ownerSession && <ProtectedAccess.Provider value={{ active, readVersion }}>
          <PageTitle screen={config.screen} />
          {logoutError && <p className="notice mb-4" role="alert">Could not confirm sign-out. Your session is still active. Try signing out again.</p>}
          {resumed && <p className="notice mb-4" role="status">You’re signed in again. Review your entries before submitting. Nothing was submitted for you.</p>}
          <ProtectedScreen config={config} session={ownerSession} />
        </ProtectedAccess.Provider>}
      </div>
    </main>
  </>
}
