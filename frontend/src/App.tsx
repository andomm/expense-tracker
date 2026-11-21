import { ExpensesPage, LoadingExpenses } from "./expenses/ExpensesPage"
import { ReadFailure, Shell, SignInNotice, type AppConfig } from "./Shell"
import { useRead, type Session } from "./lib/api"

export function App({ config }: { config: AppConfig }) {
  const { result, retry } = useRead<Session>(config.urls.sessionApi)
  const session = result.state === "ready" ? result.data : null
  return (
    <Shell config={config} session={session}>
      {result.state === "loading" ? <LoadingExpenses /> :
        result.state === "error" ? <ReadFailure message={result.message} retry={retry} /> :
        !result.data.user ? <SignInNotice login={config.urls.login} /> :
        <ExpensesPage urls={config.urls} />}
    </Shell>
  )
}
