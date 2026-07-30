from django.core.management.base import BaseCommand
from main.models import OjaUser
from main.services.bmoni_service import BMONIService


class Command(BaseCommand):
    help = 'Check wallet balance for a user by phone number'

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
        self.stdout.write(f"Local wallet balance: {user.wallet_balance or 0:,.2f}")
        
        if user.bmoni_user_id:
            self.stdout.write(f"BMONI User ID: {user.bmoni_user_id}")
            
            # Try to fetch BMONI wallet balance
            balance_result = BMONIService.get_balances(user.bmoni_user_id)
            if balance_result.get('success'):
                balances = balance_result.get('data', {}).get('balances', [])
                if balances:
                    for balance in balances:
                        currency = balance.get('currency', 'Unknown')
                        amount = balance.get('amount', '0')
                        self.stdout.write(f"BMONI {currency} balance: {amount}")
                else:
                    self.stdout.write("No BMONI wallet balances found")
            else:
                self.stdout.write(self.style.WARNING("Could not fetch BMONI balance"))
                self.stdout.write(f"Error: {balance_result.get('error', 'Unknown error')}")
        else:
            self.stdout.write(self.style.WARNING("User not synced with BMONI yet"))
