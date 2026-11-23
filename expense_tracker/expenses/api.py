from django.core.paginator import Paginator
from django.http import HttpRequest, JsonResponse
from django.urls import reverse

from .api_http import api_error, json_endpoint
from .expense_api import create_expense
from .expense_list import (
    ExpenseFilters,
    ExpenseListRow,
    month_key,
    picker_years,
    read_expense_list,
)
from .forms import SortForm

PAGE_SIZE = 50


def _row_json(row: ExpenseListRow) -> dict:
    expense = row.expense
    return {
        "id": expense.pk,
        "edit_url": reverse("expense_edit", args=[expense.pk]),
        "date": expense.date.isoformat(),
        "receiver": expense.receiver,
        "description": expense.description,
        "category": {"id": row.category.pk, "name": row.category.name}
        if row.category
        else None,
        "amount": f"{expense.get_source_amount():.2f}",
        "personal_share": f"{row.amount:.2f}",
    }


@json_endpoint("GET", "POST")
def expense_list(request: HttpRequest) -> JsonResponse:
    if request.method == "POST":
        return create_expense(request)

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
