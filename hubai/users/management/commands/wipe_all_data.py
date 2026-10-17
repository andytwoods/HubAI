from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from hubai.projects.models import Project


class Command(BaseCommand):
    help = "Delete every project, task, message and non-staff account (the promised post-event wipe)."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Required: confirms you mean it.")

    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError("This deletes all data. Re-run with --yes.")
        projects, _ = Project.objects.all().delete()
        users, _ = get_user_model().objects.filter(is_staff=False).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {projects} project rows and {users} user rows."))
