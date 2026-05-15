from django.shortcuts import render, get_object_or_404
from django.conf import settings
from django.http import JsonResponse
from django.views import View
from django.db import transaction
import uuid, requests, json
from ..models import OjaUser, Product, Order, PaymentLink, Notification

SQUAD_SECRET_KEY = settings.SQUAD_SECRET_KEY
SQUAD_BASE_URL = "https://sandbox-api-d.squadco.com"

class StorefrontView(View):
    def get(self, request, phone):
        user = get_object_or_404(OjaUser, phone=phone)
        products = Product.objects.filter(user=user, quantity_in_stock__gt=0)
        return render(request, 'customerstorefront.html', {'merchant': user, 'products': products})

class StorefrontCheckoutView(View):
    def post(self, request, phone):
        try:
            data = json.loads(request.body)
            user = get_object_or_404(OjaUser, phone=phone)
            total, oids = 0, []
            
            with transaction.atomic():
                for item in data.get('cart', []):
                    product = get_object_or_404(Product, id=item['id'], user=user)
                    order = Order.objects.create(
                        user=user, 
                        customer_name=data.get('customerName'), 
                        product=product, 
                        quantity=item['quantity'], 
                        total_amount=product.selling_price * item['quantity']
                    )
                    total += float(order.total_amount)
                    oids.append(str(order.id))
                    
                ref = f"SF-{uuid.uuid4().hex[:12].upper()}"
                
                # Create PaymentLink so webhook can resolve the merchant (user)
                PaymentLink.objects.create(
                    user=user,
                    transaction_ref=ref,
                    amount=total,
                    status='pending',
                    description=f"Storefront Order: {data.get('customerName')}"
                )

                payload = {
                    "amount": int(total * 100), 
                    "email": data.get('customerEmail'), 
                    "currency": "NGN",
                    "initiate_type": "inline",
                    "transaction_ref": ref, 
                    "metadata": {
                        "type": "storefront_order",
                        "order_ids": ",".join(oids)
                    },
                    "callback_url": request.build_absolute_uri(f"/payment-link/verify/{ref}/")
                }
                
                try:
                    res_raw = requests.post(
                        f"{SQUAD_BASE_URL}/transaction/initiate", 
                        json=payload, 
                        headers={"Authorization": f"Bearer {SQUAD_SECRET_KEY}"},
                        timeout=10
                    )
                    res = res_raw.json()
                    
                    if res_raw.status_code == 200 and res.get('success') and 'data' in res and 'checkout_url' in res['data']:
                        # Update the payment link with the actual checkout URL
                        PaymentLink.objects.filter(transaction_ref=ref).update(checkout_url=res['data']['checkout_url'])
                        return JsonResponse({"success": True, "checkoutUrl": res['data']['checkout_url']})
                    
                    raise Exception(res.get('message', 'Squad initiation failed'))
                    
                except requests.exceptions.RequestException as e:
                    raise Exception(f"Squad request failed: {str(e)}")

        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)}, status=400)