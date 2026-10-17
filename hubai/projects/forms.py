from django import forms

from .models import Task


class ProjectForm(forms.Form):
    name = forms.CharField(max_length=120)


class JoinForm(forms.Form):
    join_code = forms.CharField(max_length=32)


class TaskForm(forms.Form):
    title = forms.CharField(max_length=200)
    description = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)


class MessageForm(forms.Form):
    body = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}))


class TaskStatusForm(forms.Form):
    status = forms.ChoiceField(choices=Task.Status.choices)
