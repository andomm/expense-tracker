from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.urls import reverse

from .api_http import MalformedRequest, api_error, json_endpoint, json_object
from .category_tree import category_groups
from .forms import CategoryForm
from .models import Category, MAX_CATEGORY_DEPTH


def _entry(category: Category, count: int) -> dict:
    return {
        "id": category.pk,
        "parent_id": category.parent_id,
        "name": category.name,
        "category_type": category.category_type,
        "type_label": category.get_category_type_display(),
        "keyword_count": count,
        "edit_url": reverse("category_edit", args=[category.pk]),
        "delete_url": reverse("category_delete", args=[category.pk]),
    }


@json_endpoint("GET", "POST")
def categories(request: HttpRequest) -> JsonResponse:
    if request.method == "POST":
        with transaction.atomic():
            return _save(request, Category(user=request.user), status=201)

    entries = []
    for group in category_groups(request.user):
        entries.append(_entry(group["parent"], group["parent_keyword_count"]))
        entries.extend(
            _entry(child["category"], child["keyword_count"]) for child in group["children"]
        )
    return JsonResponse({"categories": entries})


def _form_data(request: HttpRequest, category: Category) -> JsonResponse:
    form = CategoryForm(instance=category, user=request.user)
    parents = {int(value): label for value, label in form.fields["parent"].choices if value}
    return JsonResponse({
        "id": category.pk,
        "name": category.name,
        "category_type": category.category_type,
        "parent_id": category.parent_id if category.parent_id in parents else None,
        "keywords": category.keywords,
        "parent_choices": [{"id": value, "label": label} for value, label in parents.items()],
        "category_types": [
            {"id": value, "label": label} for value, label in Category.CATEGORY_TYPE_CHOICES
        ],
        "max_depth": MAX_CATEGORY_DEPTH,
    })


@json_endpoint("GET")
def form_options(request: HttpRequest) -> JsonResponse:
    return _form_data(request, Category(user=request.user))


@json_endpoint("GET", "PUT", "DELETE")
def category_detail(request: HttpRequest, pk: int) -> HttpResponse:
    categories = Category.objects.filter(user=request.user, pk=pk)
    if request.method in {"PUT", "DELETE"}:
        with transaction.atomic():
            category = categories.select_for_update().first()
            if category is not None:
                if request.method == "PUT":
                    return _save(request, category, status=200)
                # Both relations use SET_NULL, as on the legacy deletion page.
                category.delete()
                messages.success(request, f"Category '{category.name}' deleted.")
                return HttpResponse(status=204)
    else:
        category = categories.first()
        if category is not None:
            return _form_data(request, category)
    return api_error("not_found", "This category was not found.", 404)


def _save(request: HttpRequest, category: Category, *, status: int) -> JsonResponse:
    data = json_object(request)
    fields = {name: data.get(name, "") for name in ("name", "category_type", "keywords")}
    for name, value in fields.items():
        if not isinstance(value, str):
            raise MalformedRequest(f"{name} must be a string.")
    parent_id = data.get("parent_id")
    if parent_id is not None and type(parent_id) is not int:
        raise MalformedRequest("parent_id must be an ID or null.")
    form = CategoryForm({**fields, "parent": parent_id}, instance=category, user=request.user)
    if not form.is_valid():
        errors = {
            "parent_id" if name == "parent" else name: list(messages)
            for name, messages in form.errors.items()
        }
        return api_error("validation_failed", "Check the highlighted fields.", 422, fields=errors)

    saved = form.save()
    action = "created" if status == 201 else "updated"
    messages.success(request, f"Category '{saved.name}' {action}.")
    return JsonResponse({"id": saved.pk}, status=status)
