import { AlertTriangle } from "lucide-react"
import { AlertDialog } from "radix-ui"
import { useEffect, useRef, useState, type FormEvent, type RefObject } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Field, Messages } from "@/components/ui/form-field"
import { Input } from "@/components/ui/input"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { ApiError, readJson, useRead, writeJson, type FieldErrors, type Session } from "@/lib/api"
import { ReadFailure, SignInNotice, type AppUrls, type CategoryActionRoutes } from "@/Shell"

import { LoadingCategories } from "./CategoriesPage"

type Draft = { name: string; category_type: string; parent_id: number | null; keywords: string }
type CategoryDetail = Draft & {
  parent_choices: { id: number; label: string }[]
  category_types: { id: string; label: string }[]
  max_depth: number
}

type Props = {
  routes: CategoryActionRoutes
  screen: "category-add" | "category-edit" | "category-delete"
  urls: AppUrls
  userId: number
  session: Session
  onSessionChange: (session: Session | null) => void
}

type Failure = { kind: "rejected" | "check-session" | "unknown" | "missing"; message: string; fields?: FieldErrors }
type Action = { kind: "save"; draft: Draft } | { kind: "delete" } | { kind: "session" }

function useCategoryWrite({ routes, screen, urls, userId, session, onSessionChange }: Props) {
  const request = useRef<AbortController | null>(null)
  const leaving = useRef(false)
  const [pending, setPending] = useState<"write" | "session" | null>(null)
  const [failure, setFailure] = useState<Failure | null>(null)
  const deleting = screen === "category-delete"
  useEffect(() => () => request.current?.abort(), [])

  function goBack(replace = false) {
    leaving.current = true
    if (replace) window.location.replace(urls.categories)
    else window.location.assign(urls.categories)
  }

  async function checkSession(signal: AbortSignal) {
    setPending("session")
    try {
      const current = await readJson<Session>(urls.sessionApi, signal)
      if (signal.aborted) return
      if (current.user?.id !== userId) {
        onSessionChange(null)
        return
      }
      onSessionChange(current)
      setFailure({ kind: "rejected", message: deleting
        ? "Deletion was blocked. Your session is ready. Review the category and confirm again if you still want to delete it."
        : "Save was blocked. Your session is ready. Review your entries and choose Save category again." })
    } catch {
      if (!signal.aborted) setFailure({ kind: "check-session", message: "Could not check your session. Nothing was sent again. Check your session or cancel." })
    }
  }

  async function run(action: Action) {
    if (request.current) return
    const controller = new AbortController()
    const { signal } = controller
    request.current = controller
    setFailure(null)
    try {
      if (action.kind === "session") {
        await checkSession(signal)
        return
      }
      setPending("write")
      const options = { csrfToken: session.csrf_token, userId, signal }
      if (action.kind === "delete") await writeJson(routes.writeApi, { ...options, method: "DELETE" })
      else await writeJson(routes.writeApi, { ...options, method: screen === "category-add" ? "POST" : "PUT", body: action.draft })
      if (!signal.aborted) goBack(true)
    } catch (error) {
      if (signal.aborted) return
      if (error instanceof ApiError && error.status === 401) onSessionChange(null)
      else if (error instanceof ApiError && error.needsSessionCheck) await checkSession(signal)
      else if (error instanceof ApiError && error.status === 404) {
        setFailure({ kind: "missing", message: "This category is no longer available. Check Categories." })
      } else if (error instanceof ApiError && error.status < 500) {
        setFailure({ kind: "rejected", message: error.message || "The request was rejected.", fields: error.body?.fields })
      } else {
        setFailure({ kind: "unknown", message: `${deleting ? "Deletion" : "Save"} result is unknown. Check Categories before trying again. Nothing will be sent automatically.` })
      }
    } finally {
      if (!signal.aborted && !leaving.current) {
        request.current = null
        setPending(null)
      }
    }
  }

  return { failure, pending, leaving, goBack, run }
}

type Write = ReturnType<typeof useCategoryWrite>

export function CategoryActionPage(props: Props) {
  const { result, retry } = useRead<CategoryDetail>(props.routes.readApi, props.userId)
  const deleting = props.screen === "category-delete"
  if (result.state === "loading") return <LoadingCategories />
  if (result.state === "error") {
    if (result.status === 401) return <SignInNotice login={props.urls.login} categories form={!deleting} deletion={deleting} />
    return <div className="grid justify-items-start gap-3">
      {result.status === 404 ? <p className="notice" role="alert">This category is no longer available.</p> :
        <ReadFailure title="Could not open this category page" message={result.message} retry={retry} />}
      <Button asChild variant="outline"><a href={props.urls.categories}>Back to categories</a></Button>
    </div>
  }
  return deleting ? <DeleteCategory {...props} category={result.data} /> : <CategoryEditor {...props} category={result.data} />
}

function Feedback({ write, form, checkUrl, hide }: {
  write: Write; form: RefObject<HTMLFormElement | null>; checkUrl?: string; hide?: boolean
}) {
  const feedback = useRef<HTMLDivElement>(null)
  const { failure } = write
  useEffect(() => {
    if (failure) (form.current?.querySelector<HTMLElement>('[aria-invalid="true"]') ?? feedback.current)?.focus()
  }, [failure, form])
  if (!failure || hide) return null
  return <div ref={feedback} tabIndex={-1} role="alert" className="grid justify-items-start gap-2 rounded-md border border-destructive/50 p-3 text-sm">
    <p className="font-semibold">{failure.message}</p>
    <Messages errors={failure.fields?.__all__} />
    {failure.kind === "unknown" && checkUrl && <a className="font-bold underline" href={checkUrl}
      target="_blank" rel="noopener">Check categories in a new tab</a>}
    {failure.kind === "check-session" && <Button type="button" variant="outline" onClick={() => void write.run({ kind: "session" })}>Check session</Button>}
  </div>
}

function CategoryEditor({ category, ...props }: Props & { category: CategoryDetail }) {
  const { name, category_type, parent_id, keywords } = category
  const [draft, setDraft] = useState<Draft>({ name, category_type, parent_id, keywords })
  const [discard, setDiscard] = useState(false)
  const [changed, setChanged] = useState<Set<keyof Draft>>(new Set())
  const form = useRef<HTMLFormElement>(null)
  const write = useCategoryWrite(props)
  const { leaving, pending, failure } = write
  const dirty = draft.name !== name || draft.category_type !== category_type || draft.parent_id !== parent_id || draft.keywords !== keywords
  useEffect(() => {
    if (!dirty && !pending) return
    const warn = (event: BeforeUnloadEvent) => {
      if (!leaving.current) {
        event.preventDefault()
        event.returnValue = true
      }
    }
    window.addEventListener("beforeunload", warn)
    return () => window.removeEventListener("beforeunload", warn)
  }, [dirty, leaving, pending])

  function change<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((current) => ({ ...current, [key]: value }))
    setChanged((current) => new Set([...current, key, ...(key === "parent_id" ? ["category_type" as const] : [])]))
  }
  const errors = (field: keyof Draft) => changed.has(field) ? undefined : failure?.fields?.[field]
  const blocked = Boolean(pending || failure?.kind === "check-session" || failure?.kind === "missing")
  const editedAllErrors = failure?.fields && Object.keys(failure.fields).every((key) => changed.has(key as keyof Draft))
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (blocked) return
    setChanged(new Set())
    void write.run({ kind: "save", draft })
  }

  return <AlertDialog.Root open={discard} onOpenChange={setDiscard}>
    <Card className="max-w-2xl gap-4 py-4 shadow-none sm:py-5">
      <CardHeader className="gap-2 px-4 sm:px-5">
        <h2 className="font-extrabold">Category details</h2>
        <p className="text-sm text-muted-foreground">Names and types organize your ledger. Keywords help match imported expenses.</p>
      </CardHeader>
      <CardContent className="px-4 sm:px-5">
        <form ref={form} aria-label={props.screen === "category-add" ? "Add category" : "Edit category"} onSubmit={submit} noValidate className="grid gap-4">
          <Feedback form={form} write={write} checkUrl={props.urls.categories} hide={editedAllErrors} />
          <fieldset disabled={Boolean(pending)} className="grid min-w-0 gap-4 sm:grid-cols-2">
            <Field id="category-name" label="Name" errors={errors("name")} wide>
              {(control) => <Input {...control} required value={draft.name} className="h-11" onChange={(event) => change("name", event.target.value)} />}
            </Field>
            <Field id="category-parent" label="Parent category" errors={errors("parent_id")}
              help={`Optional. Includes only parents with room within the ${category.max_depth}-level limit.`}>
              {(control) => <NativeSelect {...control} value={draft.parent_id ?? ""} className="h-11 text-base sm:text-sm"
                onChange={(event) => change("parent_id", event.target.value ? Number(event.target.value) : null)}>
                <NativeSelectOption value="">None (top level)</NativeSelectOption>
                {category.parent_choices.map(({ id, label }) => <NativeSelectOption key={id} value={id}>{label}</NativeSelectOption>)}
              </NativeSelect>}
            </Field>
            <Field id="category-type" label="Type" errors={errors("category_type")}
              help="Match the parent and any subcategories. Savings and transfers do not count as spending.">
              {(control) => <NativeSelect {...control} value={draft.category_type} className="h-11 text-base sm:text-sm"
                onChange={(event) => change("category_type", event.target.value)}>
                {category.category_types.map(({ id, label }) => <NativeSelectOption key={id} value={id}>{label}</NativeSelectOption>)}
              </NativeSelect>}
            </Field>
            <Field id="category-keywords" label="Keywords" errors={errors("keywords")} wide
              help="Separate keywords with commas (for example, market, bakery). Saving here does not reassign existing expenses.">
              {(control) => <textarea {...control} rows={3} value={draft.keywords} onChange={(event) => change("keywords", event.target.value)}
                className="w-full resize-y rounded-md border border-input px-3 py-2 text-base outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-50 aria-invalid:border-destructive sm:text-sm dark:bg-input/30" />}
            </Field>
          </fieldset>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" className="h-11" disabled={blocked}>
              {pending === "write" ? "Saving…" : pending === "session" ? "Checking session…" : "Save category"}
            </Button>
            <AlertDialog.Trigger asChild>
              <Button type="button" variant="outline" className="h-11" disabled={Boolean(pending)}
                onClick={(event) => { if (!dirty) { event.preventDefault(); write.goBack() } }}>
                {failure?.kind === "missing" ? "Back to categories" : "Cancel"}
              </Button>
            </AlertDialog.Trigger>
          </div>
          {pending && <p role="status" className="sr-only">{pending === "write" ? "Saving category" : "Checking your session"}</p>}
        </form>
      </CardContent>
    </Card>
    <AlertDialog.Portal>
      <AlertDialog.Overlay className="fixed inset-0 z-20 bg-black/50" />
      <AlertDialog.Content className="fixed top-1/2 left-1/2 z-30 grid w-[calc(100%-1.5rem)] max-w-md -translate-1/2 gap-4 rounded-xl border bg-card p-5 shadow-xl">
        <AlertDialog.Title className="text-lg font-extrabold">Discard unsaved changes?</AlertDialog.Title>
        <AlertDialog.Description className="text-sm text-muted-foreground">Your changes will be lost. Return to Categories without saving?</AlertDialog.Description>
        <div className="flex flex-wrap gap-2">
          <AlertDialog.Cancel asChild><Button variant="outline" className="h-11">Keep editing</Button></AlertDialog.Cancel>
          <AlertDialog.Action asChild><Button variant="destructive" className="h-11 dark:bg-destructive dark:text-background"
            onClick={() => write.goBack()}>Discard changes</Button></AlertDialog.Action>
        </div>
      </AlertDialog.Content>
    </AlertDialog.Portal>
  </AlertDialog.Root>
}

function DeleteCategory({ category, ...props }: Props & { category: CategoryDetail }) {
  const write = useCategoryWrite(props)
  const form = useRef<HTMLFormElement>(null)
  const { pending, failure } = write
  const blocked = Boolean(pending || (failure && failure.kind !== "rejected"))

  return <Card className="max-w-xl gap-4 py-4 shadow-none sm:py-5">
    <CardHeader className="gap-2 px-4 sm:px-5">
      <h2 className="flex items-start gap-2 font-extrabold wrap-anywhere">
        <AlertTriangle className="size-5 shrink-0 text-destructive" aria-hidden="true" />
        <span>{category.name}</span>
      </h2>
      <p className="text-sm text-muted-foreground">This permanently removes the category and its keywords.</p>
      <ul id="category-delete-warning" className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
        <li>Assigned expenses stay in your account but become uncategorized.</li>
        <li>Direct subcategories move to the top level, keeping their own children and expenses.</li>
      </ul>
    </CardHeader>
    <CardContent className="px-4 sm:px-5">
      <form ref={form} aria-label="Confirm category deletion" aria-describedby="category-delete-warning" className="grid gap-4"
        onSubmit={(event) => { event.preventDefault(); if (!blocked) void write.run({ kind: "delete" }) }}>
        <Feedback form={form} write={write} />
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" className="h-11" disabled={Boolean(pending)} onClick={() => write.goBack()}>
            {failure?.kind === "unknown" || failure?.kind === "missing" ? "Check categories" : "Cancel"}
          </Button>
          <Button type="submit" variant="destructive" disabled={blocked} className="h-11 dark:bg-destructive dark:text-background dark:hover:bg-destructive/90">
            {pending === "write" ? "Deleting…" : pending === "session" ? "Checking session…" : "Delete category"}
          </Button>
        </div>
        {pending && <p role="status" className="sr-only">{pending === "write" ? "Deleting category" : "Checking your session"}</p>}
      </form>
    </CardContent>
  </Card>
}
