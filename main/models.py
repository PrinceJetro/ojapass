from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

class OjaUserManager(BaseUserManager):
    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError('The Phone Number must be set')
        user = self.model(phone=phone, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(phone, password, **extra_fields)

class OjaUser(AbstractBaseUser, PermissionsMixin):
    phone = models.CharField(max_length=15, unique=True)
    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    dob = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=10, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    bvn = models.CharField(max_length=11, blank=True, null=True)
    lga = models.CharField(max_length=100, blank=True, null=True, default='Surulere')
    
    ROLE_CHOICES = [
        ('trader', 'Trader'),
        ('seeker', 'Seeker'),
        ('both', 'Both'),
        ('lender', 'Lender'),
        ('gov', 'Government'),
    ]
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='trader')
    
    ojapass_id = models.CharField(max_length=20, blank=True, null=True)
    ojapass_score = models.IntegerField(default=0)
    ojapass_narrative = models.TextField(blank=True, null=True)
    virtual_account_number = models.CharField(max_length=20, blank=True, null=True)
    bank_name = models.CharField(max_length=50, default='GTBank')
    
    # Business Fields
    business_name = models.CharField(max_length=255, blank=True, null=True)
    trade_category = models.CharField(max_length=100, blank=True, null=True)
    years_in_business = models.IntegerField(default=0)
    daily_sales = models.CharField(max_length=50, blank=True, null=True)
    
    # Seeker/Worker Fields
    skills = models.CharField(max_length=255, blank=True, null=True) # comma separated skills
    bio = models.TextField(blank=True, null=True)
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    
    objects = OjaUserManager()

    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = ['full_name']

    def __str__(self):
        return self.phone

class OjaTransaction(models.Model):
    user = models.ForeignKey(OjaUser, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_reference = models.CharField(max_length=100, unique=True)
    gateway_reference = models.CharField(max_length=100, blank=True, null=True)
    sender_name = models.CharField(max_length=255, blank=True, null=True)
    sender_bank = models.CharField(max_length=100, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Metadata for OjaScore signals
    transaction_type = models.CharField(max_length=20, default='inflow') # inflow, outflow
    status = models.CharField(max_length=20, default='success')
    
    def __str__(self):
        return f"{self.user.phone} - {self.amount} ({self.status})"

class PaymentLink(models.Model):
    user = models.ForeignKey(OjaUser, on_delete=models.CASCADE, related_name='payment_links')
    transaction_ref = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    checkout_url = models.URLField(blank=True, null=True) # Remote Squad URL
    status = models.CharField(max_length=20, default='pending') # pending, paid, expired
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.transaction_ref} - {self.amount} ({self.status})"


class Product(models.Model):
    user = models.ForeignKey(OjaUser, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=255)
    quantity_in_stock = models.IntegerField(default=0)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    category = models.CharField(max_length=100, blank=True, null=True)
    low_stock_threshold = models.IntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.quantity_in_stock})"

    @property
    def profit(self):
        return self.selling_price - self.cost_price
    
    @property
    def margin(self):
        if self.cost_price > 0:
            return (self.profit / self.cost_price) * 100
        return 0

class PaymentLinkItem(models.Model):
    payment_link = models.ForeignKey(PaymentLink, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    price_at_time = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

class Sale(models.Model):
    user = models.ForeignKey(OjaUser, on_delete=models.CASCADE, related_name='sales')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales')
    quantity = models.IntegerField(default=1)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    payment_method = models.CharField(max_length=50, default='squad')
    transaction_ref = models.CharField(max_length=100, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Sale {self.transaction_ref or self.id} - {self.amount}"

class Order(models.Model):
    user = models.ForeignKey(OjaUser, on_delete=models.CASCADE, related_name='store_orders')
    customer_name = models.CharField(max_length=255)
    customer_phone = models.CharField(max_length=15, blank=True, null=True)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    quantity = models.IntegerField(default=1)
    status = models.CharField(max_length=20, default='pending') # pending, confirmed, fulfilled, paid
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order #{self.id} - {self.customer_name}"

class Gig(models.Model):
    employer = models.ForeignKey(OjaUser, on_delete=models.CASCADE, related_name='gigs_posted', null=True)
    worker = models.ForeignKey(OjaUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='gigs_taken')
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    skills_needed = models.CharField(max_length=255, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    date_time = models.DateTimeField(blank=True, null=True)
    duration = models.CharField(max_length=100, blank=True, null=True)
    pay_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    number_of_people = models.IntegerField(default=1)
    
    # Escrow fields
    escrow_transaction_ref = models.CharField(max_length=100, null=True, blank=True)
    escrow_paid = models.BooleanField(default=False)
    escrow_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    status = models.CharField(max_length=20, default='open') # open, matched, in_progress, completed, cancelled, paid
    
    # Lifecycle Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    matched_at = models.DateTimeField(blank=True, null=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    # Rating & Feedback
    rating = models.IntegerField(blank=True, null=True) # 1-5
    review = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.title} ({self.status})"

class GigApplication(models.Model):
    gig = models.ForeignKey(Gig, on_delete=models.CASCADE, related_name='applications')
    seeker = models.ForeignKey(OjaUser, on_delete=models.CASCADE, related_name='gig_applications')
    status = models.CharField(max_length=20, default='applied') # applied, shortlisted, rejected, accepted
    applied_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('gig', 'seeker')

    def __str__(self):
        return f"{self.seeker.full_name} -> {self.gig.title}"

class Notification(models.Model):
    user = models.ForeignKey(OjaUser, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notification for {self.user.full_name}: {self.message}"

class StockMovement(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='movements')
    user = models.ForeignKey(OjaUser, on_delete=models.CASCADE, related_name='stock_movements')
    movement_type = models.CharField(max_length=20) # restock, sale, adjustment, spoilage
    quantity = models.IntegerField() # positive for addition, negative for deduction
    reason = models.CharField(max_length=255, blank=True, null=True)
    supplier_name = models.CharField(max_length=255, blank=True, null=True)
    cost_paid = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.name} - {self.movement_type} ({self.quantity})"

class OjaScoreHistory(models.Model):
    user = models.ForeignKey(OjaUser, on_delete=models.CASCADE, related_name='score_history')
    score = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Store the individual signals at the time of calculation
    # to understand what caused the score
    frequency_score = models.FloatField(default=0)
    consistency_score = models.FloatField(default=0)
    diversity_score = models.FloatField(default=0)
    repayment_score = models.FloatField(default=0)
    tenure_score = models.FloatField(default=0)
    
    turnover_score = models.FloatField(default=0)
    restock_score = models.FloatField(default=0)
    fulfillment_score = models.FloatField(default=0)
    gig_score = models.FloatField(default=0)
    rating_score = models.FloatField(default=0)

    def __str__(self):
        return f"{self.user.phone} - Score: {self.score} at {self.timestamp.date()}"

class AjoGroup(models.Model):
    FREQUENCY_CHOICES = [('weekly', 'Weekly'), ('biweekly', 'Bi-Weekly'), ('monthly', 'Monthly')]
    STATUS_CHOICES = [('active', 'Active'), ('completed', 'Completed'), ('paused', 'Paused')]

    name = models.CharField(max_length=100)
    creator = models.ForeignKey(OjaUser, on_delete=models.CASCADE, related_name='created_ajo_groups')
    contribution_amount = models.DecimalField(max_digits=10, decimal_places=2)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    max_members = models.IntegerField(default=10)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    current_cycle = models.IntegerField(default=1)  # which cycle we're on
    current_beneficiary_index = models.IntegerField(default=0)  # whose turn it is
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - ₦{self.contribution_amount} {self.frequency}"


class AjoMembership(models.Model):
    group = models.ForeignKey(AjoGroup, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(OjaUser, on_delete=models.CASCADE, related_name='ajo_memberships')
    rotation_order = models.IntegerField()  # position in the rotation — who collects when
    joined_at = models.DateTimeField(auto_now_add=True)
    cycles_completed = models.IntegerField(default=0)
    cycles_defaulted = models.IntegerField(default=0)
    total_contributed = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_received = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        unique_together = ('group', 'user')
        ordering = ['rotation_order']

    def __str__(self):
        return f"{self.user.full_name} in {self.group.name} (position {self.rotation_order})"


class AjoCycle(models.Model):
    STATUS_CHOICES = [('open', 'Open'), ('collecting', 'Collecting'), ('disbursed', 'Disbursed'), ('defaulted', 'Defaulted')]

    group = models.ForeignKey(AjoGroup, on_delete=models.CASCADE, related_name='cycles')
    cycle_number = models.IntegerField()
    beneficiary = models.ForeignKey(OjaUser, on_delete=models.CASCADE, related_name='ajo_beneficiary_cycles')
    expected_amount = models.DecimalField(max_digits=10, decimal_places=2)  # contribution * members
    collected_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    due_date = models.DateTimeField()
    disbursed_at = models.DateTimeField(null=True, blank=True)
    transaction_ref = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AjoContribution(models.Model):
    STATUS_CHOICES = [('pending', 'Pending'), ('paid', 'Paid'), ('defaulted', 'Defaulted')]

    cycle = models.ForeignKey(AjoCycle, on_delete=models.CASCADE, related_name='contributions')
    member = models.ForeignKey(OjaUser, on_delete=models.CASCADE, related_name='ajo_contributions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_link = models.CharField(max_length=500, null=True, blank=True)
    transaction_ref = models.CharField(max_length=100, null=True, blank=True, unique=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class LoanOffer(models.Model):
    """Generated automatically when user hits score threshold"""
    PRODUCT_CHOICES = [
        ('savings_goal', 'Savings Goal'),
        ('nano_loan', 'Nano Loan'),
        ('working_capital', 'Working Capital Loan'),
        ('credit_line', 'Merchant Credit Line'),
        ('micro_insurance', 'Micro Insurance'),
    ]
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('applied', 'Applied'),
        ('approved', 'Approved'),
        ('disbursed', 'Disbursed'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ]

    user = models.ForeignKey(OjaUser, on_delete=models.CASCADE, related_name='loan_offers')
    product_type = models.CharField(max_length=30, choices=PRODUCT_CHOICES)
    offer_amount = models.DecimalField(max_digits=12, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)  # % per month
    tenure_months = models.IntegerField(default=3)
    monthly_repayment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    avg_monthly_turnover = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    oja_score_at_offer = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    applied_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.full_name} - {self.product_type} - ₦{self.offer_amount} ({self.status})"


class Loan(models.Model):
    """Active loan after approval and disbursement"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('defaulted', 'Defaulted'),
        ('restructured', 'Restructured'),
    ]

    user = models.ForeignKey(OjaUser, on_delete=models.CASCADE, related_name='loans')
    offer = models.OneToOneField(LoanOffer, on_delete=models.CASCADE, related_name='loan')
    principal = models.DecimalField(max_digits=12, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    tenure_months = models.IntegerField()
    monthly_repayment = models.DecimalField(max_digits=12, decimal_places=2)
    total_repayable = models.DecimalField(max_digits=12, decimal_places=2)
    amount_repaid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_outstanding = models.DecimalField(max_digits=12, decimal_places=2)
    disbursement_ref = models.CharField(max_length=100, null=True, blank=True)
    disbursed_at = models.DateTimeField(null=True, blank=True)
    next_repayment_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.full_name} - ₦{self.principal} ({self.status})"


class LoanRepayment(models.Model):
    """Individual repayment installment"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('missed', 'Missed'),
        ('partial', 'Partial'),
    ]

    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='repayments')
    installment_number = models.IntegerField()
    amount_due = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    due_date = models.DateField()
    paid_at = models.DateTimeField(null=True, blank=True)
    transaction_ref = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    def __str__(self):
        return f"Loan {self.loan.id} - Installment {self.installment_number} ({self.status})"


class SavingsGoal(models.Model):
    """Savings goal — unlocked at score 31+"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('withdrawn', 'Withdrawn'),
    ]

    user = models.ForeignKey(OjaUser, on_delete=models.CASCADE, related_name='savings_goals')
    name = models.CharField(max_length=255)  # e.g. "New Generator"
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    current_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    frequency = models.CharField(max_length=20, default='weekly')
    contribution_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    target_date = models.DateField(null=True, blank=True)

    @property
    def progress_percent(self):
        if self.target_amount > 0:
            return min(float(self.current_amount / self.target_amount * 100), 100)
        return 0

    def __str__(self):
        return f"{self.user.full_name} - {self.name} ({self.progress_percent:.0f}%)"