from django.contrib import admin
from .models import (
    OjaUser, OjaTransaction, PaymentLink, Sale, Gig, Product, Order, 
    OjaScoreHistory, AjoGroup, AjoMembership, AjoCycle, AjoContribution,
    LoanOffer, Loan, LoanRepayment, SavingsGoal
)

@admin.register(OjaScoreHistory)
class OjaScoreHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'score', 'timestamp')
    list_filter = ('timestamp',)
    search_fields = ('user__phone', 'user__full_name')

@admin.register(AjoGroup)
class AjoGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'creator', 'contribution_amount', 'frequency', 'status', 'created_at')
    list_filter = ('frequency', 'status', 'created_at')
    search_fields = ('name', 'creator__phone', 'creator__full_name')

@admin.register(AjoMembership)
class AjoMembershipAdmin(admin.ModelAdmin):
    list_display = ('group', 'user', 'rotation_order', 'joined_at')
    list_filter = ('joined_at',)
    search_fields = ('group__name', 'user__phone', 'user__full_name')

@admin.register(AjoCycle)
class AjoCycleAdmin(admin.ModelAdmin):
    list_display = ('group', 'cycle_number', 'beneficiary', 'status', 'expected_amount', 'collected_amount')
    list_filter = ('status', 'group')
    search_fields = ('group__name', 'beneficiary__phone', 'beneficiary__full_name')

@admin.register(AjoContribution)
class AjoContributionAdmin(admin.ModelAdmin):
    list_display = ('cycle', 'member', 'amount', 'status', 'paid_at')
    list_filter = ('status', 'cycle__group')
    search_fields = ('member__phone', 'member__full_name', 'cycle__group__name')


@admin.register(OjaUser)
class OjaUserAdmin(admin.ModelAdmin):
    list_display = ('phone', 'full_name', 'ojapass_id', 'ojapass_score', 'virtual_account_number', 'is_staff')
    search_fields = ('phone', 'full_name', 'ojapass_id', 'virtual_account_number')
    readonly_fields = ('ojapass_id', 'virtual_account_number')

@admin.register(OjaTransaction)
class OjaTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'transaction_reference', 'status', 'timestamp')
    list_filter = ('status', 'transaction_type', 'timestamp')
    search_fields = ('transaction_reference', 'user__phone', 'user__full_name')
    readonly_fields = ('timestamp',)

@admin.register(PaymentLink)
class PaymentLinkAdmin(admin.ModelAdmin):
    list_display = ('transaction_ref', 'user', 'amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('transaction_ref', 'user__phone', 'user__full_name')

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('transaction_ref', 'user', 'product', 'quantity', 'amount', 'payment_method', 'created_at')
    list_filter = ('payment_method', 'created_at')
    search_fields = ('transaction_ref', 'user__phone', 'user__full_name', 'product__name')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'quantity_in_stock', 'cost_price', 'selling_price', 'low_stock_threshold', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'user__phone', 'user__full_name')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('customer_name', 'user', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('customer_name', 'user__phone', 'user__full_name')

@admin.register(Gig)
class GigAdmin(admin.ModelAdmin):
    list_display = ('title', 'worker', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('title', 'worker__phone', 'worker__full_name')

@admin.register(LoanOffer)
class LoanOfferAdmin(admin.ModelAdmin):
    list_display = ('user', 'product_type', 'offer_amount', 'status', 'expires_at', 'created_at')
    list_filter = ('product_type', 'status', 'created_at')
    search_fields = ('user__phone', 'user__full_name')

@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ('user', 'principal', 'amount_outstanding', 'status', 'disbursed_at', 'next_repayment_date')
    list_filter = ('status', 'disbursed_at', 'next_repayment_date')
    search_fields = ('user__phone', 'user__full_name')

@admin.register(LoanRepayment)
class LoanRepaymentAdmin(admin.ModelAdmin):
    list_display = ('loan', 'installment_number', 'amount_due', 'status', 'due_date', 'paid_at')
    list_filter = ('status', 'due_date', 'paid_at')
    search_fields = ('loan__user__phone', 'loan__user__full_name', 'transaction_ref')

@admin.register(SavingsGoal)
class SavingsGoalAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'target_amount', 'current_amount', 'status', 'target_date')
    list_filter = ('status', 'target_date')
    search_fields = ('user__phone', 'user__full_name', 'name')
