from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AjoContribution, AjoCycle, AjoGroup, OjaUser


class PaymentCheckoutTests(TestCase):
    def test_ajo_contribution_checkout_renders_pending_page(self):
        user = OjaUser.objects.create_user(phone='08000000000', full_name='Test User')
        group = AjoGroup.objects.create(
            name='Test Ajo',
            creator=user,
            contribution_amount=1000,
            frequency='weekly',
        )
        cycle = AjoCycle.objects.create(
            group=group,
            cycle_number=1,
            beneficiary=user,
            expected_amount=5000,
            due_date=timezone.now() + timedelta(days=7),
        )
        contribution = AjoContribution.objects.create(
            cycle=cycle,
            member=user,
            amount=1000,
            transaction_ref='AJO-TEST-1234',
        )

        response = self.client.get(
            reverse('payment_link_checkout', kwargs={'transaction_ref': contribution.transaction_ref})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Payment Pending')
        self.assertContains(response, contribution.transaction_ref)
        self.assertContains(response, '₦1,000')
