"""
URL configuration for expense_tracker project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from secrets import token_urlsafe

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.http import HttpRequest, HttpResponse
from django.middleware.csrf import rotate_token
from django.shortcuts import redirect
from django.urls import include, path
from expenses import views as expense_views
from expenses.react_pages import migrated_auth_page
from expenses.session_api import mark_logout


class AppLogoutView(auth_views.LogoutView):
    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        response = super().post(request, *args, **kwargs)
        rotate_token(request)
        mark_logout(response, token_urlsafe(16))
        return response


def home(request):
    if request.user.is_authenticated:
        return redirect('expense_list')
    return redirect('login')

urlpatterns = [
    path('', home),
    path('admin/', admin.site.urls),
    path('api/', include('expenses.api_urls')),

    path('expenses/', include('expenses.urls')),

    # Auth URLs
    path(
        "login/",
        migrated_auth_page("login", auth_views.LoginView.as_view(template_name="login.html")),
        name="login",
    ),
    path("logout/", AppLogoutView.as_view(next_page="login"), name="logout"),
    path("signup/", migrated_auth_page("signup", expense_views.signup), name="signup"),
]
