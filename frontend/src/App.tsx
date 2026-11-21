import { useEffect, useState } from "react"

import { CategoriesPage, LoadingCategories } from "./categories/CategoriesPage"
import { CategoryActionPage } from "./categories/CategoryActionPage"
import { CategorySyncPage, CategorySyncResultPage, LoadingSync } from "./categories/CategorySyncPage"
import { ExpenseDeletePage, LoadingExpenseDeletion } from "./expenses/ExpenseDeletePage"
import { ExpenseFormPage, LoadingExpenseForm } from "./expenses/ExpenseFormPage"
import { ExpensesPage, LoadingExpenses } from "./expenses/ExpensesPage"
import { ReadFailure, Shell, SignInNotice, type AppConfig } from "./Shell"
import { readJson, useRead, type Session } from "./lib/api"

function SignedInApp({ config, initialSession }: { config: AppConfig; initialSession: Session }) {
  const [session, setSession] = useState<Session | null>(initialSession)
  // A different tab can end the session while this page is hidden.
  useEffect(() => {
    let check: AbortController | undefined
    const revalidate = () => {
      check?.abort()
      if (document.visibilityState !== "visible") return
      const controller = new AbortController()
      check = controller
      void readJson<Session>(config.urls.sessionApi, controller.signal).then((current) => {
        if (!controller.signal.aborted && current.user?.id !== config.userId) setSession(null)
      }).catch(() => { /* Protected requests still check the session. */ })
    }
    document.addEventListener("visibilitychange", revalidate)
    return () => {
      check?.abort()
      document.removeEventListener("visibilitychange", revalidate)
    }
  }, [config.urls.sessionApi, config.userId])

  let content
  if (!session) {
    content = <ScreenSignIn config={config} />
  } else if (config.screen === "expenses") {
    content = <ExpensesPage urls={config.urls} notices={config.notices} userId={config.userId} />
  } else if ("categoryList" in config) {
    content = <CategoriesPage routes={config.categoryList} login={config.urls.login} userId={config.userId} />
  } else if ("categoryAction" in config) {
    content = <CategoryActionPage routes={config.categoryAction} screen={config.screen} urls={config.urls}
      userId={config.userId} session={session} onSessionChange={setSession} />
  } else if ("categorySync" in config) {
    content = config.screen === "category-sync" ?
      <CategorySyncPage routes={config.categorySync} urls={config.urls} userId={config.userId}
        session={session} onSessionChange={setSession} /> :
      <CategorySyncResultPage routes={config.categorySync} urls={config.urls} userId={config.userId} />
  } else if ("deletion" in config) {
    content = <ExpenseDeletePage routes={config.deletion} allExpenses={config.screen === "expense-delete-all"}
      urls={config.urls} userId={config.userId} session={session} onSessionChange={setSession} />
  } else {
    content = <ExpenseFormPage routes={config.form} urls={config.urls} userId={config.userId}
      session={session} onSessionChange={setSession} />
  }

  return <Shell config={config} session={session}>{content}</Shell>
}

function ScreenSignIn({ config }: { config: AppConfig }) {
  return <SignInNotice login={config.urls.login}
    categories={"categoryList" in config || "categoryAction" in config}
    sync={"categorySync" in config}
    form={"form" in config || ("categoryAction" in config && config.screen !== "category-delete")}
    deletion={"deletion" in config || config.screen === "category-delete"} />
}

export function App({ config }: { config: AppConfig }) {
  const { result, retry } = useRead<Session>(config.urls.sessionApi)
  const categories = "categoryList" in config || "categoryAction" in config
  const sync = "categorySync" in config
  const loading = sync ? <LoadingSync result={config.screen === "category-sync-result"} /> :
    categories ? <LoadingCategories /> : "deletion" in config ? <LoadingExpenseDeletion /> :
    "form" in config ? <LoadingExpenseForm /> : <LoadingExpenses />
  const errorTitle = sync ? "Could not open category sync" :
    categories ? "Could not open Categories" : "deletion" in config ? "Could not open the confirmation" :
    "form" in config ? "Could not open the expense form" : undefined
  if (result.state === "ready" && result.data.user?.id === config.userId) {
    return <SignedInApp config={config} initialSession={result.data} />
  }
  return (
    <Shell config={config} session={null}>
      {result.state === "loading" ? loading :
        result.state === "error" ? <ReadFailure title={errorTitle} message={result.message} retry={retry} /> :
        <ScreenSignIn config={config} />}
    </Shell>
  )
}
