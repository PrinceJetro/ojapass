import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from main.models import Loan, LoanRepayment, Notification
from main.services.oja_score import recalculate_ojascore

class Command(BaseCommand):
    help = 'Checks for overdue loan payments and applies penalties'

    def handle(self, *args, **kwargs):
        today = timezone.now().date()
        self.stdout.write(f"Running delinquency check for {today}...")

        # 1. Find newly missed payments (due_date < today and status == 'pending')
        missed_repayments = LoanRepayment.objects.filter(
            status='pending',
            due_date__lt=today
        )

        users_to_recalculate = set()

        for rep in missed_repayments:
            rep.status = 'missed'
            rep.save(update_fields=['status'])
            users_to_recalculate.add(rep.loan.user)
            
            self.stdout.write(self.style.WARNING(f"Marked Repayment {rep.id} as missed (Due: {rep.due_date})"))
            
            Notification.objects.create(
                user=rep.loan.user,
                message=f"WARNING: You missed your loan repayment of ₦{rep.amount_due:,.0f} due on {rep.due_date}. Your OjaScore has been penalized."
            )

        # 2. Find severe defaults (missed and due_date <= today - 7 days)
        seven_days_ago = today - datetime.timedelta(days=7)
        defaulted_repayments = LoanRepayment.objects.filter(
            status='missed',
            due_date__lte=seven_days_ago,
            loan__status='active'
        )

        for rep in defaulted_repayments:
            loan = rep.loan
            loan.status = 'defaulted'
            loan.save(update_fields=['status'])
            users_to_recalculate.add(loan.user)
            
            self.stdout.write(self.style.ERROR(f"Marked Loan {loan.id} as DEFAULTED (Repayment {rep.id} is > 7 days overdue)"))
            
            Notification.objects.create(
                user=loan.user,
                message=f"CRITICAL: Your loan for ₦{loan.principal:,.0f} has been marked as DEFAULTED. Your OjaScore has been severely penalized. Please repay immediately to restore your standing."
            )

        # 3. Recalculate OjaScores for affected users
        for user in users_to_recalculate:
            self.stdout.write(f"Recalculating score for {user.phone}...")
            recalculate_ojascore(user.id)

        self.stdout.write(self.style.SUCCESS("Delinquency check complete."))
