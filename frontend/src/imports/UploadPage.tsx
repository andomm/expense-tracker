import { FileUp } from "lucide-react"
import { useEffect, useRef, useState, type FormEvent } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Field } from "@/components/ui/form-field"
import { Input } from "@/components/ui/input"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { ApiError, readJson, writeMultipart, type FieldErrors, type Session } from "@/lib/api"
import type { AppUrls, CsvImportRoutes } from "@/Shell"

type UploadState = { kind: "ready" | "pending" | "unknown" }
  | { kind: "rejected"; message: string; fields?: FieldErrors }

export function LoadingImport({ result = false }: { result?: boolean }) {
  return <div className="notice" role="status"><p>{result ? "Loading latest import result…" : "Loading CSV upload…"}</p></div>
}

export function UploadPage({ routes, urls, userId, session, onSessionChange }: {
  routes: CsvImportRoutes; urls: AppUrls; userId: number; session: Session
  onSessionChange: (value: Session | null) => void
}) {
  const [state, setState] = useState<UploadState>({ kind: "ready" })
  const [hasFile, setHasFile] = useState(false)
  const inFlight = useRef<AbortController | null>(null)
  const canLeave = useRef(false)
  const pending = state.kind === "pending"
  const unknown = state.kind === "unknown"
  const errors = state.kind === "rejected" ? state.fields : undefined
  useEffect(() => () => inFlight.current?.abort(), [])
  useEffect(() => {
    if (!hasFile || unknown) return
    function warn(event: BeforeUnloadEvent) {
      if (!canLeave.current) event.preventDefault()
    }
    window.addEventListener("beforeunload", warn)
    return () => window.removeEventListener("beforeunload", warn)
  }, [hasFile, unknown])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (inFlight.current || pending || unknown) return
    const body = new FormData(event.currentTarget)
    const controller = new AbortController()
    const { signal } = controller
    inFlight.current = controller
    setState({ kind: "pending" })
    try {
      const outcome = await writeMultipart<{ result_id: string; result_url: string }>(routes.startApi, {
        body, csrfToken: session.csrf_token, userId, signal,
      })
      if (signal.aborted) return
      if (!outcome?.result_id || outcome.result_url !== routes.resultUrl) {
        setState({ kind: "unknown" })
        return
      }
      canLeave.current = true
      window.location.replace(routes.resultUrl)
    } catch (error) {
      if (signal.aborted) return
      if (error instanceof ApiError && error.needsSessionCheck) {
        try {
          const current = await readJson<Session>(urls.sessionApi, signal)
          if (signal.aborted) return
          if (current.user?.id !== userId) {
            onSessionChange(null)
            return
          }
          onSessionChange(current)
          setState({ kind: "rejected", message: "Import did not start. The session was checked. Select Import expenses to try again." })
        } catch {
          if (!signal.aborted) setState({ kind: "rejected", message: "Import did not start. Reload the page to check your session before trying again." })
        }
      } else if (error instanceof ApiError && (
        (error.status === 422 && error.body?.code === "validation_failed") ||
        (error.status === 400 && error.body?.code === "invalid_request")
      )) {
        setState({ kind: "rejected", message: error.message, fields: error.body?.fields })
      } else {
        setState({ kind: "unknown" })
      }
    } finally {
      inFlight.current = null
    }
  }

  return (
    <div className="max-w-2xl space-y-4">
      <Card aria-labelledby="import-file-title" className="gap-0 py-0 shadow-none">
        <CardHeader className="gap-3 border-b px-4 py-5 sm:px-6 sm:py-6">
          <div className="flex items-center gap-3">
            <FileUp className="size-5 shrink-0 text-primary" aria-hidden="true" />
            <h2 id="import-file-title" className="text-lg font-extrabold tracking-tight">Choose an export</h2>
          </div>
          <p className="text-sm leading-relaxed text-muted-foreground">Import transactions from OP or Spiir. Your category keywords are used to match expenses as they are imported.</p>
        </CardHeader>
        <CardContent className="px-4 py-5 sm:px-6 sm:py-6">
          <form onSubmit={submit} method="post" action={routes.startApi} encType="multipart/form-data" className="space-y-4">
            {state.kind === "rejected" && <p role="alert" className="text-sm font-semibold text-destructive">{state.message}</p>}
            <fieldset disabled={pending || unknown} className="grid min-w-0 gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
              <Field id="csv-format" label="File format" errors={errors?.import_format}>
                {(props) => <NativeSelect {...props} name="import_format" className="h-11 text-base sm:text-sm" defaultValue="osuuspankki_csv">
                  <NativeSelectOption value="osuuspankki_csv">OP</NativeSelectOption>
                  <NativeSelectOption value="spiir_csv">Spiir</NativeSelectOption>
                </NativeSelect>}
              </Field>
              <Field id="csv-file" label="CSV file" help="Choose a semicolon-separated CSV export." errors={errors?.file}>
                {(props) => <Input {...props} name="file" type="file" accept=".csv,text/csv" required
                  onChange={(event) => setHasFile(Boolean(event.currentTarget.files?.length))}
                  className="h-11 py-1.5 file:mr-2 file:rounded-sm file:bg-accent file:px-2 file:font-semibold" />}
              </Field>
            </fieldset>
            {pending && <p role="status" className="text-sm font-semibold">Importing expenses… Keep this page open to see the result.</p>}
            {unknown && <div role="alert" className="space-y-1 rounded-lg border bg-background p-3 text-sm">
              <p className="font-extrabold">Could not confirm whether the import finished</p>
              <p>The upload was not retried. Check Expenses before uploading this file again so you don’t import the same transactions twice.</p>
            </div>}
            <div className="flex flex-wrap gap-2">
              {unknown ? <Button asChild className="h-11"><a href={`${urls.expenses}?month=all`}>Check Expenses</a></Button> : <>
                <Button type="submit" disabled={pending} className="h-11">{pending ? "Importing…" : "Import expenses"}</Button>
                {!pending && <Button asChild variant="outline" className="h-11"><a href={urls.expenses}>Cancel</a></Button>}
              </>}
            </div>
          </form>
        </CardContent>
      </Card>
      {!pending && <Button asChild variant="link" className="h-11 px-0"><a href={routes.resultUrl}>View latest result</a></Button>}
    </div>
  )
}
