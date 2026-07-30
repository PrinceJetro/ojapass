from django.core.management.base import BaseCommand
from main.models import OjaUser
from main.services.bmoni_service import BMONIService


class Command(BaseCommand):
    help = 'Delete a user from both BMONI and local database by phone number'

    def add_arguments(self, parser):
        parser.add_argument('phone', type=str, help='Phone number of the user to delete')

    def handle(self, *args, **options):
        phone = options['phone']

        try:
            user = OjaUser.objects.get(phone=phone)
        except OjaUser.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"User not found with phone: {phone}"))
            return

        self.stdout.write(f"Found user: {user.full_name} ({user.email or 'N/A'})")
        self.stdout.write(f"Phone: {user.phone}")
        self.stdout.write(f"BMONI ID: {user.bmoni_user_id or 'None'}")

        if not user.bmoni_user_id:
            self.stdout.write(self.style.WARNING("User has no BMONI ID - deleting from local database only"))
            user.delete()
            self.stdout.write(self.style.SUCCESS("User deleted from local database"))
            return

        # Delete from BMONI
        self.stdout.write("Deleting from BMONI...")
        delete_result = BMONIService.delete_user(user.bmoni_user_id)

        if delete_result and delete_result.get('success'):
            self.stdout.write(self.style.SUCCESS("User deleted from BMONI"))
            # Delete from local database
            user.delete()
            self.stdout.write(self.style.SUCCESS("User deleted from local database"))
        else:
            self.stdout.write(self.style.ERROR(f"Failed to delete from BMONI: {delete_result.get('error', 'Unknown error')}"))
            self.stdout.write("User NOT deleted from local database")
