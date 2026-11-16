// THROWAWAY: three expense-screen layouts at /expenses/?variant=A|B|C.
// Synthetic, in-memory data only. No Django, API calls, or real mutations.
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDownLeft,
  ArrowDownUp,
  ArrowUpRight,
  BarChart3,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Coffee,
  CreditCard,
  FileUp,
  Home,
  Layers3,
  Menu,
  Moon,
  MoreHorizontal,
  Plus,
  Search,
  ShoppingBasket,
  SlidersHorizontal,
  Sparkles,
  Sun,
  Tag,
  Trash2,
  TrendingUp,
  Wallet,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";

type Variant = "A" | "B" | "C";
type PreviewState = "ready" | "loading" | "empty" | "error";
type Row = {
  id: string;
  expenseId: string;
  day: number;
  receiver: string;
  detail: string;
  category: string;
  amount: number;
  type: "expense" | "income" | "saving";
  note?: string;
};
const layouts: Record<Variant, string> = {
  A: "Sidebar dashboard",
  B: "The monthly ledger",
  C: "Balance-first overview",
};
const months = ["April 2026", "May 2026", "June 2026"];
const money = (cents: number) =>
  new Intl.NumberFormat("en-FI", { style: "currency", currency: "EUR" }).format(
    cents / 100,
  );
const sampleRows: Row[] = [
  {
    id: "market",
    expenseId: "market",
    day: 28,
    receiver: "K-Citymarket",
    detail: "The weekly grocery run",
    category: "Groceries",
    amount: -6840,
    type: "expense",
  },
  {
    id: "coffee",
    expenseId: "coffee",
    day: 28,
    receiver: "Café Aalto",
    detail: "Coffee with a friend",
    category: "Food & drink",
    amount: -940,
    type: "expense",
  },
  {
    id: "salary",
    expenseId: "salary",
    day: 27,
    receiver: "Example employer",
    detail: "Monthly salary",
    category: "Income",
    amount: 320000,
    type: "income",
  },
  {
    id: "saving",
    expenseId: "saving",
    day: 27,
    receiver: "Savings account",
    detail: "Monthly savings",
    category: "Savings",
    amount: -40000,
    type: "saving",
  },
  {
    id: "hsl",
    expenseId: "hsl",
    day: 25,
    receiver: "HSL",
    detail: "Monthly travel pass",
    category: "Transport",
    amount: -7290,
    type: "expense",
  },
  {
    id: "dinner-food",
    expenseId: "dinner",
    day: 24,
    receiver: "Bistro Demo",
    detail: "Dinner · category allocation",
    category: "Food & drink",
    amount: -4200,
    type: "expense",
    note: "1 of 2 allocations",
  },
  {
    id: "dinner-other",
    expenseId: "dinner",
    day: 24,
    receiver: "Bistro Demo",
    detail: "Gift · category allocation",
    category: "Other",
    amount: -1800,
    type: "expense",
    note: "2 of 2 allocations",
  },
  {
    id: "book",
    expenseId: "book",
    day: 21,
    receiver: "Akateeminen",
    detail: "Something good to read",
    category: "Shopping",
    amount: -2890,
    type: "expense",
  },
  {
    id: "electric",
    expenseId: "electric",
    day: 16,
    receiver: "Example energy",
    detail: "Electricity bill",
    category: "Home",
    amount: -5670,
    type: "expense",
  },
  {
    id: "lidl",
    expenseId: "lidl",
    day: 12,
    receiver: "Lidl",
    detail: "Groceries for the weekend",
    category: "Groceries",
    amount: -4380,
    type: "expense",
  },
  {
    id: "uncategorized",
    expenseId: "uncategorized",
    day: 8,
    receiver: "Card purchase",
    detail: "Needs a category",
    category: "Uncategorized",
    amount: -2450,
    type: "expense",
  },
  {
    id: "rent",
    expenseId: "rent",
    day: 2,
    receiver: "Example housing",
    detail: "Monthly rent · personal share",
    category: "Home",
    amount: -88000,
    type: "expense",
    note: "50% of €1,760.00",
  },
];
const categories = [
  "All categories",
  "Home",
  "Groceries",
  "Food & drink",
  "Transport",
  "Shopping",
  "Other",
  "Uncategorized",
  "Income",
  "Savings",
];

function CategoryIcon({ category }: { category: string }) {
  const Icon =
    category === "Home"
      ? Home
      : category === "Groceries"
        ? ShoppingBasket
        : category === "Food & drink"
          ? Coffee
          : category === "Income"
            ? ArrowDownLeft
            : category === "Savings"
              ? Wallet
              : CreditCard;
  return (
    <span
      className={`merchant-icon icon-${category.toLowerCase().replaceAll(" ", "-")}`}
    >
      <Icon size={17} aria-hidden="true" />
    </span>
  );
}

export default function App() {
  const params = new URLSearchParams(window.location.search);
  const initial = params.get("variant") as Variant;
  const [variant, setVariant] = useState<Variant>(
    initial in layouts ? initial : "A",
  );
  const [dark, setDark] = useState(params.get("theme") === "dark");
  const initialState = params.get("state") as PreviewState;
  const [preview, setPreview] = useState<PreviewState>(
    ["ready", "loading", "empty", "error"].includes(initialState)
      ? initialState
      : "ready",
  );
  const [month, setMonth] = useState("1");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All categories");
  const [sort, setSort] = useState("newest");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [info, setInfo] = useState<{ title: string; body: string } | null>(
    null,
  );
  const [mobileOpen, setMobileOpen] = useState(false);
  const lastFocus = useRef<HTMLElement | null>(null);
  const monthIndex = month === "all" ? 1 : Number(month);
  const monthName = months[monthIndex];
  const shortMonth = monthName.split(" ")[0];
  const rowsForMonth = sampleRows.map((row) => ({
    ...row,
    amount:
      monthIndex === 0 && row.type === "expense"
        ? Math.round(row.amount * 0.92)
        : row.amount,
  }));
  const rows = useMemo(() => {
    if (preview !== "ready") {
      return [];
    }
    const term = query.toLowerCase().trim();
    const filtered = rowsForMonth.filter(
      (row) =>
        (category === "All categories" || row.category === category) &&
        `${row.receiver} ${row.detail} ${row.category} ${row.note ?? ""}`
          .toLowerCase()
          .includes(term),
    );
    return filtered.sort((a, b) =>
      sort === "amount"
        ? a.amount - b.amount
        : sort === "oldest"
          ? a.day - b.day
          : b.day - a.day,
    );
  }, [month, query, category, sort, preview]);
  const totals = rows.reduce(
    (sum, row) => ({
      spent: sum.spent + (row.type === "expense" ? -row.amount : 0),
      income: sum.income + (row.type === "income" ? row.amount : 0),
      savings: sum.savings + (row.type === "saving" ? -row.amount : 0),
      balance: sum.balance + row.amount,
    }),
    { spent: 0, income: 0, savings: 0, balance: 0 },
  );
  const sourceIds = [...new Set(rows.map((row) => row.expenseId))];
  const breakdown = Object.entries(
    rows
      .filter((row) => row.type === "expense")
      .reduce<
        Record<string, number>
      >((sum, row) => ({ ...sum, [row.category]: (sum[row.category] ?? 0) - row.amount }), {}),
  ).sort((a, b) => b[1] - a[1]);
  const topRows = rows
    .filter((row) => row.type === "expense")
    .sort((a, b) => a.amount - b.amount)
    .slice(0, 3);
  const stats = [
    {
      label: "Spent",
      amount: totals.spent,
      icon: ArrowUpRight,
      detail: "Expense allocations",
      className: "spent",
    },
    {
      label: "Income",
      amount: totals.income,
      icon: ArrowDownLeft,
      detail: "Money received",
      className: "income",
    },
    {
      label: "Savings",
      amount: totals.savings,
      icon: Wallet,
      detail: "Put aside",
      className: "saving",
    },
    {
      label: "Balance",
      amount: totals.balance,
      icon: TrendingUp,
      detail: "After expenses & savings",
      className: "balance",
    },
  ];

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.dataset.variant = variant;
    const next = new URL(window.location.href);
    next.searchParams.set("variant", variant);
    next.searchParams.set("theme", dark ? "dark" : "light");
    next.searchParams.set("state", preview);
    window.history.replaceState({}, "", next);
    console.info("Prototype state", {
      variant,
      theme: dark ? "dark" : "light",
      preview,
      month,
      category,
      query,
      sort,
      selected: [...selected],
    });
  }, [variant, dark, preview, month, category, query, sort, selected]);

  useEffect(() => {
    const cycle = (event: KeyboardEvent) => {
      const target = event.target;
      if (
        event.defaultPrevented ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        document.querySelector(
          '[role="dialog"], [role="listbox"], [role="menu"]',
        )
      ) {
        return;
      }
      if (
        target instanceof HTMLElement &&
        target.closest(
          'input, textarea, select, [contenteditable], [role="combobox"], [role="checkbox"]',
        )
      ) {
        return;
      }
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        const keys: Variant[] = ["A", "B", "C"];
        setVariant(
          keys[
            (keys.indexOf(variant) + (event.key === "ArrowRight" ? 1 : 2)) % 3
          ],
        );
      }
    };
    window.addEventListener("keydown", cycle);
    return () => window.removeEventListener("keydown", cycle);
  }, [variant]);

  function openInfo(
    title: string,
    body = "This is a layout preview. This workflow will be designed separately; no records are created, changed, or deleted.",
  ) {
    lastFocus.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    setInfo({ title, body });
  }
  function clearFilters() {
    setQuery("");
    setCategory("All categories");
    setSelected(new Set());
  }
  function toggleRow(id: string, checked: boolean) {
    setSelected((previous) => {
      const next = new Set(previous);
      if (checked) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  }
  function changeMonth(value: string) {
    setMonth(value);
    setSelected(new Set());
  }
  const themeButton = (
    <Button
      className="theme-button"
      variant="ghost"
      size="icon"
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      onClick={() => setDark(!dark)}
    >
      {dark ? <Sun /> : <Moon />}
    </Button>
  );
  const brand = (
    <a
      className="brand"
      href="/expenses/?variant=A"
      aria-label="Expense Tracker home"
    >
      <span className="brand-symbol">
        <Layers3 size={22} strokeWidth={1.8} />
      </span>
      <span>
        expense<span className="brand-sub">tracker</span>
      </span>
    </a>
  );
  const navigation = (compact = false) => (
    <nav
      className={compact ? "inline-nav" : "side-nav"}
      aria-label="Main navigation"
    >
      {[
        { name: "Expenses", icon: Wallet },
        { name: "Analytics", icon: BarChart3 },
        { name: "Categories", icon: Tag },
        { name: "Upload CSV", icon: FileUp },
      ].map(({ name, icon: Icon }) => (
        <button
          key={name}
          className={`nav-item ${name === "Expenses" ? "active" : ""}`}
          aria-current={name === "Expenses" ? "page" : undefined}
          onClick={() =>
            name === "Expenses"
              ? window.scrollTo({ top: 0, behavior: "smooth" })
              : openInfo(name)
          }
        >
          <Icon size={18} />
          <span>{name}</span>
          {name === "Expenses" && !compact && (
            <span className="nav-count">{sourceIds.length}</span>
          )}
        </button>
      ))}
    </nav>
  );
  const mobileMenu = (
    <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="mobile-menu-button"
          aria-label="Open navigation"
        >
          <Menu />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="mobile-sheet">
        <SheetHeader>
          <SheetTitle>Expense Tracker</SheetTitle>
          <SheetDescription>Design preview · sample data only</SheetDescription>
        </SheetHeader>
        {navigation()}
        <Button variant="ghost" onClick={() => openInfo("Account and logout")}>
          Demo account · Logout
        </Button>
      </SheetContent>
    </Sheet>
  );
  const account = (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          className="account-button"
          variant="ghost"
          aria-label="Open demo account menu"
        >
          <span className="avatar">D</span>
          <span className="account-copy">
            Demo account<small>Personal workspace</small>
          </span>
          <ChevronDown size={14} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem
          onSelect={() =>
            openInfo(
              "Demo account",
              "Synthetic account. No login, personal profile, or stored financial data is used in this prototype.",
            )
          }
        >
          Demo account
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() =>
            openInfo(
              "Delete all expenses",
              "Destructive actions will have a confirmation step. This preview cannot delete any real or sample data.",
            )
          }
          className="text-destructive"
        >
          Delete all expenses
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() =>
            openInfo(
              "Logout",
              "This preview has no active login session. Django authentication stays unchanged until its own migration step.",
            )
          }
        >
          Logout
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
  const monthPicker = (
    <div className="month-picker">
      <Button
        variant="ghost"
        size="icon"
        aria-label="Previous month"
        disabled={month === "all" || monthIndex === 0}
        onClick={() => changeMonth(String(monthIndex - 1))}
      >
        <ChevronLeft />
      </Button>
      <Select value={month} onValueChange={changeMonth}>
        <SelectTrigger aria-label="Choose month" className="month-select">
          <CalendarDays size={16} />
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {months.map((name, index) => (
            <SelectItem key={name} value={String(index)}>
              {name}
            </SelectItem>
          ))}
          <SelectItem value="all">All dates</SelectItem>
        </SelectContent>
      </Select>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Next month"
        disabled={month === "all" || monthIndex === 2}
        onClick={() => changeMonth(String(monthIndex + 1))}
      >
        <ChevronRight />
      </Button>
    </div>
  );
  const actions = (
    <div className="page-actions">
      <Button
        variant="outline"
        className="import-action"
        onClick={() => openInfo("Upload CSV")}
      >
        <FileUp />
        Upload CSV
      </Button>
      <Button className="add-action" onClick={() => openInfo("Add expense")}>
        <Plus />
        Add expense
      </Button>
    </div>
  );
  const filters = (
    <div className="filter-bar">
      <div className="search-field">
        <Search size={17} aria-hidden="true" />
        <Input
          aria-label="Search expenses"
          value={query}
          placeholder="Search receiver, note or category…"
          onChange={(event) => {
            setQuery(event.target.value);
            setSelected(new Set());
          }}
        />
        {query && (
          <button aria-label="Clear search" onClick={clearFilters}>
            <X size={15} />
          </button>
        )}
      </div>
      <Select
        value={category}
        onValueChange={(value) => {
          setCategory(value);
          setSelected(new Set());
        }}
      >
        <SelectTrigger
          className="category-select"
          aria-label="Filter by category"
        >
          <SlidersHorizontal size={15} />
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {categories.map((name) => (
            <SelectItem key={name} value={name}>
              {name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select value={sort} onValueChange={setSort}>
        <SelectTrigger className="sort-select" aria-label="Sort expenses">
          <ArrowDownUp size={15} />
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="newest">Newest first</SelectItem>
          <SelectItem value="oldest">Oldest first</SelectItem>
          <SelectItem value="amount">Amount: low to high</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
  const previewControls = (
    <div className="preview-state-control">
      <span className="sample-label">
        <span className="sample-dot" />
        Design preview · sample data
      </span>
      <Select
        value={preview}
        onValueChange={(value) => {
          setPreview(value as PreviewState);
          setSelected(new Set());
        }}
      >
        <SelectTrigger aria-label="Preview state" className="state-select">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="ready">Populated</SelectItem>
          <SelectItem value="loading">Loading</SelectItem>
          <SelectItem value="empty">First use</SelectItem>
          <SelectItem value="error">Load error</SelectItem>
        </SelectContent>
      </Select>
    </div>
  );
  const summary = (strip = false) => (
    <div className={strip ? "summary-strip" : "summary-cards"}>
      {stats.map((stat) => (
        <section className={`stat ${stat.className}`} key={stat.label}>
          <div className="stat-label">
            {stat.label}
            <stat.icon size={16} aria-hidden="true" />
          </div>
          <strong>
            {preview === "loading" || preview === "error"
              ? "—"
              : money(stat.amount)}
          </strong>
          <small>{stat.detail}</small>
        </section>
      ))}
    </div>
  );
  const selectionBar = selected.size > 0 && (
    <div className="selection-bar" role="status">
      <span>
        <Check size={15} />
        <strong>{selected.size}</strong> transaction
        {selected.size > 1 ? "s" : ""} selected
      </span>
      <div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => openInfo("Categorize selected transactions")}
        >
          <Tag />
          Categorize
        </Button>
        <Button
          size="icon"
          variant="ghost"
          aria-label="Delete selected transactions"
          onClick={() =>
            openInfo(
              "Delete selected transactions",
              "Both category allocations of a selected source transaction are selected together. A confirmation step would appear before deletion. This prototype never deletes data.",
            )
          }
        >
          <Trash2 />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          aria-label="Clear selection"
          onClick={() => setSelected(new Set())}
        >
          <X />
        </Button>
      </div>
    </div>
  );

  function rowMenu(row: Row) {
    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Actions for ${row.receiver}, ${row.category}`}
          >
            <MoreHorizontal />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => openInfo(`Edit ${row.receiver}`)}>
            Edit expense
          </DropdownMenuItem>
          <DropdownMenuItem
            onSelect={() =>
              openInfo(
                "Category allocations",
                "One source transaction can have several category allocation rows. Selecting any allocation selects the source transaction. Personal-share rules and category allocations remain separate concepts.",
              )
            }
          >
            View allocation details
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            className="text-destructive"
            onSelect={() => openInfo(`Delete ${row.receiver}`)}
          >
            Delete expense
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }
  const emptyState =
    preview === "loading" ? (
      <div
        className="loading-state"
        role="status"
        aria-label="Loading expenses"
      >
        {[1, 2, 3, 4, 5].map((item) => (
          <div className="skeleton-row" key={item}>
            <Skeleton className="size-10 rounded-xl" />
            <div>
              <Skeleton className="h-3 w-36" />
              <Skeleton className="mt-2 h-2 w-24" />
            </div>
            <Skeleton className="ml-auto h-4 w-20" />
          </div>
        ))}
        <span className="sr-only">Loading expenses</span>
      </div>
    ) : preview === "error" ? (
      <div className="empty-state" role="alert">
        <span className="empty-icon">
          <CircleHelp />
        </span>
        <h3>Expenses couldn’t be loaded</h3>
        <p>Your data hasn’t changed. Try loading this view again.</p>
        <Button onClick={() => setPreview("ready")}>Try again</Button>
      </div>
    ) : (
      <div className="empty-state">
        <span className="empty-icon">
          {query || category !== "All categories" ? <Search /> : <Wallet />}
        </span>
        <h3>
          {query || category !== "All categories"
            ? "No matching expenses"
            : "A clean slate."}
        </h3>
        <p>
          {query || category !== "All categories"
            ? "Try another search or clear your filters."
            : "Start with a CSV from your bank, or add your first expense."}
        </p>
        <Button
          onClick={() =>
            query || category !== "All categories"
              ? clearFilters()
              : openInfo("Upload your first CSV")
          }
        >
          {query || category !== "All categories"
            ? "Clear filters"
            : "Upload CSV"}
        </Button>
      </div>
    );
  const resultFooter = (
    <div className="result-footer">
      <span>
        {sourceIds.length} transactions · {rows.length} allocation rows
      </span>
      <span>
        {category !== "All categories" || query
          ? "Summary reflects filters"
          : "All amounts are your share"}
      </span>
    </div>
  );
  const transactionTable = (
    <>
      {selectionBar}
      {rows.length === 0 ? (
        emptyState
      ) : (
        <>
          <div className="desktop-transactions">
            <table>
              <caption className="sr-only">
                Synthetic expense allocations for{" "}
                {month === "all" ? "all dates" : monthName}
              </caption>
              <thead>
                <tr>
                  <th className="check-cell">
                    <Checkbox
                      aria-label="Select all visible transactions"
                      checked={
                        sourceIds.every((id) => selected.has(id))
                          ? true
                          : sourceIds.some((id) => selected.has(id))
                            ? "indeterminate"
                            : false
                      }
                      onCheckedChange={(checked) =>
                        setSelected(checked ? new Set(sourceIds) : new Set())
                      }
                    />
                  </th>
                  <th>
                    <button
                      className="table-sort"
                      onClick={() =>
                        setSort(sort === "oldest" ? "newest" : "oldest")
                      }
                    >
                      Date <ChevronDown size={12} />
                    </button>
                  </th>
                  <th>Transaction</th>
                  <th>Category</th>
                  <th className="amount-cell">
                    <button
                      className="table-sort"
                      onClick={() => setSort("amount")}
                    >
                      Your amount <ArrowDownUp size={12} />
                    </button>
                  </th>
                  <th className="menu-cell">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} data-selected={selected.has(row.expenseId)}>
                    <td className="check-cell">
                      <Checkbox
                        aria-label={`Select ${row.receiver}, ${row.category}`}
                        checked={selected.has(row.expenseId)}
                        onCheckedChange={(checked) =>
                          toggleRow(row.expenseId, !!checked)
                        }
                      />
                    </td>
                    <td className="date-cell">
                      {shortMonth.slice(0, 3)} {row.day}
                    </td>
                    <td>
                      <div className="merchant-cell">
                        <CategoryIcon category={row.category} />
                        <div>
                          <button
                            className="merchant-name"
                            onClick={() => openInfo(`Edit ${row.receiver}`)}
                          >
                            {row.receiver}
                          </button>
                          <span className="row-detail">{row.detail}</span>
                        </div>
                      </div>
                    </td>
                    <td>
                      <Badge
                        variant="outline"
                        className={
                          row.category === "Uncategorized"
                            ? "uncategorized"
                            : "category-badge"
                        }
                      >
                        {row.category === "Uncategorized" && (
                          <span className="warning-dot" />
                        )}
                        {row.category}
                      </Badge>
                    </td>
                    <td
                      className={`amount-cell ${row.type === "income" ? "positive" : ""}`}
                    >
                      <strong>
                        {row.type === "income" ? "+" : ""}
                        {money(row.amount)}
                      </strong>
                      {row.note && <span className="row-note">{row.note}</span>}
                    </td>
                    <td className="menu-cell">{rowMenu(row)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mobile-transactions">
            {rows.map((row) => (
              <div
                className="mobile-row"
                key={row.id}
                data-selected={selected.has(row.expenseId)}
              >
                <Checkbox
                  aria-label={`Select ${row.receiver}, ${row.category}`}
                  checked={selected.has(row.expenseId)}
                  onCheckedChange={(checked) =>
                    toggleRow(row.expenseId, !!checked)
                  }
                />
                <CategoryIcon category={row.category} />
                <div className="mobile-row-copy">
                  <button
                    className="merchant-name"
                    onClick={() => openInfo(`Edit ${row.receiver}`)}
                  >
                    {row.receiver}
                  </button>
                  <span>
                    {shortMonth.slice(0, 3)} {row.day} · {row.category}
                  </span>
                  {row.note && <small>{row.note}</small>}
                </div>
                <strong className={row.type === "income" ? "positive" : ""}>
                  {row.type === "income" ? "+" : ""}
                  {money(row.amount)}
                </strong>
                {rowMenu(row)}
              </div>
            ))}
          </div>
        </>
      )}
      {resultFooter}
    </>
  );
  const topExpenses = (
    <section className="top-expenses">
      <div className="section-title">
        <h2>Largest expenses</h2>
        <span>Your share</span>
      </div>
      {topRows.length ? (
        topRows.map((row, index) => (
          <button
            className="top-expense"
            key={row.id}
            onClick={() => openInfo(`Edit ${row.receiver}`)}
          >
            <span className="rank">0{index + 1}</span>
            <div>
              <strong>{row.receiver}</strong>
              <small>{row.category}</small>
            </div>
            <strong>{money(-row.amount)}</strong>
          </button>
        ))
      ) : (
        <p className="muted-copy">No expenses to compare.</p>
      )}
    </section>
  );
  const categoryBreakdown = (
    <section className="category-breakdown">
      <div className="section-title">
        <h2>Where it went</h2>
        <Tag size={15} />
      </div>
      {breakdown.slice(0, 4).map(([name, amount], index) => (
        <button
          key={name}
          className="breakdown-item"
          onClick={() => {
            setCategory(name);
            setSelected(new Set());
          }}
        >
          <span>
            <i
              style={{
                background: ["#486b65", "#a2b7ac", "#cea57c", "#8d8f9b"][index],
              }}
            />
            {name}
            <strong>{money(amount)}</strong>
          </span>
          <span className="breakdown-track">
            <i
              style={{
                width: `${totals.spent ? (amount / totals.spent) * 100 : 0}%`,
                background: ["#486b65", "#a2b7ac", "#cea57c", "#8d8f9b"][index],
              }}
            />
          </span>
        </button>
      ))}
      {!breakdown.length && (
        <p className="muted-copy">No spending in this view.</p>
      )}
    </section>
  );

  const variantA = (
    <div className="layout-a">
      <aside className="sidebar">
        {brand}
        <p className="nav-heading">WORKSPACE</p>
        {navigation()}
        <div className="sidebar-bottom">
          <div className="workspace-note">
            <span className="workspace-icon">
              <Sparkles size={17} />
            </span>
            <strong>A clearer picture.</strong>
            <p>Every expense, in its place.</p>
            <span>Personal finance, without the noise.</span>
          </div>
          <button
            className="sidebar-help"
            onClick={() =>
              openInfo(
                "About this prototype",
                "Three visual directions for Expense Tracker. Real shadcn components, entirely synthetic data, no backend connection. Use the floating arrows to compare layouts.",
              )
            }
          >
            <CircleHelp size={17} />
            About this preview
          </button>
          {account}
        </div>
      </aside>
      <div className="a-workspace">
        <header className="workspace-header">
          <div>
            {mobileMenu}
            <span className="breadcrumb">
              Workspace <ChevronRight size={12} />
              <strong>Expenses</strong>
            </span>
          </div>
          <div>
            {previewControls}
            {themeButton}
          </div>
        </header>
        <main id="main-content" className="a-main">
          <div className="page-heading">
            <div>
              <p className="eyebrow">YOUR PERSONAL FINANCES</p>
              <h1>Expenses</h1>
              <p className="page-description">
                A clearer view of where your money goes.
              </p>
            </div>
            {actions}
          </div>
          <div className="period-row">
            {monthPicker}
            <span className="period-note">
              {month === "all" ? "All sample dates" : "Your month, at a glance"}
            </span>
          </div>
          {summary()}
          <div className="a-content-grid">
            <section className="transactions-panel">
              <div className="section-title">
                <h2>
                  Transactions{" "}
                  <span className="count-pill">{sourceIds.length}</span>
                </h2>
                <span>Personal share</span>
              </div>
              {filters}
              {transactionTable}
            </section>
            <aside className="insights-column">
              {topExpenses}
              {categoryBreakdown}
              <div className="sample-footnote">
                <Layers3 size={16} />
                <p>
                  Split expenses show your share. Category allocations stay
                  linked to their original transaction.
                </p>
              </div>
            </aside>
          </div>
        </main>
      </div>
    </div>
  );
  const variantB = (
    <div className="layout-b">
      <header className="ledger-header">
        <div>
          {mobileMenu}
          {brand}
        </div>
        {navigation(true)}
        <div>
          {themeButton}
          {account}
        </div>
      </header>
      <main id="main-content" className="ledger-main">
        <div className="ledger-meta">
          {previewControls}
          <span className="ledger-issue">PERSONAL FINANCE / 2026</span>
        </div>
        <div className="ledger-hero">
          <div>
            <p className="eyebrow">KEEPING TRACK, MAKING ROOM.</p>
            <h1>
              The monthly ledger<span>.</span>
            </h1>
          </div>
          <div className="ledger-hero-aside">
            <p>
              A little attention.
              <br />A lot more clarity.
            </p>
            {actions}
          </div>
        </div>
        <div className="ledger-period">
          <span className="ledger-section-number">01 / THE NUMBERS</span>
          {monthPicker}
        </div>
        {summary(true)}
        <div className="ledger-table-heading">
          <div>
            <p className="eyebrow">02 / THE DETAILS</p>
            <h2>Every little thing.</h2>
          </div>
          <span>{sourceIds.length} transactions in view</span>
        </div>
        <section className="ledger-transactions">
          {filters}
          {transactionTable}
        </section>
        <div className="ledger-bottom">
          {topExpenses}
          {categoryBreakdown}
        </div>
        <footer className="ledger-footer">
          <span>Expense Tracker</span>
          <span>Small details. Bigger picture.</span>
          <span>Synthetic data · no real account</span>
        </footer>
      </main>
    </div>
  );
  const variantC = (
    <div className="layout-c">
      <header className="overview-header">
        <div>
          {mobileMenu}
          {brand}
        </div>
        {navigation(true)}
        <div>
          {themeButton}
          {account}
        </div>
      </header>
      <main id="main-content" className="overview-main">
        <div className="overview-title">
          <div>
            <p className="eyebrow">MAKE SPACE FOR WHAT MATTERS</p>
            <h1>Your month, in focus.</h1>
          </div>
          {previewControls}
        </div>
        <div className="overview-grid">
          <aside className="month-overview">
            <div className="balance-panel">
              <span className="balance-kicker">
                <span className="live-dot" />
                MONTHLY BALANCE
              </span>
              <strong>
                {preview === "loading" || preview === "error"
                  ? "—"
                  : money(totals.balance)}
              </strong>
              <p>After expenses and savings.</p>
              <div className="balance-divider" />
              {stats.slice(0, 3).map((stat) => (
                <div className="balance-line" key={stat.label}>
                  <span>
                    <stat.icon size={16} />
                    {stat.label}
                  </span>
                  <strong>
                    {preview === "loading" || preview === "error"
                      ? "—"
                      : money(stat.amount)}
                  </strong>
                </div>
              ))}
              <span className="balance-footer">
                <Wallet size={14} />
                Your share · synthetic sample
              </span>
            </div>
            {categoryBreakdown}
            <div className="overview-note">
              <span>
                Less noise.
                <br />
                <em>More perspective.</em>
              </span>
              <p>
                A home for the details, so you can focus on the bigger picture.
              </p>
            </div>
          </aside>
          <section className="activity-panel">
            <div className="activity-heading">
              <div>
                <h2>Money in motion</h2>
                <p>Income, expenses, and everything between.</p>
              </div>
              {actions}
            </div>
            {monthPicker}
            {filters}
            {selectionBar}
            {rows.length === 0 ? (
              emptyState
            ) : (
              <div className="activity-days">
                {[...new Set(rows.map((row) => row.day))].map((day) => (
                  <section className="activity-day" key={day}>
                    <div className="activity-date">
                      <span>{shortMonth.slice(0, 3)}</span>
                      <strong>{day.toString().padStart(2, "0")}</strong>
                    </div>
                    <div className="activity-day-rows">
                      {rows
                        .filter((row) => row.day === day)
                        .map((row) => (
                          <div
                            className="activity-row"
                            key={row.id}
                            data-selected={selected.has(row.expenseId)}
                          >
                            <Checkbox
                              aria-label={`Select ${row.receiver}, ${row.category}`}
                              checked={selected.has(row.expenseId)}
                              onCheckedChange={(checked) =>
                                toggleRow(row.expenseId, !!checked)
                              }
                            />
                            <CategoryIcon category={row.category} />
                            <div className="activity-row-copy">
                              <button
                                className="merchant-name"
                                onClick={() => openInfo(`Edit ${row.receiver}`)}
                              >
                                {row.receiver}
                              </button>
                              <span>
                                {row.category}
                                {row.note ? ` · ${row.note}` : ""}
                              </span>
                            </div>
                            <strong
                              className={
                                row.type === "income" ? "positive" : ""
                              }
                            >
                              {row.type === "income" ? "+" : ""}
                              {money(row.amount)}
                            </strong>
                            {rowMenu(row)}
                          </div>
                        ))}
                    </div>
                  </section>
                ))}
              </div>
            )}
            {resultFooter}
          </section>
        </div>
      </main>
    </div>
  );
  const keys: Variant[] = ["A", "B", "C"];
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to expenses
      </a>
      {variant === "A" ? variantA : variant === "B" ? variantB : variantC}
      <Dialog
        open={info !== null}
        onOpenChange={(open) => !open && setInfo(null)}
      >
        <DialogContent
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            lastFocus.current?.focus();
          }}
        >
          <DialogHeader>
            <DialogTitle>{info?.title}</DialogTitle>
            <DialogDescription>{info?.body}</DialogDescription>
          </DialogHeader>
          <div className="prototype-dialog-note">
            <Badge variant="secondary">Prototype only</Badge>
            <p>No backend connected. No data is saved.</p>
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Back to preview</Button>
            </DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {import.meta.env.DEV && (
        <div
          className="prototype-switcher"
          aria-label="Prototype layout switcher"
        >
          <Button
            variant="ghost"
            size="icon"
            aria-label="Previous layout"
            onClick={() => setVariant(keys[(keys.indexOf(variant) + 2) % 3])}
          >
            <ChevronLeft />
          </Button>
          <div className="switcher-label" role="status">
            <span>SAMPLE DATA · {keys.indexOf(variant) + 1} / 3</span>
            <strong>
              {variant} — {layouts[variant]}
            </strong>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Next layout"
            onClick={() => setVariant(keys[(keys.indexOf(variant) + 1) % 3])}
          >
            <ChevronRight />
          </Button>
        </div>
      )}
    </>
  );
}
