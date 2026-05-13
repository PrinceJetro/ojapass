from django.core.management.base import BaseCommand
from django.utils import timezone
from main.models import AjoGroup, AjoCycle, AjoContribution, AjoMembership, Notification
from main.services.oja_score import recalculate_ojascore
from decimal import Decimal

class Command(BaseCommand):
    help = 'Processes automated Ajo contributions and handles penalties for missed payments'

    def handle(self, *args, **options):
        self.stdout.write("Starting Ajo processing...")
        now = timezone.now()
        
        # 1. Find all active cycles that are past their due date
        overdue_cycles = AjoCycle.objects.filter(status__in=['open', 'collecting'], due_date__lte=now)
        
        for cycle in overdue_cycles:
            self.stdout.write(f"Processing overdue cycle {cycle.id} for group {cycle.group.name}")
            
            # 2. Process each pending contribution in the cycle
            pending_contributions = cycle.contributions.filter(status='pending')
            
            for contrib in pending_contributions:
                user = contrib.member
                amount = contrib.amount
                
                # Attempt Auto-Debit from Wallet Balance
                if user.wallet_balance >= amount:
                    user.wallet_balance -= amount
                    user.save()
                    
                    contrib.status = 'paid'
                    contrib.paid_at = now
                    contrib.auto_debit_attempted = True
                    contrib.save()
                    
                    # Update Membership Stats
                    membership = AjoMembership.objects.filter(group=cycle.group, user=user).first()
                    if membership:
                        membership.total_contributed += amount
                        membership.last_payment_date = now
                        membership.save()
                    
                    Notification.objects.create(
                        user=user,
                        message=f"Auto-debit of ₦{amount} for Ajo group '{cycle.group.name}' successful."
                    )
                    recalculate_ojascore(user.id)
                    self.stdout.write(f"Successfully auto-debited {user.phone} for {amount}")
                else:
                    # INSUFFICIENT FUNDS - Penalty Logic
                    contrib.status = 'defaulted'
                    contrib.auto_debit_attempted = True
                    contrib.save()
                    
                    # Penalize OjaScore
                    user.ojapass_score = max(0, user.ojapass_score - 20)
                    user.ojapass_narrative = f"Score dropped due to missed Ajo contribution in '{cycle.group.name}'."
                    user.save()
                    
                    # Update Membership Stats
                    membership = AjoMembership.objects.filter(group=cycle.group, user=user).first()
                    if membership:
                        membership.missed_payments += 1
                        membership.cycles_defaulted += 1
                        membership.save()
                    
                    Notification.objects.create(
                        user=user,
                        message=f"FAILED: Auto-debit for Ajo group '{cycle.group.name}' failed due to insufficient funds. Your OjaScore has been penalized."
                    )
                    self.stdout.write(f"Auto-debit FAILED for {user.phone}. Score penalized.")

            # 3. Check if cycle can be disbursed (if all paid or if we proceed with partial)
            # For this simple logic, if we reached due date, we try to disburse whatever was collected
            total_collected = sum(c.amount for c in cycle.contributions.filter(status='paid'))
            cycle.collected_amount = total_collected
            
            if total_collected > 0:
                # In a real system, you'd trigger SquadService.process_transfer here
                # For now, we update the cycle status
                cycle.status = 'collecting' # Or 'disbursed' if you call the service
                cycle.save()
                self.stdout.write(f"Cycle {cycle.id} processed. Total collected: {total_collected}")
            else:
                cycle.status = 'defaulted'
                cycle.save()
                self.stdout.write(f"Cycle {cycle.id} DEFAULTED. No contributions collected.")

        self.stdout.write("Ajo processing complete.")
