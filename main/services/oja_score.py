"""
OjaScore Engine — OjaPass
=========================
Score range : 0–100 (hard cap)
Start       : 0 (BVN is mandatory, so no floor needed)

Structure
---------
Layer 1 — Payment Reliability  : 60 pts max  (same for every role)
Layer 2 — Performance Signals  : 40 pts max  (varies by role)

Layer 2 breakdown by role:
  trader  → business signals      (40 pts)
  seeker  → portfolio signals     (40 pts)
  both    → average of both       (40 pts)
"""

import math
from datetime import timedelta, date
from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum
from django.db.models.functions import TruncMonth


# ============================================================
# TIER DEFINITIONS  (0–100 scale)
# ============================================================

TIERS = [
    {"name": "Verified Member", "min": 0,  "max": 30,  "next": "Rising Star",    "next_min": 31},
    {"name": "Rising Star",     "min": 31, "max": 55,  "next": "Gold Standard",  "next_min": 56},
    {"name": "Gold Standard",   "min": 56, "max": 74,  "next": "Platinum Plus",  "next_min": 75},
    {"name": "Platinum Plus",   "min": 75, "max": 89,  "next": "Diamond Elite",  "next_min": 90},
    {"name": "Diamond Elite",   "min": 90, "max": 100, "next": None,             "next_min": None},
]

LOAN_THRESHOLDS = [31, 56, 75, 90]


def get_tier(score: int) -> dict:
    for t in reversed(TIERS):
        if score >= t["min"]:
            return t
    return TIERS[0]


# ============================================================
# HELPERS
# ============================================================

def _pct(value: float, maximum: float) -> float:
    """Return value as a percentage of maximum, clamped 0–1."""
    if maximum <= 0:
        return 0.0
    return min(value / maximum, 1.0)


# ============================================================
# SEEKER PORTFOLIO SCORE  (0–40 pts)
# ============================================================

def calculate_seeker_portfolio_score(seeker) -> float:
    """
    Bayesian average of verified client reviews mapped to 0–40 pts.

    Bayesian formula:
        avg = (C × m + Σratings) / (C + n)
        C = 5   (confidence threshold — reviews needed for full trust)
        m = 3.5 (platform mean — assumed rating for new seekers)

    Stars → points:
        1★ = 0 pts,  3★ = 20 pts,  5★ = 40 pts
        formula: ((avg - 1) / 4) × 40

    Credibility multiplier:
        More verified posts make the score more stable, not automatically higher.
        credibility = min(verified_post_count / 10, 1.0)
        final = quality × (0.4 + 0.6 × credibility)
        — even 1 review contributes 40% of its potential score
    """
    from ..models import PortfolioPost, ClientReview

    reviews = ClientReview.objects.filter(
        post__seeker=seeker,
        is_completed=True
    )

    n = reviews.count()
    C = 5.0
    m = 3.5

    if n == 0:
        # No reviews yet — no score. Don't assume average.
        # (We removed the BVN floor, so newcomers start at 0)
        return 0.0

    sum_ratings = sum(r.rating for r in reviews)
    bayesian_avg = (C * m + sum_ratings) / (C + n)

    # Map 1–5 stars to 0–40 pts
    quality_pts = ((bayesian_avg - 1.0) / 4.0) * 40.0

    # Credibility — how many verified posts back the reviews
    verified_count = PortfolioPost.objects.filter(
        seeker=seeker,
        status='active',
        client_review__is_completed=True
    ).count()
    credibility = min(verified_count / 10.0, 1.0)

    portfolio_score = quality_pts * (0.4 + 0.6 * credibility)
    return round(min(portfolio_score, 40.0), 2)


# ============================================================
# MAIN ENGINE
# ============================================================

def recalculate_ojascore(user_id: int):
    """
    Recalculate and persist OjaScore for a user.
    Returns the new score (int 0–100), or None on error.
    Never writes a 0 on exception — protects against wipeouts.
    """
    from ..models import (
        OjaUser, OjaTransaction, OjaScoreHistory,
        Sale, StockMovement, Order, AjoMembership,
        Gig, Loan, LoanRepayment, LoanOffer, Notification,
    )

    try:
        user = OjaUser.objects.get(id=user_id)
        prev_score = user.ojapass_score
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)

        # ── Base querysets ──────────────────────────────────────
        inflows   = OjaTransaction.objects.filter(
            user=user, transaction_type='inflow', status='success'
        )
        recent_tx = inflows.filter(timestamp__gte=thirty_days_ago)
        sales     = Sale.objects.filter(user=user)
        movements = StockMovement.objects.filter(user=user)
        # Orders placed ON the trader's storefront (customer orders)
        orders    = Order.objects.filter(user=user)
        gigs      = Gig.objects.filter(worker=user)
        ajo_memberships = AjoMembership.objects.filter(user=user)

        # ================================================================
        # LAYER 1 — PAYMENT RELIABILITY  (60 pts max)
        # ================================================================

        # 1. Transaction frequency — 20 pts
        #    10 inflows in 30 days = full score
        freq_count     = recent_tx.count()
        frequency_score = round(min(_pct(freq_count, 10) * 20.0, 20.0), 2)

        # 2. Transaction consistency — 15 pts
        #    How many of the last 4 calendar weeks had at least one inflow?
        #    4/4 active weeks = full score
        active_weeks = set()
        for tx in recent_tx.order_by('timestamp'):
            active_weeks.add(tx.timestamp.isocalendar()[1])
        consistency_score = round(min(_pct(len(active_weeks), 4) * 15.0, 15.0), 2)

        # 3. Payer diversity — 10 pts
        #    5 unique senders in 30 days = full score
        unique_payers = (
            recent_tx
            .exclude(sender_name__isnull=True)
            .exclude(sender_name='')
            .values('sender_name')
            .distinct()
            .count()
        )
        diversity_score = round(min(_pct(unique_payers, 5) * 10.0, 10.0), 2)

        # 4. Repayment history — 10 pts
        #    Sources: Ajo contribution behaviour + loan repayment behaviour
        #    New users with no history get 0 — they haven't proven themselves yet
        total_ajo_cycles   = sum(m.cycles_completed + m.cycles_defaulted for m in ajo_memberships)
        total_ajo_defaults = sum(m.cycles_defaulted for m in ajo_memberships)

        if total_ajo_cycles == 0:
            ajo_repay_rate = 1.0  # no data — benefit of the doubt at 100%
        else:
            ajo_repay_rate = 1.0 - (total_ajo_defaults / total_ajo_cycles)

        # Loan penalties
        missed_installments = LoanRepayment.objects.filter(
            loan__user=user, status='missed'
        ).count()
        defaulted_loans = Loan.objects.filter(
            user=user, status='defaulted'
        ).count()

        if defaulted_loans > 0:
            repayment_score = 0.0          # full wipeout for loan default
        elif missed_installments > 0:
            penalty = missed_installments * 3.0   # -3 pts per missed installment
            repayment_score = max(0.0, ajo_repay_rate * 10.0 - penalty)
        else:
            repayment_score = round(min(ajo_repay_rate * 10.0, 10.0), 2)

        # 5. Platform tenure — 5 pts
        #    90 days of inflow history = full score
        first_inflow = inflows.order_by('timestamp').first()
        if first_inflow:
            tenure_days  = (now - first_inflow.timestamp).days
            tenure_score = round(min(_pct(tenure_days, 90) * 5.0, 5.0), 2)
        else:
            tenure_score = 0.0

        layer1 = frequency_score + consistency_score + diversity_score + repayment_score + tenure_score
        # max: 20 + 15 + 10 + 10 + 5 = 60

        # ================================================================
        # LAYER 2 — PERFORMANCE SIGNALS  (40 pts max)
        # ================================================================

        # ── TRADER SIGNALS  (40 pts max) ────────────────────────────────

        # a. Monthly sales turnover — 15 pts
        #    ₦50,000 avg / month = full score
        if sales.exists():
            monthly_agg = (
                sales
                .annotate(month=TruncMonth('created_at'))
                .values('month')
                .annotate(total=Sum('amount'))
            )
        else:
            monthly_agg = None

        if monthly_agg and monthly_agg.exists():
            avg_monthly   = sum(float(m['total']) for m in monthly_agg) / monthly_agg.count()
            turnover_score = round(min(_pct(avg_monthly, 50_000) * 15.0, 15.0), 2)
        else:
            turnover_score = 0.0

        # b. Inventory restock frequency — 8 pts
        #    4 restocks in 30 days (weekly) = full score
        restock_count = movements.filter(
            movement_type='restock',
            timestamp__gte=thirty_days_ago
        ).count()
        restock_score = round(min(_pct(restock_count, 4) * 8.0, 8.0), 2)

        # c. Order fulfillment rate — 7 pts
        #    Complete all storefront orders = full score
        #    New users with no orders → 0 (they haven't been tested yet)
        total_orders     = orders.count()
        fulfilled_orders = orders.filter(status__in=['fulfilled', 'paid']).count()
        fulfillment_score = round(
            (fulfilled_orders / total_orders * 7.0) if total_orders > 0 else 0.0,
            2
        )

        # d. Gig completion rate — 5 pts
        total_gigs     = gigs.count()
        completed_gigs = gigs.filter(status__in=['completed', 'paid']).count()
        gig_score = round(
            (completed_gigs / total_gigs * 5.0) if total_gigs > 0 else 0.0,
            2
        )

        # e. Customer / employer ratings — 5 pts
        #    Based on gig ratings only (1–5 stars mapped to 0–5 pts)
        #    No free points — unrated = 0
        rated_gigs = gigs.exclude(rating__isnull=True)
        if rated_gigs.exists():
            avg_gig_rating = sum(g.rating for g in rated_gigs) / rated_gigs.count()
            rating_score   = round(min(_pct(avg_gig_rating, 5) * 5.0, 5.0), 2)
        else:
            rating_score = 0.0

        trader_layer2 = (
            turnover_score + restock_score + fulfillment_score
            + gig_score + rating_score
        )
        # max: 15 + 8 + 7 + 5 + 5 = 40

        # ── SEEKER SIGNALS  (40 pts max) ────────────────────────────────
        seeker_layer2 = calculate_seeker_portfolio_score(user)
        # Already capped at 40 inside the function

        # ── Role consolidation ───────────────────────────────────────────
        if user.role == 'seeker':
            layer2 = seeker_layer2
        elif user.role == 'trader':
            layer2 = trader_layer2
        else:  # 'both'
            layer2 = round((seeker_layer2 + trader_layer2) / 2.0, 2)

        layer2 = min(layer2, 40.0)

        # ================================================================
        # TOTAL  (0–100, no floor — everyone starts at 0)
        # ================================================================
        raw_score = layer1 + layer2
        new_score = int(min(max(round(raw_score), 0), 100))
        delta     = new_score - prev_score

        # ================================================================
        # NARRATIVE  (plain English fallback — Gemini overrides if available)
        # ================================================================
        tier       = get_tier(new_score)
        next_tier  = tier['next']
        next_min   = tier['next_min']
        pts_to_next = (next_min - new_score) if next_min else 0

        # Find weakest signal as a percentage of its max
        if user.role == 'seeker':
            signals = {
                "transaction frequency":   (frequency_score,   20.0),
                "transaction consistency": (consistency_score, 15.0),
                "payer diversity":         (diversity_score,   10.0),
                "repayment history":       (repayment_score,   10.0),
                "portfolio quality":       (seeker_layer2,     40.0),
            }
        elif user.role == 'trader':
            signals = {
                "transaction frequency":   (frequency_score,   20.0),
                "transaction consistency": (consistency_score, 15.0),
                "payer diversity":         (diversity_score,   10.0),
                "repayment history":       (repayment_score,   10.0),
                "sales turnover":          (turnover_score,    15.0),
                "inventory restocking":    (restock_score,      8.0),
                "order fulfillment":       (fulfillment_score,  7.0),
                "gig completion":          (gig_score,          5.0),
                "customer ratings":        (rating_score,       5.0),
            }
        else:
            signals = {
                "transaction frequency":   (frequency_score,   20.0),
                "transaction consistency": (consistency_score, 15.0),
                "payer diversity":         (diversity_score,   10.0),
                "repayment history":       (repayment_score,   10.0),
                "portfolio quality":       (seeker_layer2,     20.0),
                "sales turnover":          (turnover_score,    20.0),
            }

        weakest = min(
            signals,
            key=lambda k: signals[k][0] / signals[k][1] if signals[k][1] > 0 else 1.0
        )

        action_tips = {
            "transaction frequency":   "Accept more payments through your OjaPass account — aim for at least 10 this month.",
            "transaction consistency": "Try to receive payments every week, even small ones keep your score healthy.",
            "payer diversity":         "Grow your customer base — receiving money from 5+ different people boosts your score significantly.",
            "repayment history":       "Stay on top of your Ajo contributions and loan repayments — missed payments hurt the most.",
            "portfolio quality":       "Add your best work to your portfolio and share the review link with past clients — even one 5★ review makes a difference.",
            "sales turnover":          "Record your daily sales in Mamatally so your real revenue shows in your score.",
            "inventory restocking":    "Restock your inventory at least once a week to show an active, growing business.",
            "order fulfillment":       "Fulfil all open customer orders quickly — 100% completion is a strong trust signal.",
            "gig completion":          "Complete every gig you accept — showing up and delivering is the fastest way to build trust.",
            "customer ratings":        "Ask employers to rate you after each gig — ratings unlock higher tiers.",
        }

        first_name = user.full_name.split()[0] if user.full_name else "Trader"

        if delta > 0:
            change_line = f"Great news {first_name} — your OjaScore went up {delta} points! "
        elif delta < 0:
            change_line = f"{first_name}, your OjaScore dipped {abs(delta)} points this period. "
        else:
            change_line = f"{first_name}, your OjaScore is holding steady at {new_score}. "

        if next_tier:
            tier_line = f"You are {pts_to_next} points away from {next_tier} tier."
        else:
            tier_line = "You have reached the highest tier — Diamond Elite. Outstanding!"

        narrative = f"{change_line}{action_tips[weakest]} {tier_line}"

        # ================================================================
        # SAVE — only write history when score changes
        # ================================================================
        user.ojapass_score     = new_score
        user.ojapass_narrative = narrative
        user.save(update_fields=['ojapass_score', 'ojapass_narrative'])

        if not OjaScoreHistory.objects.filter(user=user).exists() or new_score != prev_score:
            history = OjaScoreHistory.objects.create(
                user=user,
                score=new_score,
                frequency_score=frequency_score,
                consistency_score=consistency_score,
                diversity_score=diversity_score,
                repayment_score=repayment_score,
                tenure_score=tenure_score,
                turnover_score=turnover_score,
                restock_score=restock_score,
                fulfillment_score=fulfillment_score,
                gig_score=gig_score,
                rating_score=rating_score,
            )

            # Try Gemini narrative — silently fall back to built-in if unavailable
            try:
                from .gemini_service import GeminiService
                ai_narrative = GeminiService.generate_score_narrative(user, history)
                if ai_narrative:
                    user.ojapass_narrative = ai_narrative
                    user.save(update_fields=['ojapass_narrative'])
            except Exception as e:
                print(f"[OjaScore] Gemini narrative unavailable: {e}")

        # ================================================================
        # AUTO-TRIGGER LOAN OFFER when user crosses a tier threshold
        # ================================================================
        for threshold in LOAN_THRESHOLDS:
            if prev_score < threshold <= new_score:
                from .loan_engine import calculate_loan_offer
                existing = LoanOffer.objects.filter(
                    user=user, status='available'
                ).exists()
                if not existing:
                    offer_data = calculate_loan_offer(user)
                    if offer_data and offer_data['product_type'] != 'savings_goal':
                        LoanOffer.objects.create(
                            user=user,
                            product_type=offer_data['product_type'],
                            offer_amount=offer_data['offer_amount'],
                            interest_rate=offer_data['interest_rate'],
                            tenure_months=offer_data['tenure_months'],
                            monthly_repayment=offer_data['monthly_repayment'],
                            avg_monthly_turnover=offer_data['avg_monthly_turnover'],
                            oja_score_at_offer=new_score,
                            expires_at=timezone.now() + timedelta(days=7),
                        )
                        Notification.objects.create(
                            user=user,
                            message=(
                                f"NEW OFFER UNLOCKED! Your OjaScore reached {new_score}. "
                                f"You qualify for ₦{offer_data['offer_amount']:,.0f}. "
                                f"Check your Loans dashboard."
                            )
                        )
                break  # only trigger one threshold per recalculation

        return new_score

    except OjaUser.DoesNotExist:
        print(f"[OjaScore] User {user_id} not found.")
        return None
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[OjaScore] Error for user {user_id}: {e}")
        # NEVER save on exception — protects against score wipeout
        return None


# ============================================================
# GEMINI PROMPT BUILDER
# ============================================================

def build_narrative_prompt(user, history_record, new_score: int, delta: int) -> str:
    """
    Builds the prompt sent to Gemini for AI narrative generation.
    Called from GeminiService.generate_score_narrative().
    """
    tier       = get_tier(new_score)
    next_tier  = tier['next']
    next_min   = tier['next_min']
    pts_to_next = (next_min - new_score) if next_min else 0

    if history_record:
        signals_block = f"""
Signal breakdown (actual / max):
  Payment signals (60 pts max):
    - Transaction frequency:   {history_record.frequency_score:.1f} / 20
    - Transaction consistency: {history_record.consistency_score:.1f} / 15
    - Payer diversity:         {history_record.diversity_score:.1f} / 10
    - Repayment history:       {history_record.repayment_score:.1f} / 10
    - Platform tenure:         {history_record.tenure_score:.1f} / 5

  Performance signals (40 pts max):
    - Sales turnover:          {history_record.turnover_score:.1f} / 15
    - Restock frequency:       {history_record.restock_score:.1f} / 8
    - Order fulfillment:       {history_record.fulfillment_score:.1f} / 7
    - Gig completion:          {history_record.gig_score:.1f} / 5
    - Customer ratings:        {history_record.rating_score:.1f} / 5
"""
    else:
        signals_block = "No signal history available yet."

    tier_context = (
        "They have reached Diamond Elite — the highest tier. Celebrate this!"
        if not next_tier
        else f"They are {pts_to_next} points away from '{next_tier}' tier."
    )

    role_context = {
        'trader': "They are a market trader who sells goods and manages inventory.",
        'seeker': "They are a gig worker who completes jobs and builds a portfolio of verified work.",
        'both':   "They are both a trader and a gig worker.",
    }.get(user.role, "They are an OjaPass user.")

    return f"""You are the OjaScore Coach for OjaPass, a financial identity platform for Nigeria's informal economy.

User: {user.full_name}
Role: {role_context}
Current Score: {new_score}/100
Current Tier: {tier['name']}
Score Change This Period: {"+" if delta >= 0 else ""}{delta} points

{signals_block}
{tier_context}

Write exactly 2–3 sentences directly to this user:
1. Acknowledge whether the score went up, down, or stayed the same. Name the 1–2 weakest signals as the reason using plain conversational language — not field names. For example say "you haven't been receiving payments from enough different customers" not "payer diversity is low".
2. Give ONE specific action they can take THIS WEEK to improve their score.
3. Tell them how close they are to their next tier, or celebrate if they just hit a new one.

Rules:
- Warm coach tone — encouraging, never judgemental.
- Plain English — no numbers from the signal table, no jargon, no bullet points.
- Maximum 3 sentences. Write as if you are texting a friend.
"""