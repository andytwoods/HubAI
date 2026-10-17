import secrets

from django.conf import settings
from django.db import models

JOIN_WORDS = [
    "otter", "falcon", "maple", "comet", "pixel", "tiger", "cobalt", "ember", "lotus", "orbit",
    "raven", "quartz", "willow", "nebula", "badger", "cedar", "delta", "fjord", "gecko", "harbor",
]


def generate_join_code():
    return f"{secrets.choice(JOIN_WORDS).upper()}-{secrets.randbelow(9000) + 1000}"


def generate_token():
    return secrets.token_urlsafe(32)


class Project(models.Model):
    name = models.CharField(max_length=120)
    join_code = models.CharField(max_length=32, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Membership(models.Model):
    """A person in a project. Its token is what their AI agents authenticate with."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    token = models.CharField(max_length=64, unique=True, default=generate_token)
    # Highest message id this member's agents have already been handed by read_inbox.
    inbox_cursor = models.PositiveBigIntegerField(default=0)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "user"], name="unique_membership")]
        ordering = ["joined_at"]

    def __str__(self):
        return f"{self.user} in {self.project}"


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "To do"
        DOING = "doing", "Doing"
        BLOCKED = "blocked", "Blocked"
        DONE = "done", "Done"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TODO)
    created_by = models.ForeignKey(Membership, on_delete=models.SET_NULL, null=True, related_name="+")
    claimed_by = models.ForeignKey(
        Membership, on_delete=models.SET_NULL, null=True, blank=True, related_name="claimed_tasks"
    )
    agent = models.CharField(max_length=60, blank=True, help_text="Which agent of the claimer is on it")
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["project", "status"])]

    def __str__(self):
        return f"#{self.pk} {self.title}"


class Message(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(Membership, on_delete=models.SET_NULL, null=True, related_name="sent_messages")
    agent = models.CharField(max_length=60, blank=True, help_text="Blank when a human posted from the dashboard")
    # Null recipient means everyone in the project.
    recipient = models.ForeignKey(
        Membership, on_delete=models.CASCADE, null=True, blank=True, related_name="received_messages"
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["project", "id"])]

    def __str__(self):
        return self.body[:50]
