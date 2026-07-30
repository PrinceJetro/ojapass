from django.core.management.base import BaseCommand
from main.models import PaymentLink
from main.views.payment_views import _confirm_transaction


class Command(BaseCommand):
    help = 'Manually confirm a payment link as paid (for development/testing)'

    def add_arguments(self, parser):
        parser.add_argument('transaction_ref', type=str, help='Transaction reference to confirm')

    def handle(self, *args, **options):
        transaction_ref = options['transaction_ref']
        link = PaymentLink.objects.filter(transaction_ref=transaction_ref).first()
        
        if not link:
            self.stdout.write(self.style.ERROR(f"Payment link not found: {transaction_ref}"))
            return
        
        if link.status == 'paid':
            self.stdout.write(self.style.WARNING(f"Payment link already paid: {transaction_ref}"))
            return
        
        # Manually confirm the payment
        result = _confirm_transaction(transaction_ref, float(link.amount), {"type": "invoice_payment"})
        
        if result.get('user'):
            self.stdout.write(self.style.SUCCESS(f"Payment confirmed: {transaction_ref} for ₦{link.amount}"))
        else:
            self.stdout.write(self.style.ERROR(f"Failed to confirm payment: {transaction_ref}"))
