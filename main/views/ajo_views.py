from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
import json
import uuid
import requests
import traceback
from ..models import OjaUser, AjoGroup, AjoMembership, AjoCycle, AjoContribution, PaymentLink, Notification
from ..services.squad_service import SquadService
from ..services.oja_score import recalculate_ojascore

SQUAD_SECRET_KEY = settings.SQUAD_SECRET_KEY
SQUAD_BASE_URL = "https://sandbox-api-d.squadco.com"

def _create_next_cycle(group):
    members = list(group.memberships.order_by('rotation_order'))
    if not members: return None
    beneficiary = members[group.current_beneficiary_index % len(members)].user
    days = 7 if group.frequency == 'weekly' else 30
    cycle = AjoCycle.objects.create(group=group, cycle_number=group.current_cycle, beneficiary=beneficiary, expected_amount=group.contribution_amount * len(members), due_date=timezone.now() + timedelta(days=days))
    for m in members: AjoContribution.objects.create(cycle=cycle, member=m.user, amount=group.contribution_amount)
    return cycle

def _disburse_cycle(cycle, group):
    if not cycle: return {"success": False, "message": "No active cycle to disburse."}
    total = sum(c.amount for c in cycle.contributions.filter(status='paid'))
    if total <= 0: return {"success": False, "message": "No contributions found for this cycle."}
    
    if not cycle.beneficiary.virtual_account_number:
        return {"success": False, "message": f"Beneficiary {cycle.beneficiary.full_name} has no virtual account."}

    res = SquadService.process_transfer(total, cycle.beneficiary.virtual_account_number, "Ajo Payout", SQUAD_SECRET_KEY, SQUAD_BASE_URL)
    if res.get('success'):
        cycle.status, cycle.disbursed_at = 'disbursed', timezone.now()
        cycle.save()
        group.current_cycle += 1
        group.current_beneficiary_index = (group.current_beneficiary_index + 1) % group.memberships.count()
        group.save()
        # Update beneficiary stats
        beneficiary_membership = AjoMembership.objects.filter(group=group, user=cycle.beneficiary).first()
        if beneficiary_membership:
            beneficiary_membership.cycles_completed += 1
            beneficiary_membership.total_received += Decimal(str(total))
            beneficiary_membership.save()

        for m in group.memberships.all(): recalculate_ojascore(m.user.id)
        return {"success": True}
    return {"success": False, "message": "Transfer failed."}

class AjoGroupListView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        memberships = AjoMembership.objects.filter(user=user)
        
        total_saved = sum(m.total_contributed for m in memberships)
        active_cycles_count = memberships.filter(group__status='active').count()
        
        # Find next payout date and amount
        next_cycle = AjoCycle.objects.filter(beneficiary=user, status__in=['open', 'collecting']).order_by('due_date').first()
        next_payout_date = next_cycle.due_date if next_cycle else None
        next_payout_amount = next_cycle.expected_amount if next_cycle else 0
        
        # All available groups for discovery
        discover_groups = AjoGroup.objects.exclude(memberships__user=user).filter(status='active')[:10]
        
        context = {
            'memberships': memberships,
            'total_saved': float(total_saved),
            'active_cycles_count': active_cycles_count,
            'next_payout_date': next_payout_date,
            'next_payout_amount': float(next_payout_amount),
            'discover_groups': discover_groups
        }
        return render(request, 'ajodashboard.html', context)

    def post(self, request):
        try:
            data = json.loads(request.body)
        except:
            data = request.POST
            
        contrib_amount = float(data.get('contributionAmount', 0))
        if contrib_amount <= 0:
            return JsonResponse({"success": False, "message": "Contribution amount must be greater than 0."}, status=400)

        g = AjoGroup.objects.create(
            name=data.get('name'), 
            creator=request.user, 
            contribution_amount=contrib_amount, 
            frequency=data.get('frequency', 'weekly'),
            max_members=int(data.get('maxMembers', 10))
        )
        AjoMembership.objects.create(group=g, user=request.user, rotation_order=1)
        _create_next_cycle(g)
        return JsonResponse({"success": True})

class AjoGroupDetailView(LoginRequiredMixin, View):
    def get(self, request, pk):
        group = get_object_or_404(AjoGroup, id=pk)
        membership = get_object_or_404(AjoMembership, group=group, user=request.user)
        current_cycle = group.cycles.filter(status__in=['open', 'collecting']).first()
        
        # Get all cycles for history/schedule
        all_cycles = group.cycles.all().order_by('cycle_number')
        
        # Get all members with their payment status for this cycle
        members_data = []
        for m in group.memberships.all().order_by('rotation_order'):
            contribution = AjoContribution.objects.filter(cycle=current_cycle, member=m.user).first() if current_cycle else None
            members_data.append({
                'user': m.user,
                'order': m.rotation_order,
                'status': contribution.status if contribution else 'N/A',
                'is_me': m.user == request.user
            })
            
        context = {
            'group': group,
            'membership': membership,
            'current_cycle': current_cycle,
            'all_cycles': all_cycles,
            'members': members_data,
            'progress': (current_cycle.collected_amount / current_cycle.expected_amount * 100) if current_cycle and current_cycle.expected_amount > 0 else 0
        }
        return render(request, 'ajogroupdetails.html', context)

class AjoJoinView(LoginRequiredMixin, View):
    def post(self, request, pk):
        group = get_object_or_404(AjoGroup, id=pk)
        if group.memberships.count() >= group.max_members:
            return JsonResponse({"success": False, "message": "Group is full."}, status=400)

        membership, created = AjoMembership.objects.get_or_create(
            group=group, 
            user=request.user, 
            defaults={'rotation_order': group.memberships.count() + 1}
        )
        
        if created:
            # If there's an open cycle, add a contribution record for the new member
            current_cycle = group.cycles.filter(status='open').first()
            if current_cycle:
                AjoContribution.objects.get_or_create(
                    cycle=current_cycle,
                    member=request.user,
                    defaults={'amount': group.contribution_amount}
                )
                # Update cycle expected amount
                current_cycle.expected_amount = group.contribution_amount * group.memberships.count()
                current_cycle.save()

        return JsonResponse({"success": True})

class AjoContributeView(LoginRequiredMixin, View):
    def post(self, request, pk):
        group = AjoGroup.objects.get(id=pk)
        cycle = group.cycles.filter(status__in=['open', 'collecting']).first()
        if not cycle:
            return JsonResponse({"success": False, "message": "No active cycle."}, status=400)
            
        contrib = AjoContribution.objects.filter(cycle=cycle, member=request.user).first()
        if contrib and contrib.status == 'paid':
            return JsonResponse({"success": False, "message": "Already contributed this cycle."}, status=400)
            
        ref = f"AJO-{uuid.uuid4().hex[:12].upper()}"
        payload = {
            "amount": int(float(group.contribution_amount) * 100), 
            "email": request.user.email or f"{request.user.phone}@ojapass.com",
            "customer_name": request.user.full_name,
            "currency": "NGN",
            "initiate_type": "inline",
            "transaction_ref": ref,
            "callback_url": request.build_absolute_uri(f"/payment-link/verify/{ref}/"),
            "payment_channels": ["card", "bank", "ussd", "transfer"],
            "metadata": {
                "type": "ajo_contribution", 
                "group_id": str(group.id), 
                "cycle_id": str(cycle.id), 
                "member_id": str(request.user.id)
            }
        }
        try:
            res = requests.post(f"{SQUAD_BASE_URL}/transaction/initiate", json=payload, headers={"Authorization": f"Bearer {SQUAD_SECRET_KEY}"}, timeout=5)
            data = res.json()
            status = res.status_code
        except requests.exceptions.RequestException:
            status = 200
            data = {"success": True, "data": {"checkout_url": payload["callback_url"]}}
            
        if status == 200 and data.get('success'):
            AjoContribution.objects.filter(cycle=cycle, member=request.user).update(payment_link=data['data']['checkout_url'], transaction_ref=ref)
            return JsonResponse({"success": True, "checkoutUrl": data['data']['checkout_url']})
        return JsonResponse({"success": False}, status=400)

class AjoDisbursementView(LoginRequiredMixin, View):
    def post(self, request, pk):
        group = AjoGroup.objects.get(id=pk, creator=request.user)
        result = _disburse_cycle(group.cycles.filter(status='collecting').first(), group)
        return JsonResponse(result)

class UserAjoHistoryView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        memberships = AjoMembership.objects.filter(user=user)
        total_contributed = sum(m.total_contributed for m in memberships)
        total_received = sum(m.total_received for m in memberships)
        
        # Get cycles from all groups user is a member of
        group_ids = memberships.values_list('group_id', flat=True)
        cycles = AjoCycle.objects.filter(group_id__in=group_ids).order_by('-created_at')[:50]
        
        # Calculate overall progress for active cycles
        active_cycles = AjoCycle.objects.filter(group_id__in=group_ids, status__in=['open', 'collecting'])
        total_expected = sum(c.expected_amount for c in active_cycles)
        total_collected = sum(c.collected_amount for c in active_cycles)
        progress = (total_collected / total_expected * 100) if total_expected > 0 else 0
        
        context = {
            'memberships': memberships,
            'total_contributed': float(total_contributed),
            'total_received': float(total_received),
            'cycles': cycles,
            'progress': progress
        }
        return render(request, 'ajohistory.html', context)

class ScoreNarrativeView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'ojascore_narrative.html', {'user': request.user})

class FundWalletView(LoginRequiredMixin, View):
    def post(self, request):
        amount = request.POST.get('amount', 0)
        try:
            amount = Decimal(str(amount))
            if amount > 0:
                user = request.user
                user.wallet_balance += amount
                user.save()
                Notification.objects.create(
                    user=user,
                    message=f"Wallet funded with ₦{amount} successfully."
                )
        except:
            pass
        return redirect('ajo_list')