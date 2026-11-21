from collections.abc import Callable
from functools import wraps

from django.core.paginator import Paginator
from django.http import HttpRequest, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_cookie

from .expense_list import (
    ExpenseFilters,
    ExpenseListRow,
    month_key,
    picker_years,
    read_expense_list,
)
from .forms import SortForm

PAGE_SIZE = 50


def api_error(code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse({"code": code, "message": message}, status=status)


def json_read(*, login_required: bool = True):
    def decorate(view: Callable[[HttpRequest], JsonResponse]):
        @never_cache
        @vary_on_cookie
        @wraps(view)
        def read(request: HttpRequest) -> JsonResponse:
            if request.method not in {"GET", "HEAD"}:
                response = api_error(
                    "method_not_allowed", "This endpoint is read-only.", 405
                )
                response.headers["Allow"] = "GET, HEAD"
                return response
            if login_required and not request.user.is_authenticated:
                return api_error("sign_in_required", "Sign in to continue.", 401)
            return view(request)

        return read

    return decorate


@json_read(login_required=False)
def session_status(request: HttpRequest) -> JsonResponse:
    user = request.user
    return JsonResponse(
        {
            "user": {"id": user.pk, "username": user.get_username()}
            if user.is_authenticated
            else None,
            "csrf_token": get_token(request),
        }
    )


def _row_json(row: ExpenseListRow) -> dict:
    expense = row.expense
    return {
        "id": expense.pk,
        "date": expense.date.isoformat(),
        "receiver": expense.receiver,
        "description": expense.description,
        "category": {"id": row.category.pk, "name": row.category.name}
        if row.category
        else None,
        "amount": f"{expense.get_source_amount():.2f}",
        "personal_share": f"{row.amount:.2f}",
    }


@json_read()
def expense_list(request: HttpRequest) -> JsonResponse:
    params = request.GET
    try:
        number = int(params.get("page", "1"))
        if number < 1:
            raise ValueError
    except ValueError:
        return api_error("invalid_page", "Page must be a positive whole number.", 400)

    form = SortForm(params, user=request.user)
    filters = ExpenseFilters.from_params(params, form)
    listing = read_expense_list(request.user, filters, form.categories)
    page = Paginator(listing.rows, PAGE_SIZE).get_page(number)
    years = picker_years(request.user, filters.current_month)

    return JsonResponse(
        {
            "filters": {
                "month": filters.period,
                "search": filters.search,
                "category_filter": filters.category_filter or "all",
                "order_by": filters.order_by,
            },
            "months": {
                "current": month_key(filters.current_month),
                "previous": filters.previous,
                "next": filters.next,
                "min_year": years.start,
                "max_year": years.stop - 1,
            },
            "categories": [
                {"value": value or "all", "label": label}
                for value, label in form.fields["category_filter"].choices
            ],
            "pagination": {
                "page": page.number,
                "page_size": PAGE_SIZE,
                "pages": page.paginator.num_pages,
                "count": page.paginator.count,
            },
            "rows": [_row_json(row) for row in page],
            "summary": {
                key: f"{value:.2f}" for key, value in listing.summary().items()
            },
            "top_expenses": [_row_json(row) for row in listing.top_expenses()],
        }
    )
