import { Field, type Control } from "@/components/ui/form-field"
import { Input } from "@/components/ui/input"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import type { FieldErrors } from "@/lib/api"

import type { Choice, Draft, FormOptions, MainFields } from "./form"

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
