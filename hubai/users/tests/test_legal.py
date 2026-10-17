import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from hubai.projects.helpers import hub
from hubai.projects.models import Membership
from hubai.projects.models import Message
from hubai.projects.models import Project
from hubai.projects.models import Task

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("name", ["users:privacy", "users:terms"])
def test_legal_pages_are_public_and_show_deletion_date(client, name):
    response = client.get(reverse(name))
    assert response.status_code == 200
    assert "31 October 2026" in response.text


def test_login_page_links_terms_and_privacy(client):
    text = client.get(reverse("users:login")).text
    assert reverse("users:terms") in text and reverse("users:privacy") in text


def test_delete_account_removes_user_messages_and_empty_projects(client):
    User = get_user_model()
    ada = User.objects.create_user(email="ada@example.com")
    bob = User.objects.create_user(email="bob@example.com")
    shared = hub.create_project(ada, "Shared")
    hub.join_project(bob, shared.join_code)
    solo = hub.create_project(ada, "Solo")
    ada_m = Membership.objects.get(user=ada, project=shared)
    hub.post_message(ada_m, "from ada")
    hub.post_message(Membership.objects.get(user=bob), "from bob")
    hub.create_task(ada_m, "Ada's task")

    client.force_login(ada)
    response = client.post(reverse("users:delete_account"))

    assert response.url == reverse("users:login")
    assert not User.objects.filter(email="ada@example.com").exists()
    assert list(Message.objects.values_list("body", flat=True)) == ["from bob"]
    assert not Project.objects.filter(pk=solo.pk).exists()
    assert Project.objects.filter(pk=shared.pk).exists()
    assert Task.objects.get().created_by is None


def test_delete_account_requires_post(client):
    user = get_user_model().objects.create_user(email="ada@example.com")
    client.force_login(user)
    assert client.get(reverse("users:delete_account")).status_code == 405


def test_wipe_all_data_needs_yes_and_keeps_staff():
    User = get_user_model()
    User.objects.create_superuser(email="admin@example.com", password="x")
    hub.create_project(User.objects.create_user(email="ada@example.com"), "P")
    with pytest.raises(CommandError):
        call_command("wipe_all_data")
    call_command("wipe_all_data", "--yes")
    assert not Project.objects.exists()
    assert list(User.objects.values_list("email", flat=True)) == ["admin@example.com"]
