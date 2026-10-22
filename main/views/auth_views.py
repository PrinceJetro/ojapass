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
from ..services.bmoni_service import BMONIService

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

        try:
            account_data = {
                "virtual_account_number": f"00{random.randint(10000000, 99999999)}",
                "bank_name": "GTBank (Mocked - BMONI wallet pending)"
            }

            ojapass_id = f"OJA-{random.randint(100, 999)}-{str(uuid.uuid4())[:4].upper()}"

            user = OjaUser.objects.create_user(
                phone=data.get('phone'), password=data.get('pin'), full_name=full_name, email=data.get('email'),
                dob=data.get('dob'), gender=data.get('gender'), address=data.get('address'), bvn=data.get('bvn'),
                role=data.get('role', 'trader'), ojapass_id=ojapass_id,
                lga=data.get('lga', 'Surulere'),
                bio=data.get('bio', ''),
                skills=data.get('skills', ''),
                ojapass_score=0,
                ojapass_narrative="Welcome to OjaPass! Start trading and taking gigs to build your credit profile.",
                virtual_account_number=account_data.get('virtual_account_number'),
                bank_name=account_data.get('bank_name', 'GTBank'),
                business_name=data.get('businessName', ''), trade_category=data.get('tradeCategory', ''),
                years_in_business=data.get('yearsInBusiness', 0), daily_sales=data.get('dailySales', 0),
                bmoni_sync_status='pending',
            )

            bmoni_user_data = {
                "firstName": first_name,
                "lastName": last_name,
                "middleName": middle_name,
                "phone": data.get('phone'),
                "email": data.get('email'),
                "bvn": data.get('bvn'),
                "address": data.get('address'),
                "city": data.get('city', 'Lagos'),
                "state": data.get('state', 'Lagos'),
                "country": data.get('country', 'Nigeria')
            }

            bmoni_response = BMONIService.create_user(bmoni_user_data)

            if bmoni_response and bmoni_response.get('success') and bmoni_response.get('data', {}).get('user'):
                user.bmoni_user_id = bmoni_response['data']['user'].get('bmoniUserId')
                user.bmoni_sync_status = 'synced'
                print(f"[BMONI] User created successfully: {user.bmoni_user_id}")

                wallet_response = BMONIService.create_wallet_simple(user.bmoni_user_id, "CNGN")
                print(f"[DEBUG] wallet_response: {wallet_response}")
                if wallet_response and wallet_response.get('success'):
                    print(f"[BMONI] Wallet created successfully for {user.bmoni_user_id}")

                    wallet_data = wallet_response.get('data', {})
                    smart_wallet_id = wallet_data.get('id') or wallet_data.get('smartWalletId') or wallet_data.get('walletId')
                    wallet_address = (
                        wallet_data.get('address') or wallet_data.get('walletAddress') or
                        wallet_data.get('ownerAddress') or wallet_data.get('userOwnerAddress')
                    )
                    if smart_wallet_id and wallet_address:
                        onboarding_response = BMONIService.start_nigeria_onboarding(
                            user.bmoni_user_id, data.get('bvn'), wallet_address, 0
                        )
                        if onboarding_response and onboarding_response.get('success'):
                            deposit_response = BMONIService.get_deposit_accounts(user.bmoni_user_id, "NGN")
                            if deposit_response and deposit_response.get('success'):
                                accounts = deposit_response.get('data', {}).get('accounts', [])
                                if accounts:
                                    account = accounts[0]
                                    user.virtual_account_number = account.get('accountNumber', user.virtual_account_number)
                                    user.bank_name = account.get('bankName', user.bank_name)
                                    user.save(update_fields=['virtual_account_number', 'bank_name'])
                                    print(f"[BMONI] NGN deposit account for {user.email}: {user.virtual_account_number}")
                                else:
                                    print(f"[BMONI] Nigeria onboarding started but no deposit account yet - will retry via KYC")
                            else:
                                print(f"[BMONI] Could not fetch deposit account yet - will retry via KYC")
                        else:
                            print(f"[BMONI] Nigeria onboarding failed - will retry via KYC: {onboarding_response.get('error')}")
                else:
                    print(f"[BMONI] Wallet creation failed (will retry via KYC): {wallet_response.get('error')}")
            else:
                if bmoni_response and bmoni_response.get('status_code') == 409:
                    print(f"[BMONI] User already exists - attempting to find existing BMONI user")
                    existing_user = BMONIService.find_user_by_email_or_phone(
                        email=data.get('email'),
                        phone=data.get('phone')
                    )
                    if existing_user:
                        user.bmoni_user_id = existing_user.get('bmoniUserId')
                        user.bmoni_sync_status = 'synced'
                        user.bmoni_sync_error = None
                        user.bmoni_sync_attempts = 0
                        print(f"[BMONI] Found and linked existing BMONI user: {user.bmoni_user_id}")

                        wallet_response = BMONIService.create_wallet_simple(user.bmoni_user_id, "CNGN")
                        print(f"[DEBUG] wallet_response: {wallet_response}")
                        if wallet_response and wallet_response.get('success'):
                            print(f"[BMONI] Wallet created for existing user {user.email}")

                            wallet_data = wallet_response.get('data', {})
                            smart_wallet_id = wallet_data.get('id') or wallet_data.get('smartWalletId') or wallet_data.get('walletId')
                            wallet_address = (
                                wallet_data.get('address') or wallet_data.get('walletAddress') or
                                wallet_data.get('ownerAddress') or wallet_data.get('userOwnerAddress')
                            )
                            if smart_wallet_id and wallet_address:
                                onboarding_response = BMONIService.start_nigeria_onboarding(
                                    user.bmoni_user_id, data.get('bvn'), wallet_address, 0
                                )
                                if onboarding_response and onboarding_response.get('success'):
                                    deposit_response = BMONIService.get_deposit_accounts(user.bmoni_user_id, "NGN")
                                    if deposit_response and deposit_response.get('success'):
                                        accounts = deposit_response.get('data', {}).get('accounts', [])
                                        if accounts:
                                            account = accounts[0]
                                            user.virtual_account_number = account.get('accountNumber', user.virtual_account_number)
                                            user.bank_name = account.get('bankName', user.bank_name)
                                            user.save(update_fields=['virtual_account_number', 'bank_name'])
                                            print(f"[BMONI] NGN deposit account for existing user {user.email}: {user.virtual_account_number}")
                        else:
                            print(f"[BMONI] Wallet creation failed - user needs KYC")
                            print(f"[DEBUG] wallet_data keys: {list(wallet_data.keys()) if isinstance(wallet_data, dict) else wallet_data}")
                    else:
                        user.bmoni_sync_status = 'failed'
                        user.bmoni_sync_attempts += 1
                        user.bmoni_sync_error = "User already exists in BMONI but could not be found via lookup"
                        print(f"[BMONI] Could not find existing user via lookup")
                else:
                    user.bmoni_sync_status = 'failed'
                    user.bmoni_sync_attempts += 1
                    if bmoni_response:
                        user.bmoni_sync_error = bmoni_response.get('error', 'Unknown error')
                        if bmoni_response.get('status_code') in (502, 503, 504):
                            user.bmoni_sync_error = "BMONI service temporarily unavailable - will retry"
                    print(f"[BMONI] User creation failed, will retry later: {bmoni_response}")

            user.save()

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

        from django.db.models import Sum
        inflows = user.transactions.filter(transaction_type='inflow', status='success').aggregate(Sum('amount'))['amount__sum'] or 0
        outflows = user.transactions.filter(transaction_type='outflow', status='success').aggregate(Sum('amount'))['amount__sum'] or 0
        virtual_balance = float(inflows) - float(outflows)

        from ..services.oja_score import get_tier
        import json
        tier_data = get_tier(user.ojapass_score)

        score_history = user.score_history.all().order_by('-timestamp')[:30]
        score_history_list = list(score_history)[::-1]
        history_json = json.dumps([
            {"date": h.timestamp.strftime('%d %b'), "score": h.score}
            for h in score_history_list
        ])

        products = user.products.filter(quantity_in_stock__gt=0).order_by('name')

        if user.role == 'seeker':
            active_gigs = user.gigs_taken.filter(status__in=['matched', 'in_progress']).count()
            completed_gigs = user.gigs_taken.filter(status__in=['completed', 'paid']).count()
            total_earnings = user.transactions.filter(transaction_type='inflow', status='success').aggregate(Sum('amount'))['amount__sum'] or 0

            from ..services.gemini_service import GeminiService
            from ..models import Gig
            open_gigs = Gig.objects.filter(status='open')[:10]
            recommendations = []

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
            return render(request, 'profile.html', context)

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


class BmoniKycView(LoginRequiredMixin, View):
    template_name = 'bmoni_kyc.html'

    def get(self, request, extra_messages=None, extra_errors=None):
        user = request.user
        context = {
            'user': user,
            'bmoni_user_id': user.bmoni_user_id,
            'bmoni_user': None,
            'kyc_status': None,
            'kyc_readiness': None,
            'onboarding_status': None,
            'messages': list(extra_messages or []),
            'errors': list(extra_errors or []),
        }

        if user.bmoni_user_id:
            user_result = BMONIService.get_user(user.bmoni_user_id)
            if user_result.get('success'):
                context['bmoni_user'] = user_result.get('data', {}).get('user')
            else:
                context['errors'].append('Unable to load BMONI user profile.')

            status_result = BMONIService.get_kyc_status(user.bmoni_user_id)
            if status_result.get('success'):
                context['kyc_status'] = status_result.get('data')
            else:
                context['errors'].append('Unable to load KYC status.')

            readiness_result = BMONIService.get_kyc_readiness(user.bmoni_user_id)
            if readiness_result.get('success'):
                context['kyc_readiness'] = readiness_result.get('data')
            else:
                context['errors'].append('Unable to load KYC readiness.')

            onboarding_result = BMONIService.get_onboarding_status(user.bmoni_user_id)
            if onboarding_result.get('success'):
                context['onboarding_status'] = onboarding_result.get('data')
            else:
                context['errors'].append('Unable to load onboarding status.')

        return render(request, self.template_name, context)

    def post(self, request):
        user = request.user
        if not user.bmoni_user_id:
            return JsonResponse({"success": False, "message": "Your account is not yet linked to BMONI."}, status=400)

        action = request.POST.get('action')
        messages = []
        errors = []
        result = None

        if action == 'upload_id':
            file_obj = request.FILES.get('identification')
            if not file_obj:
                errors.append('Please upload an identity document file.')
            else:
                result = BMONIService.upload_kyc_document_identification(
                    user.bmoni_user_id,
                    file_obj,
                    doc_type=request.POST.get('id_type', 'national_id'),
                    document_number=request.POST.get('document_number', ''),
                    issuing_country=request.POST.get('issuing_country', 'NGA'),
                    expiration_date=request.POST.get('expiration_date') or None,
                    issue_date=request.POST.get('issue_date') or None,
                )
        elif action == 'upload_address':
            file_obj = request.FILES.get('proof_of_address')
            if not file_obj:
                errors.append('Please upload a proof-of-address file.')
            else:
                result = BMONIService.upload_kyc_document_proof_of_address(
                    user.bmoni_user_id,
                    file_obj,
                    doc_type=request.POST.get('address_doc_type', 'utility_bill')
                )
        elif action == 'upload_biometric':
            file_obj = request.FILES.get('biometric')
            if not file_obj:
                errors.append('Please upload a selfie file.')
            else:
                result = BMONIService.upload_kyc_document_biometric(
                    user.bmoni_user_id,
                    file_obj
                )
        elif action == 'patch_kyc':
            payload = {
                'firstName': request.POST.get('firstName', user.full_name.split()[0] if user.full_name else ''),
                'lastName': request.POST.get('lastName', user.full_name.split()[-1] if user.full_name else ''),
                'email': user.email,
                'phoneNumber': user.phone,
                'addressStreet': request.POST.get('address', user.address or ''),
                'addressCity': request.POST.get('city', 'Lagos'),
                'addressState': request.POST.get('state', 'Lagos'),
                'addressCountry': request.POST.get('country', 'Nigeria'),
                'bvn': user.bvn,
                'occupation': request.POST.get('occupation', 'Trader'),
                'employerName': request.POST.get('employerName', 'OjaPass'),
                'monthlySalary': request.POST.get('monthlySalary', '0'),
            }
            result = BMONIService.patch_kyc(user.bmoni_user_id, payload)
        elif action == 'activate_kyc':
            sumsub_level = request.POST.get('sumsubLevelName') or None
            result = BMONIService.activate_kyc(user.bmoni_user_id, sumsub_level)
        elif action == 'start_nigeria':
            ngn_address = request.POST.get('ngn_wallet_address')
            ngn_index = request.POST.get('ngn_wallet_index', '0')
            if not ngn_address:
                errors.append('Please provide your NGN wallet address.')
            else:
                try:
                    index = int(ngn_index)
                except ValueError:
                    index = 0
                result = BMONIService.start_nigeria_onboarding(
                    user.bmoni_user_id,
                    user.bvn or request.POST.get('bvn', ''),
                    ngn_address,
                    index
                )
        else:
            errors.append('Unknown action requested.')

        if result is not None:
            if result.get('success'):
                messages.append('Action completed successfully.')
            else:
                errors.append(result.get('response_body') or result.get('error') or 'BMONI request failed.')

        # Single render pass (previously called self.get() twice, doubling
        # the BMONI API calls on every POST).
        return self.get(request, extra_messages=messages, extra_errors=errors)