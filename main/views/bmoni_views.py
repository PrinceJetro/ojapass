from django.views import View
from django.http import JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from ..services.bmoni_service import BMONIService
from ..models import OjaTransaction, OjaUser


class SubmitProposalSignatureView(LoginRequiredMixin, View):
    """Accept an EIP-712 signature and submit it to BMONI for a proposal."""
    def post(self, request, proposal_id):
        import json
        try:
            data = json.loads(request.body)
        except Exception:
            data = request.POST

        signature = data.get('signature')
        if not signature:
            return JsonResponse({'success': False, 'message': 'signature is required'}, status=400)

        user = request.user
        bmoni_user_id = getattr(user, 'bmoni_user_id', None)
        if not bmoni_user_id:
            return JsonResponse({'success': False, 'message': 'User not linked to BMONI'}, status=400)

        res = BMONIService.submit_proposal_signature(bmoni_user_id, proposal_id, signature)
        if not res.get('success'):
            return JsonResponse({'success': False, 'message': 'BMONI submission failed', 'error': res}, status=502)

        # On success, mark any transactions tied to this proposal as successful
        txs = OjaTransaction.objects.filter(gateway_reference=proposal_id)
        for tx in txs:
            tx.status = 'success'
            tx.save()

            # Credit worker wallet if inflow and not yet credited
            if tx.transaction_type == 'inflow':
                try:
                    # Update the user's wallet balance
                    u = tx.user
                    u.wallet_balance = (u.wallet_balance or 0) + tx.amount
                    u.save()
                except Exception:
                    pass

        return JsonResponse({'success': True, 'data': res.get('data')})


class SignProposalPageView(LoginRequiredMixin, View):
    """Minimal frontend page to paste and submit a signature for a proposal."""
    def get(self, request, proposal_id):
        return render(request, 'bmoni_sign_proposal.html', {'proposal_id': proposal_id})
