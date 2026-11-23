# Expense Tracker

A personal finance web app for tracking expenses and income, built with Django. Import transactions from your bank's CSV export, auto-categorize them, and visualize spending trends with interactive charts.

> Personal project built while learning Django.

## Screenshots

### Dashboard
![Main View](pictures/main_view.png)

The main dashboard shows **Total Spent**, **Income**, **Savings**, and **Balance** summary cards, a **Top Expenses** list, and a filterable transaction table with search, category, month, and year filters.

### Adding Expenses
![Add Expense](pictures/add_expense.png)

Manually log transactions with date, description, amount, receiver, and category. Supports **Splitting Rules** for shared costs and per-transaction **Split Categories** to allocate amounts across multiple categories.

### CSV Import
![Upload CSV](pictures/upload.png)

Bulk-import transactions from your bank's CSV export. Select your bank's file format and upload — transactions are auto-categorized based on your keyword rules.

### Categories
![Categories](pictures/categories.png)

Define custom categories with keyword-based auto-categorization. Assign a type (Expense, Income, Saving, Transfer) and keywords to match incoming transactions. Use **Sync existing expenses** to re-apply rules to historical data.

### Analytics
![Analytics](pictures/analytics.png)

Interactive Plotly charts showing daily vs. cumulative spending, monthly comparisons, spending by category, and cash flow over time. Includes a yearly summary table.

## Tech Stack

- **Python 3.13** / **Django 5.2**
- **Plotly 6.4** — interactive charts
- **SQLite** — local database
- **uv** — dependency management

## Getting Started

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20.19+ on Node 20, or 22.12+, and npm for React development

### Local development

Run from the checkout in a Linux or macOS shell. The runner uses a separate local SQLite file. Migrate it and create a test account first:

```bash
uv sync --locked
npm ci --prefix frontend
DB_PATH="$PWD/expense_tracker/pilot.sqlite3" uv run python expense_tracker/manage.py migrate
DB_PATH="$PWD/expense_tracker/pilot.sqlite3" uv run python expense_tracker/manage.py createsuperuser
uv run python scripts/dev.py
```

Open [http://127.0.0.1:8000/expenses/](http://127.0.0.1:8000/expenses/) and sign in. Use the Django URL as shown (not `localhost`). Django serves pages and the session-protected API; Vite serves development assets and refresh. Ctrl+C stops both servers. Set `DJANGO_PORT` and `VITE_PORT` to use other ports, or set an absolute `DB_PATH` for both setup and the runner to use a different database.

React is the local runner default for Expenses, Categories, CSV Import, Analytics, sign-in, and signup. React and legacy pages use the same Django session. If a session expires while editing, sign in again on the same page to recover the draft. Drafts are not saved across reloads, and signing in never resubmits a write. Django admin is unchanged.

To compare legacy pages locally, restart with `LEGACY_PAGES=1 uv run python scripts/dev.py`. This uses the same database and Django port without Node or Vite; it changes routing only and does not undo or replay writes. Plain Django `runserver` without the local runner also keeps legacy routing.

Focused checks:

```bash
work=$(mktemp -d)
DB_PATH="$work/expenses.sqlite3" uv run pytest --reuse-db \
  expense_tracker/expenses/test_pilot.py expense_tracker/expenses/test_expense_forms_api.py \
  expense_tracker/expenses/test_expense_deletion.py expense_tracker/expenses/test_expense_bulk_api.py \
  expense_tracker/expenses/test_category_sync.py expense_tracker/expenses/test_csv_import.py \
  expense_tracker/expenses/test_session_api.py
npm run build --prefix frontend
```

### Demo Data

A sample CSV file (`demo_data.csv`) is included with realistic dummy transactions in the OP bank format. Upload it via the CSV import page to quickly populate the app with data for testing.

## CSV Import Formats

Two bank export formats are supported:

### OP (Osuuspankki) CSV

Semicolon-delimited with Finnish column headers:

| Column | Description |
|---|---|
| `Arvopäivä` | Transaction date |
| `Selitys` | Description |
| `Määrä EUROA` | Amount (negative = expense, positive = income) |
| `Saaja/Maksaja` | Receiver / payer |
| `Viesti` | Message / note |

Decimal commas (`,`) are handled automatically.

### Spiir CSV

Semicolon-delimited export from the [Spiir](https://spiir.dk) app:

| Column | Description |
|---|---|
| `Date` | Transaction date (`DD-MM-YYYY`) |
| `Amount` | Amount |
| `Text` | Receiver / payer |
| `Note` | Description / note |
| `Category` | Category label |

## Running Tests

```bash
uv run --directory expense_tracker python manage.py test
```
