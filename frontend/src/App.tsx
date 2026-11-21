import { useEffect, useState } from "react"

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

  return (
    <Shell config={config} session={session}>
      {!session ? <SignInNotice login={config.urls.login} form={config.screen !== "expenses"} /> :
        config.screen === "expenses" ? <ExpensesPage urls={config.urls} notices={config.notices} userId={config.userId} /> :
        <ExpenseFormPage routes={config.form} urls={config.urls} userId={config.userId}
          session={session} onSessionChange={setSession} />}
    </Shell>
  )
}

export function App({ config }: { config: AppConfig }) {
  const { result, retry } = useRead<Session>(config.urls.sessionApi)
  const isForm = config.screen !== "expenses"
  if (result.state === "ready" && result.data.user?.id === config.userId) {
    return <SignedInApp config={config} initialSession={result.data} />
  }
  return (
    <Shell config={config} session={null}>
      {result.state === "loading" ? (isForm ? <LoadingExpenseForm /> : <LoadingExpenses />) :
        result.state === "error" ? <ReadFailure title={isForm ? "Could not open the expense form" : undefined}
          message={result.message} retry={retry} /> :
        <SignInNotice login={config.urls.login} form={isForm} />}
    </Shell>
  )
}
