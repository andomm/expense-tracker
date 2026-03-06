# Copilot Instructions for Expense Tracker

This is a Django-based expense tracking web application with user authentication, CSV import, and financial analytics.

## Architecture

**Project Structure:**
- `expense_tracker/` - Django project directory (settings, URLs, WSGI)
- `expense_tracker/expenses/` - Main Django app containing models, views, forms, and templates
- `manage.py` - Django management CLI at project root
- Python 3.13 with Django 5.2.7 and Plotly 6.4.0

**Key Components:**
- **Models**: Single `Expense` model with ForeignKey to Django's built-in User model (user-scoped, supports negative amounts for expenses and positive for income)
- **Views**: Function-based views with `@login_required` decorators for access control. Views handle CRUD operations, CSV uploads, and analytics
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

**Development server:**
```bash
cd expense_tracker
python manage.py runserver
```
Server runs on `http://127.0.0.1:8000/`

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

**Run tests:**
```bash
cd expense_tracker
python manage.py test
```

**Run specific test:**
```bash
cd expense_tracker
python manage.py test expenses.tests.TestClassName
```

**Database shell (interactive):**
```bash
cd expense_tracker
python manage.py dbshell
```

## Development Notes

- The project uses `uv` for dependency management (see `pyproject.toml`)
- Static files directory: `expense_tracker/expenses/static/`
- Templates directory: `expense_tracker/expenses/templates/expenses/` (app-level templates)
- Media uploads (if any) go to: `expense_tracker/media/`
- `DEBUG = True` in settings - remember to set `False` and configure `ALLOWED_HOSTS` before production
