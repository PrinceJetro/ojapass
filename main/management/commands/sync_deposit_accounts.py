from django.core.management.base import BaseCommand
from main.models import OjaUser
from main.services.bmoni_service import BMONIService


class Command(BaseCommand):
    help = 'Sync all users local virtual account numbers with BMONI deposit accounts'

    def handle(self, *args, **options):
        users = OjaUser.objects.filter(bmoni_user_id__isnull=False).exclude(bmoni_user_id='')
        total = users.count()

        self.stdout.write(f"Found {total} users with BMONI IDs to sync")
        self.stdout.write("=" * 80)

        updated = 0
        failed = 0
        skipped = 0

        for user in users:
            self.stdout.write(f"\nProcessing: {user.email or 'N/A'} ({user.phone})")

            # Fetch BMONI deposit accounts
            deposit_result = BMONIService.get_deposit_accounts(user.bmoni_user_id, "NGN")

            if deposit_result.get('success'):
                accounts = deposit_result.get('data', {}).get('accounts', [])

                if accounts:
                    acc = accounts[0]  # Use first account
                    bmoni_account = acc.get('accountNumber')
                    bmoni_bank = acc.get('bankName')

                    if bmoni_account and bmoni_account != user.virtual_account_number:
                        user.virtual_account_number = bmoni_account
                        user.bank_name = bmoni_bank
                        user.save(update_fields=['virtual_account_number', 'bank_name'])
                        self.stdout.write(self.style.SUCCESS(f"  [UPDATED] {user.virtual_account_number} -> {bmoni_account} ({bmoni_bank})"))
                        updated += 1
                    else:
                        self.stdout.write(f"  [SKIP] Already up to date: {bmoni_account}")
                        skipped += 1
                else:
                    self.stdout.write(self.style.WARNING(f"  [SKIP] No BMONI deposit accounts found"))
                    skipped += 1
            else:
                self.stdout.write(self.style.ERROR(f"  [FAIL] Could not fetch BMONI accounts: {deposit_result.get('error', 'Unknown error')}"))
                failed += 1

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(f"Summary: Updated: {updated} | Skipped: {skipped} | Failed: {failed}")
