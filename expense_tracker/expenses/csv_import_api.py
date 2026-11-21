from django.http import HttpRequest, JsonResponse
from django.urls import reverse

from .api_http import MalformedRequest, api_error, json_endpoint
from .csv_import import latest_import, record_import
from .forms import CSVUploadForm
from .importers import CSVError


@json_endpoint("POST")
def start(request: HttpRequest) -> JsonResponse:
    if request.content_type != "multipart/form-data":
        raise MalformedRequest("Send the file and format as multipart form data.")
    if (
        len(request.FILES.getlist("file")) > 1
        or len(request.POST.getlist("import_format")) > 1
    ):
        raise MalformedRequest("Send one file and one format.")
    form = CSVUploadForm(request.POST, request.FILES)
    message = "Check the file and format. No expenses were imported."
    if not form.is_valid():
        return api_error("validation_failed", message, 422, fields=dict(form.errors))
    try:
        result = record_import(request, **form.cleaned_data)
    except CSVError as error:
        return api_error(
            "validation_failed",
            message,
            422,
            fields={"file": [str(error)]},
            row=error.row,
        )
    return JsonResponse(
        {
            "result_id": result["id"],
            "result_url": reverse("import_summary"),
            "counts": result["counts"],
        }
    )


@json_endpoint("GET")
def latest(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"result": latest_import(request)})
