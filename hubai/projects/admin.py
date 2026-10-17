from django.contrib import admin

from .models import Membership
from .models import Message
from .models import Project
from .models import Task


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["name", "join_code", "created_by", "created_at"]
    search_fields = ["name", "join_code"]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "project", "last_seen_at", "joined_at"]
    list_select_related = ["user", "project"]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["title", "project", "status", "claimed_by", "agent", "updated_at"]
    list_filter = ["status"]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["body", "project", "sender", "agent", "recipient", "created_at"]
