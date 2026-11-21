from django.urls import path
from . import views
from .react_pages import migrated_page

urlpatterns = [
    path("", migrated_page("expenses", views.expense_list), name="expense_list"),
    path("add/", migrated_page("expense-add", views.expense_add), name="expense_add"),
    path(
        "bulk-category-update/",
        views.expense_bulk_category_update,
        name="expense_bulk_category_update",
    ),
    path("bulk-delete/", views.expense_bulk_delete, name="expense_bulk_delete"),
    path(
        "<int:pk>/edit/",
        migrated_page("expense-edit", views.expense_edit),
        name="expense_edit",
    ),
    path(
        "<int:pk>/delete/",
        migrated_page("expense-delete", views.expense_delete),
        name="expense_delete",
    ),
    path(
        "delete/",
        migrated_page("expense-delete-all", views.expense_delete_all),
        name="expense_delete_all",
    ),
    path("upload/", migrated_page("csv-upload", views.upload_csv), name="upload_csv"),
    path(
        "upload/summary/",
        migrated_page("csv-import-result", views.import_summary),
        name="import_summary",
    ),
    path(
        "expenses-per-month/",
        migrated_page("analytics", views.expenses_per_month),
        name="expenses_per_month",
    ),
    path("categories/", migrated_page("categories", views.category_list), name="category_list"),
    path(
        "categories/sync/",
        migrated_page("category-sync", views.sync_categories),
        name="sync_categories",
    ),
    path(
        "categories/sync/summary/",
        migrated_page("category-sync-result", views.sync_summary),
        name="sync_summary",
    ),
    path(
        "categories/add/",
        migrated_page("category-add", views.category_add),
        name="category_add",
    ),
    path(
        "categories/<int:pk>/edit/",
        migrated_page("category-edit", views.category_edit),
        name="category_edit",
    ),
    path(
        "categories/<int:pk>/delete/",
        migrated_page("category-delete", views.category_delete),
        name="category_delete",
    ),
]
