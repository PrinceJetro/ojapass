from django.core.management.base import BaseCommand
from main.models import OjaUser


class Command(BaseCommand):
    help = 'Delete all users from the database (DANGEROUS - use with caution)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Must include this flag to confirm deletion'
        )

    def handle(self, *args, **options):
        if not options.get('confirm'):
            self.stdout.write(self.style.ERROR("This command is dangerous. Add --confirm to proceed."))
            return

        count = OjaUser.objects.count()
        self.stdout.write(f"About to delete {count} users...")
        self.stdout.write("Press Ctrl+C to cancel, or wait 5 seconds to proceed...")

        import time
        time.sleep(5)

        OjaUser.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} users from the database."))
