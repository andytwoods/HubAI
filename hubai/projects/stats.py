"""Private usage counts for the organiser: /stats/?key=<HUBAI_STATS_KEY>. 404 unless the key matches."""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db.models.functions import TruncHour
from django.http import Http404
from django.http import JsonResponse
from django.utils import timezone

from hubai.projects.models import AgentPresence
from hubai.projects.models import Message
from hubai.projects.models import Project
from hubai.projects.models import Task


def stats(request):
    key = settings.STATS_KEY
    if not key or not secrets.compare_digest(request.GET.get("key", ""), key):
        raise Http404
    now = timezone.now()
    users = get_user_model().objects.filter(is_staff=False)
    day_ago = now - timedelta(hours=24)
    signups = (
        users.filter(date_joined__gte=day_ago).annotate(hour=TruncHour("date_joined")).values("hour")
        .annotate(n=Count("id")).order_by("hour")
    )
    projects = Project.objects.annotate(n_members=Count("memberships", distinct=True), n_tasks=Count("tasks", distinct=True))
    return JsonResponse({
        "users": users.count(),
        "signups_last_24h_by_hour": {s["hour"].strftime("%H:00"): s["n"] for s in signups},
        "projects": [{"members": p.n_members, "tasks": p.n_tasks, "created": p.created_at.strftime("%d %b %H:%M")}
                     for p in projects.order_by("created_at")],
        "agents_active_last_hour": AgentPresence.objects.filter(last_seen_at__gte=now - timedelta(hours=1)).count(),
        "tasks_by_status": dict(Task.objects.values_list("status").annotate(n=Count("id"))),
        "messages": Message.objects.filter(is_event=False).count(),
    }, json_dumps_params={"indent": 1})
