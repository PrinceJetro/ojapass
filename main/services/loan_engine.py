"""
Loan Engine — OjaPass
=====================
Handles all loan sizing, eligibility, repayment schedule generation,
and defaulter risk detection.

Loan tiers align with OjaScore tiers (0–100 scale):
  31+ → Savings Goal (no loan amount)
  56+ → Nano Loan        ₦5,000  – ₦50,000   @ 5.0% / month, 3 months
  75+ → Working Capital  ₦50,000 – ₦200,000  @ 3.5% / month, 4 months
  90+ → Credit Line      ₦200,000– ₦500,000  @ 2.5% / month, 6 months
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta, date
from django.utils import timezone
from django.db.models import Sum
from django.db.models.functions import TruncMonth


# ============================================================
# TIER → PRODUCT MAP
# ============================================================

TIER_PRODUCTS = {
    90: {
        'product_type': 'credit_line',
        'label': 'Merchant Credit Line',
        'min_amount': Decimal('200000'),
        'max_amount': Decimal('500000'),
        'interest_rate': Decimal('2.5'),   # % per month
        'tenure_months': 6,
    },
    75: {
        'product_type': 'working_capital',
        'label': 'Working Capital Loan',
        'min_amount': Decimal('50000'),
        'max_amount': Decimal('200000'),
        'interest_rate': Decimal('3.5'),
        'tenure_months': 4,
    },
    56: {
        'product_type': 'nano_loan',
        'label': 'Nano Loan',
        'min_amount': Decimal('5000'),
        'max_amount': Decimal('50000'),
        'interest_rate': Decimal('5.0'),
        'tenure_months': 3,
    },
    31: {
        'product_type': 'savings_goal',
        'label': 'Savings Goal',
        'min_amount': Decimal('0'),
        'max_amount': Decimal('0'),
        'interest_rate': Decimal('0'),
        'tenure_months': 0,
    },
}


def get_eligible_product(score: int) -> dict | None:
    """Return the best product the user qualifies for based on OjaScore (0–100)."""
    for min_score in sorted(TIER_PRODUCTS.keys(), reverse=True):
        if score >= min_score:
            return TIER_PRODUCTS[min_score]
    return None


# ============================================================
# TURNOVER CALCULATOR
# ============================================================

def calculate_avg_monthly_turnover(user) -> Decimal:
    """
    Average monthly sales from the last 3 months.
    This is the Mamatally layer — actual business data drives loan sizing.
    Falls back to transaction inflows if no sales are recorded.
    """
    from ..models import Sale, OjaTransaction

    three_months_ago = timezone.now() - timedelta(days=90)

    monthly = (
        Sale.objects
        .filter(user=user, created_at__gte=three_months_ago)
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(total=Sum('amount'))
    )

    if monthly.exists():
        total = sum(Decimal(str(m['total'])) for m in monthly)
        return (total / Decimal(monthly.count())).quantize(Decimal('0.01'))

    # Fallback — use Squad inflow data if no sales recorded
    monthly_inflows = (
        OjaTransaction.objects
        .filter(
            user=user,
            transaction_type='inflow',
            status='success',
            timestamp__gte=three_months_ago
        )
        .annotate(month=TruncMonth('timestamp'))
        .values('month')
        .annotate(total=Sum('amount'))
    )

    if monthly_inflows.exists():
        total = sum(Decimal(str(m['total'])) for m in monthly_inflows)
        return (total / Decimal(monthly_inflows.count())).quantize(Decimal('0.01'))

    return Decimal('0')


# ============================================================
# LOAN OFFER CALCULATOR
# ============================================================

def calculate_loan_offer(user) -> dict | None:
    """
    Core loan sizing:
        Offer = 1.5 × average monthly turnover
        Clamped to the tier's [min_amount, max_amount] range.

    Returns a dict with all offer details, or None if not eligible.
    """
    score   = user.ojapass_score
    product = get_eligible_product(score)

    if not product:
        return None

    # Savings goal — no disbursement, just unlock the feature
    if product['product_type'] == 'savings_goal':
        return {
            'product_type':         'savings_goal',
            'label':                product['label'],
            'offer_amount':         Decimal('0'),
            'interest_rate':        Decimal('0'),
            'tenure_months':        0,
            'monthly_repayment':    Decimal('0'),
            'total_repayable':      Decimal('0'),
            'avg_monthly_turnover': calculate_avg_monthly_turnover(user),
        }

    avg_turnover = calculate_avg_monthly_turnover(user)

    if avg_turnover <= 0:
        # No transaction history — offer the floor of the tier
        offer_amount = product['min_amount']
    else:
        # 1.5× average monthly turnover, clamped to tier limits
        raw_offer    = avg_turnover * Decimal('1.5')
        offer_amount = max(product['min_amount'], min(raw_offer, product['max_amount']))
        offer_amount = offer_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    tenure = product['tenure_months']
    rate   = product['interest_rate'] / Decimal('100')  # monthly decimal rate

    # Standard amortization formula:
    # M = P × r(1+r)^n / ((1+r)^n − 1)
    if rate > 0 and tenure > 0:
        factor            = (1 + rate) ** tenure
        monthly_repayment = (offer_amount * (rate * factor) / (factor - 1))
        monthly_repayment = monthly_repayment.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    else:
        monthly_repayment = Decimal('0')

    total_repayable = (monthly_repayment * tenure).quantize(Decimal('0.01'))

    return {
        'product_type':         product['product_type'],
        'label':                product['label'],
        'offer_amount':         offer_amount,
        'interest_rate':        product['interest_rate'],
        'tenure_months':        tenure,
        'monthly_repayment':    monthly_repayment,
        'total_repayable':      total_repayable,
        'avg_monthly_turnover': avg_turnover,
    }


# ============================================================
# REPAYMENT SCHEDULE
# ============================================================

def generate_repayment_schedule(loan) -> list[dict]:
    """
    Generate a list of installment dicts for a loan.
    Each installment is due 30 days after the previous one,
    starting 30 days from disbursement.
    """
    schedule   = []
    start_date = loan.disbursed_at.date() if loan.disbursed_at else date.today()

    for i in range(1, loan.tenure_months + 1):
        due_date = start_date + timedelta(days=30 * i)
        schedule.append({
            'installment': i,
            'due_date':    due_date,
            'amount_due':  loan.monthly_repayment,
        })

    return schedule


# ============================================================
# DEFAULTER RISK CHECK
# ============================================================

def check_defaulter_risk(loan) -> dict:
    """
    Early warning system — compares recent sales to loan obligation.

    Flags a loan as at-risk if:
      - Sales dropped more than 40% vs the previous period, OR
      - Recent sales are less than 1.5× the monthly repayment amount
        (trader is not earning enough buffer to repay comfortably)

    Only fires if the loan has an actual repayment obligation (monthly_repayment > 0).
    New users or savings goals are never flagged.
    """
    from ..models import Sale

    # Guard — don't flag loans with no repayment amount
    if not loan.monthly_repayment or loan.monthly_repayment <= 0:
        return {
            'at_risk':           False,
            'recent_sales':      0.0,
            'previous_sales':    0.0,
            'drop_percent':      0.0,
            'monthly_repayment': 0.0,
            'reason':            'No repayment obligation',
        }

    now     = timezone.now()
    last_30 = now - timedelta(days=30)
    prev_30 = now - timedelta(days=60)

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

    # Calculate percentage drop
    if previous_sales > 0:
        drop_percent = float((previous_sales - recent_sales) / previous_sales * 100)
    else:
        drop_percent = 0.0

    # At-risk conditions
    sales_dropped_badly   = drop_percent > 40
    cant_afford_repayment = float(recent_sales) < float(loan.monthly_repayment * Decimal('1.5'))

    at_risk = sales_dropped_badly or cant_afford_repayment

    # Build a human-readable reason for the lender dashboard
    reasons = []
    if sales_dropped_badly:
        reasons.append(f"Sales dropped {drop_percent:.0f}% vs last period")
    if cant_afford_repayment:
        reasons.append(f"Earning less than 1.5× monthly repayment (₦{loan.monthly_repayment:,.0f})")

    return {
        'at_risk':           at_risk,
        'recent_sales':      float(recent_sales),
        'previous_sales':    float(previous_sales),
        'drop_percent':      round(drop_percent, 1),
        'monthly_repayment': float(loan.monthly_repayment),
        'reason':            ' | '.join(reasons) if reasons else 'Healthy',
    }