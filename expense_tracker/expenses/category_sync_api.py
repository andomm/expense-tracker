from django.http import HttpRequest, JsonResponse
from django.urls import reverse

from .api_http import MalformedRequest, json_endpoint, json_object
from .category_sync import latest_category_sync, record_category_sync
from .models import Expense


@json_endpoint("POST")
def start(request: HttpRequest) -> JsonResponse:
    if json_object(request):
        raise MalformedRequest("Category sync does not take filters or selections.")
    result = record_category_sync(request)
    return JsonResponse(
        {
            "result_id": result["id"],
            "result_url": reverse("sync_summary"),
            "counts": result["counts"],
        }
    )


@json_endpoint("GET")
def latest(request: HttpRequest) -> JsonResponse:
    result = latest_category_sync(request)
    if result is None:
        return JsonResponse({"result": None})

    previews = result["previews"]
    expense_ids = {row["id"] for group in previews.values() for row in group["rows"]}
    editable = set(
        Expense.objects.filter(user=request.user, pk__in=expense_ids).values_list(
            "pk", flat=True
        )
    )
    return JsonResponse(
        {
            "result": {
                **result,
                "previews": {
                    group: {
                        **preview,
                        "rows": [
                            {
                                **row,
                                "edit_url": reverse("expense_edit", args=[row["id"]])
                                if row["id"] in editable
                                else None,
                            }
                            for row in preview["rows"]
                        ],
                    }
                    for group, preview in previews.items()
                },
            }
        }
    )
