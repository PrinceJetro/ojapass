from django.shortcuts import render, get_object_or_404
from django.conf import settings
from django.http import JsonResponse
from django.views import View
from django.db import transaction
import uuid, requests, json
from ..models import OjaUser, Product, Order, PaymentLink, PaymentLinkItem, Notification
from ..services.squad_service import SquadService

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
                link = PaymentLink.objects.create(
                    user=user,
                    transaction_ref=ref,
                    amount=total,
                    status='pending',
                    description=f"Storefront Order: {data.get('customerName')}"
                )

                # Create line items so the payment confirmation path can decrement stock.
                for item in data.get('cart', []):
                    product = get_object_or_404(Product, id=item['id'], user=user)
                    quantity = int(item['quantity'])
                    PaymentLinkItem.objects.create(
                        payment_link=link,
                        product=product,
                        quantity=quantity,
                        price_at_time=product.selling_price,
                    )

                # For BMONI flow, return deposit account details for the merchant
                link = PaymentLink.objects.filter(transaction_ref=ref).first()
                if not link:
                    return JsonResponse({"success": False, "message": "Could not create payment link."}, status=500)

                merchant = user

                # Squad inline checkout per order (primary). Mock fallback so demos never block.
                if SquadService.is_configured():
                    from .payment_views import _squad_callback_url
                    email = merchant.email or f"{merchant.phone}@ojapass.local"
                    if "@" not in email or "." not in email.split("@")[-1]:
                        email = f"customer-{merchant.phone}@ojapass.ng"
                    result = SquadService.initiate_checkout(
                        email=email,
                        amount_naira=float(total),
                        transaction_ref=ref,
                        callback_url=_squad_callback_url(request, ref),
                        customer_name=data.get('customerName') or merchant.full_name,
                        metadata={"merchant": merchant.phone, "provider": "ojapass"},
                    )
                    if result.get("success"):
                        checkout_url = (result.get("data") or {}).get("checkout_url")
                        if checkout_url:
                            link.metadata = {
                                **(link.metadata or {}),
                                "squad_checkout": {"checkoutUrl": checkout_url, "transactionRef": ref},
                                "squad_provider": "squad",
                            }
                            link.checkout_url = checkout_url
                            link.save(update_fields=["metadata", "checkout_url"])
                            return JsonResponse({
                                "success": True,
                                "provider": "squad",
                                "transaction_ref": ref,
                                "checkoutUrl": checkout_url,
                                "amount": total,
                            })
                    print(f"[SQUAD] storefront initiate failed for {ref}: {result.get('error')} — using mock")

                return JsonResponse({
                    "success": True,
                    "provider": "mock",
                    "transaction_ref": ref,
                    "depositAccount": {
                        "bankName": "Wema Bank (Mock)",
                        "accountNumber": "1234567890",
                        "accountName": merchant.full_name,
                        "narration": f"Payment for invoice {ref}",
                    },
                    "amount": total,
                })

        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)}, status=400)