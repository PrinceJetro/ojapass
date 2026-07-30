from django.core.management.base import BaseCommand
from main.services.bmoni_service import BMONIService


class Command(BaseCommand):
    help = 'Check if a user exists in BMONI by email or phone'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, help='Email to check')
        parser.add_argument('--phone', type=str, help='Phone to check')

    def handle(self, *args, **options):
        email = options.get('email')
        phone = options.get('phone')

        if not email and not phone:
            self.stdout.write(self.style.ERROR("Please provide --email or --phone"))
            return

        self.stdout.write(f"Checking BMONI for user...")
        if email:
            self.stdout.write(f"Email: {email}")
        if phone:
            self.stdout.write(f"Phone: {phone}")

        result = BMONIService.find_user_by_email_or_phone(email=email, phone=phone)

        if result and result.get('success'):
            user_data = result.get('data', {}).get('user', {})
            self.stdout.write(self.style.SUCCESS(f"User found in BMONI!"))
            self.stdout.write(f"BMONI User ID: {user_data.get('bmoniUserId')}")
            self.stdout.write(f"Email: {user_data.get('email')}")
            self.stdout.write(f"Phone: {user_data.get('phone')}")
            self.stdout.write(f"First Name: {user_data.get('firstName')}")
            self.stdout.write(f"Last Name: {user_data.get('lastName')}")
            self.stdout.write(f"Status: {user_data.get('status')}")
        else:
            self.stdout.write(self.style.WARNING("User not found in BMONI"))
            if result:
                self.stdout.write(f"Error: {result.get('error')}")
