from django.shortcuts import render, get_object_or_404
from django.conf import settings
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.db.models import Sum
from datetime import timedelta, date
from decimal import Decimal
import uuid
from ..models import (
    OjaUser, LoanOffer, Loan, LoanRepayment,
    SavingsGoal, OjaTransaction, Notification, PaymentLink
)
from ..services.loan_engine import (
    calculate_loan_offer, generate_repayment_schedule, check_defaulter_risk
)
from ..services.oja_score import recalculate_ojascore
from ..services.bmoni_service import BMONIService

SITE_BASE_URL = getattr(settings, 'SITE_BASE_URL', 'https://ojapass.onrender.com')


# ---------------------------------------------------------------------------
# LOAN DASHBOARD
# ---------------------------------------------------------------------------

class LoanDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        score = user.ojapass_score

        active_loan = Loan.objects.filter(
            user=user, status='active'
        ).select_related('offer').first()

        available_offer = LoanOffer.objects.filter(
            user=user, status='available'
        ).order_by('-created_at').first()

        recent_offer_exists = LoanOffer.objects.filter(
            user=user,
            created_at__gte=timezone.now() - timedelta(hours=24)
        ).exists()

        if not available_offer and not active_loan and score >= 31 and not recent_offer_exists:
            offer_data = calculate_loan_offer(user)
            if offer_data and offer_data['product_type'] != 'savings_goal':
                available_offer = LoanOffer.objects.create(
                    user=user,
                    product_type=offer_data['product_type'],
                    offer_amount=offer_data['offer_amount'],
                    interest_rate=offer_data['interest_rate'],
                    tenure_months=offer_data['tenure_months'],
                    monthly_repayment=offer_data['monthly_repayment'],
                    avg_monthly_turnover=offer_data['avg_monthly_turnover'],
                    oja_score_at_offer=score,
                    expires_at=timezone.now() + timedelta(days=7),
                )

        repayments = []
        defaulter_risk = None
        if active_loan:
            repayments = LoanRepayment.objects.filter(
                loan=active_loan
            ).order_by('installment_number')
            defaulter_risk = check_defaulter_risk(active_loan)

            if defaulter_risk['at_risk']:
                already_notified = Notification.objects.filter(
                    user=user,
                    message__contains="sales slowed down",
                    created_at__gte=timezone.now() - timedelta(days=7)
                ).exists()

                if not already_notified:
                    Notification.objects.create(
                        user=user,
                        message=(
                            "We noticed your sales slowed down this month. "
                            "Need help restructuring your repayment? Reply here and we'll help you out."
                        )
                    )

        savings_goals = SavingsGoal.objects.filter(user=user, status='active')
        past_loans = Loan.objects.filter(
            user=user
        ).exclude(status='active').order_by('-created_at')[:5]

        context = {
            'user': user,
            'score': score,
            'available_offer': available_offer,
            'active_loan': active_loan,
            'repayments': repayments,
            'savings_goals': savings_goals,
            'past_loans': past_loans,
            'defaulter_risk': defaulter_risk,
            'can_save': score >= 31,
            'can_borrow': score >= 56,
            'can_insure': True,
        }
        return render(request, 'loans.html', context)


# ---------------------------------------------------------------------------
# LOAN APPLY
# ---------------------------------------------------------------------------

class LoanApplyView(LoginRequiredMixin, View):
    def post(self, request, offer_id):
        offer = get_object_or_404(
            LoanOffer, id=offer_id, user=request.user, status='available'
        )

        if offer.expires_at < timezone.now():
            offer.status = 'expired'
            offer.save()
            return JsonResponse(
                {"success": False, "message": "This offer has expired."}, status=400
            )

        offer.status = 'approved'
        offer.applied_at = timezone.now()
        offer.approved_at = timezone.now()
        offer.save()

        disbursement_ref = f"LOAN-{uuid.uuid4().hex[:10].upper()}"

        # NOTE: Real BMONI disbursement is not wired up yet. Sending money to
        # a user's bank account via BMONI is a signed smart-wallet-proposal
        # flow (see BMONIService.initiate_nigeria_withdrawal +
        # submit_proposal_signature), which needs:
        #   - a source smart wallet holding the funds (OjaPass's own platform
        #     wallet, presumably, since this is money going OUT to the user)
        #   - the borrower's saved bankAccountId on BMONI
        #   - a signature from whoever owns the source wallet's private key
        # None of that is available here yet, so this block intentionally
        # does NOT call BMONIService and does NOT claim a real transfer
        # happened. It only logs intent so nothing is silently faked.
        if request.user.virtual_account_number:
            print(
                f"[BMONI] Loan disbursement NOT YET IMPLEMENTED — "
                f"₦{offer.offer_amount:,.0f} owed to {request.user.full_name} "
                f"(virtual_account_number={request.user.virtual_account_number}, "
                f"ref={disbursement_ref})"
            )
        else:
            print(
                f"[BMONI] Loan approved for {request.user.full_name} but no "
                f"virtual_account_number on file (ref={disbursement_ref})"
            )

        # Placeholder for development: treat as disbursed so the rest of the
        # local flow (repayment schedule, notifications, score) can be
        # exercised end-to-end while the real BMONI transfer is built out.
        disburse_success = True

        if not disburse_success:
            return JsonResponse(
                {"success": False, "message": "Disbursement failed. Please try again."},
                status=500
            )

        total_repayable = offer.monthly_repayment * offer.tenure_months
        loan = Loan.objects.create(
            user=request.user,
            offer=offer,
            principal=offer.offer_amount,
            interest_rate=offer.interest_rate,
            tenure_months=offer.tenure_months,
            monthly_repayment=offer.monthly_repayment,
            total_repayable=total_repayable,
            amount_repaid=Decimal('0'),
            amount_outstanding=total_repayable,
            disbursement_ref=disbursement_ref,
            disbursed_at=timezone.now(),
            next_repayment_date=date.today() + timedelta(days=30),
            status='active',
        )

        schedule = generate_repayment_schedule(loan)
        for s in schedule:
            LoanRepayment.objects.create(
                loan=loan,
                installment_number=s['installment'],
                amount_due=s['amount_due'],
                due_date=s['due_date'],
                status='pending',
            )

        OjaTransaction.objects.get_or_create(
            transaction_reference=disbursement_ref,
            defaults={
                'user': request.user,
                'amount': offer.offer_amount,
                'status': 'success',
                'transaction_type': 'inflow',
                'sender_name': 'OjaPass Loan',
                'sender_bank': 'OjaPass MFB',
            }
        )

        offer.status = 'disbursed'
        offer.save()

        Notification.objects.create(
            user=request.user,
            message=(
                f"LOAN APPROVED! ₦{offer.offer_amount:,.0f} has been sent to your OjaPass account. "
                f"First repayment of ₦{offer.monthly_repayment:,.0f} is due in 30 days."
            )
        )

        recalculate_ojascore(request.user.id)

        return JsonResponse({
            "success": True,
            "message": f"₦{offer.offer_amount:,.0f} disbursed to your account!",
            "loanId": loan.id,
            "firstRepaymentDate": loan.next_repayment_date.isoformat(),
            "monthlyRepayment": float(loan.monthly_repayment),
        })


# ---------------------------------------------------------------------------
# LOAN REPAYMENT
# ---------------------------------------------------------------------------

class LoanRepaymentView(LoginRequiredMixin, View):
    """Trader initiates a repayment — generates a payment link."""

    def post(self, request, loan_id):
        loan = get_object_or_404(Loan, id=loan_id, user=request.user, status='active')

        next_installment = LoanRepayment.objects.filter(
            loan=loan, status='pending'
        ).order_by('installment_number').first()

        if not next_installment:
            return JsonResponse(
                {"success": False, "message": "No pending repayments."}, status=400
            )

        repayment_ref = f"REPAY-{uuid.uuid4().hex[:10].upper()}"

        # NOTE: real payment-gateway integration for repayment collection is
        # not wired up yet (this predates/duplicates the BMONI disbursement
        # gap above). Returning a placeholder checkout URL so the frontend
        # flow can be exercised.
        checkout_url = f"{SITE_BASE_URL}/payment-link/verify/{repayment_ref}/"
        print(f"[BMONI] Loan repayment initiation NOT YET IMPLEMENTED for loan {loan_id} (ref={repayment_ref})")

        return JsonResponse({
            "success": True,
            "checkout_url": checkout_url,
            "transaction_ref": repayment_ref
        })


# ---------------------------------------------------------------------------
# SAVINGS GOAL
# ---------------------------------------------------------------------------

class SavingsGoalView(LoginRequiredMixin, View):

    def get(self, request):
        goals = SavingsGoal.objects.filter(user=request.user)
        return render(request, 'savings_goals.html', {'goals': goals})

    def post(self, request):
        import json
        try:
            data = json.loads(request.body)
        except Exception:
            data = request.POST

        if request.user.ojapass_score < 31:
            return JsonResponse({
                "success": False,
                "message": "You need an OjaScore of at least 31 to create savings goals.",
            }, status=403)

        contribution_amount = Decimal(str(data.get('contributionAmount', 0)))
        target_amount = Decimal(str(data.get('targetAmount', 0)))

        if target_amount <= 0:
            return JsonResponse(
                {"success": False, "message": "Target amount must be greater than 0."},
                status=400
            )

        goal = SavingsGoal.objects.create(
            user=request.user,
            name=data.get('name', 'My Savings Goal'),
            target_amount=target_amount,
            contribution_amount=contribution_amount,
            frequency=data.get('frequency', 'weekly'),
        )

        Notification.objects.create(
            user=request.user,
            message=f"Savings goal created: '{goal.name}'. Target: ₦{goal.target_amount:,.0f}. Keep going!"
        )

        return JsonResponse({
            "success": True,
            "goalId": goal.id,
            "message": f"Savings goal '{goal.name}' created successfully!",
        })