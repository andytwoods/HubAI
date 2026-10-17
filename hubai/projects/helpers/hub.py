"""Business logic shared by the dashboard views and the MCP endpoint."""

from django.db import IntegrityError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from hubai.projects.models import Membership
from hubai.projects.models import Message
from hubai.projects.models import Project
from hubai.projects.models import Task
from hubai.projects.models import generate_join_code


class HubError(Exception):
    """A request the caller can fix; the message is safe to show to a person or an agent."""


def create_project(user, name):
    for _ in range(10):
        try:
            with transaction.atomic():
                project = Project.objects.create(name=name, join_code=generate_join_code(), created_by=user)
        except IntegrityError:
            continue
        Membership.objects.create(project=project, user=user)
        return project
    raise HubError("Couldn't generate a unique join code, try again.")


def join_project(user, join_code):
    try:
        project = Project.objects.get(join_code__iexact=join_code.strip())
    except Project.DoesNotExist:
        raise HubError("No project has that join code.") from None
    Membership.objects.get_or_create(project=project, user=user)
    return project


def touch(membership):
    Membership.objects.filter(pk=membership.pk).update(last_seen_at=timezone.now())


def find_member(project, who):
    """Resolve an email or display name to a membership in this project."""
    who = who.strip().lower()
    for member in project.memberships.select_related("user"):
        if who in (member.user.email.lower(), member.user.display_name.lower()):
            return member
    raise HubError(f"No one called '{who}' in this project. Call list_members to see who is.")


def get_task(project, task_id):
    try:
        return project.tasks.get(pk=task_id)
    except Task.DoesNotExist:
        raise HubError(f"No task #{task_id} in this project.") from None


def create_task(membership, title, description=""):
    title = title.strip()
    if not title:
        raise HubError("A task needs a title.")
    return Task.objects.create(
        project=membership.project, title=title[:200], description=description, created_by=membership
    )


def claim_task(membership, task_id, agent=""):
    """Atomically take a to-do task. Fails if someone else got there first."""
    task = get_task(membership.project, task_id)
    claimed = Task.objects.filter(pk=task.pk, status=Task.Status.TODO).update(
        status=Task.Status.DOING, claimed_by=membership, agent=agent[:60], updated_at=timezone.now()
    )
    task.refresh_from_db()
    if not claimed:
        holder = f" by {task.claimed_by.user}" if task.claimed_by else ""
        raise HubError(f"Task #{task.pk} is already {task.get_status_display().lower()}{holder}.")
    return task


def update_task(membership, task_id, status, note=None):
    task = get_task(membership.project, task_id)
    if status not in Task.Status.values:
        raise HubError(f"Status must be one of: {', '.join(Task.Status.values)}.")
    task.status = status
    if status == Task.Status.TODO:
        task.claimed_by = None
        task.agent = ""
    elif task.claimed_by is None:
        task.claimed_by = membership
    if note is not None:
        task.note = note
    task.save()
    return task


def post_message(membership, body, to="", agent=""):
    body = body.strip()
    if not body:
        raise HubError("Message is empty.")
    recipient = find_member(membership.project, to) if to else None
    return Message.objects.create(
        project=membership.project, sender=membership, agent=agent[:60], recipient=recipient, body=body
    )


def visible_messages(membership):
    """Broadcasts plus direct messages to or from this member."""
    return (
        membership.project.messages.filter(
            Q(recipient__isnull=True) | Q(recipient=membership) | Q(sender=membership)
        )
        .select_related("sender__user", "recipient__user")
        .order_by("id")
    )


def read_inbox(membership):
    """Messages from others since the last read, then move the read cursor past them."""
    with transaction.atomic():
        member = Membership.objects.select_for_update().get(pk=membership.pk)
        new = list(visible_messages(member).filter(id__gt=member.inbox_cursor).exclude(sender=member))
        if new:
            member.inbox_cursor = new[-1].id
            member.save(update_fields=["inbox_cursor"])
    return new


def unread_count(membership):
    return visible_messages(membership).filter(id__gt=membership.inbox_cursor).exclude(sender=membership).count()


def task_dict(task):
    return {
        "id": task.pk,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "claimed_by": str(task.claimed_by.user) if task.claimed_by else None,
        "agent": task.agent or None,
        "note": task.note or None,
        "updated_at": task.updated_at.isoformat(),
    }


def message_dict(message):
    return {
        "id": message.id,
        "from": str(message.sender.user) if message.sender else None,
        "agent": message.agent or None,
        "to": str(message.recipient.user) if message.recipient else "everyone",
        "body": message.body,
        "at": message.created_at.isoformat(),
    }
