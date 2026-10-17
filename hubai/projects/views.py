from django.contrib import messages
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from hubai.ratelimit import client_ip
from hubai.ratelimit import hit

from .forms import JoinForm
from .forms import MessageForm
from .forms import ProjectForm
from .forms import TaskForm
from .forms import TaskStatusForm
from .helpers import hub
from .models import AgentPresence
from .models import Membership
from .models import Task


@login_required
def home(request):
    project_form = ProjectForm(prefix="new")
    join_form = JoinForm(prefix="join")
    if request.method == "POST":
        if "new-name" in request.POST:
            project_form = ProjectForm(request.POST, prefix="new")
            if hit("new-project", request.user.pk, 10, 3600):
                project_form.add_error(None, "You've created a lot of projects. Wait an hour.")
            elif project_form.is_valid():
                project = hub.create_project(request.user, project_form.cleaned_data["name"])
                return redirect("projects:detail", pk=project.pk)
        else:
            join_form = JoinForm(request.POST, prefix="join")
            if hit("join", request.user.pk, 10, 600) or hit("join-ip", client_ip(request), 20, 600):
                join_form.add_error(None, "Too many join attempts. Wait ten minutes.")
                join_form.is_valid()
            elif join_form.is_valid():
                try:
                    project = hub.join_project(request.user, join_form.cleaned_data["join_code"])
                except hub.HubError as exc:
                    join_form.add_error("join_code", str(exc))
                else:
                    return redirect("projects:detail", pk=project.pk)
    memberships = request.user.memberships.select_related("project")
    context = {"memberships": memberships, "project_form": project_form, "join_form": join_form}
    status = 422 if project_form.errors or join_form.errors else 200
    return render(request, "projects/home.html", context, status=status)


def _membership(request, pk):
    return get_object_or_404(Membership.objects.select_related("project", "user"), project_id=pk, user=request.user)


def _live_context(membership):
    project = membership.project
    active_since = timezone.now() - timedelta(minutes=10)
    tasks = project.tasks.select_related("claimed_by__user")
    columns = [(value, label, [t for t in tasks if t.status == value]) for value, label in Task.Status.choices]
    return {
        "membership": membership,
        "project": project,
        "columns": columns,
        "chat": list(hub.visible_messages(membership).order_by("-id")[:50]),
        "members": project.memberships.select_related("user"),
        "active_since": active_since,
        "agents": AgentPresence.objects.filter(membership__project=project).select_related("membership__user"),
        "online_count": AgentPresence.objects.filter(
            membership__project=project, last_seen_at__gte=active_since
        ).count(),
        "status_choices": Task.Status.choices,
    }


@login_required
def detail(request, pk):
    membership = _membership(request, pk)
    context = _live_context(membership)
    if request.headers.get("HX-Request"):
        return render(request, "projects/partials/_live.html", context)
    mcp_url = request.build_absolute_uri(reverse("projects:mcp"))
    context |= {"mcp_url": mcp_url, "task_form": TaskForm(), "message_form": MessageForm()}
    return render(request, "projects/detail.html", context)


def _too_fast(request):
    if hit("dashboard-post", request.user.pk, 30, 60):
        messages.error(request, "Slow down: too many posts in a minute.")
        return True
    return False


def _respond(request, membership):
    if request.headers.get("HX-Request"):
        return render(request, "projects/partials/_live.html", _live_context(membership))
    return redirect("projects:detail", pk=membership.project_id)


@login_required
@require_POST
def task_create(request, pk):
    membership = _membership(request, pk)
    form = TaskForm(request.POST)
    if _too_fast(request):
        pass
    elif form.is_valid():
        hub.create_task(membership, form.cleaned_data["title"], form.cleaned_data["description"])
    else:
        messages.error(request, "A task needs a title.")
    return _respond(request, membership)


@login_required
@require_POST
def task_status(request, pk, task_id):
    membership = _membership(request, pk)
    form = TaskStatusForm(request.POST)
    if not _too_fast(request) and form.is_valid():
        try:
            hub.update_task(membership, task_id, form.cleaned_data["status"], override=True)
        except hub.HubError as exc:
            messages.error(request, str(exc))
    return _respond(request, membership)


@login_required
@require_POST
def message_create(request, pk):
    membership = _membership(request, pk)
    form = MessageForm(request.POST)
    if not _too_fast(request) and form.is_valid():
        hub.post_message(membership, form.cleaned_data["body"])
    return _respond(request, membership)
