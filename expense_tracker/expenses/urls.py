from django.urls import path
from . import views

urlpatterns = [
    path("", views.expense_list, name="expense_list"),
    path("add/", views.expense_add, name="expense_add"),
    path(
        "bulk-category-update/",
        views.expense_bulk_category_update,
        name="expense_bulk_category_update",
    ),
    path("bulk-delete/", views.expense_bulk_delete, name="expense_bulk_delete"),
    path("<int:pk>/edit/", views.expense_edit, name="expense_edit"),
    path("<int:pk>/delete/", views.expense_delete, name="expense_delete"),
    path("delete/", views.expense_delete_all, name="expense_delete_all"),
    path("upload/", views.upload_csv, name="upload_csv"),
    path('upload/summary/', views.import_summary, name='import_summary'),
    path('expenses-per-month/', views.expenses_per_month, name='expenses_per_month'),
    path('categories/', views.category_list, name='category_list'),
    path('categories/sync/', views.sync_categories, name='sync_categories'),
    path('categories/sync/summary/', views.sync_summary, name='sync_summary'),
    path('categories/add/', views.category_add, name='category_add'),
    path('categories/<int:pk>/edit/', views.category_edit, name='category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),
]
