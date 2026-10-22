from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Sum, F
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import uuid
import json
from ..models import Product, Sale, Order, StockMovement, OjaTransaction
from ..services.oja_score import recalculate_ojascore
from ..services.bmoni_service import BMONIService
from ..services.analytics import get_sales_trends, generate_restock_alerts
from ..services.ai_analytics import AIAnalytics

class MamatallyDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user

        # Legacy BMONI sync — best-effort only, never blocks the dashboard.
        # Squad is the primary provider; local/mock ledger is the fallback.
        if not user.bmoni_user_id or user.bmoni_sync_status in ['pending', 'failed']:
            print(f"[BMONI CHECK] Checking sync for {user.email} - status: {user.bmoni_sync_status}")

            # Prepare user data for BMONI
            first_name = user.full_name.split()[0] if user.full_name else ''
            last_name = user.full_name.split()[-1] if user.full_name and len(user.full_name.split()) > 1 else ''

            bmoni_user_data = {
                "firstName": first_name,
                "lastName": last_name,
                "phone": user.phone,
                "email": user.email,
                "bvn": user.bvn,
                "address": user.address,
            }

            try:
                bmoni_response = BMONIService.create_user(bmoni_user_data)
            except Exception as e:
                print(f"[BMONI CHECK] Sync skipped (non-blocking): {e}")
                bmoni_response = None

            if bmoni_response and bmoni_response.get('success') and bmoni_response.get('data', {}).get('user'):
                user.bmoni_user_id = bmoni_response['data']['user'].get('bmoniUserId')
                user.bmoni_sync_status = 'synced'
                user.bmoni_sync_error = None
                user.bmoni_sync_attempts = 0
                user.save()
                print(f"[BMONI CHECK] Sync successful for {user.email}")

                # Attempt wallet creation after successful sync
                wallet_response = BMONIService.create_wallet_simple(user.bmoni_user_id, "CNGN")
                if wallet_response and wallet_response.get('success'):
                    print(f"[BMONI CHECK] Wallet created for {user.email}")
                else:
                    print(f"[BMONI CHECK] Wallet creation failed - user needs KYC")
            else:
                user.bmoni_sync_attempts += 1
                if bmoni_response:
                    user.bmoni_sync_error = bmoni_response.get('error', 'Unknown error')
                    if bmoni_response.get('status_code') == 409:
                        user.bmoni_sync_error = "User already exists in BMONI with this email or phone"
                    elif bmoni_response.get('status_code') in (502, 503, 504):
                        user.bmoni_sync_error = "BMONI service temporarily unavailable - will retry"
                user.bmoni_sync_status = 'failed'
                user.save()
                print(f"[BMONI CHECK] Sync failed for {user.email}: {user.bmoni_sync_error}")

        # Check if user has a wallet - redirect to KYC if not
        if user.bmoni_user_id:
            try:
                wallet_result = BMONIService.get_wallets(user.bmoni_user_id)

                # Handle different response structures from BMONI API
                wallets = None
                if wallet_result.get('success'):
                    wallet_data = wallet_result.get('data')
                    if isinstance(wallet_data, dict):
                        wallets = wallet_data.get('wallets')
                    elif isinstance(wallet_data, list):
                        wallets = wallet_data
                else:
                    wallets = None

                # If we have wallet data, attempt to ensure a Nigeria VBA is linked
                if wallets:
                    smart_wallet = wallets[0]
                    smart_wallet_id = smart_wallet.get('id') or smart_wallet.get('smartWalletId') or smart_wallet.get('smart_wallet_id')
                    if smart_wallet_id and not user.virtual_account_number:
                        try:
                            vba_resp = BMONIService.link_nigeria_vba(user.bmoni_user_id, smart_wallet_id)
                            if vba_resp and vba_resp.get('success'):
                                vba_data = vba_resp.get('data') or {}
                                user.virtual_account_number = vba_data.get('accountNumber') or vba_data.get('virtualAccountNumber') or user.virtual_account_number
                                user.bank_name = vba_data.get('bankName') or user.bank_name
                                user.save(update_fields=['virtual_account_number', 'bank_name'])
                                print(f"[BMONI] VBA linked for {user.email}: {user.virtual_account_number}")
                            else:
                                print(f"[BMONI] VBA link attempt failed: {vba_resp.get('error') if vba_resp else 'no response'}")
                        except Exception as e:
                            print(f"[BMONI] VBA link error: {e}")

                if not wallet_result.get('success') or not wallets:
                    # Squad era: BMONI wallet is optional. Continue to dashboard
                    # with the local/mock virtual account instead of blocking.
                    print(f"[BMONI CHECK] No wallet found for {user.email} - continuing with local ledger (Squad primary)")
            except Exception as e:
                print(f"[BMONI CHECK] Wallet check failed (non-blocking): {e}")
        else:
            print(f"[BMONI CHECK] No bmoni_user_id for {user.email} - continuing with local ledger (Squad primary)")
        today = timezone.now().date()
        inventory = Product.objects.filter(user=user)
        sales = Sale.objects.filter(user=user).order_by('-created_at')[:10]
        today_revenue = Sale.objects.filter(user=user, created_at__date=today).aggregate(total=Sum('amount'))['total'] or 0
        total_inv_value = sum((p.quantity_in_stock * p.cost_price) for p in inventory)
        low_stock = inventory.filter(quantity_in_stock__lte=F('low_stock_threshold'), quantity_in_stock__gt=0)
        
        # Graph Data (Last 7 Days)
        from django.db.models.functions import TruncDate
        seven_days_ago = today - timedelta(days=6)
        daily_stats = Sale.objects.filter(
            user=user, 
            created_at__date__gte=seven_days_ago
        ).annotate(day_date=TruncDate('created_at')).values('day_date').annotate(total=Sum('amount')).order_by('day_date')

        daily_map = {str(s['day_date']): float(s['total']) for s in daily_stats}
        daily_revenue_list = []
        max_rev = 1000
        for i in range(6, -1, -1):
            date = today - timedelta(days=i)
            rev = daily_map.get(str(date), 0.0)
            daily_revenue_list.append({"day": date.strftime('%a'), "amount": rev})
            if rev > max_rev: max_rev = rev
        
        # Add height percentage for graph
        for d in daily_revenue_list:
            d['height'] = (d['amount'] / max_rev) * 100 if max_rev > 0 else 0

        # Monthly turnover estimate
        last_30_days = today - timedelta(days=30)
        monthly_turnover = float(Sale.objects.filter(user=user, created_at__date__gte=last_30_days).aggregate(total=Sum('amount'))['total'] or 0)

        context = {
            "today_revenue": float(today_revenue),
            "total_inventory_value": float(total_inv_value),
            "monthly_turnover": monthly_turnover,
            "low_stock_alerts": low_stock,
            "inventory": inventory,
            "recent_sales": sales,
            "daily_revenue_list": daily_revenue_list,
            # Sales trends and restock suggestions (heuristic)
            "sales_trends": get_sales_trends(user, days=30),
            "restock_alerts": generate_restock_alerts(user, lookback_days=90, horizon_days=30, threshold_days=7),
            # AI-driven report (if GEMINI key configured)
            "ai_report": AIAnalytics.generate_dashboard_report(user, days=30),
            "virtual_account_number": user.virtual_account_number,
            "bank_name": user.bank_name,
            "wallet_balance": float(user.wallet_balance or 0),
        }
        return render(request, 'mamatally.html', context)

class ProductListView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        products = Product.objects.filter(user=user).order_by('-created_at')
        
        # Calculate Stats
        total_potential_profit = sum(p.profit * p.quantity_in_stock for p in products)
        
        # Fastest Moving Item (Last 30 Days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        top_sale = Sale.objects.filter(user=user, created_at__gte=thirty_days_ago).values('product__name').annotate(total_qty=Sum('quantity')).order_by('-total_qty').first()
        fastest_moving = {
            "name": top_sale['product__name'] if top_sale else "No Sales Yet",
            "count": top_sale['total_qty'] if top_sale else 0
        }
        
        # Inventory Health
        low_stock_count = products.filter(quantity_in_stock__lte=F('low_stock_threshold')).count()
        total_count = products.count()
        health_percentage = ((total_count - low_stock_count) / total_count * 100) if total_count > 0 else 100
        
        # Sales Trend (Last 7 Days)
        from django.db.models.functions import TruncDate
        today = timezone.now().date()
        seven_days_ago = today - timedelta(days=6)
        sales_trend = Sale.objects.filter(
            user=user, 
            created_at__date__gte=seven_days_ago
        ).annotate(day_date=TruncDate('created_at')).values('day_date').annotate(total=Sum('amount')).order_by('day_date')
        
        trend_map = {str(s['day_date']): float(s['total']) for s in sales_trend}
        trend_labels = []
        trend_values = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            trend_labels.append(d.strftime('%b %d'))
            trend_values.append(trend_map.get(str(d), 0.0))

        context = {
            'products': products,
            'potential_profit': float(total_potential_profit),
            'fastest_moving': fastest_moving,
            'low_stock_count': low_stock_count,
            'health_percentage': health_percentage,
            'total_count': total_count,
            'trend_labels': trend_labels,
            'trend_values': trend_values
        }
        return render(request, 'productsinventry.html', context)
    
    def post(self, request):
        try:
            data = json.loads(request.body)
        except:
            data = request.POST

        name = (data.get('name') or '').strip()
        if not name:
            return JsonResponse({"success": False, "message": "Product name is required."}, status=400)
        try:
            quantity = int(data.get('quantityInStock', 0))
            cost_price = float(data.get('costPrice', 0))
            selling_price = float(data.get('sellingPrice', 0))
        except (TypeError, ValueError):
            return JsonResponse({"success": False, "message": "Quantity and prices must be numbers."}, status=400)
        if quantity < 0 or cost_price < 0 or selling_price <= 0:
            return JsonResponse({"success": False, "message": "Invalid quantity or price values."}, status=400)

        p = Product.objects.create(
            user=request.user,
            name=name,
            quantity_in_stock=quantity,
            cost_price=cost_price,
            selling_price=selling_price,
            category=data.get('category')
        )
        return JsonResponse({"success": True, "product_id": p.id})

class ProductDetailView(LoginRequiredMixin, View):
    def post(self, request, pk):
        p = get_object_or_404(Product, pk=pk, user=request.user)
        try:
            data = json.loads(request.body)
        except:
            data = request.POST

        try:
            p.name = data.get('name', p.name) or p.name
            p.quantity_in_stock = int(data.get('quantityInStock', p.quantity_in_stock))
            p.cost_price = float(data.get('costPrice', p.cost_price))
            p.selling_price = float(data.get('sellingPrice', p.selling_price))
        except (TypeError, ValueError):
            return JsonResponse({"success": False, "message": "Quantity and prices must be numbers."}, status=400)
        if p.quantity_in_stock < 0 or p.selling_price <= 0:
            return JsonResponse({"success": False, "message": "Invalid quantity or price values."}, status=400)
        p.category = data.get('category', p.category)
        p.save()
        return JsonResponse({"success": True})
        
    def delete(self, request, pk):
        p = get_object_or_404(Product, pk=pk, user=request.user)
        p.delete()
        return JsonResponse({"success": True})

class SaleListView(LoginRequiredMixin, View):
    def get(self, request):
        sales = Sale.objects.filter(user=request.user).order_by('-created_at')[:50]
        return render(request, 'transactionhistory.html', {'sales': sales})
        
    def post(self, request):
        try:
            data = json.loads(request.body)
        except:
            data = request.POST

        try:
            qty = int(data.get('quantity', 1))
        except (TypeError, ValueError):
            return JsonResponse({"success": False, "message": "Quantity must be a number."}, status=400)
        if qty <= 0:
            return JsonResponse({"success": False, "message": "Quantity must be at least 1."}, status=400)

        try:
            # Plain lookup here (select_for_update requires an active
            # transaction) — the locked re-fetch happens inside atomic below.
            product = Product.objects.get(id=data.get('productId'), user=request.user)
        except Product.DoesNotExist:
            return JsonResponse({"success": False, "message": "Product not found."}, status=404)
        except (TypeError, ValueError):
            return JsonResponse({"success": False, "message": "Invalid product."}, status=400)

        try:
            amount = Decimal(str(data.get('amount', product.selling_price)))
        except (TypeError, ValueError):
            return JsonResponse({"success": False, "message": "Invalid amount."}, status=400)

        with transaction.atomic():
            product = Product.objects.select_for_update().get(id=product.id, user=request.user)
            
            if product.quantity_in_stock < qty:
                return JsonResponse({"success": False, "message": f"Insufficient stock. Current: {product.quantity_in_stock}"}, status=400)
                
            product.quantity_in_stock -= qty
            product.save()
            sale = Sale.objects.create(
                user=request.user, 
                product=product, 
                quantity=qty, 
                amount=amount, 
                payment_method='cash'
            )
            transaction_ref = f"SALE-{uuid.uuid4().hex[:12].upper()}"
            tx, created = OjaTransaction.objects.get_or_create(
                transaction_reference=transaction_ref,
                defaults={
                    'user': request.user,
                    'amount': amount,
                    'status': 'success',
                    'transaction_type': 'inflow',
                }
            )
            if created:
                request.user.wallet_balance = (request.user.wallet_balance or Decimal('0')) + amount
                request.user.save(update_fields=['wallet_balance'])
        recalculate_ojascore(request.user.id)
        return JsonResponse({"success": True})

class OrderListView(LoginRequiredMixin, View):
    def get(self, request):
        orders = Order.objects.filter(user=request.user).order_by('-created_at')
        return render(request, 'mamatally.html', {'orders': orders}) # Or a separate orders template

class OrderDetailView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            data = json.loads(request.body)
        except:
            data = request.POST
            
        order = get_object_or_404(Order, pk=pk, user=request.user)
        new_status = data.get('status')
        if new_status not in ('pending', 'confirmed', 'fulfilled', 'paid'):
            return JsonResponse({"success": False, "message": "Invalid status."}, status=400)
        already_paid = (order.status == 'paid')
        order.status = new_status
        order.save()
        if order.status == 'paid' and not already_paid and order.product:
            order.product.quantity_in_stock = max(0, order.product.quantity_in_stock - order.quantity)
            order.product.save()
            amount = order.total_amount or Decimal(str(order.quantity * (order.product.selling_price if order.product else 0)))
            transaction_ref = f"ORDER-{uuid.uuid4().hex[:12].upper()}"
            tx, created = OjaTransaction.objects.get_or_create(
                transaction_reference=transaction_ref,
                defaults={
                    'user': request.user,
                    'amount': amount,
                    'status': 'success',
                    'transaction_type': 'inflow',
                }
            )
            if created:
                request.user.wallet_balance = (request.user.wallet_balance or Decimal('0')) + amount
                request.user.save(update_fields=['wallet_balance'])
            recalculate_ojascore(request.user.id)
        return JsonResponse({"success": True})

class LogRestockView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except:
            data = request.POST
            
        p = get_object_or_404(Product, id=data.get('productId'), user=request.user)
        try:
            qty = int(data.get('quantity'))
        except (TypeError, ValueError):
            return JsonResponse({"success": False, "message": "Quantity must be a number."}, status=400)
        if qty <= 0:
            return JsonResponse({"success": False, "message": "Quantity must be positive."}, status=400)
        p.quantity_in_stock += qty
        p.save()
        StockMovement.objects.create(product=p, user=request.user, movement_type='restock', quantity=qty)
        recalculate_ojascore(request.user.id)
        return JsonResponse({"success": True})

class StockMovementListView(LoginRequiredMixin, View):
    def get(self, request):
        movements = StockMovement.objects.filter(user=request.user).order_by('-timestamp')[:50]
        return JsonResponse({"success": True, "movements": list(movements.values())})

class PayrollBatchView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except:
            data = request.POST
            
        workers = data.get('workers', [])
        if not isinstance(workers, list):
            return JsonResponse({"success": False, "message": "Workers must be a list."}, status=400)
        for w in workers:
            # TODO: Implement Squad transfer for payroll (needs merchant profiling)
            # For now, log the transfer request
            if not isinstance(w, dict) or 'amount' not in w or 'account' not in w:
                return JsonResponse({"success": False, "message": "Each worker needs amount and account."}, status=400)
            print(f"[SQUAD] Payroll transfer: ₦{w['amount']} to {w['account']}")
        recalculate_ojascore(request.user.id)
        return JsonResponse({"success": True})