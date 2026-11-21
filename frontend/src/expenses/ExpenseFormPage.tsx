import { AlertTriangle, Plus, X } from "lucide-react"
import { AlertDialog } from "radix-ui"
import { useEffect, useRef, useState, type FormEvent } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ApiError, readJson, useRead, writeJson, type FieldErrors, type Session } from "@/lib/api"
import { ReadFailure, SignInNotice, type AppUrls, type FormRoutes } from "@/Shell"

import { ChoiceInput, ExpenseFields, Field, Messages } from "./ExpenseFields"
import { emptyDraft, saveFields, useAmountPreview, type Draft, type ExpenseDetail, type FormOptions, type MainFields } from "./form"
import { euro } from "./read"

type FormPageProps = {
  routes: FormRoutes
  urls: AppUrls
  userId: number
  session: Session
  onSessionChange: (session: Session | null) => void
}

export function LoadingExpenseForm() {
  return <div className="notice" role="status"><p>Loading expense form…</p></div>
}

export function ExpenseFormPage(props: FormPageProps) {
  const { routes, urls, userId } = props
  const options = useRead<FormOptions>(routes.optionsApi, userId)
  const detail = useRead<ExpenseDetail>(routes.detailApi, userId)
  const reads = routes.detailApi ? [options, detail] : [options]
  const back = <Button asChild variant="outline"><a href={routes.returnUrl}>Back to expenses</a></Button>

  if (reads.some(({ result }) => result.state === "error" && result.status === 401)) {
    return <SignInNotice login={urls.login} form />
  }
  if (detail.result.state === "error" && detail.result.status === 404) {
    return <div className="notice" role="alert"><h2>This expense is no longer available</h2>{back}</div>
  }
  const failure = reads.find(({ result }) => result.state === "error")
  if (failure?.result.state === "error") {
    return <div className="grid justify-items-start gap-3">
      <ReadFailure title="Could not open the expense form" message={failure.result.message} retry={failure.retry} />
      {back}
    </div>
  }
  if (options.result.state !== "ready" || (routes.detailApi && detail.result.state !== "ready")) {
    return <LoadingExpenseForm />
  }
  let initial = emptyDraft
  if (detail.result.state === "ready") {
    const { date, receiver, description, amount, category_id, share_rule_id } = detail.result.data
    initial = { date, receiver, description, amount, category_id, share_rule_id, splits: [] }
  }
  return <ExpenseEditor {...props} initial={initial} options={options.result.data} />
}

function AmountPreviewCard({ preview, pending }: { preview: ReturnType<typeof useAmountPreview>; pending: boolean }) {
  const figures = preview.state === "ready" ? preview.data : null
  return (
    <Card role="region" aria-labelledby="preview-title"
      className="expense-preview gap-4 border-transparent bg-[var(--balance)] py-4 text-[var(--balance-text)] shadow-none sm:py-5">
      <CardHeader className="px-4 sm:px-5">
        <h2 id="preview-title">Amount preview</h2>
        <p className="small-note">Calculated from this draft. Nothing is saved yet.</p>
      </CardHeader>
      <CardContent className="px-4 sm:px-5">
        <dl aria-live="polite">
          {([
            ["Full amount", figures?.amount], ["Your share", figures?.personal_share],
            ["Split total", figures?.split_total], ["Remaining amount", figures?.remaining],
          ] as const).map(([label, amount]) => <div key={label}>
            <dt>{label}</dt><dd className="money">{amount == null ? "—" : euro(amount)}</dd>
          </div>)}
        </dl>
        {preview.state === "loading" && !pending && <p className="small-note mt-3" role="status">Updating preview…</p>}
        {preview.state === "error" && <p className="small-note mt-3" role="status">Preview unavailable. Amounts will still be checked when you save.</p>}
      </CardContent>
    </Card>
  )
}

type Failure = { kind: "validation" | "rejected" | "unknown" | "check" | "missing"; message: string }
type Split = Draft["splits"][number]

function ExpenseEditor({ routes, urls, userId, session, onSessionChange, initial, options }: FormPageProps & {
  initial: Draft; options: FormOptions
}) {
  const [draft, setDraft] = useState(initial)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [failure, setFailure] = useState<Failure | null>(null)
  const [pending, setPending] = useState<"save" | "session" | null>(null)
  const [leaveTarget, setLeaveTarget] = useState<string | null>(null)
  const request = useRef<AbortController | null>(null)
  const leave = useRef(false)
  const leaveTrigger = useRef<HTMLButtonElement | null>(null)
  const formElement = useRef<HTMLFormElement>(null)
  const feedback = useRef<HTMLDivElement>(null)
  const addSplitButton = useRef<HTMLButtonElement>(null)
  const splitKey = useRef(0)
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial)
  const preview = useAmountPreview(draft, routes.previewApi, session.csrf_token, userId, onSessionChange, Boolean(pending))

  useEffect(() => () => request.current?.abort(), [])
  useEffect(() => {
    if (!failure) return
    const firstInvalid = failure.kind === "validation"
      ? formElement.current?.querySelector<HTMLElement>('[aria-invalid="true"], #split-errors')
      : null
    const focusTarget = firstInvalid ?? feedback.current
    focusTarget?.focus()
  }, [failure])
  useEffect(() => {
    if (!dirty && !pending) return
    const warn = (event: BeforeUnloadEvent) => {
      if (leave.current) return
      event.preventDefault()
      event.returnValue = true
    }
    window.addEventListener("beforeunload", warn)
    return () => window.removeEventListener("beforeunload", warn)
  }, [dirty, pending])

  function clearErrors(...names: string[]) {
    setErrors((current) => Object.fromEntries(Object.entries(current).filter(([name]) => !names.includes(name))))
  }

  function change<K extends keyof MainFields>(name: K, value: MainFields[K]) {
    setDraft((current) => ({ ...current, [name]: value }))
    clearErrors(name, ...(name === "amount" ? ["category_id", "splits"] : []))
  }

  function updateSplit(index: number, values: Partial<Omit<Split, "key">>) {
    setDraft((current) => ({ ...current, splits: current.splits.map((part, i) => i === index ? { ...part, ...values } : part) }))
    clearErrors("splits", "category_id", ...Object.keys(values).map((name) => `splits[${index}].${name}`))
  }

  function addSplit() {
    const key = ++splitKey.current
    setDraft((current) => ({ ...current, splits: [...current.splits, { key, amount: "", category_id: null }] }))
    requestAnimationFrame(() => document.getElementById(`split-${key}-amount`)?.focus())
  }

  function removeSplit(index: number) {
    setDraft((current) => ({ ...current, splits: current.splits.filter((_, i) => i !== index) }))
    // API errors use array positions. Do not carry them onto a different row.
    setErrors((current) => Object.fromEntries(Object.entries(current)
      .filter(([name]) => name !== "category_id" && !name.startsWith("splits"))))
    requestAnimationFrame(() => addSplitButton.current?.focus())
  }

  async function checkSession(signal: AbortSignal) {
    try {
      const current = await readJson<Session>(urls.sessionApi, signal)
      if (signal.aborted) return
      if (current.user?.id !== userId) {
        onSessionChange(null)
        return
      }
      onSessionChange(current)
      setFailure({ kind: "rejected", message: "The save was blocked. Your session is ready now. Review your entries and choose Save expense again." })
    } catch {
      if (!signal.aborted) setFailure({ kind: "check", message: "Could not confirm your session. Nothing was sent again. Check your session before trying to save." })
    }
  }

  async function run(action: "save" | "session") {
    if (request.current) return
    const controller = new AbortController()
    const { signal } = controller
    request.current = controller
    setPending(action)
    setFailure(null)
    try {
      if (action === "session") {
        await checkSession(signal)
        return
      }
      setErrors({})
      await writeJson(routes.detailApi ?? urls.expensesApi, {
        method: routes.detailApi ? "PUT" : "POST", csrfToken: session.csrf_token,
        userId, body: saveFields(draft), signal,
      })
      if (signal.aborted) return
      leave.current = true
      window.location.replace(routes.returnUrl)
      return
    } catch (error) {
      if (signal.aborted) return
      if (error instanceof ApiError && error.status === 401) {
        onSessionChange(null)
      } else if (error instanceof ApiError && error.needsSessionCheck) {
        setPending("session")
        await checkSession(signal)
      } else if (error instanceof ApiError && error.status === 422) {
        const fields = error.body?.fields ?? {}
        setErrors(fields)
        setFailure({
          kind: Object.keys(fields).length ? "validation" : "rejected",
          message: error.message || "Check the highlighted fields.",
        })
      } else if (error instanceof ApiError && error.status === 404) {
        setFailure({ kind: "missing", message: "This expense is no longer available." })
      } else if (error instanceof ApiError && error.status < 500) {
        setFailure({ kind: "rejected", message: error.message || "The save was rejected. Check your entries and try again." })
      } else {
        setFailure({ kind: "unknown", message: "The save result is unknown. Check Expenses before trying again to avoid creating a duplicate." })
      }
    } finally {
      if (!signal.aborted && !leave.current) {
        request.current = null
        setPending(null)
      }
    }
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (failure?.kind !== "check" && failure?.kind !== "missing") void run("save")
  }

  function navigate(url: string) {
    leave.current = true
    window.location.assign(url)
  }

  function prepareToLeave(url: string, trigger: HTMLButtonElement) {
    if (request.current) return
    if (!dirty) {
      navigate(url)
      return
    }
    leaveTrigger.current = trigger
    setLeaveTarget(url)
  }

  const missing = failure?.kind === "missing"
  const checking = failure?.kind === "check"
  const showFailure = failure && (failure.kind !== "validation" || Object.keys(errors).length > 0)
  const form = (
    <form ref={formElement} aria-label={routes.detailApi ? "Edit expense" : "Add expense"} onSubmit={save} noValidate>
      {showFailure && <div className="expense-feedback" ref={feedback} tabIndex={-1} role="alert">
        <p className="font-bold">{failure.message}</p>
        <Messages errors={errors.form} />
        {failure.kind === "unknown" && <a className="text-sm font-bold underline" href={routes.returnUrl}
          target="_blank" rel="noopener">Check expenses in a new tab</a>}
        {checking && <Button type="button" variant="outline" onClick={() => void run("session")}>Check session</Button>}
      </div>}
      <fieldset className="expense-editor" disabled={Boolean(pending)}>
        <Card className="gap-4 py-4 shadow-none sm:py-5">
          <CardHeader className="px-4 sm:px-5"><h2>Expense details</h2></CardHeader>
          <CardContent className="px-4 sm:px-5"><ExpenseFields draft={draft} options={options} errors={errors} change={change} /></CardContent>
        </Card>
        <Card className="gap-4 py-4 shadow-none sm:py-5">
          <CardHeader className="px-4 sm:px-5">
            <h2>Split into categories</h2>
            <p className="small-note">Enter positive amounts. Each part saves as a separate expense. Any remainder stays in the main category.</p>
          </CardHeader>
          <CardContent className="grid justify-items-start gap-3 px-4 sm:px-5">
            {errors.splits && <div id="split-errors" tabIndex={-1}><Messages errors={errors.splits} /></div>}
            {draft.splits.map(({ key, amount, category_id }, index) => (
              <fieldset key={key} className="expense-split-row">
                <legend className="px-1 text-xs font-bold text-muted-foreground">Split {index + 1}</legend>
                <div>
                  <Field id={`split-${key}-amount`} label="Split amount (€)" errors={errors[`splits[${index}].amount`]}>
                    {(props) => <Input {...props} inputMode="decimal" required value={amount}
                      onChange={(event) => updateSplit(index, { amount: event.target.value })} />}
                  </Field>
                  <Field id={`split-${key}-category`} label="Split category" errors={errors[`splits[${index}].category_id`]}>
                    {(props) => <ChoiceInput {...props} choices={options.categories} value={category_id}
                      emptyLabel="Choose a category" onChange={(value) => updateSplit(index, { category_id: value })} />}
                  </Field>
                  <Button type="button" variant="ghost" aria-label={`Remove split ${index + 1}`}
                    onClick={() => removeSplit(index)}><X aria-hidden="true" /> Remove</Button>
                </div>
              </fieldset>
            ))}
            {options.categories.length === 0 && <p className="small-note">Add categories before splitting an expense.</p>}
            <Button type="button" variant="outline" ref={addSplitButton} onClick={addSplit}
              disabled={!options.categories.length || draft.splits.length >= options.max_splits}>
              <Plus aria-hidden="true" /> Add split row
            </Button>
          </CardContent>
        </Card>
        <AmountPreviewCard preview={preview} pending={Boolean(pending)} />
        <div className="expense-actions">
          <Button type="submit" disabled={checking || missing || Boolean(pending)}>
            {pending === "save" ? "Saving…" : pending === "session" ? "Checking session…" : "Save expense"}
          </Button>
          <Button type="button" variant="outline" onClick={(event) => prepareToLeave(routes.returnUrl, event.currentTarget)}>
            Cancel
          </Button>
          {pending && <span role="status" className="sr-only">
            {pending === "save" ? "Saving expense" : "Checking your session"}
          </span>}
        </div>
      </fieldset>
    </form>
  )

  const deleteUrl = routes.deleteUrl
  return (
    <AlertDialog.Root open={leaveTarget !== null} onOpenChange={(open) => { if (!open) setLeaveTarget(null) }}>
      {form}
      {deleteUrl && !missing && (
        <section aria-labelledby="expense-delete-title" className="mt-6 grid justify-items-start gap-2 border-t pt-4">
          <h2 id="expense-delete-title" className="font-extrabold">Remove this expense</h2>
          <p className="text-sm text-muted-foreground">Review this expense before permanently deleting it.</p>
          <Button type="button" variant="outline" className="h-11 text-destructive hover:text-destructive"
            disabled={Boolean(pending)} onClick={(event) => prepareToLeave(deleteUrl, event.currentTarget)}>
            Delete expense
          </Button>
        </section>
      )}
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-20 bg-black/50" />
        <AlertDialog.Content className="expense-discard" onCloseAutoFocus={(event) => {
          event.preventDefault()
          if (!leave.current) leaveTrigger.current?.focus()
        }}>
          <AlertDialog.Title className="flex items-center gap-2 text-lg font-extrabold">
            <AlertTriangle className="size-5 text-destructive" aria-hidden="true" /> Discard unsaved changes?
          </AlertDialog.Title>
          <AlertDialog.Description className="text-sm text-muted-foreground">
            {leaveTarget === deleteUrl
              ? "Your changes will be lost. Continue to review the deletion without saving?"
              : "Your changes will be lost. Return to Expenses without saving?"}
          </AlertDialog.Description>
          <div className="flex flex-wrap gap-2">
            <AlertDialog.Cancel asChild><Button variant="outline">Keep editing</Button></AlertDialog.Cancel>
            <AlertDialog.Action asChild>
              <Button variant="destructive" onClick={() => { if (leaveTarget) navigate(leaveTarget) }}>Discard changes</Button>
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}
