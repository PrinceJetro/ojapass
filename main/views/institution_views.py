from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.db.models import Sum, Avg, Count
from main.models import OjaUser, Loan, LoanOffer, Sale, Gig, GigApplication

class LenderDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role not in ['lender', 'gov'] and not request.user.is_staff:
            return JsonResponse({"success": False, "message": "Unauthorized."}, status=403)

        # Portfolio Summary
        active_loans = Loan.objects.filter(status='active')
        total_active_loans = active_loans.count()
        
        defaulted_loans = Loan.objects.filter(status='defaulted').count()
        total_loans = total_active_loans + defaulted_loans + Loan.objects.filter(status='completed').count()
        
        default_rate = (defaulted_loans / total_loans * 100) if total_loans > 0 else 0
        
        # Calculate Average OjaScore for Active Borrowers
        borrower_ids = active_loans.values_list('user_id', flat=True)
        avg_score_agg = OjaUser.objects.filter(id__in=borrower_ids).aggregate(Avg('ojapass_score'))
        avg_ojascore = int(avg_score_agg['ojapass_score__avg'] or 0)

        # Applicant Queue
        applicants = LoanOffer.objects.filter(status='applied').select_related('user').order_by('-applied_at')[:10]
        
        # Live Sales Feed (Mamatally Integration)
        live_sales = Sale.objects.select_related('user').order_by('-created_at')[:5]

        context = {
            'total_active_loans': total_active_loans,
            'portfolio_yield': 18.4, # Mocked for demo
            'default_rate': default_rate,
            'avg_ojascore': avg_ojascore,
            'applicants': applicants,
            'live_sales': live_sales,
        }
        return render(request, 'institution/lender_dashboard.html', context)


class GovernmentDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role != 'gov' and not request.user.is_staff:
            return JsonResponse({"success": False, "message": "Unauthorized."}, status=403)

        # Inclusion Metrics
        total_users = OjaUser.objects.count()
        banked_users = OjaUser.objects.filter(ojapass_score__gte=31).count() # Score 31+ unlocks basics
        
        # Gig Economy
        gig_workers = OjaUser.objects.filter(role__in=['seeker', 'both']).count()
        
        # LGA Aggregation
        lga_data = OjaUser.objects.values('lga').annotate(
            active_traders=Count('id'),
            # We would typically aggregate transactions here, but for demo we can just count users
        ).order_by('-active_traders')[:5]

        context = {
            'banked_users': banked_users,
            'total_users': total_users,
            'gig_workers': gig_workers,
            'lga_data': lga_data,
        }
        return render(request, 'institution/gov_dashboard.html', context)
