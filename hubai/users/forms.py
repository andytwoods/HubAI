from django import forms
from django.conf import settings


class EventLoginForm(forms.Form):
    email = forms.EmailField()
    name = forms.CharField(max_length=255, required=False, help_text="Shown to your team. Optional.")
    passphrase = forms.CharField(
        min_length=6,
        max_length=128,
        widget=forms.PasswordInput,
        help_text="Choose one the first time you sign in; you'll need it to get back in.",
    )
    event_code = forms.CharField(max_length=64)

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_event_code(self):
        code = self.cleaned_data["event_code"].strip()
        if code.lower() != settings.EVENT_CODE.lower():
            raise forms.ValidationError("That event code isn't right.")
        return code
