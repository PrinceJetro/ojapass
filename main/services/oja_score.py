from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum
from django.db.models.functions import TruncMonth

def get_tier(score):
    if score >= 90:
        return {"name": "Verified Pro", "next": None, "next_min": None}
    elif score >= 75:
        return {"name": "Business Elite", "next": "Verified Pro", "next_min": 90}
    elif score >= 56:
        return {"name": "Trusted Merchant", "next": "Business Elite", "next_min": 75}
    elif score >= 31:
        return {"name": "Rising Star", "next": "Trusted Merchant", "next_min": 56}
    else:
        return {"name": "Newcomer", "next": "Rising Star", "next_min": 31}

def recalculate_ojascore(user_id):
    """
    The main OjaScore Engine.
    Calculates trust based on 10 core economic signals.
    """
    from ..models import OjaUser, OjaTransaction, OjaScoreHistory, Sale, StockMovement, Order, AjoMembership, Notification
    
    try:
        user = OjaUser.objects.get(id=user_id)
        prev_score = user.ojapass_score
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)

        # GET DATA SIGNALS
        inflows = OjaTransaction.objects.filter(user=user, transaction_type='inflow', status='success')
        sales = Sale.objects.filter(user=user)
        movements = StockMovement.objects.filter(product__user=user)
        orders = Order.objects.filter(product__user=user)
        ajo_memberships = AjoMembership.objects.filter(user=user)

        # ===================================================================
        # LAYER 1 — PAYMENT RELIABILITY (60 pts max)
        # ===================================================================

        # 1. Transaction frequency — 20 pts
        #    Target: 10 successful inflows in 30 days = full score.
        recent_inflows_count = inflows.filter(timestamp__gte=thirty_days_ago).count()
        frequency_score = min(recent_inflows_count / 10.0 * 20.0, 20.0)

        # 2. Transaction consistency — 15 pts
        #    Measures how many unique weeks (out of last 4) had activity.
        #    Target: 4/4 weeks active = full score.
        weeks_active = inflows.filter(timestamp__gte=thirty_days_ago).annotate(
            week=TruncMonth('timestamp') # Actually we want week, but TruncMonth is available
        ).values('timestamp__week').distinct().count() # Simplified for logic
        # Better week logic:
        active_weeks = set()
        for tx in inflows.filter(timestamp__gte=thirty_days_ago):
            active_weeks.add(tx.timestamp.isocalendar()[1])
        consistency_score = min(len(active_weeks) / 4.0 * 15.0, 15.0)

        # 3. Payer diversity — 10 pts
        #    Target: 5 unique senders in 30 days = full score.
        unique_payers = (
            inflows.filter(timestamp__gte=thirty_days_ago)
            .exclude(sender_name='')
            .values('sender_name')
            .distinct()
            .count()
        )
        diversity_score = min(unique_payers / 5.0 * 10.0, 10.0)

        # 4. Repayment history — 10 pts
        # Ajo Contributions
        total_contributions = sum(m.cycles_completed + m.cycles_defaulted for m in ajo_memberships)
        total_defaults = sum(m.cycles_defaulted for m in ajo_memberships)
        if total_contributions == 0:
            repayment_score = 8.0
        else:
            repayment_rate  = 1.0 - (total_defaults / total_contributions)
            repayment_score = min(repayment_rate * 10.0, 10.0)

        # Apply Loan Delinquency Penalties
        from ..models import LoanRepayment, Loan
        missed_repayments = LoanRepayment.objects.filter(loan__user=user, status='missed').count()
        defaulted_loans = Loan.objects.filter(user=user, status='defaulted').count()

        if defaulted_loans > 0:
            repayment_score = 0.0  # Massive hit for full default
        elif missed_repayments > 0:
            repayment_score = max(0.0, repayment_score - (missed_repayments * 3.0)) # Deduct 3 pts per missed payment


        # 5. Platform tenure — 5 pts
        first_inflow = inflows.order_by('timestamp').first()
        if first_inflow:
            tenure_days   = (now - first_inflow.timestamp).days
            tenure_score  = min(tenure_days / 90.0 * 5.0, 5.0)
        else:
            tenure_score  = 0.0

        # ===================================================================
        # LAYER 2 — BUSINESS SIGNALS  (40 pts max)
        # ===================================================================
        if sales.exists():
            monthly_agg = sales.annotate(month=TruncMonth('created_at')).values('month').annotate(total=Sum('amount'))
        else:
            monthly_agg = inflows.annotate(month=TruncMonth('timestamp')).values('month').annotate(total=Sum('amount'))

        if monthly_agg.exists():
            avg_monthly    = sum(float(m['total']) for m in monthly_agg) / monthly_agg.count()
            turnover_score = min(avg_monthly / 50_000.0 * 15.0, 15.0)
        else:
            turnover_score = 0.0

        restock_count = movements.filter(movement_type='restock', timestamp__gte=thirty_days_ago).count()
        restock_score = min(restock_count / 4.0 * 8.0, 8.0)

        total_orders     = orders.count()
        fulfilled_orders = orders.filter(status__in=['fulfilled', 'paid']).count()
        fulfillment_score = (fulfilled_orders / total_orders * 7.0) if total_orders > 0 else 0.0

        from ..models import Gig
        gigs = Gig.objects.filter(worker=user)
        total_gigs = gigs.count()
        completed_gigs = gigs.filter(status__in=['completed', 'paid']).count()
        gig_score = (completed_gigs / total_gigs * 5.0) if total_gigs > 0 else 0.0

        rated_gigs = gigs.exclude(rating__isnull=True)
        if rated_gigs.exists():
            avg_rating = sum(g.rating for g in rated_gigs) / rated_gigs.count()
            rating_score = (avg_rating / 5.0) * 5.0
        else:
            rating_score = 3.5 if completed_gigs > 0 else 0.0

        # FINAL CALCULATION
        new_score = int(
            frequency_score + consistency_score + diversity_score + repayment_score + tenure_score +
            turnover_score + restock_score + fulfillment_score + gig_score + rating_score
        )
        new_score = min(new_score, 100)
        delta = new_score - prev_score

        # Narrative Logic
        tier = get_tier(new_score)
        next_tier = tier['next']
        pts_to_next = (tier['next_min'] - new_score) if tier['next_min'] else 0

        signals = {
            "transaction frequency": (frequency_score, 20.0),
            "transaction consistency": (consistency_score, 15.0),
            "payer diversity": (diversity_score, 10.0),
            "repayment history": (repayment_score, 10.0),
            "sales turnover": (turnover_score, 15.0),
            "inventory restocking": (restock_score, 8.0),
            "order fulfillment": (fulfillment_score, 7.0),
            "gig completion": (gig_score, 5.0),
            "customer ratings": (rating_score, 5.0),
        }
        weakest = min(signals, key=lambda k: signals[k][0] / signals[k][1] if signals[k][1] > 0 else 1)
        action_tips = {
            "transaction frequency": "Accept more payments through your OjaPass account.",
            "transaction consistency": "Try to make sales or accept payments every week.",
            "payer diversity": "Grow your customer base — different payers boost your score.",
            "repayment history": "Stay on top of your Ajo contributions.",
            "sales turnover": "Log your sales in Mamatally regularly.",
            "inventory restocking": "Restock your inventory at least once a week.",
            "order fulfillment": "Fulfil all open orders quickly.",
            "gig completion": "Complete the gigs you accept.",
            "customer ratings": "Ask employers or customers to rate you.",
        }

        change_line = f"Your OjaScore went up {delta} points!" if delta > 0 else f"Your score is steady at {new_score}."
        narrative = f"{change_line} {action_tips[weakest]} Next tier: {next_tier}."

        user.ojapass_score = new_score
        user.ojapass_narrative = narrative
        user.save(update_fields=['ojapass_score', 'ojapass_narrative'])

        # History and AI
        prev_history = OjaScoreHistory.objects.filter(user=user).order_by('-timestamp').first()
        if not prev_history or new_score != prev_score:
            history = OjaScoreHistory.objects.create(
                user=user, score=new_score,
                frequency_score=round(frequency_score, 2), consistency_score=round(consistency_score, 2),
                diversity_score=round(diversity_score, 2), repayment_score=round(repayment_score, 2),
                tenure_score=round(tenure_score, 2), turnover_score=round(turnover_score, 2),
                restock_score=round(restock_score, 2), fulfillment_score=round(fulfillment_score, 2),
                gig_score=round(gig_score, 2), rating_score=round(rating_score, 2)
            )
            try:
                from .gemini_service import GeminiService
                ai_narrative = GeminiService.generate_score_narrative(user, history)
                if ai_narrative:
                    user.ojapass_narrative = ai_narrative
                    user.save(update_fields=['ojapass_narrative'])
            except Exception as e: print(f"AI Error: {e}")

        # Loan Trigger
        OFFER_THRESHOLDS = [31, 56, 75, 90]
        for threshold in OFFER_THRESHOLDS:
            if prev_score < threshold <= new_score:
                from ..models import LoanOffer
                from .loan_engine import calculate_loan_offer
                if not LoanOffer.objects.filter(user=user, status='available').exists():
                    offer_data = calculate_loan_offer(user)
                    if offer_data and offer_data['product_type'] != 'savings_goal':
                        LoanOffer.objects.create(
                            user=user, product_type=offer_data['product_type'],
                            offer_amount=offer_data['offer_amount'], interest_rate=offer_data['interest_rate'],
                            tenure_months=offer_data['tenure_months'], monthly_repayment=offer_data['monthly_repayment'],
                            avg_monthly_turnover=offer_data['avg_monthly_turnover'], oja_score_at_offer=new_score,
                            expires_at=timezone.now() + timedelta(days=7)
                        )
                        Notification.objects.create(user=user, message=f"NEW OFFER UNLOCKED! Score: {new_score}. Qualify for ₦{offer_data['offer_amount']:,.0f}.")
                break
        return new_score
    except Exception as e:
        print(f"Error: {e}")
        return None

def build_narrative_prompt(user, history_record, new_score, delta):
    tier = get_tier(new_score)
    pts_to_next = (tier['next_min'] - new_score) if tier['next_min'] else 0
    signals_block = f"Frequency: {history_record.frequency_score}/20, Turnover: {history_record.turnover_score}/15" if history_record else ""
    
    return f"You are OjaScore Coach. User: {user.full_name}, Score: {new_score}, Delta: {delta}. {signals_block}. Next tier in {pts_to_next} pts. Write 2-3 encouraging sentences in plain English."