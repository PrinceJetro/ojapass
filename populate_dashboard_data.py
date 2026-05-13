import os
import django
import random
from datetime import timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ajopass.settings')
django.setup()

from main.models import OjaUser, Loan, LoanOffer, Sale

def populate_dummy_data():
    print("Generating dummy data for dashboards...")
    
    lgas = ['Surulere', 'Alimosho', 'Ikeja', 'Lagos Island', 'Yaba']
    roles = ['trader', 'seeker', 'both']
    trade_categories = ['Retail / Fashion', 'Agro-Processing', 'Digital Services', 'Construction', 'FMCG']
    
    users = []
    for i in range(25):
        phone = f"081{random.randint(1000000, 9999999)}"
        user, created = OjaUser.objects.get_or_create(
            phone=phone,
            defaults={
                'full_name': f"Dummy User {i}",
                'lga': random.choice(lgas),
                'role': random.choice(roles),
                'trade_category': random.choice(trade_categories),
                'ojapass_score': random.randint(10, 95),
            }
        )
        users.append(user)
    
    print(f"Created {len(users)} dummy users.")

    traders = [u for u in users if u.role in ['trader', 'both']]
    for i, trader in enumerate(traders[:10]):
        status = 'active' if i % 4 != 0 else 'defaulted'
        offer, _ = LoanOffer.objects.get_or_create(
            user=trader,
            product_type='working_capital',
            defaults={
                'offer_amount': 50000 + (i * 10000),
                'interest_rate': 15.0,
                'tenure_months': 6,
                'monthly_repayment': 10000,
                'oja_score_at_offer': 70,
                'status': 'disbursed',
                'expires_at': timezone.now() + timedelta(days=30),
            }
        )
        
        Loan.objects.get_or_create(
            user=trader,
            offer=offer,
            defaults={
                'principal': offer.offer_amount,
                'interest_rate': offer.interest_rate,
                'tenure_months': offer.tenure_months,
                'monthly_repayment': offer.monthly_repayment,
                'total_repayable': offer.monthly_repayment * offer.tenure_months,
                'amount_outstanding': 30000 + (i * 5000),
                'status': status,
            }
        )

    print("Created loans.")

    for i, trader in enumerate(traders[10:15]):
        LoanOffer.objects.get_or_create(
            user=trader,
            product_type='nano_loan',
            status='applied',
            defaults={
                'offer_amount': 150000,
                'interest_rate': 12.0,
                'tenure_months': 3,
                'monthly_repayment': 55000,
                'oja_score_at_offer': 65,
                'expires_at': timezone.now() + timedelta(days=30),
                'applied_at': timezone.now() - timedelta(hours=i)
            }
        )

    print("Created applicant queue.")

    for i, trader in enumerate(traders[:5]):
        Sale.objects.create(
            user=trader,
            amount=random.randint(5000, 50000),
            payment_method='cash',
            created_at=timezone.now() - timedelta(minutes=random.randint(1, 60))
        )

    print("Created live sales.")
    print("Done!")

if __name__ == '__main__':
    populate_dummy_data()
