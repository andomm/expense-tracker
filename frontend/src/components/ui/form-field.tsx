import type { ReactNode } from "react"

export function Messages({ id, errors = [] }: { id?: string; errors?: string[] }) {
  if (!errors.length) return null
  return <ul id={id} className="text-sm font-semibold text-destructive" role="list">
    {errors.map((message, index) => <li key={index}>{message}</li>)}
  </ul>
}

export type Control = { id: string; "aria-invalid"?: boolean; "aria-describedby"?: string }

export function Field({ id, label, help, errors, children, wide = false }: {
  id: string; label: string; help?: string; errors?: string[]; children: (props: Control) => ReactNode; wide?: boolean
}) {
  const invalid = Boolean(errors?.length)
  const description = [help && `${id}-hint`, invalid && `${id}-errors`].filter(Boolean).join(" ")
  return (
    <div className={`grid min-w-0 content-start gap-1.5 ${wide ? "sm:col-span-2" : ""}`}>
      <label htmlFor={id} className="text-sm font-bold">{label}</label>
      {children({ id, "aria-invalid": invalid || undefined, "aria-describedby": description || undefined })}
      {help && <p id={`${id}-hint`} className="small-note">{help}</p>}
      <Messages id={`${id}-errors`} errors={errors} />
    </div>
  )
}
