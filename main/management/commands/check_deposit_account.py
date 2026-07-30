from django.core.management.base import BaseCommand
from main.models import OjaUser
from main.services.bmoni_service import BMONIService


class Command(BaseCommand):
    help = 'Check BMONI deposit account for a user by phone number'

    def add_arguments(self, parser):
        parser.add_argument('phone', type=str, help='Phone number of the user')

    def handle(self, *args, **options):
        phone = options['phone']

        try:
            user = OjaUser.objects.get(phone=phone)
        except OjaUser.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"User not found with phone: {phone}"))
            return

        self.stdout.write(self.style.SUCCESS(f"User: {user.full_name} ({user.email or 'N/A'})"))
        self.stdout.write(f"Phone: {user.phone}")
        self.stdout.write(f"Local virtual account: {user.virtual_account_number or 'None'}")
        self.stdout.write(f"Local bank name: {user.bank_name or 'None'}")

        if user.bmoni_user_id:
            self.stdout.write(f"BMONI User ID: {user.bmoni_user_id}")

            # Try to fetch BMONI deposit accounts
            deposit_result = BMONIService.get_deposit_accounts(user.bmoni_user_id, "NGN")
            if deposit_result.get('success'):
                accounts = deposit_result.get('data', {}).get('accounts', [])
                if accounts:
                    self.stdout.write(self.style.SUCCESS(f"Found {len(accounts)} deposit account(s):"))
                    for acc in accounts:
                        self.stdout.write(f"  Account Number: {acc.get('accountNumber')}")
                        self.stdout.write(f"  Bank Name: {acc.get('bankName')}")
                        self.stdout.write(f"  Account Name: {acc.get('accountName')}")
                        self.stdout.write(f"  Currency: {acc.get('currency')}")
                else:
                    self.stdout.write(self.style.WARNING("No BMONI deposit accounts found"))
            else:
                self.stdout.write(self.style.WARNING("Could not fetch BMONI deposit accounts"))
                self.stdout.write(f"Error: {deposit_result.get('error', 'Unknown error')}")
        else:
            self.stdout.write(self.style.WARNING("User not synced with BMONI yet"))
