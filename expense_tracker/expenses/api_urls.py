from django.urls import path

from . import api

app_name = "api"
urlpatterns = [
    path("session/", api.session_status, name="session"),
    path("expenses/", api.expense_list, name="expenses"),
]
