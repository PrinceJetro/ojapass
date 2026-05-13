from decimal import Decimal
from datetime import timedelta, date
from django.utils import timezone
from django.db.models import Sum
from django.db.models.functions import TruncMonth

# ---------------------------------------------------------------------------
# TIER PRODUCT DEFINITIONS
# ---------------------------------------------------------------------------

TIER_PRODUCTS = {
    # score_min: { product_type, min_amount, max_amount, interest_rate, tenure_months }
    90: {
        'product_type': 'credit_line',
        'min_amount': Decimal('200000'),
        'max_amount': Decimal('500000'),
        'interest_rate': Decimal('2.5'),   # % per month
        'tenure_months': 6,
    },
    75: {
        'product_type': 'working_capital',
        'min_amount': Decimal('50000'),
        'max_amount': Decimal('200000'),
        'interest_rate': Decimal('3.5'),
        'tenure_months': 4,
    },
    56: {
        'product_type': 'nano_loan',
        'min_amount': Decimal('5000'),
        'max_amount': Decimal('50000'),
        'interest_rate': Decimal('5.0'),
        'tenure_months': 3,
    },
    31: {
        'product_type': 'savings_goal',
        'min_amount': Decimal('0'),
        'max_amount': Decimal('0'),
        'interest_rate': Decimal('0'),
        'tenure_months': 0,
    },
}


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def get_eligible_product(score: int) -> dict | None:
    """Return the best loan product the user qualifies for based on OjaScore."""
    for min_score in sorted(TIER_PRODUCTS.keys(), reverse=True):
        if score >= min_score:
            return TIER_PRODUCTS[min_score]
    return None


def calculate_avg_monthly_turnover(user) -> Decimal:
    """
    Average monthly sales revenue over the last 3 months.
    Uses Mamatally (Sale model) data — actual recorded business transactions.
    Returns Decimal('0') if no sales history exists.
    """
    from ..models import Sale

    three_months_ago = timezone.now() - timedelta(days=90)
    monthly = (
        Sale.objects
        .filter(user=user, created_at__gte=three_months_ago)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=Sum('amount'))
    )

    if not monthly.exists():
        return Decimal('0')

    total = sum(Decimal(str(m['total'])) for m in monthly)
    return total / Decimal(str(monthly.count()))


# ---------------------------------------------------------------------------
# LOAN OFFER CALCULATION
# ---------------------------------------------------------------------------

def calculate_loan_offer(user) -> dict | None:
    """
    Core loan sizing:
      Offer = 1.5× average monthly turnover
      Clamped within tier product min/max limits.

    Returns an offer dict or None if not eligible.
    """
    score = user.ojapass_score
    product = get_eligible_product(score)

    if not product:
        return None

    # Savings-goal tier has no loan amount
    if product['product_type'] == 'savings_goal':
        return {
            'product_type': 'savings_goal',
            'offer_amount': Decimal('0'),
            'interest_rate': Decimal('0'),
            'tenure_months': 0,
            'monthly_repayment': Decimal('0'),
            'avg_monthly_turnover': calculate_avg_monthly_turnover(user),
        }

    avg_turnover = calculate_avg_monthly_turnover(user)

    if avg_turnover <= Decimal('0'):
        # No sales history — start at minimum of tier range
        offer_amount = product['min_amount']
    else:
        raw_offer = avg_turnover * Decimal('1.5')
        offer_amount = max(
            product['min_amount'],
            min(raw_offer, product['max_amount'])
        )

    tenure = product['tenure_months']
    rate = product['interest_rate'] / Decimal('100')   # monthly rate as decimal

    # Standard amortisation: M = P × r(1+r)^n / ((1+r)^n − 1)
    if rate > Decimal('0') and tenure > 0:
        factor = (1 + rate) ** tenure
        monthly_repayment = offer_amount * (rate * factor) / (factor - 1)
    else:
        monthly_repayment = Decimal('0')

    return {
        'product_type': product['product_type'],
        'offer_amount': offer_amount.quantize(Decimal('0.01')),
        'interest_rate': product['interest_rate'],
        'tenure_months': tenure,
        'monthly_repayment': monthly_repayment.quantize(Decimal('0.01')),
        'avg_monthly_turnover': avg_turnover.quantize(Decimal('0.01')),
    }


# ---------------------------------------------------------------------------
# REPAYMENT SCHEDULE
# ---------------------------------------------------------------------------

def generate_repayment_schedule(loan) -> list:
    """Generate a per-installment repayment schedule for a loan."""
    schedule = []
    start_date = loan.disbursed_at.date() if loan.disbursed_at else date.today()

    for i in range(1, loan.tenure_months + 1):
        due = start_date + timedelta(days=30 * i)
        schedule.append({
            'installment': i,
            'due_date': due,
            'amount_due': loan.monthly_repayment,
        })

    return schedule


# ---------------------------------------------------------------------------
# DEFAULTER RISK CHECK
# ---------------------------------------------------------------------------

def check_defaulter_risk(loan) -> dict:
    """
    Early warning: compare recent sales vs repayment obligation.
    Flags traders whose revenue has dropped significantly while a loan is active.

    FIX: at_risk is False when monthly_repayment is 0 (e.g. new/just-approved loans
    with no repayment history yet) — prevents false positives for brand-new users.
    """
    from ..models import Sale

    now = timezone.now()
    last_30  = now - timedelta(days=30)
    prev_30  = now - timedelta(days=60)

    recent_sales = (
        Sale.objects
        .filter(user=loan.user, created_at__gte=last_30)
        .aggregate(total=Sum('amount'))['total']
        or Decimal('0')
    )

    previous_sales = (
        Sale.objects
        .filter(user=loan.user, created_at__gte=prev_30, created_at__lt=last_30)
        .aggregate(total=Sum('amount'))['total']
        or Decimal('0')
    )

    # Calculate percentage drop in sales
    drop_percent = 0.0
    if previous_sales > Decimal('0'):
        drop_percent = float(
            (previous_sales - recent_sales) / previous_sales * 100
        )

    monthly_repayment = loan.monthly_repayment or Decimal('0')

    # FIX: never flag at_risk when there is no repayment obligation yet
    if monthly_repayment <= Decimal('0'):
        at_risk = False
    else:
        at_risk = (
            drop_percent > 40  # sales dropped more than 40%
            or float(recent_sales) < float(monthly_repayment * Decimal('1.5'))
            # earning less than 1.5× monthly repayment — danger zone
        )

    return {
        'at_risk': at_risk,
        'recent_sales': float(recent_sales),
        'previous_sales': float(previous_sales),
        'drop_percent': round(drop_percent, 1),
        'monthly_repayment': float(monthly_repayment),
    }