from datetime import timedelta, date
from collections import defaultdict
from django.utils import timezone
from django.db.models import Sum


def get_sales_trends(user, days=30):
    """
    Return daily sales totals for the last `days` and weekly/monthly aggregates.
    Output: {
      'daily': [{'date': '2026-07-01', 'amount': 123.45}, ...],
      'weekly': [{'week_start': '2026-06-28', 'amount': 1234.0}, ...],
      'monthly': [{'month': '2026-07', 'amount': 4321.0}, ...]
    }
    """
    end = timezone.now().date()
    start = end - timedelta(days=days - 1)

    from ..models import Sale
    qs = Sale.objects.filter(user=user, created_at__date__gte=start, created_at__date__lte=end)

    # Daily totals
    daily_map = defaultdict(float)
    for s in qs.values('created_at').annotate(total=Sum('amount')):
        d = s['created_at'].date() if hasattr(s['created_at'], 'date') else s['created_at']
        daily_map[str(d)] += float(s['total'] or 0)

    daily = []
    for i in range(days):
        d = start + timedelta(days=i)
        daily.append({'date': str(d), 'amount': round(daily_map.get(str(d), 0.0), 2)})

    # Weekly aggregates (ISO weeks starting Monday)
    weekly_map = defaultdict(float)
    for entry in daily:
        d = date.fromisoformat(entry['date'])
        week_start = d - timedelta(days=d.weekday())
        weekly_map[str(week_start)] += entry['amount']
    weekly = [{'week_start': k, 'amount': round(v, 2)} for k, v in sorted(weekly_map.items())]

    # Monthly aggregates
    monthly_map = defaultdict(float)
    for entry in daily:
        d = date.fromisoformat(entry['date'])
        month = f"{d.year}-{d.month:02d}"
        monthly_map[month] += entry['amount']
    monthly = [{'month': k, 'amount': round(v, 2)} for k, v in sorted(monthly_map.items())]

    return {'daily': daily, 'weekly': weekly, 'monthly': monthly}


def forecast_inventory_demand(product, lookback_days=90, horizon_days=30):
    """
    Simple demand forecast: compute average daily sales over the lookback window
    and project future consumption for `horizon_days`.
    Returns dict with avg_daily, projected_consumption, days_until_stockout (float or None).
    """
    from ..models import Sale
    end = timezone.now().date()
    start = end - timedelta(days=lookback_days - 1)

    qs = Sale.objects.filter(product=product, created_at__date__gte=start, created_at__date__lte=end)
    total = qs.aggregate(total=Sum('amount'))['total'] or 0

    # We want units sold, not currency; use quantity if available
    total_qty = qs.aggregate(q=Sum('quantity'))['q'] or 0
    if total_qty == 0:
        # If no recorded quantity, fallback to using amount / price if possible
        try:
            unit_estimate = float(total) / float(product.selling_price) if product.selling_price else 0
        except Exception:
            unit_estimate = 0
        total_qty = unit_estimate

    avg_daily = float(total_qty) / float(lookback_days) if lookback_days > 0 else 0.0
    projected = avg_daily * horizon_days

    qty_on_hand = float(product.quantity_in_stock or 0)
    days_until_stockout = None
    if avg_daily > 0:
        days_until_stockout = qty_on_hand / avg_daily

    return {
        'product_id': product.id,
        'product_name': product.name,
        'avg_daily': round(avg_daily, 3),
        'projected_consumption': round(projected, 2),
        'qty_on_hand': qty_on_hand,
        'days_until_stockout': round(days_until_stockout, 1) if days_until_stockout is not None else None,
    }


def generate_restock_alerts(user, lookback_days=90, horizon_days=30, threshold_days=7):
    """
    For each product belonging to `user`, forecast demand and generate alerts
    if stock is expected to run out within `threshold_days` or within the horizon.
    Returns list of alerts with recommended reorder quantities.
    """
    from ..models import Product
    products = Product.objects.filter(user=user)
    alerts = []
    for p in products:
        f = forecast_inventory_demand(p, lookback_days=lookback_days, horizon_days=horizon_days)
        days_left = f['days_until_stockout']
        recommended_order = 0
        if f['avg_daily'] > 0:
            required = f['avg_daily'] * horizon_days
            if required > f['qty_on_hand']:
                recommended_order = max(0, int(round(required - f['qty_on_hand'] + 0.5)))

        if (days_left is not None and days_left <= threshold_days) or (recommended_order > 0):
            alerts.append({
                'product_id': p.id,
                'product_name': p.name,
                'qty_on_hand': f['qty_on_hand'],
                'days_until_stockout': f['days_until_stockout'],
                'recommended_order': recommended_order,
            })

    return alerts
