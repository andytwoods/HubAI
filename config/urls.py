from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("hubai.projects.urls", namespace="projects")),
    path("users/", include("hubai.users.urls", namespace="users")),
]
