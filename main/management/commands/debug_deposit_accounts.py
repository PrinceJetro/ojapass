from django.core.management.base import BaseCommand
from main.models import OjaUser
from main.services.bmoni_service import BMONIService
import json


class Command(BaseCommand):
    help = 'Debug BMONI deposit account responses for all users'

    def handle(self, *args, **options):
        users = OjaUser.objects.filter(bmoni_user_id__isnull=False).exclude(bmoni_user_id='')

        for user in users:
            self.stdout.write(f"\n{'='*80}")
            self.stdout.write(f"User: {user.email or 'N/A'} ({user.phone})")
            self.stdout.write(f"BMONI ID: {user.bmoni_user_id}")

            deposit_result = BMONIService.get_deposit_accounts(user.bmoni_user_id, "NGN")
            self.stdout.write(f"Raw response: {json.dumps(deposit_result, indent=2)}")
