from django.core.management.base import BaseCommand

from datasets.services import operations


class Command(BaseCommand):
    help = "Delete datasets (and their files) that have been idle for longer than DATASET_TTL_HOURS."

    def handle(self, *args, **options):
        removed = operations.purge_expired()
        self.stdout.write(self.style.SUCCESS(f"Removed {removed} expired dataset(s)."))
