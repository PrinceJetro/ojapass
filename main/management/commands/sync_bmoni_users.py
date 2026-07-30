from django.core.management.base import BaseCommand
from main.models import OjaUser
from main.services.bmoni_service import BMONIService


class Command(BaseCommand):
    help = 'Retry BMONI user creation for accounts that failed to sync'

    def handle(self, *args, **options):
        pending = OjaUser.objects.filter(bmoni_sync_status__in=['pending', 'failed'])
        self.stdout.write(f"Found {pending.count()} users to sync")
        
        for user in pending:
            self.stdout.write(f"Attempting to sync {user.email} (phone: {user.phone})")
            
            # Prepare user data for BMONI
            first_name = user.full_name.split()[0] if user.full_name else ''
            last_name = user.full_name.split()[-1] if user.full_name and len(user.full_name.split()) > 1 else ''
            
            bmoni_user_data = {
                "firstName": first_name,
                "lastName": last_name,
                "phone": user.phone,
                "email": user.email,
                "bvn": user.bvn,
                "address": user.address,
            }

            result = BMONIService.create_user(bmoni_user_data)

            if result.get("success") and result.get("data", {}).get("user"):
                user.bmoni_user_id = result["data"]["user"].get("bmoniUserId")
                user.bmoni_sync_status = "synced"
                user.bmoni_sync_error = None
                user.save()
                self.stdout.write(self.style.SUCCESS(f"[OK] Synced {user.email} - BMONI ID: {user.bmoni_user_id}"))
            elif result.get("status_code") == 409:
                # Already exists on BMONI - try to find existing user
                existing_user = BMONIService.find_user_by_email_or_phone(
                    email=user.email,
                    phone=user.phone
                )
                if existing_user:
                    user.bmoni_user_id = existing_user.get("bmoniUserId")
                    user.bmoni_sync_status = "synced"
                    user.bmoni_sync_error = None
                    user.save()
                    self.stdout.write(self.style.SUCCESS(f"[OK] Found existing BMONI user for {user.email}"))
                else:
                    user.bmoni_sync_attempts += 1
                    user.bmoni_sync_error = "Conflict - user may already exist on BMONI"
                    user.save()
                    self.stdout.write(self.style.WARNING(f"[WARN] 409 Conflict for {user.email} - could not find existing user"))
            else:
                user.bmoni_sync_attempts += 1
                user.bmoni_sync_error = result.get("error", "Unknown error")
                user.save()
                self.stdout.write(self.style.ERROR(f"[FAIL] Still failing for {user.email}: {result.get('error')}"))

        self.stdout.write(self.style.SUCCESS("Sync complete"))
