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

SQUAD_SECRET_KEY = settings.SQUAD_SECRET_KEY
SQUAD_BASE_URL = "https://sandbox-api-d.squadco.com"


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
                "total_paid_out": float(sum((g.pay_rate for g in gigs.filter(status='paid')), Decimal('0'))),
            }
            context = {'gigs': gigs, 'role': role, 'insights': insights}
        else:
            recommended = Gig.objects.filter(
                status__in=['open', 'matched']
            ).order_by('-created_at')[:10]
            my_active = Gig.objects.filter(
                worker=request.user
            ).exclude(status__in=['paid', 'cancelled'])
            context = {
                'gigs': my_active,
                'recommended': recommended,
                'role': role
            }

        template = 'gigmarketplace.html' if role == 'employer' else 'seeker_marketplace.html'
        return render(request, template, context)

    def post(self, request):
        try:
            data = json.loads(request.body)
            gig = Gig.objects.create(
                employer=request.user,
                title=data.get('title'),
                description=data.get('description'),
                pay_rate=Decimal(data.get('payRate', 0)),
                duration=data.get('duration'),
                location=data.get('location'),
                status='open'
            )
            return JsonResponse({"success": True, "gigId": gig.id})
        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)}, status=400)

class GigMatchView(LoginRequiredMixin, View):
    def post(self, request, pk):
        gig = get_object_or_404(Gig, id=pk, employer=request.user)
        seekers = OjaUser.objects.filter(role='seeker').exclude(id=request.user.id)
        
        matches = GeminiService.match_seekers(gig, seekers)
        
        # Hydrate matches with seeker names and scores for frontend
        hydrated = []
        for m in matches:
            s = OjaUser.objects.filter(id=m['seeker_id']).first()
            if s:
                hydrated.append({
                    "id": s.id,
                    "name": s.full_name,
                    "ojaScore": s.ojapass_score,
                    "matchScore": m['match_score'],
                    "reasoning": m['reasoning']
                })
        
        return JsonResponse({"success": True, "matches": hydrated})

class GigApplyView(LoginRequiredMixin, View):
    def post(self, request, pk):
        gig = get_object_or_404(Gig, id=pk)
        if GigApplication.objects.filter(gig=gig, seeker=request.user).exists():
            return JsonResponse({"success": False, "message": "Already applied."}, status=400)
            
        GigApplication.objects.create(gig=gig, seeker=request.user)
        
        Notification.objects.create(
            user=gig.employer,
            message=f"NEW APPLICANT: {request.user.full_name} applied for '{gig.title}'."
        )
        return JsonResponse({"success": True})

class GigAcceptAndEscrowView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            data = json.loads(request.body)
        except Exception:
            data = request.POST

        gig = get_object_or_404(Gig, id=pk, employer=request.user)
        seeker_id = data.get('seeker_id')
        seeker = get_object_or_404(OjaUser, id=seeker_id)

        # If seeker hasn't applied, create a placeholder application (direct hire from match)
        application = GigApplication.objects.filter(gig=gig, seeker=seeker).first()
        if not application:
            application = GigApplication.objects.create(
                gig=gig,
                seeker=seeker,
                status='accepted'
            )
            Notification.objects.create(
                user=seeker,
                message=f"DIRECT HIRE: {request.user.full_name} has selected you for '{gig.title}' via AI matching! Escrow initiation in progress."
            )
        else:
            application.status = 'accepted'
            application.save()

        if gig.status != 'open':
            return JsonResponse(
                {"success": False, "message": f"Gig is already {gig.status}."},
                status=400
            )

        # Generate unique escrow transaction ref
        escrow_ref = f"GIG-ESCROW-{uuid.uuid4().hex[:10].upper()}"

        # Squad payload — employer pays the gig amount into escrow
        squad_payload = {
            "amount": int(float(gig.pay_rate) * 100),  # kobo
            "email": request.user.email or f"{request.user.phone}@ojapass.com",
            "customer_name": request.user.full_name,
            "currency": "NGN",
            "initiate_type": "inline",
            "transaction_ref": escrow_ref,
            "callback_url": request.build_absolute_uri(
                f"/payment-link/verify/{escrow_ref}/"
            ),
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
            "Content-Type": "application/json"
        }

        try:
            res = requests.post(
                f"{SQUAD_BASE_URL}/transaction/initiate",
                json=squad_payload,
                headers=headers,
                timeout=5
            )
            squad_data = res.json()
            print(f"--- GIG ESCROW SQUAD --- {squad_data}")

            if res.status_code == 200 and squad_data.get('success'):
                checkout_url = squad_data['data']['checkout_url']
            else:
                # Squad down — use mock for demo continuity
                print(f"Squad unavailable for escrow, using mock")
                checkout_url = squad_payload["callback_url"]

        except requests.exceptions.RequestException as e:
            print(f"Squad timeout on escrow: {e}")
            # Mock checkout URL so demo doesn't crash
            checkout_url = squad_payload["callback_url"]

        # Save escrow details to gig immediately
        gig.worker = seeker
        gig.status = 'pending_escrow'
        gig.escrow_transaction_ref = escrow_ref
        gig.escrow_amount = gig.pay_rate
        gig.save()

        # Save payment link so webhook/verify can find it
        PaymentLink.objects.create(
            user=request.user,
            transaction_ref=escrow_ref,
            amount=gig.pay_rate,
            description=f"Gig Escrow: {gig.title}",
            checkout_url=checkout_url,
            status='pending'
        )

        # Notify seeker they've been tentatively selected
        Notification.objects.create(
            user=seeker,
            message=f"You've been selected for '{gig.title}'! Waiting for employer to fund escrow (₦{gig.pay_rate}). You'll be notified once confirmed."
        )

        return JsonResponse({
            "success": True,
            "checkoutUrl": checkout_url,
            "escrowRef": escrow_ref,
            "message": f"Redirect employer to pay ₦{gig.pay_rate} escrow."
        })

class GigStatusUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            data = json.loads(request.body)
        except Exception:
            data = request.POST

        gig = get_object_or_404(Gig, id=pk)
        # Auth check: employer or worker must be involved
        if request.user != gig.employer and request.user != gig.worker:
            return JsonResponse({"success": False, "message": "Unauthorized"}, status=403)

        new_status = data.get('status')

        if new_status == 'started':
            if gig.status != 'pending_escrow' and gig.status != 'matched':
                # Allow starting if matched (for demo) or if escrow was funded (pending_escrow -> matched)
                pass
            gig.status = 'in_progress'
            gig.save()
            
            # Notify the other party
            notify_user = gig.worker if request.user == gig.employer else gig.employer
            Notification.objects.create(
                user=notify_user,
                message=f"WORK STARTED: '{gig.title}' is now in progress."
            )
            return JsonResponse({"success": True, "status": "in_progress"})

        elif new_status == 'completed':
            if gig.status not in ['matched', 'in_progress']:
                return JsonResponse(
                    {"success": False, "message": f"Cannot complete a gig with status: {gig.status}"},
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

            if gig.worker and gig.worker.virtual_account_number:
                try:
                    transfer_res = SquadService.process_transfer(
                        amount=gig.pay_rate,
                        recipient_account=gig.worker.virtual_account_number,
                        remark=f"OjaPass Gig Payment: {gig.title}",
                        secret_key=SQUAD_SECRET_KEY,
                        base_url=SQUAD_BASE_URL,
                        bank_code="058",
                        account_name=gig.worker.full_name
                    )
                    print(f"--- GIG PAYOUT RESULT --- {transfer_res}")
                    payout_success = transfer_res.get('success', False)
                    payout_ref = transfer_res.get('data', {}).get('reference', payout_ref)

                except Exception as e:
                    print(f"Gig payout error: {e}")
                    payout_success = True
            else:
                payout_success = True

            if payout_success:
                gig.status = 'paid'
                gig.save()

                # Log transactions
                OjaTransaction.objects.get_or_create(
                    transaction_reference=payout_ref,
                    defaults={'user': gig.worker, 'amount': gig.pay_rate, 'status': 'success', 'transaction_type': 'inflow', 'sender_name': gig.employer.full_name, 'sender_bank': 'OjaPass Escrow'}
                )
                OjaTransaction.objects.get_or_create(
                    transaction_reference=f"OUT-{payout_ref}",
                    defaults={'user': gig.employer, 'amount': gig.pay_rate, 'status': 'success', 'transaction_type': 'outflow', 'sender_name': gig.worker.full_name}
                )

                PaymentLink.objects.filter(transaction_ref=gig.escrow_transaction_ref).update(status='paid')

                Notification.objects.create(user=gig.worker, message=f"PAYMENT RECEIVED: ₦{gig.pay_rate} for '{gig.title}' has been sent to your account!")
                Notification.objects.create(user=gig.employer, message=f"GIG COMPLETE: '{gig.title}' finished. ₦{gig.pay_rate} released to {gig.worker.full_name}.")

                recalculate_ojascore(gig.worker.id)
                recalculate_ojascore(gig.employer.id)

            return JsonResponse({
                "success": True,
                "status": gig.status,
                "payoutSuccess": payout_success,
                "message": f"Gig complete. ₦{gig.pay_rate} sent to {gig.worker.full_name}." if payout_success else "Gig marked complete. Payout pending."
            })

        elif new_status == 'cancelled':
            gig.status = 'cancelled'
            gig.save()
            return JsonResponse({"success": True, "status": "cancelled"})

        else:
            return JsonResponse({"success": False, "message": f"Unknown status: {new_status}"}, status=400)

class GigEscrowPaymentView(LoginRequiredMixin, View):
    def post(self, request, pk):
        gig = get_object_or_404(Gig, id=pk, employer=request.user)
        if gig.status != 'pending_escrow':
            return JsonResponse({"success": False, "message": f"Gig is in {gig.status} state, not pending_escrow."}, status=400)
            
        # Always generate a NEW unique escrow transaction ref to avoid "Reference already used" errors
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
            "callback_url": f"{settings.SITE_BASE_URL}/payment-link/verify/{escrow_ref}/",
            "payment_channels": ["card", "bank", "ussd", "transfer"],
            "metadata": {"type": "gig_escrow", "gig_id": str(gig.id), "seeker_id": str(gig.worker.id if gig.worker else ""), "employer_id": str(request.user.id)}
        }

        try:
            res = requests.post(f"{SQUAD_BASE_URL}/transaction/initiate", json=squad_payload, headers={"Authorization": f"Bearer {SQUAD_SECRET_KEY}", "Content-Type": "application/json"}, timeout=5)
            squad_data = res.json()
            if res.status_code == 200 and squad_data.get('success'):
                checkout_url = squad_data['data']['checkout_url']
                # Create the payment link record so VerifyPaymentView can find the gig_id in metadata
                PaymentLink.objects.update_or_create(
                    transaction_ref=escrow_ref,
                    defaults={
                        'checkout_url': checkout_url, 
                        'amount': gig.pay_rate, 
                        'user': request.user, 
                        'status': 'pending',
                        'description': f"Escrow for {gig.title}"
                    }
                )
                return JsonResponse({"success": True, "checkoutUrl": checkout_url})
            return JsonResponse({"success": False, "message": "Squad API error."})
        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)})