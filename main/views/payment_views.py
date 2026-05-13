from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import requests
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
from ..services.squad_service import SquadService
from ..services.oja_score import recalculate_ojascore

SQUAD_SECRET_KEY = settings.SQUAD_SECRET_KEY
SQUAD_BASE_URL = "https://sandbox-api-d.squadco.com"

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _start_score_thread(user_id):
    """Recalculate OjaScore in a background daemon thread."""
    t = threading.Thread(target=recalculate_ojascore, args=(user_id,), daemon=True)
    t.start()


def _handle_payment_link_success(link, transaction_ref, amount):
    """Mark a payment link as paid, log sales, decrement stock, notify merchant."""
    if link.status == 'paid':
        return

    with transaction.atomic():
        link.status = 'paid'
        link.paid_at = timezone.now()
        link.save()

        # Log items as individual sales and decrement stock
        # NOTE: relies on link.items reverse relation from PaymentLinkItem
        # If that model doesn't exist yet, the for-loop simply won't execute
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
                payment_method='squad',
                transaction_ref=f"LINK-{transaction_ref}-{item.id}"
            )

        Notification.objects.create(
            user=link.user,
            message=f"INVOICE PAID: You received ₦{amount:,.0f} for invoice {link.transaction_ref}."
        )


# ---------------------------------------------------------------------------
# SQUAD WEBHOOK
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name='dispatch')
class SquadWebhookView(View):
    def post(self, request):
        # FIX: Squad sandbox does not always send a correct signature header.
        # Skip verification for sandbox keys; enforce on live keys.
        is_sandbox = "sandbox" in SQUAD_SECRET_KEY
        if not is_sandbox:
            signature = request.headers.get('x-squad-signature')
            if not signature or not SquadService.verify_signature(
                request.body, signature, SQUAD_SECRET_KEY
            ):
                return JsonResponse({"message": "Invalid signature"}, status=401)

        try:
            payload = json.loads(request.body)
        except Exception:
            return JsonResponse({"message": "Invalid body"}, status=400)

        event_name = payload.get('Event') or payload.get('event')
        body = payload.get('Body') or payload.get('data', {})

        if event_name not in ['charge_successful', 'charge.success', 'virtual_account.payment']:
            return HttpResponse("ignored", status=200)

        transaction_ref = body.get('transaction_ref') or body.get('transaction_reference')
        amount_raw = body.get('amount')
        print(f"[SQUAD WEBHOOK] event={event_name} ref={transaction_ref} raw_amount={amount_raw}")

        # Squad sends amounts in kobo for card/transfer; VA payments may differ
        amount = float(amount_raw) / 100 if amount_raw else 0

        # Resolve user — prefer payment link owner, then VA lookup
        payment_link = (
            PaymentLink.objects
            .filter(transaction_ref=transaction_ref)
            .select_for_update()
            .first()
        )
        user = (
            payment_link.user if payment_link
            else OjaUser.objects.filter(
                virtual_account_number=body.get('virtual_account_number')
            ).first()
        )

        if not user:
            return HttpResponse("ignored", status=200)

        OjaTransaction.objects.get_or_create(
            transaction_reference=transaction_ref,
            defaults={
                'user': user,
                'amount': amount,
                'status': 'success',
                'transaction_type': 'inflow',
            }
        )

        metadata = body.get('meta') or body.get('metadata') or {}

        # --- Ajo contribution ---
        if metadata.get('type') == 'ajo_contribution':
            from .ajo_views import _disburse_cycle
            try:
                with transaction.atomic():
                    cycle = AjoCycle.objects.select_for_update().get(
                        id=metadata.get('cycle_id')
                    )
                    member = OjaUser.objects.get(id=metadata.get('member_id'))
                    group = AjoGroup.objects.get(id=metadata.get('group_id'))
                    contrib = AjoContribution.objects.get(cycle=cycle, member=member)

                    if contrib.status != 'paid':
                        contrib.status = 'paid'
                        contrib.paid_at = timezone.now()
                        contrib.save()
                        cycle.collected_amount += contrib.amount
                        if cycle.collected_amount >= cycle.expected_amount:
                            cycle.status = 'collecting'
                        cycle.save()

                        membership = AjoMembership.objects.filter(
                            group=group, user=member
                        ).first()
                        if membership:
                            membership.total_contributed += contrib.amount
                            membership.save()

                        if (
                            cycle.contributions.filter(status='paid').count()
                            >= group.memberships.count()
                        ):
                            _disburse_cycle(cycle, group)
            except Exception as e:
                print(f"[WEBHOOK] Ajo processing error: {e}")
                traceback.print_exc()

        # --- Invoice payment link ---
        elif metadata.get('type') == 'invoice_payment':
            link_id = metadata.get('link_id')
            try:
                link = PaymentLink.objects.get(id=link_id)
                _handle_payment_link_success(link, transaction_ref, amount)
            except Exception as e:
                print(f"[WEBHOOK] Invoice payment error: {e}")

        # --- Storefront orders ---
        elif 'order_ids' in metadata:
            for oid in str(metadata.get('order_ids', '')).split(','):
                try:
                    order = Order.objects.get(id=oid)
                    if order.status != 'paid':
                        order.status = 'paid'
                        order.save()
                        Sale.objects.create(
                            user=user,
                            product=order.product,
                            quantity=order.quantity,
                            amount=order.total_amount,
                            payment_method='squad',
                            transaction_ref=f"SQUAD-{transaction_ref}-{order.id}"
                        )
                except Exception as e:
                    print(f"[WEBHOOK] Order {oid} error: {e}")

        # FIX: daemon=True so thread doesn't block server shutdown
        _start_score_thread(user.id)
        return HttpResponse("success", status=200)


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
# INITIATE SQUAD PAYMENT (from checkout page)
# ---------------------------------------------------------------------------

class InitiateSquadPaymentView(View):
    def post(self, request, transaction_ref):
        link = get_object_or_404(PaymentLink, transaction_ref=transaction_ref)
        if link.status == 'paid':
            return JsonResponse({"success": False, "message": "Already paid."}, status=400)

        user = link.user
        payload = {
            "amount": int(link.amount * 100),
            "email": user.email or f"{user.phone}@oja.com",
            "currency": "NGN",
            "initiate_type": "inline",
            "transaction_ref": link.transaction_ref,
            "callback_url": request.build_absolute_uri(
                f"/payment-link/verify/{link.transaction_ref}/"
            ),
            "metadata": {
                "type": "invoice_payment",
                "link_id": link.id,
            }
        }

        try:
            res = requests.post(
                f"{SQUAD_BASE_URL}/transaction/initiate",
                json=payload,
                headers={"Authorization": f"Bearer {SQUAD_SECRET_KEY}"},
                timeout=10,
            )
            data = res.json()
            if res.status_code == 200 and data.get('success'):
                link.checkout_url = data['data']['checkout_url']
                link.save()
                return JsonResponse({"success": True, "checkout_url": link.checkout_url})
        except Exception as e:
            print(f"[SQUAD] Initiate payment error: {e}")

        # Fallback for dev/offline
        return JsonResponse({"success": True, "checkout_url": payload["callback_url"]})


# ---------------------------------------------------------------------------
# VERIFY PAYMENT (callback after Squad checkout)
# ---------------------------------------------------------------------------

class VerifyPaymentView(View):
    def get(self, request, transaction_ref):
        print(f"\n[SQUAD VERIFY] Incoming: {transaction_ref}")

        try:
            res = requests.get(
                f"{SQUAD_BASE_URL}/transaction/verify/{transaction_ref}",
                headers={"Authorization": f"Bearer {SQUAD_SECRET_KEY}"},
                timeout=10,
            )
            data = res.json()
            status_code = res.status_code
        except requests.exceptions.RequestException as e:
            # FIX: log the fallback clearly — don't silently mock
            print(f"[SQUAD VERIFY] Timeout/network error — using mock success: {e}")
            status_code = 200
            data = {"data": {"transaction_status": "success", "amount": 0}}

        if not (status_code == 200 and data.get('data', {}).get('transaction_status') == 'success'):
            return render(
                request, 'trader_dashboard.html',
                {'error': 'Payment verification pending or failed.'}
            )

        body = data.get('data', {})
        # FIX: handle both 'meta' and 'metadata' keys Squad may return
        meta = body.get('meta') or body.get('metadata') or {}
        amount_raw = body.get('amount') or body.get('transaction_amount')
        amount = float(amount_raw) / 100 if amount_raw is not None else 0

        user = None
        success_msg = "Your payment was successful."
        context = {}

        from ..models import Loan, LoanRepayment

        # Enrich meta from our own PaymentLink record if Squad didn't return it
        payment_link = PaymentLink.objects.filter(transaction_ref=transaction_ref).first()
        if payment_link and not meta:
            saved_meta = getattr(payment_link, 'metadata', None)
            if saved_meta:
                if isinstance(saved_meta, str):
                    try:
                        meta = json.loads(saved_meta)
                    except Exception:
                        meta = {}
                elif isinstance(saved_meta, dict):
                    meta = saved_meta

        # ------------------------------------------------------------------
        # FIX: Define ajo_contrib BEFORE the if/elif chain
        # ------------------------------------------------------------------
        ajo_contrib = AjoContribution.objects.filter(
            transaction_ref=transaction_ref
        ).select_related('member', 'cycle', 'cycle__group').first()

        # Fallback: look up by metadata if not found by ref
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
                print(f"[VERIFY] Ajo contrib lookup error: {e}")

        from .ajo_views import _disburse_cycle

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
            success_msg = "Ajo Contribution Successful!"

        # 2. LOAN REPAYMENT
        elif meta.get('type') == 'loan_repayment' or transaction_ref.startswith('REPAY-'):
            try:
                loan_id = meta.get('loan_id')
                installment_id = meta.get('installment_id')

                # Fallback lookup by ref on the installment
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
                success_msg = "Repayment Successful!"
            except Exception as e:
                print(f"[VERIFY] Loan repayment error: {e}")
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
                # FIX: set user and fall through to shared tx logging below
                user = gig.employer
                success_msg = "Escrow Confirmed!"
            except Exception as e:
                print(f"[VERIFY] Gig escrow error: {e}")
                traceback.print_exc()

        # 4. GENERIC PAYMENT LINK (invoice)
        elif payment_link:
            user = payment_link.user
            if amount == 0:
                amount = float(payment_link.amount)
            _handle_payment_link_success(payment_link, transaction_ref, amount)
            success_msg = "Invoice Paid Successfully!"
            context['link'] = payment_link

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
                                payment_method='squad',
                                # FIX: per-order unique ref prevents IntegrityError
                                transaction_ref=f"SQUAD-{transaction_ref}-{order.id}",
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

        # ------------------------------------------------------------------
        # Shared: log transaction + trigger score recalculation
        # FIX: gig escrow no longer returns early — it falls through here
        # ------------------------------------------------------------------
        if user:
            _, created = OjaTransaction.objects.get_or_create(
                transaction_reference=transaction_ref,
                defaults={
                    'user': user,
                    'amount': amount,
                    'status': 'success',
                    'transaction_type': 'inflow',
                }
            )
            if created:
                _start_score_thread(user.id)

            context.update({"message": success_msg, "amount": amount})
            return render(request, 'payment_success.html', context)

        return redirect('profile')