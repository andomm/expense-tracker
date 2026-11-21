import type { ReactNode } from "react"

import { Input } from "@/components/ui/input"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import type { FieldErrors } from "@/lib/api"

import type { Choice, Draft, FormOptions, MainFields } from "./form"

export function Messages({ id, errors = [] }: { id?: string; errors?: string[] }) {
  if (!errors.length) return null
  return <ul id={id} className="text-sm font-semibold text-destructive" role="list">
    {errors.map((message, index) => <li key={index}>{message}</li>)}
  </ul>
}

type Control = { id: string; "aria-invalid"?: boolean; "aria-describedby"?: string }

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

export function ChoiceInput({ value, choices, emptyLabel, onChange, ...props }: Control & {
  value: number | null; choices: Choice[]; emptyLabel: string; onChange: (value: number | null) => void
}) {
  return (
    <NativeSelect {...props} value={value ?? ""}
      onChange={(event) => onChange(event.target.value ? Number(event.target.value) : null)}>
      <NativeSelectOption value="">{emptyLabel}</NativeSelectOption>
      {choices.map(({ id, label }) => <NativeSelectOption key={id} value={id}>{label}</NativeSelectOption>)}
    </NativeSelect>
  )
}

export function ExpenseFields({ draft, options, errors, change }: {
  draft: Draft; options: FormOptions; errors: FieldErrors
  change: <K extends keyof MainFields>(name: K, value: MainFields[K]) => void
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field id="expense-date" label="Date" errors={errors.date}>
        {(props) => <Input {...props} type="date" required value={draft.date}
          onChange={(event) => change("date", event.target.value)} />}
      </Field>
      <Field id="expense-amount" label="Full amount (€)" errors={errors.amount}
        help="Use a minus sign for spending and a positive amount for income or refunds.">
        {(props) => <Input {...props} inputMode="text" required value={draft.amount}
          onChange={(event) => change("amount", event.target.value)} />}
      </Field>
      <Field id="expense-receiver" label="Receiver" errors={errors.receiver}>
        {(props) => <Input {...props} value={draft.receiver}
          onChange={(event) => change("receiver", event.target.value)} />}
      </Field>
      <Field id="expense-category" label="Category" errors={errors.category_id}
        help="Choose a category unless you split the full amount.">
        {(props) => <ChoiceInput {...props} choices={options.categories} value={draft.category_id}
          emptyLabel="Choose a category" onChange={(value) => change("category_id", value)} />}
      </Field>
      <Field id="expense-description" label="Description" errors={errors.description} wide>
        {(props) => <textarea {...props} className="expense-description" rows={2} value={draft.description}
          onChange={(event) => change("description", event.target.value)} />}
      </Field>
      <Field id="expense-share-rule" label="Your share rule" errors={errors.share_rule_id}
        help="Apply an existing percentage rule to the expense and each split part.">
        {(props) => <ChoiceInput {...props} choices={options.share_rules} value={draft.share_rule_id}
          emptyLabel="No share rule" onChange={(value) => change("share_rule_id", value)} />}
      </Field>
    </div>
  )
}
