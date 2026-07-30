from django.shortcuts import render, get_object_or_404
from django.conf import settings
from django.http import JsonResponse
from django.views import View
from django.db import transaction
import uuid, requests, json
from ..models import OjaUser, Product, Order, PaymentLink, PaymentLinkItem, Notification
from ..services.bmoni_service import BMONIService

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
                bmoni_user_id = getattr(merchant, 'bmoni_user_id', None)

                # Fallback: if BMONI not set up or API down, return mock deposit account for development
                if not bmoni_user_id:
                    if settings.DEBUG:
                        return JsonResponse({
                            "success": True,
                            "transaction_ref": ref,
                            "depositAccount": {
                                "bankName": "Wema Bank (Mock)",
                                "accountNumber": "1234567890",
                                "accountName": merchant.full_name,
                                "narration": f"Payment for invoice {ref}",
                            },
                            "amount": total,
                        })
                    return JsonResponse({"success": False, "message": "Merchant not configured for BMONI deposits."}, status=400)

                deposit_result = BMONIService.get_deposit_accounts(bmoni_user_id, "NGN")
                if not deposit_result or not deposit_result.get('success'):
                    if settings.DEBUG:
                        return JsonResponse({
                            "success": True,
                            "transaction_ref": ref,
                            "depositAccount": {
                                "bankName": "Wema Bank (Mock)",
                                "accountNumber": "1234567890",
                                "accountName": merchant.full_name,
                                "narration": f"Payment for invoice {ref}",
                            },
                            "amount": total,
                        })
                    return JsonResponse({"success": False, "message": "Unable to fetch deposit account."}, status=502)

                accounts = deposit_result.get('data', {}).get('accounts', [])
                if not accounts:
                    return JsonResponse({"success": False, "message": "No deposit account available for this merchant yet."}, status=400)

                account = accounts[0]
                # Return deposit instructions to the client
                return JsonResponse({
                    "success": True,
                    "transaction_ref": ref,
                    "depositAccount": {
                        "bankName": account.get('bankName'),
                        "accountNumber": account.get('accountNumber'),
                        "accountName": account.get('accountName'),
                        "narration": account.get('depositMessage') or f"Payment for invoice {ref}",
                    },
                    "amount": total,
                })

        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)}, status=400)