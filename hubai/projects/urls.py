from django.urls import path

from . import mcp
from . import stats
from . import views

app_name = "projects"
urlpatterns = [
    path("", views.home, name="home"),
    path("mcp/", mcp.mcp_endpoint, name="mcp"),
    path("stats/", stats.stats, name="stats"),
    path("p/<int:pk>/", views.detail, name="detail"),
    path("p/<int:pk>/tasks/", views.task_create, name="task_create"),
    path("p/<int:pk>/tasks/<int:task_id>/status/", views.task_status, name="task_status"),
    path("p/<int:pk>/tasks/reorder/", views.task_reorder, name="task_reorder"),
    path("p/<int:pk>/tasks/<int:task_id>/", views.task_detail, name="task_detail"),
    path("p/<int:pk>/tasks/<int:task_id>/edit/", views.task_edit, name="task_edit"),
    path("p/<int:pk>/messages/", views.message_create, name="message_create"),
]
