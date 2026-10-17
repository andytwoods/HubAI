from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import EventLoginForm


def login_view(request):
    """Email + shared event code signs you in, creating the account on first visit.

    Deliberately weak: anyone with the event code who knows your email can be you.
    Acceptable for a disposable hackathon tool; agents use per-membership tokens instead.
    """
    if request.user.is_authenticated:
        return redirect("projects:home")
    form = EventLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user, created = get_user_model().objects.get_or_create(email=form.cleaned_data["email"])
        if created:
            user.set_unusable_password()
        if form.cleaned_data["name"]:
            user.name = form.cleaned_data["name"]
        user.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        next_url = request.GET.get("next", "")
        if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        return redirect("projects:home")
    return render(request, "users/login.html", {"form": form}, status=422 if form.errors else 200)


@require_POST
def logout_view(request):
    logout(request)
    return redirect("users:login")
