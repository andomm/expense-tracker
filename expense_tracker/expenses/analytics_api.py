from django.http import HttpRequest, JsonResponse

from .analytics import read_analytics
from .api_http import json_endpoint


@json_endpoint("GET")
def analytics(request: HttpRequest) -> JsonResponse:
    return JsonResponse(read_analytics(request.user, request.GET.get("month", "")))
