from django.urls import path

from . import api, expense_api

app_name = "api"
urlpatterns = [
    path("session/", api.session_status, name="session"),
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
]
