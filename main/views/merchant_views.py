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
from ..services.squad_service import SquadService

SQUAD_SECRET_KEY = settings.SQUAD_SECRET_KEY
SQUAD_BASE_URL = "https://sandbox-api-d.squadco.com"

class MamatallyDashboardView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
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
            "daily_revenue_list": daily_revenue_list
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
            
        p = Product.objects.create(
            user=request.user, 
            name=data.get('name'), 
            quantity_in_stock=int(data.get('quantityInStock', 0)), 
            cost_price=float(data.get('costPrice', 0)), 
            selling_price=float(data.get('sellingPrice', 0)), 
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
            
        p.name = data.get('name', p.name)
        p.quantity_in_stock = int(data.get('quantityInStock', p.quantity_in_stock))
        p.cost_price = float(data.get('costPrice', p.cost_price))
        p.selling_price = float(data.get('sellingPrice', p.selling_price))
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
            
        with transaction.atomic():
            product = Product.objects.select_for_update().get(id=data.get('productId'), user=request.user)
            qty = int(data.get('quantity', 1))
            
            if product.quantity_in_stock < qty:
                return JsonResponse({"success": False, "message": f"Insufficient stock. Current: {product.quantity_in_stock}"}, status=400)
                
            product.quantity_in_stock -= qty
            product.save()
            Sale.objects.create(
                user=request.user, 
                product=product, 
                quantity=qty, 
                amount=float(data.get('amount')), 
                payment_method='cash'
            )
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
        order.status = data.get('status')
        order.save()
        if order.status == 'paid' and order.product:
            order.product.quantity_in_stock -= order.quantity
            order.product.save()
            recalculate_ojascore(request.user.id)
        return JsonResponse({"success": True})

class LogRestockView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except:
            data = request.POST
            
        p = get_object_or_404(Product, id=data.get('productId'), user=request.user)
        qty = int(data.get('quantity'))
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
        for w in workers:
            SquadService.process_transfer(w['amount'], w['account'], "Payroll", SQUAD_SECRET_KEY, SQUAD_BASE_URL)
        recalculate_ojascore(request.user.id)
        return JsonResponse({"success": True})