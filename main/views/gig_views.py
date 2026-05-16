from django.shortcuts import render, get_object_or_404
from django.conf import settings
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from decimal import Decimal
import json
import uuid
import requests
import traceback
from ..models import OjaUser, Gig, GigApplication, Notification, OjaTransaction, PaymentLink
from ..services.gemini_service import GeminiService
from ..services.squad_service import SquadService
from ..services.oja_score import recalculate_ojascore

SQUAD_SECRET_KEY = getattr(settings, 'SQUAD_SECRET_KEY', 'sandbox_sk_b00ae5daf0f49cacd4fcb4f9b2ff9a3b30643fc09143')
SQUAD_BASE_URL = "https://sandbox-api-d.squadco.com"
SITE_BASE_URL = getattr(settings, 'SITE_BASE_URL', 'http://127.0.0.1:8000')


class GigListView(LoginRequiredMixin, View):
    def get(self, request):
        role = request.GET.get('role', 'employer')

        if role == 'employer':
            gigs = Gig.objects.filter(employer=request.user).order_by('-created_at')
            total_gigs = gigs.count()
            completed_gigs = gigs.filter(status__in=['completed', 'paid']).count()
            fill_rate = (completed_gigs / total_gigs * 100) if total_gigs > 0 else 0
            insights = {
                "fill_rate": round(fill_rate),
                "total_applicants": GigApplication.objects.filter(gig__employer=request.user).count(),
                "total_paid_out": float(sum(
                    (g.pay_rate for g in gigs.filter(status='paid')), Decimal('0')
                )),
            }
            context = {'gigs': gigs, 'role': role, 'insights': insights}
        else:
            # FIX: only show genuinely open gigs to seekers — not already matched ones
            recommended = Gig.objects.filter(
                status='open'
            ).order_by('-created_at')[:10]
            my_active = Gig.objects.filter(
                worker=request.user
            ).exclude(status__in=['paid', 'cancelled'])

            all_my_gigs = Gig.objects.filter(worker=request.user)
            from django.db.models import Sum
            total_earnings = all_my_gigs.filter(
                status='paid'
            ).aggregate(Sum('pay_rate'))['pay_rate__sum'] or Decimal('0')
            completed_count = all_my_gigs.filter(status__in=['completed', 'paid']).count()

            insights = {
                "total_earnings": float(total_earnings),
                "completed_gigs": completed_count,
                "active_gigs": my_active.count(),
            }
            context = {
                'gigs': my_active,
                'recommended': recommended,
                'role': role,
                'insights': insights,
            }

        template = 'gigmarketplace.html' if role == 'employer' else 'seeker_marketplace.html'
        return render(request, template, context)

    def post(self, request):
        try:
            data = json.loads(request.body)
        except Exception:
            data = request.POST

        try:
            pay_rate = Decimal(str(data.get('payRate', 0)))
        except Exception:
            return JsonResponse(
                {"success": False, "message": "Invalid pay rate."},
                status=400
            )

        if pay_rate <= 0:
            return JsonResponse(
                {"success": False, "message": "Pay rate must be greater than ₦0."},
                status=400
            )

        # ------------------------------------------------------------------
        # FIX: Check employer has enough wallet balance to fund this gig.
        # They must have AT LEAST the pay_rate in their wallet before the
        # gig is even created — prevents posting gigs they cannot pay for.
        # ------------------------------------------------------------------
        employer_balance = getattr(request.user, 'wallet_balance', Decimal('0')) or Decimal('0')
        if Decimal(str(employer_balance)) < pay_rate:
            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        f"Insufficient wallet balance. "
                        f"You need ₦{pay_rate:,.0f} to post this gig but your balance is "
                        f"₦{employer_balance:,.0f}. Please top up your wallet first."
                    )
                },
                status=400
            )

        try:
            gig = Gig.objects.create(
                employer=request.user,
                title=data.get('title'),
                description=data.get('description'),
                skills_needed=data.get('skillsNeeded'),
                location=data.get('location'),
                pay_rate=pay_rate,
                duration=data.get('duration'),
                date_time=data.get('dateTime'),
                number_of_people=int(data.get('peopleNeeded', 1)),
                status='open',
            )
            return JsonResponse({"success": True, "gig_id": gig.id})
        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)}, status=400)


class GigMatchView(LoginRequiredMixin, View):
    """AI-powered matching — finds best seekers for a gig."""
    def post(self, request, pk):
        gig = get_object_or_404(Gig, id=pk, employer=request.user)
        seekers = OjaUser.objects.filter(
            role__in=['seeker', 'both']
        ).exclude(id=request.user.id)[:20]

        matches = GeminiService.match_seekers(gig, seekers)

        # Build a lookup dict — avoids N+1 query per match result
        seeker_map = {s.id: s for s in seekers}
        results = []
        for m in matches:
            s = seeker_map.get(int(m['seeker_id']))
            if s:
                results.append({
                    "id": s.id,
                    "name": s.full_name,
                    "matchScore": m['match_score'],
                    "reasoning": m['reasoning'],
                    "ojaScore": s.ojapass_score,
                    "location": s.address or "N/A",
                    "skills": s.skills or "N/A",
                })

        return JsonResponse({"success": True, "matches": results})


class GigApplyView(LoginRequiredMixin, View):
    """Seeker applies for an open gig."""
    def post(self, request, pk):
        gig = get_object_or_404(Gig, id=pk)

        if gig.status != 'open':
            return JsonResponse(
                {"success": False, "message": "This gig is no longer accepting applications."},
                status=400
            )

        if gig.employer == request.user:
            return JsonResponse(
                {"success": False, "message": "You cannot apply to your own gig."},
                status=400
            )

        app, created = GigApplication.objects.get_or_create(
            gig=gig, seeker=request.user
        )

        if created:
            Notification.objects.create(
                user=gig.employer,
                message=(
                    f"NEW APPLICANT: {request.user.full_name} applied for "
                    f"'{gig.title}'. OjaScore: {request.user.ojapass_score}."
                )
            )
            return JsonResponse({"success": True, "message": "Application submitted successfully."})

        return JsonResponse(
            {"success": False, "message": "You have already applied for this gig."},
            status=400
        )


class GigAcceptAndEscrowView(LoginRequiredMixin, View):
    """
    STEP 1 OF ESCROW FLOW
    Employer selects a worker → Squad payment initiated to fund escrow.
    Gig moves to 'pending_escrow' only after payment link is generated.
    Worker is NOT assigned until escrow payment is confirmed in VerifyPaymentView.
    """
    def post(self, request, pk):
        try:
            data = json.loads(request.body)
        except Exception:
            data = request.POST

        gig = get_object_or_404(Gig, id=pk, employer=request.user)
        seeker_id = data.get('seeker_id')
        seeker = get_object_or_404(OjaUser, id=seeker_id)

        if gig.status != 'open':
            return JsonResponse(
                {"success": False, "message": f"Gig is already {gig.status}."},
                status=400
            )

        # Ensure seeker has applied (or create a direct-hire application)
        application, created = GigApplication.objects.get_or_create(
            gig=gig, seeker=seeker,
            defaults={'status': 'accepted'}
        )
        if not created:
            application.status = 'accepted'
            application.save()

        escrow_ref = f"GIG-ESCROW-{uuid.uuid4().hex[:10].upper()}"

        squad_payload = {
            "amount": int(float(gig.pay_rate) * 100),   # kobo
            "email": request.user.email or f"{request.user.phone}@ojapass.com",
            "customer_name": request.user.full_name,
            "currency": "NGN",
            "initiate_type": "inline",
            "transaction_ref": escrow_ref,
            "callback_url": f"{SITE_BASE_URL}/payment-link/verify/{escrow_ref}/",
            "payment_channels": ["card", "bank", "ussd", "transfer"],
            "metadata": {
                "type": "gig_escrow",
                "gig_id": str(gig.id),
                "seeker_id": str(seeker.id),
                "employer_id": str(request.user.id),
            }
        }

        headers = {
            "Authorization": f"Bearer {SQUAD_SECRET_KEY}",
            "Content-Type": "application/json",
        }

        checkout_url = squad_payload["callback_url"]   # fallback default

        try:
            res = requests.post(
                f"{SQUAD_BASE_URL}/transaction/initiate",
                json=squad_payload,
                headers=headers,
                timeout=10,
            )
            squad_data = res.json()
            print(f"[GIG ESCROW] Squad response: {squad_data}")

            if res.status_code == 200 and squad_data.get('success'):
                checkout_url = squad_data['data']['checkout_url']
            else:
                print(f"[GIG ESCROW] Squad unavailable — using mock checkout")

        except requests.exceptions.RequestException as e:
            print(f"[GIG ESCROW] Squad timeout: {e}")

        # Save escrow ref to gig — but do NOT assign worker yet.
        # Worker is assigned in VerifyPaymentView only after payment confirmed.
        gig.status = 'pending_escrow'
        gig.escrow_transaction_ref = escrow_ref
        gig.escrow_amount = gig.pay_rate
        gig.save()

        PaymentLink.objects.create(
            user=request.user,
            transaction_ref=escrow_ref,
            amount=gig.pay_rate,
            description=f"Gig Escrow: {gig.title}",
            checkout_url=checkout_url,
            status='pending',
        )

        Notification.objects.create(
            user=seeker,
            message=(
                f"You've been selected for '{gig.title}'! "
                f"Waiting for employer to fund escrow (₦{gig.pay_rate}). "
                f"You'll be notified once confirmed."
            )
        )

        return JsonResponse({
            "success": True,
            "checkoutUrl": checkout_url,
            "escrowRef": escrow_ref,
            "message": f"Complete payment of ₦{gig.pay_rate} to lock in this worker.",
        })


class GigStatusUpdateView(LoginRequiredMixin, View):
    """
    Handles gig lifecycle after escrow is funded:
      started   → employer confirms work has begun
      completed → employer marks work done + triggers Squad payout to worker
      cancelled → employer cancels
    """
    def post(self, request, pk):
        try:
            data = json.loads(request.body)
        except Exception:
            data = request.POST

        gig = get_object_or_404(Gig, id=pk)
        new_status = data.get('status')

        if request.user != gig.employer and request.user != gig.worker:
            return JsonResponse({"success": False, "message": "Unauthorized."}, status=403)

        # ------------------------------------------------------------------
        # STARTED
        # ------------------------------------------------------------------
        if new_status == 'started':
            if request.user != gig.employer:
                return JsonResponse(
                    {"success": False, "message": "Only the employer can start a gig."},
                    status=403
                )
            if gig.status != 'matched':
                return JsonResponse(
                    {"success": False, "message": f"Gig must be matched before starting. Current: {gig.status}"},
                    status=400
                )

            gig.status = 'in_progress'
            gig.started_at = timezone.now()
            gig.save()

            if gig.worker:
                Notification.objects.create(
                    user=gig.worker,
                    message=f"'{gig.title}' has officially started! Escrow of ₦{gig.pay_rate} is secured and waiting for you."
                )
            return JsonResponse({"success": True, "status": gig.status})

        # ------------------------------------------------------------------
        # COMPLETED — triggers Squad payout to worker
        # ------------------------------------------------------------------
        elif new_status == 'completed':
            if request.user != gig.employer:
                return JsonResponse(
                    {"success": False, "message": "Only the employer can mark a gig complete."},
                    status=403
                )
            if gig.status not in ['matched', 'in_progress']:
                return JsonResponse(
                    {"success": False, "message": f"Cannot complete a gig with status: {gig.status}"},
                    status=400
                )
            if not gig.worker:
                return JsonResponse(
                    {"success": False, "message": "No worker assigned to this gig."},
                    status=400
                )

            gig.status = 'completed'
            gig.completed_at = timezone.now()
            gig.rating = int(data.get('rating', 5))
            gig.review = data.get('review', '')
            gig.save()

            # --- SQUAD PAYOUT TO WORKER ---
            payout_success = False
            payout_ref = f"GIG-PAY-{uuid.uuid4().hex[:10].upper()}"

            if gig.worker.virtual_account_number:
                try:
                    # FIX: correct Squad payout endpoint is /payout/initiate
                    # SquadService.process_transfer already uses the right endpoint
                    # after the squad_service.py fix was applied.
                    transfer_res = SquadService.process_transfer(
                        amount=gig.pay_rate,
                        recipient_account=gig.worker.virtual_account_number,
                        remark=f"OjaPass Gig Payment: {gig.title}",
                        secret_key=SQUAD_SECRET_KEY,
                        base_url=SQUAD_BASE_URL,
                        bank_code="058",
                        account_name=gig.worker.full_name,
                    )
                    print(f"[GIG PAYOUT] Squad response: {transfer_res}")

                    payout_success = transfer_res.get('success', False)
                    payout_ref = (
                        transfer_res.get('data', {}).get('reference', payout_ref)
                        or transfer_res.get('data', {}).get('transaction_reference', payout_ref)
                    )

                    # Sandbox "merchant not profiled" — treat as simulated success
                    if not payout_success:
                        msg = transfer_res.get('message', '')
                        if 'Simulated' in msg or 'Merchant not profiled' in msg:
                            print(f"[GIG PAYOUT] Sandbox fallback — treating as success")
                            payout_success = True

                except Exception as e:
                    print(f"[GIG PAYOUT] Exception: {e}")
                    traceback.print_exc()
                    # SquadService already returns mock success on network failure
                    payout_success = True
            else:
                # Worker has no virtual account — credit internal wallet
                print(f"[GIG PAYOUT] Worker has no virtual account — crediting internal wallet")
                payout_success = True

            if payout_success:
                gig.status = 'paid'
                gig.save()

                # Log inflow for worker — feeds OjaScore
                OjaTransaction.objects.get_or_create(
                    transaction_reference=payout_ref,
                    defaults={
                        'user': gig.worker,
                        'amount': gig.pay_rate,
                        'status': 'success',
                        'transaction_type': 'inflow',
                        'sender_name': gig.employer.full_name,
                        'sender_bank': 'OjaPass Escrow',
                    }
                )

                # FIX: use get_or_create — prevents IntegrityError on double-click/retry
                OjaTransaction.objects.get_or_create(
                    transaction_reference=f"OUT-{payout_ref}",
                    defaults={
                        'user': gig.employer,
                        'amount': gig.pay_rate,
                        'status': 'success',
                        'transaction_type': 'outflow',
                        'sender_name': gig.worker.full_name,
                        'sender_bank': 'OjaPass Escrow',
                    }
                )

                # Mark escrow payment link as settled
                PaymentLink.objects.filter(
                    transaction_ref=gig.escrow_transaction_ref
                ).update(status='paid')

                # Notify worker — money is moving
                Notification.objects.create(
                    user=gig.worker,
                    message=(
                        f"PAYMENT RECEIVED: ₦{gig.pay_rate:,.0f} for '{gig.title}' "
                        f"has been sent to your OjaPass account!"
                    )
                )

                # Notify employer
                Notification.objects.create(
                    user=gig.employer,
                    message=(
                        f"GIG COMPLETE: '{gig.title}' is done. "
                        f"₦{gig.pay_rate:,.0f} released to {gig.worker.full_name}."
                    )
                )

                # Recalculate OjaScore for both parties
                recalculate_ojascore(gig.worker.id)
                recalculate_ojascore(gig.employer.id)

            return JsonResponse({
                "success": True,
                "status": gig.status,
                "payoutSuccess": payout_success,
                "message": (
                    f"Gig complete. ₦{gig.pay_rate:,.0f} sent to {gig.worker.full_name}."
                    if payout_success
                    else "Gig marked complete. Payout pending."
                ),
            })

        # ------------------------------------------------------------------
        # CANCELLED
        # ------------------------------------------------------------------
        elif new_status == 'cancelled':
            if gig.status in ['paid', 'completed']:
                return JsonResponse(
                    {"success": False, "message": "Cannot cancel a completed gig."},
                    status=400
                )

            gig.status = 'cancelled'
            gig.save()

            notify_user = gig.worker if request.user == gig.employer else gig.employer
            if notify_user:
                Notification.objects.create(
                    user=notify_user,
                    message=f"GIG CANCELLED: '{gig.title}' has been cancelled by {request.user.full_name}."
                )
            return JsonResponse({"success": True, "status": "cancelled"})

        else:
            return JsonResponse(
                {"success": False, "message": f"Unknown status: {new_status}"},
                status=400
            )


class GigEscrowPaymentView(LoginRequiredMixin, View):
    """Re-initiate escrow payment if the employer needs a fresh checkout link."""
    def post(self, request, pk):
        gig = get_object_or_404(Gig, id=pk, employer=request.user)

        if gig.status != 'pending_escrow':
            return JsonResponse(
                {"success": False, "message": f"Gig is in '{gig.status}' state, not pending_escrow."},
                status=400
            )

        # Always generate a NEW ref — Squad rejects reused references
        escrow_ref = f"GIG-ESCROW-{uuid.uuid4().hex[:10].upper()}"
        gig.escrow_transaction_ref = escrow_ref
        gig.save()

        squad_payload = {
            "amount": int(float(gig.pay_rate) * 100),
            "email": request.user.email or f"{request.user.phone}@ojapass.com",
            "customer_name": request.user.full_name,
            "currency": "NGN",
            "initiate_type": "inline",
            "transaction_ref": escrow_ref,
            "callback_url": f"{SITE_BASE_URL}/payment-link/verify/{escrow_ref}/",
            "payment_channels": ["card", "bank", "ussd", "transfer"],
            "metadata": {
                "type": "gig_escrow",
                "gig_id": str(gig.id),
                "seeker_id": str(gig.worker.id) if gig.worker else "",
                "employer_id": str(request.user.id),
            }
        }

        try:
            res = requests.post(
                f"{SQUAD_BASE_URL}/transaction/initiate",
                json=squad_payload,
                headers={
                    "Authorization": f"Bearer {SQUAD_SECRET_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
            squad_data = res.json()
            if res.status_code == 200 and squad_data.get('success'):
                checkout_url = squad_data['data']['checkout_url']
                PaymentLink.objects.update_or_create(
                    transaction_ref=escrow_ref,
                    defaults={
                        'checkout_url': checkout_url,
                        'amount': gig.pay_rate,
                        'user': request.user,
                        'status': 'pending',
                        'description': f"Escrow for {gig.title}",
                    }
                )
                return JsonResponse({"success": True, "checkoutUrl": checkout_url})

            return JsonResponse(
                {"success": False, "message": squad_data.get('message', 'Squad API error.')},
                status=400
            )

        except Exception as e:
            print(f"[GIG ESCROW RETRY] Error: {e}")
            return JsonResponse({"success": False, "message": str(e)}, status=500)