import { ChevronRight, Pencil, Plus, RefreshCw, Tags, Trash2 } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { useRead } from "@/lib/api"
import { ReadFailure, type CategoryListRoutes } from "@/Shell"

type CategoryEntry = {
  id: number
  parent_id: number | null
  name: string
  type_label: string
  keyword_count: number
  edit_url: string
  delete_url: string
}

type Tree = Map<number | null, CategoryEntry[]>

export function LoadingCategories() {
  return <div className="notice" role="status"><p>Loading categories…</p></div>
}

function CategoryBranch({ entry, tree }: { entry: CategoryEntry; tree: Tree }) {
  const [open, setOpen] = useState(false)
  const children = tree.get(entry.id)
  const count = entry.keyword_count
  return (
    <li className="min-w-0">
      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-1 py-1.5 sm:gap-x-3">
        <div className="min-w-0">
          {children ? (
            <button type="button" aria-expanded={open} aria-controls={`category-children-${entry.id}`}
              className="flex min-h-11 w-full min-w-0 items-center gap-1 rounded-md px-1 text-left text-sm font-extrabold hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring sm:gap-2"
              onClick={() => setOpen((value) => !value)}>
              <ChevronRight className={`size-4 shrink-0 text-primary ${open ? "rotate-90" : ""}`} aria-hidden="true" />
              <span className="wrap-anywhere">{entry.name}</span>
            </button>
          ) : <p className="pl-6 text-sm font-bold wrap-anywhere sm:pl-7">{entry.name}</p>}
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 pl-6 text-xs text-muted-foreground sm:pl-7">
            <Badge variant="secondary">{entry.type_label}</Badge>
            <span>{count === 0 ? "No keywords" : `${count} ${count === 1 ? "keyword" : "keywords"}`}
              {entry.parent_id === null && children ? " in branch" : ""}</span>
          </p>
        </div>
        <div className="flex items-center">
          <Button asChild variant="ghost" size="icon-lg" className="size-11">
            <a href={entry.edit_url} aria-label={`Edit ${entry.name}`} title={`Edit ${entry.name}`}>
              <Pencil aria-hidden="true" />
            </a>
          </Button>
          <Button asChild variant="ghost" size="icon-lg" className="size-11 text-destructive">
            <a href={entry.delete_url} aria-label={`Delete ${entry.name}`} title={`Delete ${entry.name}`}>
              <Trash2 aria-hidden="true" />
            </a>
          </Button>
        </div>
      </div>
      {children && <ul role="list" id={`category-children-${entry.id}`} hidden={!open}
        className="ml-2 border-l pl-1 sm:ml-4 sm:pl-2">
        {open && children.map((child) => <CategoryBranch key={child.id} entry={child} tree={tree} />)}
      </ul>}
    </li>
  )
}

function SyncCard({ url, resultUrl }: { url: string; resultUrl: string }) {
  return (
    <Card className="gap-3 py-4 shadow-none sm:py-5" role="region" aria-labelledby="sync-title">
      <CardHeader className="gap-2 px-4 sm:px-5">
        <h2 id="sync-title" className="font-extrabold">Keyword matching</h2>
        <p id="sync-scope" className="text-sm text-muted-foreground">
          Saving keywords does not change existing expenses. Sync can categorize unmatched expenses and move
          matches to a more specific category within the same top-level category.
        </p>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 sm:px-5">
        <Button asChild variant="outline" className="h-11">
          <a href={url} aria-describedby="sync-scope"><RefreshCw aria-hidden="true" /> Sync existing expenses</a>
        </Button>
        <Button asChild variant="link" className="h-11 px-1"><a href={resultUrl}>View latest result</a></Button>
      </CardContent>
    </Card>
  )
}

export function CategoriesPage({ routes, userId }: {
  routes: CategoryListRoutes; userId: number
}) {
  const { result, retry } = useRead<{ categories: CategoryEntry[] }>(routes.api, userId)
  if (result.state === "loading") return <LoadingCategories />
  if (result.state === "error") {
    return <ReadFailure title="Could not load categories" message={result.message} retry={retry} />
  }
  const tree: Tree = new Map()
  for (const entry of result.data.categories) {
    const siblings = tree.get(entry.parent_id)
    if (siblings) siblings.push(entry)
    else tree.set(entry.parent_id, [entry])
  }
  const roots = tree.get(null) ?? []
  return (
    <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] lg:gap-6">
      <section aria-labelledby="category-tree-title" className="min-w-0 rounded-xl border bg-card">
        {routes.notices.length > 0 && <div role="status" className="border-b bg-accent px-4 py-3 text-sm font-bold wrap-anywhere sm:px-5">
          {routes.notices.map((message, index) => <p key={index}>{message}</p>)}
        </div>}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-3 py-3 sm:px-5">
          <div className="flex items-center gap-2">
            <Tags className="size-5 text-primary" aria-hidden="true" />
            <h2 id="category-tree-title" className="text-lg font-extrabold tracking-tight">My categories</h2>
          </div>
          <Button asChild className="h-11"><a href={routes.addUrl}><Plus aria-hidden="true" /> Add category</a></Button>
        </div>
        {roots.length > 0 ? <ul role="list" aria-labelledby="category-tree-title" className="divide-y px-2 py-1 sm:px-4">
          {roots.map((root) => <CategoryBranch key={root.id} entry={root} tree={tree} />)}
        </ul> : <p className="p-4 text-sm text-muted-foreground sm:p-5">No categories yet. Add a category to get started.</p>}
      </section>
      <SyncCard url={routes.syncUrl} resultUrl={routes.syncResultUrl} />
    </div>
  )
}
