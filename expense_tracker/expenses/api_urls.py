from django.urls import path

from . import api, category_api, category_sync_api, expense_api
from . import expense_bulk_api as bulk

app_name = "api"
urlpatterns = [
    path("session/", api.session_status, name="session"),
    path("categories/", category_api.categories, name="categories"),
    path("categories/form-options/", category_api.form_options, name="category-form-options"),
    path("categories/<int:pk>/", category_api.category_detail, name="category-detail"),
    path("categories/sync/", category_sync_api.start, name="category-sync"),
    path("categories/sync/latest-result/", category_sync_api.latest, name="category-sync-latest"),
    path("expenses/", api.expense_list, name="expenses"),
    path(
        "expenses/form-options/",
        expense_api.expense_form_options,
        name="expense-form-options",
    ),
    path(
        "expenses/delete-all/",
        expense_api.expense_delete_all,
        name="expense-delete-all",
    ),
    path("expenses/preview/", expense_api.expense_preview, name="expense-preview"),
    path("expenses/<int:pk>/", expense_api.expense_detail, name="expense-detail"),
    path(
        "expenses/<int:pk>/preview/",
        expense_api.expense_preview,
        name="expense-preview",
    ),
    path("expenses/bulk/confirm/", bulk.confirm, name="expense-bulk-confirm"),
    path("expenses/bulk/delete/", bulk.apply, name="expense-bulk-delete"),
    path(
        "expenses/bulk/recategorize/",
        bulk.apply,
        {"recategorize": True},
        name="expense-bulk-recategorize",
    ),
]
