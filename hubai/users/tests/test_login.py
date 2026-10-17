import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_new_email_with_event_code_creates_account_and_signs_in(client):
    response = client.post(
        reverse("users:login"), {"email": "Ada@Example.com", "name": "Ada", "event_code": "TEST-EVENT"}
    )
    assert response.status_code == 302
    user = get_user_model().objects.get()
    assert user.email == "ada@example.com"
    assert user.name == "Ada"
    assert client.get(reverse("projects:home")).status_code == 200


def test_same_email_returns_to_existing_account(client):
    get_user_model().objects.create_user(email="ada@example.com", name="Ada")
    client.post(reverse("users:login"), {"email": "ada@example.com", "event_code": "test-event"})
    assert get_user_model().objects.count() == 1
    assert get_user_model().objects.get().name == "Ada"


def test_wrong_event_code_is_rejected(client):
    response = client.post(reverse("users:login"), {"email": "x@example.com", "event_code": "nope"})
    assert response.status_code == 422
    assert not get_user_model().objects.exists()


def test_next_redirect_rejects_other_hosts(client):
    url = reverse("users:login") + "?next=https://evil.example/"
    response = client.post(url, {"email": "x@example.com", "event_code": "test-event"})
    assert response.url == reverse("projects:home")


def test_login_attempts_are_rate_limited(client):
    from django.core.cache import cache

    cache.clear()
    codes = [
        client.post(reverse("users:login"), {"email": "x@example.com", "event_code": "wrong"}).status_code
        for _ in range(12)
    ]
    assert codes[0] == 422 and codes[-1] == 429


def test_pages_have_icons_and_link_preview(client):
    text = client.get(reverse("users:login")).text
    assert 'rel="icon"' in text and 'property="og:image" content="http://testserver/static/img/og.png"' in text
    assert client.get("/favicon.ico").status_code == 301


def test_staff_accounts_cannot_use_event_code_login(client):
    get_user_model().objects.create_superuser(email="admin@example.com", password="x")
    response = client.post(reverse("users:login"), {"email": "admin@example.com", "event_code": "test-event"})
    assert response.status_code == 422
    assert "_auth_user_id" not in client.session
