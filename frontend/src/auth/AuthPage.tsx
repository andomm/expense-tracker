import { ArrowRight, ShieldCheck } from "lucide-react"
import { useEffect, useRef, useState, type FormEvent } from "react"

import { AppHeader, ReadFailure } from "@/Shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Field, Messages } from "@/components/ui/form-field"
import { Input } from "@/components/ui/input"
import { ApiError, readJson, submitAuth, useRead, type AuthResult, type FieldErrors, type Session } from "@/lib/api"

import { notifySignIn } from "./session-events"

export type SessionUrls = Record<"login" | "signup" | "sessionApi" | "loginApi" | "signupApi" | "logoutApi", string>
export type AuthConfig = { screen: "login" | "signup"; urls: SessionUrls; next: string }

export function AuthCard({ urls, next, session, signup = false, inline = false, retained = false, onSuccess, onRefresh }: {
  urls: SessionUrls; next: string; session: Session; signup?: boolean; inline?: boolean; retained?: boolean
  onSuccess: (result: AuthResult) => void; onRefresh: (session: Session) => void
}) {
  const form = useRef<HTMLFormElement>(null)
  const request = useRef<AbortController | null>(null)
  const title = useRef<HTMLHeadingElement>(null)
  const feedback = useRef<HTMLDivElement>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<{ message: string; fields?: FieldErrors }>()
  const [current, setCurrent] = useState(session)
  const label = signup ? "Create account" : "Sign in"
  const target = signup ? urls.signupApi : urls.loginApi
  const switchUrl = `${signup ? urls.login : urls.signup}?${new URLSearchParams({ next })}`

  useEffect(() => {
    title.current?.focus()
    function clearCredentials() { form.current?.reset() }
    window.addEventListener("pagehide", clearCredentials)
    return () => {
      request.current?.abort()
      window.removeEventListener("pagehide", clearCredentials)
    }
  }, [])
  useEffect(() => {
    if (error) (form.current?.querySelector<HTMLElement>('[aria-invalid="true"]') ?? feedback.current)?.focus()
  }, [error])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (request.current) return
    const data = new FormData(event.currentTarget)
    const credentials = { ...Object.fromEntries(data), next }
    // A rejected attempt never leaves passwords in the rendered form.
    event.currentTarget.querySelectorAll<HTMLInputElement>('input[type="password"]').forEach((input) => { input.value = "" })
    const controller = new AbortController()
    request.current = controller
    setPending(true)
    setError(undefined)
    try {
      const result = await submitAuth(target, current, credentials, controller.signal)
      if (!controller.signal.aborted) {
        notifySignIn()
        onSuccess(result)
      }
    } catch (failure) {
      if (controller.signal.aborted) return
      if (failure instanceof ApiError && failure.needsSessionCheck) {
        try {
          const fresh = await readJson<Session>(urls.sessionApi, controller.signal)
          if (controller.signal.aborted) return
          setCurrent(fresh)
          onRefresh(fresh)
          setError({ message: "Your session changed. Enter your password and try again." })
        } catch {
          if (!controller.signal.aborted) setError({ message: "Could not verify your session. Reload or try again." })
        }
      } else if (failure instanceof ApiError && failure.status === 422) {
        setError({ message: failure.message, fields: failure.body?.fields })
      } else {
        setError({ message: "Could not confirm the result. Check your connection and try again." })
      }
    } finally {
      request.current = null
      if (!controller.signal.aborted) setPending(false)
    }
  }

  return <Card className="mx-auto w-full max-w-md gap-0 overflow-hidden py-0 shadow-none">
    <CardHeader className="gap-3 border-b bg-accent/45 px-5 py-6 sm:px-7">
      <div className="flex items-center gap-2 text-xs font-bold tracking-widest text-primary uppercase">
        <ShieldCheck className="size-5 shrink-0" aria-hidden="true" /> Personal ledger
      </div>
      <h1 ref={title} tabIndex={-1} className="text-2xl font-extrabold tracking-tight outline-none sm:text-3xl">
        {inline ? "Sign in again" : label}
      </h1>
      <p className="text-sm leading-relaxed text-muted-foreground">
        {inline ? retained ? "Your session ended. Sign in to the same account to return to this page with any unsaved input. Nothing will be submitted automatically."
          : "Your session ended. Sign in to reopen this page. Nothing will be submitted automatically."
          : signup ? "Start a private ledger for your income and expenses." : "Open your ledger to track expenses and see where your money goes."}
      </p>
    </CardHeader>
    <CardContent className="grid gap-5 px-5 py-6 sm:px-7">
      <form ref={form} method="post" aria-label={label} onSubmit={submit} className="grid gap-4">
        {error && <div ref={feedback} tabIndex={-1} role="alert" className="grid gap-1 rounded-lg border border-destructive/40 p-3 text-sm">
          <p className="font-bold">{error.message}</p>
          <Messages errors={error.fields?.form} />
        </div>}
        <fieldset disabled={pending} className="grid min-w-0 gap-4">
          <Field id="auth-username" label="Username" errors={error?.fields?.username}>
            {(control) => <Input {...control} name="username" autoComplete="username" required maxLength={150}
              autoCapitalize="none" spellCheck={false} className="h-11" />}
          </Field>
          <Field id="auth-password" label="Password" errors={error?.fields?.[signup ? "password1" : "password"]}>
            {(control) => <Input {...control} name={signup ? "password1" : "password"} type="password" required
              autoComplete={signup ? "new-password" : "current-password"} className="h-11" />}
          </Field>
          {signup && <Field id="auth-confirm" label="Confirm password" errors={error?.fields?.password2}>
            {(control) => <Input {...control} name="password2" type="password" required autoComplete="new-password" className="h-11" />}
          </Field>}
          <Button type="submit" className="h-11 w-full" disabled={pending}>
            {pending ? signup ? "Creating account…" : "Signing in…" : label}<ArrowRight aria-hidden="true" />
          </Button>
        </fieldset>
        {pending && <p role="status" className="sr-only">{signup ? "Creating account" : "Signing in"}</p>}
      </form>
      {!inline && <p className="border-t pt-4 text-sm text-muted-foreground">
        {signup ? "Already have an account?" : "New to Expense Tracker?"}{" "}
        <a className="font-bold text-primary underline underline-offset-4" href={switchUrl}>{signup ? "Sign in" : "Create account"}</a>
      </p>}
    </CardContent>
  </Card>
}

export function AuthPage({ config }: { config: AuthConfig }) {
  const { result, retry } = useRead<Session>(config.urls.sessionApi)
  return <>
    <AppHeader />
    <main id="main" className="frame app-main pt-8 sm:pt-16" tabIndex={-1}>
      {result.state === "ready" ? <AuthCard {...config} signup={config.screen === "signup"} session={result.data}
        onSuccess={({ next }) => window.location.replace(next)} onRefresh={() => {}} /> :
        result.state === "error" ? <ReadFailure title="Could not open the sign-in page" message="" retry={retry} /> :
        <p className="notice" role="status">Checking your session…</p>}
    </main>
  </>
}
