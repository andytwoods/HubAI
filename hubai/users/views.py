from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from hubai.ratelimit import client_ip
from hubai.ratelimit import hit

from .forms import EventLoginForm
from .helpers import delete_user_data


def login_view(request):
    """Email + passphrase + shared event code signs you in, creating the account on first visit.

    The first sign-in with an email sets its passphrase; later sign-ins must match it. There is no
    email verification, so whoever signs in with an email first owns it: a wrong-passphrase error on
    your first visit means someone else got there first, which organisers can fix in the admin.
    Accounts created before passphrases existed set theirs on their next sign-in.
    """
    if request.user.is_authenticated:
        return redirect("projects:home")
    form = EventLoginForm(request.POST or None)
    if request.method == "POST":
        ip = client_ip(request)
        if hit("login-min", ip, 10, 60) or hit("login-hour", ip, 40, 3600):
            return render(request, "users/login.html", {"form": form, "rate_limited": True}, status=429)
    if request.method == "POST" and form.is_valid():
        user, created = get_user_model().objects.get_or_create(email=form.cleaned_data["email"])
        if user.is_staff or user.is_superuser or not user.is_active:
            form.add_error("email", "This account can't sign in here.")
            return render(request, "users/login.html", {"form": form}, status=422)
        if created or not user.has_usable_password():
            user.set_password(form.cleaned_data["passphrase"])
        elif not user.check_password(form.cleaned_data["passphrase"]):
            form.add_error("passphrase", "Wrong passphrase for this email.")
            return render(request, "users/login.html", {"form": form}, status=422)
        if form.cleaned_data["name"]:
            user.name = form.cleaned_data["name"]
        user.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        next_url = request.GET.get("next", "")
        if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        return redirect("projects:home")
    return render(request, "users/login.html", {"form": form}, status=422 if form.errors else 200)


@login_required
@require_POST
def delete_account(request):
    delete_user_data(request.user)
    logout(request)
    messages.success(request, "Your account, memberships and messages have been deleted.")
    return redirect("users:login")


def privacy(request):
    return render(request, "users/privacy.html")


def terms(request):
    return render(request, "users/terms.html")


@require_POST
def logout_view(request):
    logout(request)
    return redirect("projects:home")
