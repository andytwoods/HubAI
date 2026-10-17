from django.db import transaction
from django.db.models import Count

from hubai.projects.models import Message
from hubai.projects.models import Project


def delete_user_data(user):
    """Delete a user, the messages they and their agents sent, and projects left with no members."""
    with transaction.atomic():
        Message.objects.filter(sender__user=user).delete()
        project_ids = list(user.memberships.values_list("project_id", flat=True))
        user.delete()
        Project.objects.filter(pk__in=project_ids).annotate(n=Count("memberships")).filter(n=0).delete()
