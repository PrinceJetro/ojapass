from django.urls import path
from django.views.generic import TemplateView

from .views import (
    ResolveBVNView, RegisterView, LoginView, LogoutView, UserProfileView, 
    SquadWebhookView, TransactionListView, CreatePaymentLinkView, 
    PaymentLinkCheckoutView, InitiateSquadPaymentView,
    VerifyPaymentView, MamatallyDashboardView, ProductListView, 
    ProductDetailView, SaleListView, OrderListView, OrderDetailView,
    StorefrontView, StorefrontCheckoutView, NotificationListView,
    LogRestockView, StockMovementListView,
    AjoGroupListView, AjoGroupDetailView, AjoJoinView, AjoContributeView, AjoDisbursementView, UserAjoHistoryView, FundWalletView,
    GigListView, GigMatchView, GigApplyView, GigStatusUpdateView, GigAcceptAndEscrowView, GigEscrowPaymentView,
    PayrollBatchView, ScoreNarrativeView, ScoreNarrativeAPIView, LoanDashboardView, LoanApplyView, LoanRepaymentView,
    SavingsGoalView, LenderDashboardView, GovernmentDashboardView
)

urlpatterns = [
    path('', TemplateView.as_view(template_name='index.html'), name='index'),
    path('onboarding/', RegisterView.as_view(), name='onboarding'),
    path('resolve-bvn/', ResolveBVNView.as_view(), name='resolve_bvn'),
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('squad-webhook/', SquadWebhookView.as_view(), name='squad_webhook'),
    path('transactions/', TransactionListView.as_view(), name='transaction_list'),
    path('payment-link/', CreatePaymentLinkView.as_view(), name='create_payment_link'),
    path('payment-link/checkout/<str:transaction_ref>/', PaymentLinkCheckoutView.as_view(), name='payment_link_checkout'),
    path('payment-link/initiate/<str:transaction_ref>/', InitiateSquadPaymentView.as_view(), name='initiate_payment_link'),
    path('payment-link/verify/<str:transaction_ref>/', VerifyPaymentView.as_view(), name='verify_payment'),
    
    # Mamatally Endpoints
    path('mamatally/dashboard/', MamatallyDashboardView.as_view(), name='mamatally_dashboard'),
    path('mamatally/products/', ProductListView.as_view(), name='mamatally_products'),
    path('mamatally/products/<int:pk>/', ProductDetailView.as_view(), name='mamatally_product_detail'),
    path('mamatally/sales/', SaleListView.as_view(), name='mamatally_sales'),
    path('mamatally/orders/', OrderListView.as_view(), name='mamatally_orders'),
    path('mamatally/orders/<int:pk>/', OrderDetailView.as_view(), name='mamatally_order_detail'),
    path('mamatally/restock/', LogRestockView.as_view(), name='mamatally_restock'),
    path('mamatally/movements/', StockMovementListView.as_view(), name='mamatally_movements'),
    
    # Storefront Endpoints
    path('mamatally/storefront/<str:phone>/', StorefrontView.as_view(), name='mamatally_storefront'),
    path('mamatally/storefront/<str:phone>/checkout/', StorefrontCheckoutView.as_view(), name='mamatally_storefront_checkout'),
    
    # Notifications
    path('notifications/', NotificationListView.as_view(), name='notification_list'),
    path('notifications/<int:pk>/mark-read/', NotificationListView.as_view(), name='notification_mark_read'),
    path('notifications/<int:pk>/', NotificationListView.as_view(), name='notification_detail'),
    
    # Gig Marketplace Endpoints
    path('gigs/', GigListView.as_view(), name='gig_list'),
    path('gigs/<int:pk>/match/', GigMatchView.as_view(), name='gig_match'),
    path('gigs/<int:pk>/apply/', GigApplyView.as_view(), name='gig_apply'),
    path('gigs/<int:pk>/status/', GigStatusUpdateView.as_view(), name='gig_status_update'),
    path('gigs/<int:pk>/accept/', GigAcceptAndEscrowView.as_view(), name='gig_accept_escrow'),
    path('gigs/<int:pk>/initiate-escrow-payment/', GigEscrowPaymentView.as_view(), name='gig_escrow_payment'),
    
    # Payroll
    path('mamatally/payroll/', PayrollBatchView.as_view(), name='mamatally_payroll'),
    
    # OjaScore
    path('ojascore-narrative/', ScoreNarrativeView.as_view(), name='ojascore_narrative'),
    path('api/ojascore-narrative/', ScoreNarrativeAPIView.as_view(), name='ojascore_narrative_api'),
    path('ajo/', AjoGroupListView.as_view(), name='ajo_list'),
    path('ajo/<int:pk>/', AjoGroupDetailView.as_view(), name='ajo_detail'),
    path('ajo/<int:pk>/join/', AjoJoinView.as_view(), name='ajo_join'),
    path('ajo/<int:pk>/contribute/', AjoContributeView.as_view(), name='ajo_contribute'),
    path('ajo/<int:pk>/disburse/', AjoDisbursementView.as_view(), name='ajo_disburse'),
    path('ajo/history/', UserAjoHistoryView.as_view(), name='ajo_history'),
    path('ajo/fund/', FundWalletView.as_view(), name='fund_wallet'),
    path('loans/', LoanDashboardView.as_view(), name='loans'),
    path('loans/apply/<int:offer_id>/', LoanApplyView.as_view(), name='loan_apply'),
    path('loans/<int:loan_id>/repay/', LoanRepaymentView.as_view(), name='loan_repay'),
    path('savings/', SavingsGoalView.as_view(), name='savings_goals'),
    
    # Institution / Government Dashboards
    path('institution/lender/', LenderDashboardView.as_view(), name='lender_dashboard'),
    path('institution/gov/', GovernmentDashboardView.as_view(), name='gov_dashboard'),
]
