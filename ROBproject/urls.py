from django.contrib import admin
from django.urls import path
from controlapp.views import index, login_view, logout_view, control_view, settings_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", index, name="index"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("control/", control_view, name="control"),
    path("settings/", settings_view, name="settings"), 
]
