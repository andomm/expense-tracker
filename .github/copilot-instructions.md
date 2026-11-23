# Copilot Instructions for Expense Tracker

This is a Django-based expense tracking web application with user authentication, CSV import, and financial analytics.

## Architecture

**Project Structure:**
- `expense_tracker/` - Django project directory (settings, URLs, WSGI)
- `expense_tracker/expenses/` - Main Django app containing models, views, forms, and templates
- `expense_tracker/manage.py` - Django management CLI
- `frontend/` - React, TypeScript, Vite, shadcn/ui and Recharts

**Key Components:**
- **Models**: Single `Expense` model with ForeignKey to Django's built-in User model (user-scoped, supports negative amounts for expenses and positive for income)
- **Views**: Explicit app screen routes render a React host. Django JSON endpoints handle CRUD operations, CSV uploads and analytics.
- **Forms**: `ExpenseForm` (ModelForm), `SortForm` (for ordering), `CSVUploadForm` (file uploads)
- **Database**: SQLite3 (`db.sqlite3`) with standard Django auth system

**Key Conventions:**
- **Amount field**: Uses `DecimalField(max_digits=10, decimal_places=2)`. Negative values represent expenses, positive values represent income
- **User isolation**: All expense queries filter by `request.user` to ensure multi-user data isolation
- **CSV import**: Expects semicolon-delimited files with Finnish headers: "Arvopäivä", "Selitys", "Määrä EUROA", "Saaja/Maksaja", "Viesti"
  - Handles comma decimal separators by converting to dots
- **Authentication**: Uses Django's built-in `UserCreationForm` and `@login_required` decorator; login redirects to `/expenses/`, logout to `/login/`
- **URL routing**: Two-level routing - project URLs in `expense_tracker/urls.py`, app URLs in `expenses/urls.py`

## Build, Test & Run Commands

**Local Django and Vite servers:** follow the setup in [README.md](../README.md), then run `uv run python scripts/dev.py` from the checkout root.

**Run migrations:**
```bash
cd expense_tracker
python manage.py migrate
```

**Create superuser (admin access):**
```bash
cd expense_tracker
python manage.py createsuperuser
```

**Run tests from repository root:**
```bash
uv run pytest --reuse-db
```

**Run a focused test file:**
```bash
uv run pytest --reuse-db expense_tracker/expenses/test_analytics.py
```

**Database shell (interactive):**
```bash
cd expense_tracker
python manage.py dbshell
```

## Development Notes

- The project uses `uv` for dependency management (see `pyproject.toml`)
- App host template: `expense_tracker/expenses/templates/react_host.html`
- Media uploads (if any) go to: `expense_tracker/media/`
- `DEBUG = True` in settings - remember to set `False` and configure `ALLOWED_HOSTS` before production
