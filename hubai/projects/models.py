import secrets

from django.conf import settings
from django.db import models

JOIN_WORDS = [
    "otter", "falcon", "maple", "comet", "pixel", "tiger", "cobalt", "ember", "lotus", "orbit",
    "raven", "quartz", "willow", "nebula", "badger", "cedar", "delta", "fjord", "gecko", "harbor",
]


def generate_join_code():
    words = "-".join(secrets.choice(JOIN_WORDS).upper() for _ in range(3))
    return f"{words}-{secrets.randbelow(9000) + 1000}"


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
    last_seen_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "user"], name="unique_membership")]
        ordering = ["joined_at"]

    def __str__(self):
        return f"{self.user} in {self.project}"


class AgentPresence(models.Model):
    """One row per named agent per member: lets the dashboard show which agents are connected."""

    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="agents")
    agent = models.CharField(max_length=60)
    last_seen_at = models.DateTimeField()
    last_tool = models.CharField(max_length=40, blank=True)
    calls = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["membership", "agent"], name="unique_agent_presence")]
        ordering = ["-last_seen_at"]

    def __str__(self):
        return f"{self.agent} ({self.membership.user})"


class InboxCursor(models.Model):
    """How far one named agent has read. Agents sharing a token each keep their own place."""

    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="inbox_cursors")
    agent = models.CharField(max_length=60)
    last_id = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["membership", "agent"], name="unique_inbox_cursor")]

    def __str__(self):
        return f"{self.membership} / {self.agent} @ {self.last_id}"


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "To do"
        DOING = "doing", "Doing"
        BLOCKED = "blocked", "Postpone"  # the API value stays "blocked"
        DONE = "done", "Done"

    class Priority(models.TextChoices):
        HIGH = "high", "High"
        NORMAL = "normal", "Normal"
        LOW = "low", "Low"

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
    attempts = models.PositiveSmallIntegerField(default=0, help_text="How many times it has been claimed")
    # A label, and a placement: setting high moves the task to the top of its column, low to the bottom.
    priority = models.CharField(max_length=6, choices=Priority.choices, default=Priority.NORMAL)
    # Board order within a column (people drag cards on the dashboard). Workers take the lowest To do first.
    position = models.IntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "created_at"]
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
    # Posted by HubAI itself when the board changes, e.g. "Ada · claude-1 claimed #3".
    is_event = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["project", "id"])]

    def __str__(self):
        return self.body[:50]
