import { Skeleton } from "@/components/ui/skeleton"

export function LoadingAnalytics() {
  return (
    <div role="status" className="space-y-3">
      <p className="text-sm text-muted-foreground">Loading Analytics…</p>
      <div aria-hidden="true" className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    </div>
  )
}
