from django.conf import settings
from django.contrib import admin
from django.templatetags.static import static
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("favicon.ico", RedirectView.as_view(url=static("favicon.ico"), permanent=True)),
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("hubai.projects.urls", namespace="projects")),
    path("users/", include("hubai.users.urls", namespace="users")),
]
