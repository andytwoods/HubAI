import json

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from hubai.projects.helpers import hub
from hubai.projects.models import Membership
from hubai.projects.models import Task

pytestmark = pytest.mark.django_db


@pytest.fixture
def team():
    User = get_user_model()
    ada = User.objects.create_user(email="ada@example.com", name="Ada")
    bob = User.objects.create_user(email="bob@example.com", name="Bob")
    project = hub.create_project(ada, "Rocket")
    hub.join_project(bob, project.join_code.lower())
    return project, Membership.objects.get(user=ada), Membership.objects.get(user=bob)


def rpc(client, token, method, params=None, msg_id=1):
    body = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if msg_id is not None:
        body["id"] = msg_id
    return client.post(
        reverse("projects:mcp"), json.dumps(body), content_type="application/json",
        headers={"Authorization": f"Bearer {token}"},
    )


def tool(client, token, name, **arguments):
    result = rpc(client, token, "tools/call", {"name": name, "arguments": arguments}).json()["result"]
    return result["isError"], result["content"][0]["text"]


def test_join_with_bad_code_fails(team):
    with pytest.raises(hub.HubError):
        hub.join_project(team[1].user, "NOPE-0000")


def test_home_creates_and_joins_projects(client, team):
    _, ada, _ = team
    client.force_login(ada.user)
    response = client.post(reverse("projects:home"), {"new-name": "Second"})
    assert response.status_code == 302
    response = client.post(reverse("projects:home"), {"join-join_code": "BAD-1"})
    assert response.status_code == 422


def test_detail_is_members_only(client, team):
    project, _, _ = team
    outsider = get_user_model().objects.create_user(email="eve@example.com")
    client.force_login(outsider)
    assert client.get(reverse("projects:detail", args=[project.pk])).status_code == 404


def test_detail_htmx_returns_partial(client, team):
    project, ada, _ = team
    client.force_login(ada.user)
    response = client.get(reverse("projects:detail", args=[project.pk]), headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Join code" not in response.text


def test_mcp_requires_token(client):
    assert rpc(client, "wrong", "tools/list").status_code == 401


def test_mcp_initialize_and_notification(client, team):
    _, ada, _ = team
    result = rpc(client, ada.token, "initialize", {"protocolVersion": "2025-06-18"}).json()["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert rpc(client, ada.token, "notifications/initialized", msg_id=None).status_code == 202
    names = {t["name"] for t in rpc(client, ada.token, "tools/list").json()["result"]["tools"]}
    assert {"claim_task", "post_message", "read_inbox"} <= names


def test_mcp_task_claiming_is_exclusive(client, team):
    _, ada, bob = team
    is_error, text = tool(client, ada.token, "create_task", title="Build login")
    task_id = json.loads(text)["id"]
    assert not tool(client, ada.token, "claim_task", task_id=task_id, agent="claude-1")[0]
    is_error, text = tool(client, bob.token, "claim_task", task_id=task_id)
    assert is_error and "already doing by Ada (claude-1)" in text
    is_error, text = tool(client, bob.token, "update_task", task_id=task_id, status="done")
    assert is_error and "held by Ada" in text
    tool(client, ada.token, "update_task", task_id=task_id, status="done", note="shipped", agent="claude-1")
    assert Task.objects.get().status == "done"


def test_mcp_doing_without_claim_is_refused(client, team):
    _, ada, _ = team
    task_id = json.loads(tool(client, ada.token, "create_task", title="X")[1])["id"]
    is_error, text = tool(client, ada.token, "update_task", task_id=task_id, status="doing")
    assert is_error and "claim_task" in text


def test_board_events_reach_other_agents(client, team):
    _, ada, bob = team
    task_id = json.loads(tool(client, ada.token, "create_task", title="Login")[1])["id"]
    tool(client, ada.token, "claim_task", task_id=task_id, agent="claude-1")
    inbox = json.loads(tool(client, bob.token, "read_inbox", agent="gemini")[1])
    assert inbox[0]["type"] == "board_event" and "claimed #" in inbox[0]["body"]
    assert json.loads(tool(client, ada.token, "read_inbox", agent="claude-1")[1]) == []


def test_mcp_messages_reach_inbox_once(client, team):
    _, ada, bob = team
    tool(client, ada.token, "post_message", body="API is at /api/v1", agent="claude-1")
    tool(client, ada.token, "post_message", body="psst bob", to="Bob", agent="claude-1")
    _, text = tool(client, bob.token, "read_inbox")
    assert [m["body"] for m in json.loads(text)] == ["API is at /api/v1", "psst bob"]
    assert json.loads(tool(client, bob.token, "read_inbox")[1]) == []
    assert json.loads(tool(client, ada.token, "read_inbox", agent="claude-1")[1]) == []


def test_agents_sharing_a_token_each_get_every_message(client, team):
    _, ada, bob = team
    tool(client, ada.token, "post_message", body="hello", to="everyone")
    for agent in ("claude-1", "claude-2"):
        assert [m["body"] for m in json.loads(tool(client, bob.token, "read_inbox", agent=agent)[1])] == ["hello"]


def test_humans_dashboard_message_reaches_own_agent(client, team):
    project, ada, _ = team
    client.force_login(ada.user)
    client.post(reverse("projects:message_create", args=[project.pk]), {"body": "focus on auth"})
    inbox = json.loads(tool(client, ada.token, "read_inbox", agent="claude-1")[1])
    assert [m["body"] for m in inbox] == ["focus on auth"]


def test_ambiguous_name_is_refused(team):
    project, ada, bob = team
    bob.user.name = "Ada"
    bob.user.save()
    with pytest.raises(hub.HubError, match="email"):
        hub.post_message(ada, "hi", to="ada")


def test_bad_arguments_are_tool_errors_not_500s(client, team):
    _, ada, _ = team
    assert tool(client, ada.token, "claim_task", task_id="abc")[0]
    assert tool(client, ada.token, "post_message", body=["x"])[0]
    assert tool(client, ada.token, "claim_task")[0]
    response = rpc(client, ada.token, "tools/call", {"name": "list_tasks", "arguments": "x"})
    assert response.json()["error"]["code"] == -32602
    assert rpc(client, ada.token, "tools/list", params=None).status_code == 200


def test_cross_site_origin_is_rejected(client, team):
    _, ada, _ = team
    response = client.post(
        reverse("projects:mcp"), json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}),
        content_type="application/json",
        headers={"Authorization": f"Bearer {ada.token}", "Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_mcp_unknown_recipient_is_tool_error(client, team):
    _, ada, _ = team
    is_error, text = tool(client, ada.token, "post_message", body="hi", to="nobody")
    assert is_error and "list_members" in text


def test_mcp_unknown_tool(client, team):
    _, ada, _ = team
    response = rpc(client, ada.token, "tools/call", {"name": "rm_rf", "arguments": {}}).json()
    assert response["error"]["code"] == -32602


def test_dashboard_posts_task_and_message(client, team):
    project, ada, _ = team
    client.force_login(ada.user)
    client.post(reverse("projects:task_create", args=[project.pk]), {"title": "Deploy"}, headers={"HX-Request": "1"})
    client.post(reverse("projects:message_create", args=[project.pk]), {"body": "hello"})
    task = Task.objects.get()
    client.post(reverse("projects:task_status", args=[project.pk, task.pk]), {"status": "doing"})
    task.refresh_from_db()
    assert task.status == "doing" and task.claimed_by == ada
    assert project.messages.filter(is_event=False).get().body == "hello"


def test_tool_calls_record_agent_presence_shown_on_dashboard(client, team):
    project, ada, _ = team
    tool(client, ada.token, "list_tasks", agent="workpc-worker")
    tool(client, ada.token, "read_inbox", agent="workpc-worker")
    rpc(client, ada.token, "tools/list")
    presence = ada.agents.get()
    assert (presence.agent, presence.last_tool, presence.calls) == ("workpc-worker", "read_inbox", 2)
    client.force_login(ada.user)
    text = client.get(reverse("projects:detail", args=[project.pk]), headers={"HX-Request": "1"}).text
    assert "workpc-worker" in text and "1 active" in text
