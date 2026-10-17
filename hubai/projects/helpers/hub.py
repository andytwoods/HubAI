"""Business logic shared by the dashboard views and the MCP endpoint."""

from django.db import IntegrityError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from django.db.models import F

from hubai.projects.models import AgentPresence
from hubai.projects.models import InboxCursor
from hubai.projects.models import Membership
from hubai.projects.models import Message
from hubai.projects.models import Project
from hubai.projects.models import Task
from hubai.projects.models import generate_join_code


BROADCAST_NAMES = {"", "everyone", "all", "team"}
DEFAULT_AGENT = "agent"
MAX_BODY = 4000
INBOX_LIMIT = 50


class HubError(Exception):
    """A request the caller can fix; the message is safe to show to a person or an agent."""


def create_project(user, name):
    for _ in range(10):
        try:
            with transaction.atomic():
                project = Project.objects.create(name=name, join_code=generate_join_code(), created_by=user)
                Membership.objects.create(project=project, user=user)
        except IntegrityError:
            continue
        return project
    raise HubError("Couldn't generate a unique join code, try again.")


def join_project(user, join_code):
    try:
        project = Project.objects.get(join_code__iexact=join_code.strip())
    except Project.DoesNotExist:
        raise HubError("No project has that join code.") from None
    Membership.objects.get_or_create(project=project, user=user)
    return project


def touch(membership, agent="", tool=""):
    now = timezone.now()
    Membership.objects.filter(pk=membership.pk).update(last_seen_at=now)
    if not tool:
        return
    agent = agent[:60] or DEFAULT_AGENT
    updated = AgentPresence.objects.filter(membership=membership, agent=agent).update(
        last_seen_at=now, last_tool=tool[:40], calls=F("calls") + 1
    )
    if not updated:
        try:
            with transaction.atomic():
                AgentPresence.objects.create(
                    membership=membership, agent=agent, last_seen_at=now, last_tool=tool[:40], calls=1
                )
        except IntegrityError:
            pass  # a concurrent first call created it


def find_member(project, who):
    """Resolve an email or display name to a membership in this project."""
    who = who.strip().lower()
    matches = [
        member
        for member in project.memberships.select_related("user")
        if who in (member.user.email.lower(), member.user.display_name.lower())
    ]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise HubError(f"More than one person is called '{who}'. Use their email instead.")
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


def _holder(task):
    if not task.claimed_by:
        return ""
    return f" by {task.claimed_by.user}" + (f" ({task.agent})" if task.agent else "")


def _announce(membership, agent, text):
    Message.objects.create(project=membership.project, sender=membership, agent=agent[:60], body=text, is_event=True)


def _actor(membership, agent):
    return f"{membership.user}" + (f" · {agent}" if agent else "")


def claim_task(membership, task_id, agent=""):
    """Atomically take a to-do task. Fails if someone else got there first."""
    task = get_task(membership.project, task_id)
    claimed = Task.objects.filter(pk=task.pk, status=Task.Status.TODO).update(
        status=Task.Status.DOING, claimed_by=membership, agent=agent[:60], updated_at=timezone.now()
    )
    task.refresh_from_db()
    if not claimed:
        raise HubError(
            f"Task #{task.pk} is already {task.get_status_display().lower()}{_holder(task)}. "
            "Pick another task or post_message them."
        )
    _announce(membership, agent, f"{_actor(membership, agent)} claimed #{task.pk} {task.title}")
    return task


def update_task(membership, task_id, status, note=None, agent="", override=False):
    """Change a task's status. Agents may only change tasks they hold; humans on the dashboard can override."""
    if status not in Task.Status.values:
        raise HubError(f"Status must be one of: {', '.join(Task.Status.values)}.")
    with transaction.atomic():
        try:
            task = membership.project.tasks.select_for_update().get(pk=task_id)
        except Task.DoesNotExist:
            raise HubError(f"No task #{task_id} in this project.") from None
        if not override:
            if task.claimed_by_id and task.claimed_by_id != membership.pk:
                raise HubError(f"Task #{task.pk} is held{_holder(task)}. Ask them with post_message.")
            if task.claimed_by_id is None and status == Task.Status.DOING:
                raise HubError(f"Use claim_task to start task #{task.pk}.")
        status_changed = task.status != status
        task.status = status
        if status == Task.Status.TODO:
            task.claimed_by = None
            task.agent = ""
        elif task.claimed_by is None:
            task.claimed_by = membership
            task.agent = agent[:60]
        if note is not None:
            task.note = note[:MAX_BODY]
        task.save()
    # Progress notes on an unchanged status stay on the card; only status changes go to everyone's inbox.
    if status_changed:
        _announce(membership, agent, f"{_actor(membership, agent)} set #{task.pk} {task.title} to {task.status}")
    return task


def post_message(membership, body, to="", agent=""):
    body = body.strip()
    if not body:
        raise HubError("Message is empty.")
    if len(body) > MAX_BODY:
        raise HubError(f"Message is over {MAX_BODY} characters. Summarise, or put details in a file in the repo.")
    recipient = None if to.strip().lower() in BROADCAST_NAMES else find_member(membership.project, to)
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


def _unread(membership, agent, last_id):
    # Everything except what this same agent posted, so a human's dashboard messages reach their own agents.
    return visible_messages(membership).filter(id__gt=last_id).exclude(sender=membership, agent=agent)


def read_inbox(membership, agent=""):
    """Up to INBOX_LIMIT new messages for this agent, then move its read cursor past them."""
    agent = agent[:60] or DEFAULT_AGENT
    with transaction.atomic():
        cursor, _ = InboxCursor.objects.get_or_create(membership=membership, agent=agent)
        cursor = InboxCursor.objects.select_for_update().get(pk=cursor.pk)
        new = list(_unread(membership, agent, cursor.last_id)[:INBOX_LIMIT])
        if new:
            cursor.last_id = new[-1].id
            cursor.save(update_fields=["last_id"])
    return new


def unread_count(membership, agent=""):
    agent = agent[:60] or DEFAULT_AGENT
    cursor = InboxCursor.objects.filter(membership=membership, agent=agent).first()
    return _unread(membership, agent, cursor.last_id if cursor else 0).count()


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
        "type": "board_event" if message.is_event else "message",
        "body": message.body,
        "at": message.created_at.isoformat(),
    }
