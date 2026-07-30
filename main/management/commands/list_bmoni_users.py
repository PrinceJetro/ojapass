from django.core.management.base import BaseCommand
from main.models import OjaUser


class Command(BaseCommand):
    help = 'List users and their BMONI sync status'

    def handle(self, *args, **options):
        users = OjaUser.objects.all().order_by('id')
        
        self.stdout.write(self.style.SUCCESS(f"Total users: {users.count()}"))
        self.stdout.write("\n" + "=" * 80)
        
        for user in users:
            status = user.bmoni_sync_status or "pending"
            bmoni_id = user.bmoni_user_id or "None"
            attempts = user.bmoni_sync_attempts
            
            status_color = self.style.SUCCESS if status == "synced" else (
                self.style.WARNING if status == "pending" else self.style.ERROR
            )
            
            self.stdout.write(
                f"ID: {user.id} | Phone: {user.phone} | Email: {user.email or 'N/A'} | "
                f"BMONI ID: {bmoni_id} | Status: {status_color(status)} | "
                f"Attempts: {attempts}"
            )
            
            if user.bmoni_sync_error:
                self.stdout.write(f"  Error: {user.bmoni_sync_error}")
        
        self.stdout.write("\n" + "=" * 80)
        
        # Summary
        synced = users.filter(bmoni_sync_status='synced').count()
        pending = users.filter(bmoni_sync_status='pending').count()
        failed = users.filter(bmoni_sync_status='failed').count()
        
        self.stdout.write(f"Synced: {synced} | Pending: {pending} | Failed: {failed}")



