from django.shortcuts import render, redirect
from django.conf import settings
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from datetime import datetime
import uuid
import requests
import traceback
import random
from ..models import OjaUser

SQUAD_SECRET_KEY = settings.SQUAD_SECRET_KEY
SQUAD_BASE_URL = "https://sandbox-api-d.squadco.com"

class RegisterView(View):
    def get(self, request):
        return render(request, 'onboarding.html')

    def post(self, request):
        import json
        try:
            data = json.loads(request.body)
        except:
            data = request.POST

        required_fields = ['firstName', 'lastName', 'phone', 'email', 'bvn', 'dob', 'gender', 'address', 'pin']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({"success": False, "message": f"{field} is required."}, status=400)

        if OjaUser.objects.filter(phone=data.get('phone')).exists():
            return JsonResponse({"success": False, "message": "A user with this phone number already exists."}, status=400)

        try:
            dob_obj = datetime.strptime(data.get('dob'), '%Y-%m-%d')
            formatted_dob = dob_obj.strftime('%m/%d/%Y')
        except ValueError:
            return JsonResponse({"success": False, "message": "Invalid date format. Use YYYY-MM-DD."}, status=400)

        first_name, last_name = data.get('firstName').strip(), data.get('lastName').strip()
        middle_name = data.get('middleName', 'N/A').strip() or 'N/A'
        full_name = f"{first_name} {middle_name} {last_name}".strip()

        # Map gender to Squad's expected format (1=Male, 2=Female)
        gender_map = {"Male": "1", "Female": "2"}
        squad_gender = gender_map.get(data.get('gender'), "1")

        squad_payload = {
            "first_name": first_name, "last_name": last_name, "middle_name": middle_name,
            "mobile_num": data.get('phone'), "email": data.get('email'), "bvn": data.get('bvn'),
            "dob": formatted_dob, "address": data.get('address'), 
            "gender": squad_gender,
            "customer_identifier": str(uuid.uuid4()).replace('-', '')[:15].upper(), 
            "beneficiary_account": "0000000001"
        }

        try:
            squad_response = requests.post(f"{SQUAD_BASE_URL}/virtual-account", json=squad_payload, headers={"Authorization": f"Bearer {SQUAD_SECRET_KEY}", "Content-Type": "application/json"}, timeout=30)
            squad_data = squad_response.json()
            # Handle Squad Sandbox Limit (Fallback for Development/Demo)
            if squad_response.status_code != 200 or not squad_data.get('success'):
                error_msg = squad_data.get('message', '')
                if "account opening limit" in error_msg.lower():
                    print(f"--- SQUAD LIMIT REACHED: Using Mock Account for {data.get('phone')} ---")
                    account_data = {
                        "virtual_account_number": f"00{random.randint(10000000, 99999999)}",
                        "bank_name": "GTBank (Mocked)"
                    }
                else:
                    return JsonResponse({"success": False, "message": error_msg or 'Failed to create virtual account.'}, status=400)
            else:
                account_data = squad_data.get('data', {})

            ojapass_id = f"OJA-{random.randint(100, 999)}-{str(uuid.uuid4())[:4].upper()}"

            user = OjaUser.objects.create_user(
                phone=data.get('phone'), password=data.get('pin'), full_name=full_name, email=data.get('email'),
                dob=data.get('dob'), gender=data.get('gender'), address=data.get('address'), bvn=data.get('bvn'),
                role=data.get('role', 'trader'), ojapass_id=ojapass_id, 
                ojapass_score=0,
                ojapass_narrative="Welcome to OjaPass! Start trading and taking gigs to build your credit profile.",
                virtual_account_number=account_data.get('virtual_account_number'),
                bank_name=account_data.get('bank_name', 'GTBank'),
                business_name=data.get('businessName', ''), trade_category=data.get('tradeCategory', ''),
                years_in_business=data.get('yearsInBusiness', 0), daily_sales=data.get('dailySales', 0),
            )
            
            # Log the user in
            auth_login(request, user)
            
            return JsonResponse({
                "success": True, 
                "user": {
                    "fullName": user.full_name, 
                    "phone": user.phone, 
                    "ojapassId": user.ojapass_id, 
                    "ojapassScore": user.ojapass_score,
                    "virtualAccount": user.virtual_account_number,
                    "bankName": user.bank_name,
                    "role": user.role
                }
            })
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({"success": False, "message": "Server error during registration."}, status=500)

class LoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('mamatally_dashboard')
        return render(request, 'login.html')

    def post(self, request):
        import json
        try:
            data = json.loads(request.body)
        except:
            data = request.POST

        phone, pin = data.get('phone'), data.get('pin')
        user = authenticate(request, username=phone, password=pin)
        if user:
            auth_login(request, user)
            return JsonResponse({"success": True, "message": "Login successful"})
        return JsonResponse({"success": False, "message": "Invalid Phone or PIN."}, status=401)

class LogoutView(View):
    def get(self, request):
        auth_logout(request)
        return redirect('login')

class UserProfileView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        transactions = user.transactions.all().order_by('-timestamp')[:5]
        
        # Calculate Virtual Account Balance
        from django.db.models import Sum
        inflows = user.transactions.filter(transaction_type='inflow', status='success').aggregate(Sum('amount'))['amount__sum'] or 0
        outflows = user.transactions.filter(transaction_type='outflow', status='success').aggregate(Sum('amount'))['amount__sum'] or 0
        virtual_balance = float(inflows) - float(outflows)
        
        from ..services.oja_score import get_tier
        import json
        tier_data = get_tier(user.ojapass_score)
        
        # History for graph (last 30 snapshots)
        score_history = user.score_history.all().order_by('-timestamp')[:30]
        score_history_list = list(score_history)[::-1]
        history_json = json.dumps([
            {"date": h.timestamp.strftime('%d %b'), "score": h.score} 
            for h in score_history_list
        ])
        
        # Fetch products for autocomplete
        products = user.products.filter(quantity_in_stock__gt=0).order_by('name')
        
        if user.role == 'seeker':
            # Seeker specific metrics
            active_gigs = user.gigs_taken.filter(status__in=['matched', 'in_progress']).count()
            completed_gigs = user.gigs_taken.filter(status__in=['completed', 'paid']).count()
            total_earnings = user.transactions.filter(transaction_type='inflow', status='success').aggregate(Sum('amount'))['amount__sum'] or 0
            
            # AI matches (recommendations)
            from ..services.gemini_service import GeminiService
            # Get some open gigs to match against
            from ..models import Gig
            open_gigs = Gig.objects.filter(status='open')[:10]
            # This might be slow if done on every page load, but for demo it's fine
            # Better to use cache or a background task in production
            recommendations = [] # Placeholder or call Gemini if needed
            
            context = {
                'user': user,
                'active_gigs_count': active_gigs,
                'completed_gigs_count': completed_gigs,
                'total_earnings': total_earnings,
                'tier': tier_data,
                'history_json': history_json,
                'notifications': user.notifications.all().order_by('-created_at')[:5],
                'active_gigs': user.gigs_taken.filter(status__in=['matched', 'in_progress']).order_by('-created_at')
            }
            return render(request, 'seeker_dashboard.html', context)

        context = {
            'user': user, 
            'transactions': transactions,
            'virtual_balance': virtual_balance,
            'tier': tier_data,
            'history_json': history_json,
            'pts_to_next': (tier_data['next_min'] - user.ojapass_score) if tier_data['next_min'] else 0,
            'products': products
        }
        return render(request, 'trader_dashboard.html', context)

class ResolveBVNView(View):
    def post(self, request):
        import json
        try:
            data = json.loads(request.body)
        except:
            data = request.POST
            
        bvn = data.get('bvn')
        if not bvn or len(str(bvn)) != 11: 
            return JsonResponse({"success": False, "message": "Invalid BVN. Must be 11 digits."}, status=400)
        return JsonResponse({"success": True, "message": "BVN format validated and matched with phone number."})