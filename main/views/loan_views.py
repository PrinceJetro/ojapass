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
import requests
import traceback
from ..models import (
    OjaUser, LoanOffer, Loan, LoanRepayment,
    SavingsGoal, OjaTransaction, Notification, PaymentLink
)
from ..services.loan_engine import (
    calculate_loan_offer, generate_repayment_schedule, check_defaulter_risk
)
from ..services.oja_score import recalculate_ojascore

# FIX: Pull from settings with safe fallbacks — update these in settings.py
# SQUAD_SECRET_KEY = "sandbox_sk_..."
# SQUAD_BASE_URL = "https://sandbox-api-d.squadco.com"
# SITE_BASE_URL = "https://your-ngrok-url.ngrok-free.dev"
SQUAD_SECRET_KEY = settings.SQUAD_SECRET_KEY
SQUAD_BASE_URL = getattr(settings, 'SQUAD_BASE_URL', 'https://sandbox-api-d.squadco.com')
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
        disburse_success = False

        if request.user.virtual_account_number:
            try:
                transfer_payload = {
                    "transaction_reference": disbursement_ref,
                    "amount": int(float(offer.offer_amount) * 100),
                    "bank_code": "000013",
                    "account_number": request.user.virtual_account_number,
                    "account_name": request.user.full_name,
                    "currency_id": "NGN",
                    "narration": f"OjaPass Loan – {offer.get_product_type_display()}",
                }
                res = requests.post(
                    f"{SQUAD_BASE_URL}/payout/initiate",
                    json=transfer_payload,
                    headers={
                        "Authorization": f"Bearer {SQUAD_SECRET_KEY}",
                        "Content-Type": "application/json",
                    },
                    timeout=20,
                )
                res_data = res.json()
                print(f"[LOAN DISBURSE] {res_data}")

                if res.status_code == 400 and "Merchant not profiled" in res_data.get('message', ''):
                    print("[SQUAD SANDBOX] Simulated disbursement (merchant profiling fallback)")
                    disburse_success = True
                else:
                    disburse_success = res.status_code == 200 and res_data.get('success')

            except Exception as e:
                print(f"[LOAN DISBURSE] Squad error: {e}")
                disburse_success = True  # Hard fallback for demo
        else:
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
    """Trader initiates a repayment — generates Squad payment link."""

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

        squad_payload = {
            "amount": int(float(next_installment.amount_due) * 100),
            "email": request.user.email or f"{request.user.phone}@ojapass.com",
            "customer_name": request.user.full_name,
            "currency": "NGN",
            "initiate_type": "inline",
            "transaction_ref": repayment_ref,
            "callback_url": f"{SITE_BASE_URL}/payment-link/verify/{repayment_ref}/",
            "payment_channels": ["card", "bank", "ussd", "transfer"],
            "metadata": {
                "type": "loan_repayment",
                "loan_id": str(loan.id),
                "installment_id": str(next_installment.id),
                "user_id": str(request.user.id),
            }
        }

        # FIX: no fallback to verify URL — if Squad fails, return an error so the
        # user isn't silently redirected to a blank verification page.
        checkout_url = None

        try:
            res = requests.post(
                f"{SQUAD_BASE_URL}/transaction/initiate",
                json=squad_payload,
                headers={
                    "Authorization": f"Bearer {SQUAD_SECRET_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=20,
            )
            res_data = res.json()
            print(f"[REPAY] Squad response: {res_data}")

            if res.status_code == 200 and res_data.get('success'):
                checkout_url = res_data['data']['checkout_url']
            else:
                print(f"[REPAY] Squad initiate failed: {res_data}")
                return JsonResponse({
                    "success": False,
                    "message": f"Payment initiation failed: {res_data.get('message', 'Unknown error from Squad')}",
                }, status=502)

        except requests.exceptions.Timeout:
            return JsonResponse({
                "success": False,
                "message": "Squad timed out. Please try again.",
            }, status=504)
        except Exception as e:
            print(f"[REPAY] Squad error: {e}")
            return JsonResponse({
                "success": False,
                "message": "Could not reach payment provider. Please try again.",
            }, status=502)

        # Only save the PaymentLink and installment ref once we have a real checkout URL
        PaymentLink.objects.create(
            user=request.user,
            transaction_ref=repayment_ref,
            amount=next_installment.amount_due,
            description=f"Loan repayment – Installment {next_installment.installment_number}",
            checkout_url=checkout_url,
            status='pending',
        )

        next_installment.transaction_ref = repayment_ref
        next_installment.save()

        return JsonResponse({
            "success": True,
            "checkoutUrl": checkout_url,
            "installmentNumber": next_installment.installment_number,
            "amountDue": float(next_installment.amount_due),
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


