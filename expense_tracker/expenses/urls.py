from django.urls import path

from .react_pages import react_host

urlpatterns = [
    path("", react_host, {"screen": "expenses"}, name="expense_list"),
    path("add/", react_host, {"screen": "expense-add"}, name="expense_add"),
    path("<int:pk>/edit/", react_host, {"screen": "expense-edit"}, name="expense_edit"),
    path("<int:pk>/delete/", react_host, {"screen": "expense-delete"}, name="expense_delete"),
    path("delete/", react_host, {"screen": "expense-delete-all"}, name="expense_delete_all"),
    path("upload/", react_host, {"screen": "csv-upload"}, name="upload_csv"),
    path("upload/summary/", react_host, {"screen": "csv-import-result"}, name="import_summary"),
    path("expenses-per-month/", react_host, {"screen": "analytics"}, name="expenses_per_month"),
    path("categories/", react_host, {"screen": "categories"}, name="category_list"),
    path("categories/sync/", react_host, {"screen": "category-sync"}, name="sync_categories"),
    path("categories/sync/summary/", react_host, {"screen": "category-sync-result"}, name="sync_summary"),
    path("categories/add/", react_host, {"screen": "category-add"}, name="category_add"),
    path("categories/<int:pk>/edit/", react_host, {"screen": "category-edit"}, name="category_edit"),
    path("categories/<int:pk>/delete/", react_host, {"screen": "category-delete"}, name="category_delete"),
]
