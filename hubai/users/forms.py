from django import forms
from django.conf import settings


class EventLoginForm(forms.Form):
    email = forms.EmailField()
    name = forms.CharField(max_length=255, required=False, help_text="Shown to your team. Optional.")
    event_code = forms.CharField(max_length=64)

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_event_code(self):
        code = self.cleaned_data["event_code"].strip()
        if code.lower() != settings.EVENT_CODE.lower():
            raise forms.ValidationError("That event code isn't right.")
        return code
