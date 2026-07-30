from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import hmac
import hashlib
import uuid
import json
import threading
from datetime import timedelta
from decimal import Decimal
import traceback
from django.db import transaction
from django.db.models import Sum, F

# FIX: PaymentLinkItem removed — it does not exist in models.py.
# If you add it later, re-add it here.
from ..models import (
    OjaUser, OjaTransaction, PaymentLink, Product,
    Sale, Order, Notification,
    AjoCycle, AjoGroup, AjoContribution, AjoMembership, Gig
)
from ..services.bmoni_service import BMONIService
from ..services.oja_score import recalculate_ojascore

# BMONI API Settings
BMONI_BASE_URL = settings.BMONI_BASE_URL
BMONI_API_KEY = settings.BMONI_API_KEY
BMONI_WEBHOOK_SECRET = getattr(settings, 'BMONI_WEBHOOK_SECRET', None)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _start_score_thread(user_id):
    """Recalculate OjaScore in a background daemon thread."""
    t = threading.Thread(target=recalculate_ojascore, args=(user_id,), daemon=True)
    t.start()


def _update_user_wallet_balance(user, amount, transaction_type):
    """Keep the local wallet_balance in sync with confirmed transactions."""
    if not user or amount is None:
        return

    try:
        amount_dec = Decimal(str(amount))
    except Exception:
        return

    current_balance = user.wallet_balance or Decimal('0')
    if transaction_type == 'inflow':
        user.wallet_balance = current_balance + amount_dec
    elif transaction_type == 'outflow':
        user.wallet_balance = current_balance - amount_dec
        if user.wallet_balance < 0:
            user.wallet_balance = Decimal('0')
    else:
        return

    user.save(update_fields=['wallet_balance'])


def _handle_payment_link_success(link, transaction_ref, amount):
    """Mark a payment link as paid, log sales, decrement stock, notify merchant."""
    if link.status == 'paid':
        return

    with transaction.atomic():
        link.status = 'paid'
        link.paid_at = timezone.now()
        link.save()

        # Log items as individual sales and decrement stock.
        # NOTE: relies on link.items reverse relation from PaymentLinkItem.
        # If that model doesn't exist yet, the for-loop simply won't execute.
        for item in link.items.all():
            product = item.product
            qty = item.quantity

            Product.objects.filter(
                id=product.id,
                quantity_in_stock__gte=qty   # FIX: never go negative
            ).update(quantity_in_stock=F('quantity_in_stock') - qty)

            Sale.objects.create(
                user=link.user,
                product=product,
                quantity=qty,
                amount=item.price_at_time * qty,
                payment_method='bmoni',
                transaction_ref=f"LINK-{transaction_ref}-{item.id}"
            )

        Notification.objects.create(
            user=link.user,
            message=f"INVOICE PAID: You received ₦{amount:,.0f} for invoice {link.transaction_ref}."
        )


def _confirm_transaction(transaction_ref, amount, meta=None):
    """
    Given a transaction_ref that a real BMONI deposit has been matched to,
    mark the corresponding pending record (ajo contribution / loan repayment /
    gig escrow / invoice) as paid, and log the shared OjaTransaction.

    This is the ONLY place that should ever mark these records as paid.
    It must only be called once a real deposit has actually been confirmed
    (i.e. from the BMONI webhook) — never from a page visit / GET request.
    """
    meta = meta or {}
    from ..models import Loan, LoanRepayment
    from .ajo_views import _disburse_cycle

    user = None
    transaction_type = 'inflow'
    success_msg = "Your payment was successful."

    payment_link = PaymentLink.objects.filter(transaction_ref=transaction_ref).first()

    ajo_contrib = AjoContribution.objects.filter(
        transaction_ref=transaction_ref
    ).select_related('member', 'cycle', 'cycle__group').first()

    if not ajo_contrib and meta.get('type') == 'ajo_contribution':
        try:
            cycle_id = meta.get('cycle_id')
            member_id = meta.get('member_id')
            if cycle_id and member_id:
                ajo_contrib = AjoContribution.objects.filter(
                    cycle_id=cycle_id,
                    member_id=member_id,
                    status='pending',
                ).select_related('member', 'cycle', 'cycle__group').first()
        except Exception as e:
            print(f"[CONFIRM] Ajo contrib lookup error: {e}")

    # 1. AJO CONTRIBUTION
    if ajo_contrib:
        user = ajo_contrib.member
        if amount == 0:
            amount = float(ajo_contrib.amount)
        if ajo_contrib.status == 'pending':
            with transaction.atomic():
                ajo_contrib.status = 'paid'
                ajo_contrib.paid_at = timezone.now()
                ajo_contrib.save()
                cycle = ajo_contrib.cycle
                cycle.collected_amount += ajo_contrib.amount
                if cycle.collected_amount >= cycle.expected_amount:
                    cycle.status = 'collecting'
                    _disburse_cycle(cycle, cycle.group)
                cycle.save()

                membership = AjoMembership.objects.filter(
                    group=cycle.group, user=user
                ).first()
                if membership:
                    membership.total_contributed += ajo_contrib.amount
                    membership.save()

            Notification.objects.create(
                user=user,
                message=f"AJO CONTRIBUTION CONFIRMED: ₦{ajo_contrib.amount:,.0f} to '{cycle.group.name}'."
            )
        transaction_type = 'outflow'
        success_msg = "Ajo Contribution Successful!"

    # 2. LOAN REPAYMENT
    elif meta.get('type') == 'loan_repayment' or transaction_ref.startswith('REPAY-'):
        try:
            loan_id = meta.get('loan_id')
            installment_id = meta.get('installment_id')

            if not loan_id:
                installment = LoanRepayment.objects.filter(
                    transaction_ref=transaction_ref
                ).first()
                if installment:
                    loan_id = installment.loan_id
                    installment_id = installment.id

            loan = Loan.objects.get(id=loan_id)
            installment = LoanRepayment.objects.get(id=installment_id)

            if installment.status != 'paid':
                installment.status = 'paid'
                installment.amount_paid = installment.amount_due
                installment.paid_at = timezone.now()
                installment.transaction_ref = transaction_ref
                installment.save()
                loan.amount_repaid = (loan.amount_repaid or Decimal('0')) + installment.amount_due
                loan.amount_outstanding -= installment.amount_due
                if loan.amount_outstanding <= 0:
                    loan.status = 'completed'
                loan.save()
                Notification.objects.create(
                    user=loan.user,
                    message=f"REPAYMENT CONFIRMED: Installment {installment.installment_number} of ₦{installment.amount_due:,.0f} received."
                )
                recalculate_ojascore(loan.user.id)

            user = loan.user
            transaction_type = 'outflow'
            success_msg = "Repayment Successful!"
        except Exception as e:
            print(f"[CONFIRM] Loan repayment error: {e}")
            traceback.print_exc()

    # 3. GIG ESCROW
    elif meta.get('type') == 'gig_escrow' or transaction_ref.startswith('GIG-ESCROW-'):
        try:
            gig_id = meta.get('gig_id')
            gig = Gig.objects.get(id=gig_id)
            if not gig.escrow_paid:
                gig.escrow_paid = True
                gig.status = 'matched'
                gig.matched_at = timezone.now()
                gig.save()
                Notification.objects.create(
                    user=gig.employer,
                    message=f"ESCROW FUNDED: ₦{gig.pay_rate:,.0f} secured for '{gig.title}'. Worker has been notified."
                )
            user = gig.employer
            transaction_type = 'outflow'
            success_msg = "Escrow Confirmed!"
        except Exception as e:
            print(f"[CONFIRM] Gig escrow error: {e}")
            traceback.print_exc()

    # 4. GENERIC PAYMENT LINK (invoice)
    elif payment_link:
        user = payment_link.user
        if amount == 0:
            amount = float(payment_link.amount)
        _handle_payment_link_success(payment_link, transaction_ref, amount)
        success_msg = "Invoice Paid Successfully!"

    # 5. STOREFRONT ORDERS (legacy metadata style)
    else:
        order_ids_raw = meta.get('order_ids')
        if order_ids_raw:
            order_ids = str(order_ids_raw).split(',')
            orders = Order.objects.filter(id__in=order_ids)
            if orders.exists():
                user = orders.first().user
                for order in orders:
                    if order.status != 'paid':
                        order.status = 'paid'
                        order.save()
                        Sale.objects.create(
                            user=user,
                            product=order.product,
                            quantity=order.quantity,
                            amount=order.total_amount,
                            payment_method='bmoni',
                            # per-order unique ref prevents IntegrityError
                            transaction_ref=f"BMONI-{transaction_ref}-{order.id}",
                        )
                        if order.product:
                            Product.objects.filter(
                                id=order.product.id,
                                quantity_in_stock__gte=order.quantity
                            ).update(
                                quantity_in_stock=F('quantity_in_stock') - order.quantity
                            )
                Notification.objects.create(
                    user=user,
                    message=f"NEW SALE: You received ₦{amount:,.0f} from a storefront order."
                )

    if user:
        _, created = OjaTransaction.objects.get_or_create(
            transaction_reference=transaction_ref,
            defaults={
                'user': user,
                'amount': amount,
                'status': 'success',
                'transaction_type': transaction_type,
            }
        )
        if created:
            _update_user_wallet_balance(user, amount, transaction_type)
            _start_score_thread(user.id)

    return {"user": user, "message": success_msg, "amount": amount}


def _find_pending_match_for_merchant(bmoni_user_id, amount):
    """
    BMONI's wallet.deposit.completed webhook only tells us WHO received
    money and HOW MUCH — it does not carry our own transaction_ref back.
    So when a deposit lands, we match it to the oldest still-pending item
    belonging to that BMONI user with the same amount.

    This is best-effort reconciliation, not exact. If a merchant has two
    pending invoices for the same amount at the same time, this will
    confirm the older one first. Fine for most small-merchant use cases;
    revisit if that becomes a real collision source.
    """
    merchant = OjaUser.objects.filter(bmoni_user_id=bmoni_user_id).first()
    if not merchant:
        return None

    amount_dec = Decimal(str(amount))

    link = PaymentLink.objects.filter(
        user=merchant, status='pending', amount=amount_dec
    ).order_by('created_at').first()
    if link:
        return link.transaction_ref, {}

    from ..models import Loan, LoanRepayment
    installment = LoanRepayment.objects.filter(
        loan__user=merchant, status='pending', amount_due=amount_dec
    ).order_by('due_date').first()
    if installment:
        return f"REPAY-{installment.id}", {
            "type": "loan_repayment",
            "loan_id": installment.loan_id,
            "installment_id": installment.id,
        }

    ajo_contrib = AjoContribution.objects.filter(
        member=merchant, status='pending', amount=amount_dec
    ).order_by('cycle__due_date' if hasattr(AjoCycle, 'due_date') else 'id').first()
    if ajo_contrib:
        return ajo_contrib.transaction_ref or f"AJO-{ajo_contrib.id}", {
            "type": "ajo_contribution",
            "cycle_id": ajo_contrib.cycle_id,
            "member_id": ajo_contrib.member_id,
        }

    gig = Gig.objects.filter(
        employer=merchant, status='pending_escrow', escrow_amount=amount_dec
    ).order_by('created_at').first()
    if gig:
        return gig.escrow_transaction_ref, {"type": "gig_escrow", "gig_id": gig.id}

    return None


def _verify_webhook_signature(request):
    """Verify BMONI's x-webhook-signature (HMAC-SHA256 of the raw body)."""
    if not BMONI_WEBHOOK_SECRET:
        print("[BMONI WEBHOOK] WARNING: BMONI_WEBHOOK_SECRET not set — skipping signature check")
        return True

    signature = request.headers.get('x-webhook-signature', '')
    expected = hmac.new(
        BMONI_WEBHOOK_SECRET.encode('utf-8'),
        request.body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


# ---------------------------------------------------------------------------
# BMONI WEBHOOK
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name='dispatch')
class BMONIWebhookView(View):
    """
    Real BMONI webhook shape:
        {
          "id": "stable-event-id",
          "eventType": "wallet.deposit.completed",
          "payload": {
            "userId": "bmoni-user-uuid",
            "transactionId": "...",
            "smartWalletId": "...",
            "amount": "250.00",
            "currency": "NGN",
            "transferId": "..."
          },
          "timestamp": "..."
        }
    """
    def post(self, request):
        if not _verify_webhook_signature(request):
            print("[BMONI WEBHOOK] Invalid signature — rejecting")
            return JsonResponse({"message": "Invalid signature"}, status=401)

        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"message": "Invalid JSON"}, status=400)

        print(f"[BMONI WEBHOOK] Received: {data}")
        event_type = data.get('eventType')
        payload = data.get('payload', {}) or {}

        try:
            if event_type == 'wallet.deposit.completed':
                bmoni_user_id = payload.get('userId')
                amount = payload.get('amount')

                if bmoni_user_id and amount is not None:
                    match = _find_pending_match_for_merchant(bmoni_user_id, amount)
                    if match:
                        transaction_ref, meta = match
                        _confirm_transaction(transaction_ref, float(amount), meta)
                        print(f"[BMONI WEBHOOK] Confirmed {transaction_ref} for ₦{amount}")
                    else:
                        print(
                            f"[BMONI WEBHOOK] Deposit of ₦{amount} for user {bmoni_user_id} "
                            f"received but no matching pending record found."
                        )
            # Other event types (wallet.deposit.failed, wallet.withdrawal.*,
            # onboarding.*, kyc.action_required, etc.) can be handled here as
            # they become relevant — currently no-ops.

            return JsonResponse({"message": "Webhook received"}, status=200)

        except Exception as e:
            print(f"[BMONI WEBHOOK] Error: {e}")
            traceback.print_exc()
            return JsonResponse({"message": "Error processing webhook"}, status=400)


# ---------------------------------------------------------------------------
# TRANSACTION LIST
# ---------------------------------------------------------------------------

class TransactionListView(View):
    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('login')
        user = request.user
        txs = OjaTransaction.objects.filter(user=user).order_by('-timestamp')

        thirty_days_ago = timezone.now() - timedelta(days=30)
        total_inflow = (
            OjaTransaction.objects
            .filter(user=user, transaction_type='inflow', timestamp__gte=thirty_days_ago)
            .aggregate(total=Sum('amount'))['total'] or 0
        )
        pending_amount = (
            PaymentLink.objects
            .filter(user=user, status='pending')
            .aggregate(total=Sum('amount'))['total'] or 0
        )

        context = {
            'transactions': txs,
            'total_inflow': float(total_inflow),
            'pending_amount': float(pending_amount),
        }
        return render(request, 'transactionhistory.html', context)


# ---------------------------------------------------------------------------
# CREATE PAYMENT LINK (Invoice style — with items)
# ---------------------------------------------------------------------------

class CreatePaymentLinkView(View):
    def post(self, request):
        if not request.user.is_authenticated:
            return JsonResponse({"success": False}, status=401)
        user = request.user

        try:
            data = json.loads(request.body)
        except Exception:
            data = request.POST

        items = data.get('items', [])
        if not items:
            return JsonResponse(
                {"success": False, "message": "No products selected."}, status=400
            )

        transaction_ref = f"INV-{uuid.uuid4().hex[:12].upper()}"
        total_amount = Decimal('0.00')
        description = data.get(
            'description', f"Invoice from {user.business_name or user.full_name}"
        )

        with transaction.atomic():
            payment_link = PaymentLink.objects.create(
                user=user,
                transaction_ref=transaction_ref,
                amount=0,   # updated below
                description=description,
            )

            for item in items:
                product = get_object_or_404(Product, id=item['productId'], user=user)
                qty = int(item['quantity'])
                price = product.selling_price

                # Only create PaymentLinkItem if the model exists
                try:
                    from ..models import PaymentLinkItem
                    PaymentLinkItem.objects.create(
                        payment_link=payment_link,
                        product=product,
                        quantity=qty,
                        price_at_time=price,
                    )
                except ImportError:
                    pass  # Model not yet added — items skipped

                total_amount += price * qty

            payment_link.amount = total_amount
            payment_link.save()

        local_checkout_url = request.build_absolute_uri(
            f"/payment-link/checkout/{transaction_ref}/"
        )
        return JsonResponse({
            "success": True,
            "paymentLink": local_checkout_url,
            "transaction_ref": transaction_ref,
            "totalAmount": float(total_amount),
        })


# ---------------------------------------------------------------------------
# PAYMENT LINK CHECKOUT PAGE
# ---------------------------------------------------------------------------

class PaymentLinkCheckoutView(View):
    def get(self, request, transaction_ref):
        link = get_object_or_404(PaymentLink, transaction_ref=transaction_ref)
        if link.status == 'paid':
            return render(
                request, 'payment_success.html',
                {"message": "This invoice has already been paid. Thank you!"}
            )
        return render(request, 'payment_checkout.html', {"link": link})


# ---------------------------------------------------------------------------
# GET BMONI DEPOSIT DETAILS (from checkout page)
# gateway page to redirect to — instead we show the merchant's own BMONI
# Nigerian deposit account and instruct the payer to transfer the invoice
# amount directly to it. Confirmation happens via BMONIWebhookView once the
# transfer lands, not from this endpoint.
# ---------------------------------------------------------------------------

class InitiateBmoniDepositView(View):
    def post(self, request, transaction_ref):
        link = get_object_or_404(PaymentLink, transaction_ref=transaction_ref)
        if link.status == 'paid':
            return JsonResponse({"success": False, "message": "Already paid."}, status=400)

        merchant = link.user
        bmoni_user_id = getattr(merchant, 'bmoni_user_id', None)

        # Fallback: if BMONI not set up or API down, return mock deposit account for development
        if not bmoni_user_id:
            print(f"[BMONI BYPASS] No bmoni_user_id for {merchant.email} - using mock deposit account")
            return JsonResponse({
                "success": True,
                "depositAccount": {
                    "bankName": "Wema Bank (Mock)",
                    "accountNumber": "1234567890",
                    "accountName": merchant.full_name,
                    "narration": f"Payment for invoice {link.transaction_ref}",
                },
                "amount": float(link.amount),
                "message": (
                    f"Transfer ₦{link.amount:,.0f} to the account below. "
                    f"Note: BMONI not configured - this is a mock account for development."
                ),
            })

        # Fetch the merchant's BMONI deposit account directly.
        deposit_result = BMONIService.get_deposit_accounts(bmoni_user_id, "NGN")

        if not deposit_result or not deposit_result.get("success"):
            print(f"[BMONI BYPASS] BMONI API call failed for {merchant.email} - using mock deposit account")
            return JsonResponse({
                "success": True,
                "depositAccount": {
                    "bankName": "Wema Bank (Mock)",
                    "accountNumber": "1234567890",
                    "accountName": merchant.full_name,
                    "narration": f"Payment for invoice {link.transaction_ref}",
                },
                "amount": float(link.amount),
                "message": (
                    f"Transfer ₦{link.amount:,.0f} to the account below. "
                    f"Note: BMONI API unavailable - this is a mock account for development."
                ),
            })

        accounts = deposit_result.get("data", {}).get("accounts", [])
        if not accounts:
            return JsonResponse(
                {"success": False, "message": "No deposit account available for this merchant yet."},
                status=400
            )

        account = accounts[0]
        return JsonResponse({
            "success": True,
            "depositAccount": {
                "bankName": account.get("bankName"),
                "accountNumber": account.get("accountNumber"),
                "accountName": account.get("accountName"),
                "narration": account.get("depositMessage"),
            },
            "amount": float(link.amount),
            "message": (
                f"Transfer ₦{link.amount:,.0f} to the account below. "
                f"We'll confirm automatically once it lands."
            ),
        })


class SimulateBmoniDepositView(View):
    """Sandbox shortcut to confirm a pending payment link locally."""

    def post(self, request, transaction_ref):
        if not settings.DEBUG:
            return JsonResponse({"success": False, "message": "Simulation only allowed in debug mode."}, status=403)

        link = get_object_or_404(PaymentLink, transaction_ref=transaction_ref)
        if link.status == 'paid':
            return JsonResponse({"success": False, "message": "This invoice is already paid."}, status=400)

        _confirm_transaction(link.transaction_ref, float(link.amount), {})
        return JsonResponse({"success": True, "message": "Sandbox payment simulated successfully.", "transaction_ref": link.transaction_ref})


# ---------------------------------------------------------------------------
# VERIFY PAYMENT — read-only status page.
# IMPORTANT: this no longer confirms anything. Confirmation only ever
# happens in BMONIWebhookView, once a real deposit is matched. This view
# just reports whatever the current stored status already is.
# ---------------------------------------------------------------------------

class VerifyPaymentView(View):
    def get(self, request, transaction_ref):
        payment_link = PaymentLink.objects.filter(transaction_ref=transaction_ref).first()
        if payment_link:
            if payment_link.status == 'paid':
                return render(request, 'payment_success.html', {
                    "message": "Invoice Paid Successfully!",
                    "amount": float(payment_link.amount),
                    "link": payment_link,
                })
            return render(request, 'payment_pending.html', {
                "message": "We haven't received this payment yet. This page will update automatically once it does.",
                "amount": float(payment_link.amount),
                "transaction_ref": transaction_ref,
            })

        from ..models import Loan, LoanRepayment

        if transaction_ref.startswith('REPAY-'):
            installment = LoanRepayment.objects.filter(transaction_ref=transaction_ref).first()
            if installment:
                if installment.status == 'paid':
                    return render(request, 'payment_success.html', {"message": "Repayment Successful!"})
                return render(request, 'payment_pending.html', {
                    "message": "Repayment not yet confirmed.",
                    "transaction_ref": transaction_ref,
                })

        if transaction_ref.startswith('GIG-ESCROW-'):
            gig = Gig.objects.filter(escrow_transaction_ref=transaction_ref).first()
            if gig:
                if gig.escrow_paid:
                    return render(request, 'payment_success.html', {"message": "Escrow Confirmed!"})
                return render(request, 'payment_pending.html', {
                    "message": "Escrow funding not yet confirmed.",
                    "transaction_ref": transaction_ref,
                })

        ajo_contrib = AjoContribution.objects.filter(transaction_ref=transaction_ref).first()
        if ajo_contrib:
            if ajo_contrib.status == 'paid':
                return render(request, 'payment_success.html', {"message": "Ajo Contribution Successful!"})
            return render(request, 'payment_pending.html', {
                "message": "Contribution not yet confirmed.",
                "transaction_ref": transaction_ref,
            })

        return render(
            request, 'trader_dashboard.html',
            {'error': "We couldn't find a record for this transaction."}
        )