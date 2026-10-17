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
    assert is_error and "already in progress by Ada (claude-1)" in text
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


def test_progress_note_updates_card_without_inbox_event(client, team):
    _, ada, bob = team
    task_id = json.loads(tool(client, ada.token, "create_task", title="Login")[1])["id"]
    tool(client, ada.token, "claim_task", task_id=task_id, agent="w")
    tool(client, bob.token, "read_inbox")
    tool(client, ada.token, "update_task", task_id=task_id, status="doing", note="step 2/4: tests written", agent="w")
    assert Task.objects.get().note == "step 2/4: tests written"
    assert json.loads(tool(client, bob.token, "read_inbox")[1]) == []


def test_list_tasks_reports_creator_email(client, team):
    _, ada, bob = team
    tool(client, bob.token, "create_task", title="From Bob")
    tasks = json.loads(tool(client, ada.token, "list_tasks")[1])
    assert tasks[0]["created_by"] == "bob@example.com"


def test_mcp_rate_limits_per_member(client, team, settings):
    from django.core.cache import cache

    cache.clear()
    _, ada, _ = team
    codes = [rpc(client, ada.token, "ping").status_code for _ in range(245)]
    assert codes.count(200) == 240 and codes[-1] == 429


def test_bad_tokens_are_rate_limited(client):
    from django.core.cache import cache

    cache.clear()
    codes = [rpc(client, "nope", "ping").status_code for _ in range(32)]
    assert codes[0] == 401 and codes[-1] == 429


def test_others_cannot_change_an_unclaimed_task(client, team):
    _, ada, bob = team
    task_id = json.loads(tool(client, ada.token, "create_task", title="Ada's")[1])["id"]
    is_error, text = tool(client, bob.token, "update_task", task_id=task_id, status="todo", note="ignore previous")
    assert is_error and "isn't yours" in text
    assert Task.objects.get().note == ""


def test_agent_names_are_capped_per_member(client, team):
    _, ada, _ = team
    for i in range(20):
        assert not tool(client, ada.token, "whoami", agent=f"a{i}")[0]
    is_error, text = tool(client, ada.token, "whoami", agent="one-too-many")
    assert is_error and "Too many agent names" in text
    assert not tool(client, ada.token, "whoami", agent="a3")[0]


def test_root_shows_landing_page_to_visitors(client):
    response = client.get(reverse("projects:home"))
    assert response.status_code == 200
    assert "How it works" in response.text and reverse("users:login") in response.text


def test_empty_blocked_column_is_hidden(client, team):
    project, ada, _ = team
    client.force_login(ada.user)
    url = reverse("projects:detail", args=[project.pk])
    assert "Blocked" not in client.get(url, headers={"HX-Request": "1"}).text
    task = hub.create_task(ada, "Stuck")
    hub.update_task(ada, task.pk, "blocked", override=True)
    assert "Blocked" in client.get(url, headers={"HX-Request": "1"}).text


def test_failed_attempt_returns_task_then_blocks_after_three(client, team):
    _, ada, _ = team
    task_id = json.loads(tool(client, ada.token, "create_task", title="Flaky")[1])["id"]
    for attempt in (1, 2):
        tool(client, ada.token, "claim_task", task_id=task_id, agent="w")
        is_error, text = tool(client, ada.token, "release_task", task_id=task_id, reason="crashed", agent="w")
        assert not is_error and json.loads(text)["status"] == "todo"
    tool(client, ada.token, "claim_task", task_id=task_id, agent="w")
    released = json.loads(tool(client, ada.token, "release_task", task_id=task_id, reason="crashed", agent="w")[1])
    assert released["status"] == "blocked" and released["attempts"] == 3 and "needs a human" in released["note"]


def test_only_the_holder_can_release(client, team):
    _, ada, bob = team
    task_id = json.loads(tool(client, ada.token, "create_task", title="Mine")[1])["id"]
    tool(client, ada.token, "claim_task", task_id=task_id, agent="w")
    is_error, text = tool(client, bob.token, "release_task", task_id=task_id, reason="x")
    assert is_error and "aren't working on" in text


def test_silent_agent_task_is_released(client, team):
    from datetime import timedelta

    from django.utils import timezone

    from hubai.projects.models import AgentPresence

    _, ada, bob = team
    task_id = json.loads(tool(client, ada.token, "create_task", title="Abandoned")[1])["id"]
    tool(client, ada.token, "claim_task", task_id=task_id, agent="dead-worker")
    long_ago = timezone.now() - timedelta(minutes=30)
    Task.objects.filter(pk=task_id).update(updated_at=long_ago)
    AgentPresence.objects.filter(agent="dead-worker").update(last_seen_at=long_ago)
    todo = json.loads(tool(client, bob.token, "list_tasks", status="todo")[1])
    assert [t["id"] for t in todo] == [task_id]
    assert "silent" in Task.objects.get().note


def test_active_agent_and_human_claims_are_not_released(client, team):
    from datetime import timedelta

    from django.utils import timezone

    project, ada, bob = team
    busy = json.loads(tool(client, ada.token, "create_task", title="Busy")[1])["id"]
    tool(client, ada.token, "claim_task", task_id=busy, agent="live-worker")  # presence is fresh
    human = hub.create_task(ada, "Human doing it")
    hub.update_task(ada, human.pk, "doing", override=True)  # dashboard: no agent
    Task.objects.update(updated_at=timezone.now() - timedelta(minutes=30))
    assert hub.release_stale_tasks(project) == 0


def test_stats_needs_the_key(client, team, settings):
    settings.STATS_KEY = "s3cret"
    assert client.get(reverse("projects:stats")).status_code == 404
    assert client.get(reverse("projects:stats"), {"key": "wrong"}).status_code == 404
    data = client.get(reverse("projects:stats"), {"key": "s3cret"}).json()
    assert data["users"] == 2 and data["projects"][0]["members"] == 2


def test_dragging_reorders_a_column_and_can_change_status(client, team):
    project, ada, _ = team
    client.force_login(ada.user)
    first, second, third = (hub.create_task(ada, t) for t in ("one", "two", "three"))
    assert [t.title for t in project.tasks.all()] == ["one", "two", "three"]
    url = reverse("projects:task_reorder", args=[project.pk])
    client.post(url, {"status": "todo", "ids": f"{third.pk},{first.pk},{second.pk}"}, headers={"HX-Request": "1"})
    assert [t.title for t in project.tasks.all()] == ["three", "one", "two"]
    # Dropped into Doing: it changes status (as a human override) and keeps its place.
    response = client.post(url, {"status": "doing", "ids": str(second.pk)}, headers={"HX-Request": "1"})
    second.refresh_from_db()
    assert second.status == "doing" and second.claimed_by == ada
    assert "set #%d two to doing" % second.pk in response.text
    # list_tasks follows the board order, so a worker takes the top To do card first.
    _, text = tool(client, ada.token, "list_tasks", status="todo")
    assert [t["title"] for t in json.loads(text)] == ["three", "one"]


def test_reorder_rejects_tasks_from_other_projects(client, team):
    project, ada, bob = team
    other = hub.create_project(bob.user, "Other")
    foreign = hub.create_task(Membership.objects.get(project=other, user=bob.user), "theirs")
    mine = hub.create_task(ada, "mine")
    client.force_login(ada.user)
    url = reverse("projects:task_reorder", args=[project.pk])
    with pytest.raises(hub.HubError, match="doesn't match"):
        hub.reorder_tasks(ada, [mine.pk, foreign.pk], "doing")
    client.post(url, {"status": "doing", "ids": f"{mine.pk},{foreign.pk}"})
    foreign.refresh_from_db()
    mine.refresh_from_db()
    assert foreign.status == "todo" and mine.status == "todo"


def test_task_modal_shows_full_text_and_saves_edits(client, team):
    project, ada, bob = team
    task = hub.create_task(ada, "Ship it", "Long brief " * 50)
    client.force_login(bob.user)
    page = client.get(reverse("projects:task_detail", args=[project.pk, task.pk])).text
    assert "Long brief " * 50 in page and 'value="Ship it"' in page
    client.post(
        reverse("projects:task_edit", args=[project.pk, task.pk]),
        {"title": "Ship it today", "description": "New brief", "note": "started"},
        headers={"HX-Request": "1"},
    )
    task.refresh_from_db()
    assert (task.title, task.description, task.note) == ("Ship it today", "New brief", "started")
    assert project.messages.filter(is_event=True).last().body == f"Bob edited #{task.pk} Ship it today"
    # A note-only change is a progress update, not a new brief, so agents aren't pinged.
    client.post(reverse("projects:task_edit", args=[project.pk, task.pk]),
                {"title": "Ship it today", "description": "New brief", "note": "nearly"})
    assert project.messages.filter(is_event=True).count() == 1
    # A blank title is refused and the task is left alone.
    client.post(reverse("projects:task_edit", args=[project.pk, task.pk]), {"title": " ", "description": "", "note": ""})
    task.refresh_from_db()
    assert task.title == "Ship it today"


def test_task_modal_is_members_only(client, team):
    project, ada, _ = team
    task = hub.create_task(ada, "Private")
    User = get_user_model()
    client.force_login(User.objects.create_user(email="eve@example.com", name="Eve"))
    assert client.get(reverse("projects:task_detail", args=[project.pk, task.pk])).status_code == 404
    assert client.post(reverse("projects:task_edit", args=[project.pk, task.pk]), {"title": "Pwned"}).status_code == 404


def test_agents_can_set_priority(client, team):
    project, ada, bob = team
    one, two, three = (hub.create_task(ada, t) for t in ("one", "two", "three"))
    # High at creation goes straight to the top; low to the bottom.
    _, text = tool(client, bob.token, "create_task", title="urgent", priority="high", agent="bob-1")
    assert json.loads(text)["priority"] == "high"
    tool(client, bob.token, "create_task", title="someday", priority="low")
    assert [t.title for t in project.tasks.all()] == ["urgent", "one", "two", "three", "someday"]
    # Priority alone, on a task Bob neither created nor holds, is allowed and announced.
    err, text = tool(client, bob.token, "update_task", task_id=three.pk, priority="high", agent="bob-1")
    assert not err and json.loads(text)["priority"] == "high"
    assert [t.title for t in project.tasks.all()] == ["three", "urgent", "one", "two", "someday"]
    assert project.messages.filter(is_event=True).last().body == f"Bob · bob-1 set #{three.pk} three priority to high"
    # But status still needs ownership.
    err, text = tool(client, bob.token, "update_task", task_id=one.pk, status="done", priority="low")
    assert err and "isn't yours" in text
    err, text = tool(client, bob.token, "update_task", task_id=one.pk, priority="urgent")
    assert err and "Priority must be one of" in text
    err, text = tool(client, bob.token, "update_task", task_id=one.pk)
    assert err and "Give a status" in text
    # The dashboard modal can change it too, and the card shows the tag.
    client.force_login(ada.user)
    client.post(reverse("projects:task_edit", args=[project.pk, two.pk]),
                {"title": "two", "description": "", "note": "", "priority": "low"})
    board = client.get(reverse("projects:detail", args=[project.pk]), headers={"HX-Request": "1"}).text
    assert board.count("low priority") == 2 and board.count("high priority") == 2
    assert [t.title for t in project.tasks.all()] == ["three", "urgent", "one", "someday", "two"]


def test_unchanged_board_poll_returns_no_content(client, team):
    project, ada, _ = team
    client.force_login(ada.user)
    url = reverse("projects:detail", args=[project.pk])
    page = client.get(url).text
    digest = page.split('id="board-hash" data-hash="')[1][:16]
    assert client.get(url, {"h": digest}, headers={"HX-Request": "1"}).status_code == 204
    assert client.get(url, {"h": "stale"}, headers={"HX-Request": "1"}).status_code == 200
    hub.create_task(ada, "Something new")
    fresh = client.get(url, {"h": digest}, headers={"HX-Request": "1"})
    assert fresh.status_code == 200 and "Something new" in fresh.text and digest not in fresh.text
