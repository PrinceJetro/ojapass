# OjaPass Technical Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Features](#features)
4. [User Flows](#user-flows)
5. [Database Models](#database-models)
6. [URL Configuration](#url-configuration)
7. [Views and Controllers](#views-and-controllers)
8. [Services and Helpers](#services-and-helpers)
9. [Templates](#templates)
10. [API Integrations](#api-integrations)
11. [Security](#security)
12. [Deployment](#deployment)

---

## System Overview

OjaPass is a Django-based financial inclusion platform that serves Nigeria's informal economy. The system provides alternative credit scoring, micro-loans, gig marketplace, digital savings groups (Ajo), and business tools for informal traders and gig workers.

**Tech Stack:**
- **Backend:** Django 5.0.3 (Python 3.11+)
- **Frontend:** HTML, CSS (TailwindCSS), Vanilla JavaScript
- **Database:** SQLite (Development), PostgreSQL (Production)
- **External APIs:** BMONI (banking), Google Gemini (AI)
- **Deployment:** Render

**Core Philosophy:**
- Alternative credit scoring using real transaction data
- Embedded finance via BMONI API
- AI-powered matching and analytics
- Mobile-first design for informal economy users

---

## Architecture

### Project Structure

```
ajopass/
├── ajopass/                    # Django project settings
│   ├── settings.py            # Configuration (API keys, URLs)
│   ├── urls.py                # Root URL routing
│   └── wsgi.py                # WSGI configuration
├── main/                       # Main Django app
│   ├── models.py              # Database models
│   ├── views/                 # Request handlers
│   │   ├── auth_views.py      # Authentication (register, login, profile)
│   │   ├── merchant_views.py  # Merchant dashboard, inventory
│   │   ├── gig_views.py       # Gig marketplace
│   │   ├── ajo_views.py       # Ajo savings groups
│   │   ├── loan_views.py      # Loan applications
│   │   ├── payment_views.py   # Payment processing
│   │   └── storefront_views.py # Storefront orders
│   ├── services/              # Business logic
│   │   ├── bmoni_service.py   # BMONI API integration
│   │   ├── crypto_utils.py    # Cryptographic operations
│   │   ├── gemini_service.py  # AI integration
│   │   ├── oja_score.py       # Credit scoring engine
│   │   ├── loan_engine.py     # Loan calculations
│   │   └── analytics.py       # Business analytics
│   ├── templates/             # HTML templates
│   ├── management/commands/   # Django management commands
│   └── migrations/            # Database migrations
├── templates/                 # Base templates
└── static/                    # Static assets
```

### Data Flow

```
User → Registration → BMONI User Creation → Wallet Creation → VBA Linking
                                                              ↓
Dashboard ← Transaction History ← Webhook Confirmation ← Payment Processing
```

---

## Features

### 1. User Registration & Onboarding

**Purpose:** Create new users with BMONI banking integration

**Flow:**
1. User submits registration form (phone, email, BVN, personal details)
2. System validates required fields
3. Creates local user record with mock virtual account
4. Attempts BMONI user creation via API
5. Handles 409 conflicts by finding existing BMONI users
6. Creates Ethereum wallet with cryptographic signing
7. Initiates Nigerian onboarding for VBA
8. Fetches deposit account details
9. Updates user with real BMONI virtual account

**URL:** `/register/` (POST)

**View:** `RegisterView` in `auth_views.py`

**Key Functions:**
- `create_user()` - BMONI user creation
- `create_wallet_simple()` - Wallet generation with EIP-191 signing
- `start_nigeria_onboarding()` - Nigerian rail activation
- `get_deposit_accounts()` - Fetch virtual bank account

**Template:** `onboarding.html`

**Helper Services:**
- `BMONIService.create_user()` - API integration
- `ServerWalletManager.create_wallet_for_user()` - Ethereum wallet generation
- `EthereumWallet.sign_challenge()` - Cryptographic signing

---

### 2. Authentication System

**Purpose:** PIN-based login with session management

**Features:**
- Phone number + PIN authentication
- Session management via Django auth
- Role-based access control (trader, seeker, employer, lender)
- Remember me functionality

**URLs:**
- `/login/` (POST) - Login
- `/logout/` (GET) - Logout
- `/profile/` (GET) - User profile

**Views:** `LoginView`, `LogoutView`, `ProfileView` in `auth_views.py`

**Template:** `login.html`, `profile.html`

**Security:**
- PIN validation (4-6 digits)
- Session timeout
- CSRF protection

---

### 3. OjaScore (Alternative Credit Scoring)

**Purpose:** Calculate credit scores from transaction data without formal documents

**Algorithm:**
- Analyzes transaction history (inflows/outflows)
- Considers sales velocity and consistency
- Factors in repayment history
- Updates in real-time with each transaction
- Uses Bayesian updating for score refinement

**Service:** `oja_score.py`

**Key Functions:**
- `calculate_ojascore(user)` - Main scoring algorithm
- `get_tier(score)` - Convert score to tier (Bronze, Silver, Gold, Platinum)
- `recalculate_ojascore(user_id)` - Force recalculation

**Factors:**
- Transaction frequency
- Average transaction amount
- Payment consistency
- Account age
- Debt-to-income ratio

**Score Range:**
- 0-300: Bronze (Limited access)
- 301-600: Silver (Basic services)
- 601-800: Gold (Premium services)
- 801-1000: Platinum (VIP services)

---

### 4. Loan System

**Purpose:** Micro-loans based on OjaScore, not collateral

**Flow:**
1. User applies for loan with amount and duration
2. System calculates OjaScore
3. AI determines loan eligibility and interest rate
4. Loan offer generated based on turnover and score
5. User accepts offer
6. Funds disbursed via BMONI withdrawal
7. Repayment tracked via transactions
8. OjaScore updated based on repayment

**URLs:**
- `/loans/` (GET) - Loan dashboard
- `/loans/apply/` (POST) - Loan application

**View:** `LoanView` in `loan_views.py`

**Service:** `loan_engine.py`

**Key Functions:**
- `calculate_eligibility(user)` - Determine loan eligibility
- `generate_offer(user, amount)` - AI-powered offer generation
- `process_disbursement(loan)` - BMONI withdrawal
- `track_repayment(loan)` - Repayment monitoring

**Template:** `loans.html`

**Loan Parameters:**
- Amount: ₦5,000 - ₦500,000
- Duration: 7 - 90 days
- Interest: 5% - 25% (based on OjaScore)
- Repayment: Weekly or lump sum

---

### 5. Gig Marketplace

**Purpose:** Connect gig seekers with employers with escrow protection

**Features:**
- Gig posting by employers
- Gig application by seekers
- AI-powered matching (Gemini)
- Escrow system for payments
- Work completion verification
- Review and rating system
- Payout processing

**URLs:**
- `/gig-marketplace/` (GET) - Browse gigs
- `/post-gig/` (GET/POST) - Post new gig
- `/apply-gig/<id>/` (POST) - Apply for gig
- `/gig-status/<id>/` (POST) - Update gig status
- `/hiring-marketplace/` (GET) - Employer view
- `/seeker-marketplace/` (GET) - Seeker view

**Views:** `GigListView`, `PostGigView`, `ApplyGigView`, `GigStatusView` in `gig_views.py`

**Service:** `gemini_service.py`

**Key Functions:**
- `match_gigs(seeker)` - AI-powered gig matching
- `create_escrow(gig)` - Escrow creation
- `release_payment(gig)` - Payout processing
- `submit_review(gig)` - Review submission

**Templates:** `gigmarketplace.html`, `postgig.html`, `hiring_marketplace.html`, `seeker_marketplace.html`

**Gig Status Flow:**
- `open` → Available for applications
- `matched` → Worker selected, awaiting escrow
- `pending_escrow` → Escrow funded, awaiting work start
- `in_progress` → Work in progress
- `completed` → Work done, awaiting payout
- `paid` → Payout completed

---

### 6. Ajo Savings Groups

**Purpose:** Digital version of traditional Nigerian rotating savings groups

**Features:**
- Group creation and management
- Member onboarding
- Automated contribution collection
- Rotation cycle management
- Payout automation
- Default handling with penalties
- Group analytics

**URLs:**
- `/ajo-create/` (GET/POST) - Create Ajo group
- `/ajo-dashboard/` (GET) - Group dashboard
- `/ajo-join/<id>/` (POST) - Join group
- `/ajo-contribute/<id>/` (POST) - Make contribution

**Views:** `AjoCreateView`, `AjoDashboardView`, `AjoJoinView`, `AjoContributeView` in `ajo_views.py`

**Management Command:** `process_ajo` - Automated contribution collection

**Templates:** `ajocreate.html`, `ajodashboard.html`, `ajogroupdetails.html`

**Ajo Parameters:**
- Group size: 2-20 members
- Contribution amount: ₦1,000 - ₦100,000
- Cycle duration: Weekly, bi-weekly, monthly
- Rotation order: Random or custom

---

### 7. Merchant Dashboard (Mamatally)

**Purpose:** Business management tools for traders

**Features:**
- Inventory management
- Sales tracking
- Revenue analytics
- Low stock alerts
- Product management
- Transaction history
- BMONI wallet balance
- Virtual account display

**URLs:**
- `/mamatally/` (GET) - Main dashboard
- `/products/` (GET/POST) - Product management
- `/inventory/` (GET) - Inventory view

**View:** `MamatallyDashboardView` in `merchant_views.py`

**Service:** `analytics.py`, `ai_analytics.py`

**Key Functions:**
- `get_sales_trends(user)` - Sales analytics
- `generate_restock_alerts(user)` - Inventory optimization
- `AIAnalytics.generate_dashboard_report()` - AI insights

**Template:** `mamatally.html`, `productsinventry.html`

**Dashboard Metrics:**
- Today's sales
- Monthly revenue
- Active products
- Low stock items
- Wallet balance
- OjaScore trend

---

### 8. Payment Processing

**Purpose:** Handle payments via BMONI virtual accounts

**Flow:**
1. User initiates payment (checkout, gig escrow, etc.)
2. System generates payment link with reference
3. BMONI deposit account details displayed
4. User transfers funds to virtual account
5. BMONI webhook confirms transaction
6. System updates local ledger
7. Inventory/escrow updated
8. Notifications sent

**URLs:**
- `/payment-link/checkout/<ref>/` (GET) - Checkout page
- `/payment-link/verify/<ref>/` (POST) - Payment verification
- `/bmoni/webhook/` (POST) - BMONI webhook

**Views:** `InitiateBmoniDepositView`, `VerifyPaymentView`, `BMONIWebhookView` in `payment_views.py`

**Service:** `bmoni_service.py`

**Key Functions:**
- `get_deposit_accounts(user_id, currency)` - Fetch VBA
- `initiate_nigeria_withdrawal()` - Process withdrawals
- `submit_proposal_signature()` - Sign withdrawal proposals
- Webhook HMAC signature verification

**Templates:** `payment_checkout.html`, `payment_success.html`, `payment_pending.html`, `payment_failed.html`

**Payment Status:**
- `pending` - Awaiting payment
- `processing` - Payment received, processing
- `paid` - Payment confirmed
- `failed` - Payment failed
- `expired` - Payment link expired

---

### 9. Storefront

**Purpose:** E-commerce functionality for merchants

**Features:**
- Product catalog display
- Shopping cart
- Order processing
- Payment link generation
- Stock management
- Order tracking

**URLs:**
- `/storefront/<username>/` (GET) - Public storefront
- `/storefront/order/` (POST) - Place order

**View:** `StorefrontView` in `storefront_views.py`

**Template:** `customerstorefront.html`

**Order Flow:**
1. Customer browses storefront
2. Adds items to cart
3. Submits order with customer details
4. Payment link generated
5. Customer pays via BMONI VBA
6. Order confirmed, stock decremented
7. Notifications sent

---

### 10. BMONI Integration

**Purpose:** Embedded banking infrastructure

**Features:**
- User creation with KYC
- Smart wallet generation
- Virtual bank account (VBA) provisioning
- Nigerian onboarding
- Deposit account management
- Withdrawal processing
- Webhook handling

**Service:** `bmoni_service.py`

**Key Endpoints:**
- `POST /v1/users` - Create user
- `POST /v1/users/{id}/smart-wallets/owner-proof-challenges` - Challenge generation
- `POST /v1/users/{id}/smart-wallets/create-managed` - Wallet creation
- `POST /v1/users/{id}/onboarding/start-nigeria` - Nigerian onboarding
- `GET /v1/users/{id}/bank-accounts/deposit-accounts/{currency}` - Get VBA
- `POST /v1/users/{id}/withdrawal/wallet/nigeria` - Initiate withdrawal
- `POST /v1/users/{id}/smart-wallets/proposals/{id}/sign` - Sign proposal

**Cryptographic Operations:**
- Ethereum wallet generation (SECP256k1)
- EIP-191 personal_sign format
- Keccak-256 hashing
- Recovery ID calculation for signatures

**Service:** `crypto_utils.py`

**Key Functions:**
- `EthereumWallet.generate_wallet()` - Generate Ethereum wallet
- `EthereumWallet.sign_message()` - EIP-191 signing
- `ServerWalletManager.create_wallet_for_user()` - Server-side wallet generation

---

### 11. AI Integration (Gemini)

**Purpose:** AI-powered matching and analytics

**Features:**
- Gig seeker-employer matching
- Business insights generation
- Loan offer optimization
- Sales trend analysis

**Service:** `gemini_service.py`

**Key Functions:**
- `match_gigs(seeker_profile, available_gigs)` - Gig matching
- `generate_business_insights(user_data)` - Analytics
- `optimize_loan_offer(user_profile)` - Loan pricing

**Matching Criteria:**
- Skills and experience
- Location proximity
- OjaScore compatibility
- Availability
- Rate expectations

---

### 12. Management Commands

**Purpose:** Administrative and maintenance tasks

**Available Commands:**
- `python manage.py list_bmoni_users` - List BMONI sync status
- `python manage.py check_deposit_account <phone>` - Check user's VBA
- `python manage.py sync_deposit_accounts` - Sync all VBAs
- `python manage.py check_wallet_balance <phone>` - Check wallet balance
- `python manage.py delete_all_users --confirm` - Delete all users
- `python manage.py delete_bmoni_user <phone>` - Delete user from BMONI
- `python manage.py process_ajo` - Process Ajo contributions
- `python manage.py confirm_payment <ref>` - Manual payment confirmation

---

## User Flows

### Registration Flow

```
1. User accesses /register/
   ↓
2. Fills registration form (name, phone, email, BVN, PIN, etc.)
   ↓
3. System validates required fields
   ↓
4. Checks for duplicate phone number
   ↓
5. Creates local user record with mock VBA
   ↓
6. Attempts BMONI user creation
   ├─ Success: Store bmoni_user_id
   └─ 409 Conflict: Find existing user, link to local record
   ↓
7. Generate Ethereum wallet
   ├─ Create private key
   ├─ Derive public key
   └─ Calculate address
   ↓
8. Request owner-proof challenge from BMONI
   ↓
9. Sign challenge with EIP-191 signature
   ↓
10. Create managed wallet with signature
   ↓
11. Start Nigerian onboarding with BVN
   ↓
12. Fetch deposit accounts (VBA)
   ↓
13. Update user with real VBA details
   ↓
14. Log user in
   ↓
15. Redirect to dashboard
```

### Loan Application Flow

```
1. User accesses /loans/
   ↓
2. Views current OjaScore and eligibility
   ↓
3. Enters desired loan amount and duration
   ↓
4. System calculates eligibility
   ├─ Analyzes transaction history
   ├─ Calculates OjaScore
   └─ Determines max loan amount
   ↓
5. AI generates loan offer
   ├─ Interest rate based on score
   ├─ Repayment schedule
   └─ Fees and charges
   ↓
6. User reviews and accepts offer
   ↓
7. System creates loan record
   ↓
8. Initiates BMONI withdrawal
   ├─ Create withdrawal proposal
   ├─ Generate signing payload
   └─ Submit signature
   ↓
9. Funds transferred to user's bank account
   ↓
10. Loan marked as disbursed
   ↓
11. Repayment tracking begins
   ↓
12. OjaScore updated based on repayment
```

### Gig Marketplace Flow

**Employer Flow:**
```
1. Employer posts gig with details
   ├─ Title, description
   ├─ Skills required
   ├─ Location
   ├─ Pay rate
   └─ Deadline
   ↓
2. System generates gig reference
   ↓
3. Gig listed in marketplace
   ↓
4. Seekers apply
   ↓
5. Employer reviews applications
   ↓
6. Employer selects seeker
   ↓
7. System creates escrow payment link
   ↓
8. Employer funds escrow
   ↓
9. Gig status: matched → pending_escrow
   ↓
10. Worker notified
   ↓
11. Worker starts work
   ↓
12. Gig status: in_progress
   ↓
13. Worker completes work
   ↓
14. Employer confirms completion
   ↓
15. System initiates payout
   ├─ Create withdrawal proposal
   ├─ Sign with employer wallet
   └─ Transfer to worker's bank
   ↓
16. Gig status: paid
   ↓
17. Both parties submit reviews
```

**Seeker Flow:**
```
1. Seeker browses available gigs
   ↓
2. AI recommends matching gigs
   ↓
3. Seeker applies to gigs
   ↓
4. Waits for selection
   ↓
5. Notified when selected
   ↓
6. Accepts gig assignment
   ↓
7. Performs work
   ↓
8. Submits completion
   ↓
9. Awaits payment
   ↓
10. Receives payment
   ↓
11. Submits review
```

### Ajo Group Flow

```
1. User creates Ajo group
   ├─ Group name
   ├─ Contribution amount
   ├─ Cycle duration
   └─ Max members
   ↓
2. Group created with user as admin
   ↓
3. Admin invites members
   ↓
4. Members join group
   ↓
5. First cycle starts
   ↓
6. Members contribute on schedule
   ├─ Auto-debit from wallet
   └─ Manual contribution option
   ↓
7. System tracks contributions
   ↓
8. Cycle completes
   ↓
9. Payout to rotation winner
   ├─ BMONI withdrawal
   └─ Transfer to winner's bank
   ↓
10. Next cycle starts
   ↓
11. Repeat until all members have received payout
```

---

## Database Models

### OjaUser (Custom User Model)

**Purpose:** Extended user model with financial attributes

**Fields:**
- `phone` - Phone number (unique)
- `email` - Email address
- `full_name` - Full name
- `pin` - PIN for authentication
- `dob` - Date of birth
- `gender` - Gender
- `address` - Physical address
- `bvn` - Bank Verification Number
- `role` - User role (trader, seeker, employer, lender)
- `ojapass_id` - Unique OjaPass identifier
- `ojapass_score` - OjaScore (0-1000)
- `virtual_account_number` - BMONI VBA
- `bank_name` - Bank name for VBA
- `wallet_balance` - Local wallet balance
- `bmoni_user_id` - BMONI user ID
- `smart_wallet_id` - BMONI smart wallet ID
- `bmoni_sync_status` - Sync status (pending, synced, failed)
- `bmoni_sync_attempts` - Number of sync attempts
- `bmoni_sync_error` - Last sync error
- `business_name` - Business name (for merchants)
- `trade_category` - Trade category
- `years_in_business` - Years in business
- `daily_sales` - Average daily sales
- `skills` - Skills (for gig workers)
- `bio` - User bio
- `lga` - Local Government Area

**Methods:**
- `calculate_ojascore()` - Calculate credit score
- `update_wallet_balance()` - Update wallet balance

---

### Product

**Purpose:** Inventory items for merchants

**Fields:**
- `user` - Owner (Foreign Key to OjaUser)
- `name` - Product name
- `description` - Product description
- `selling_price` - Selling price
- `cost_price` - Cost price
- `quantity_in_stock` - Current stock
- `category` - Product category
- `image` - Product image
- `created_at` - Creation timestamp

**Methods:**
- `decrement_stock(quantity)` - Reduce stock
- `increment_stock(quantity)` - Increase stock

---

### Sale

**Purpose:** Sales records

**Fields:**
- `user` - Seller (Foreign Key to OjaUser)
- `product` - Product sold (Foreign Key to Product)
- `quantity` - Quantity sold
- `amount` - Total amount
- `description` - Sale description
- `payment_method` - Payment method (bmoni)
- `transaction_ref` - Transaction reference
- `created_at` - Sale timestamp

---

### OjaTransaction

**Purpose:** Financial transactions

**Fields:**
- `user` - User (Foreign Key to OjaUser)
- `amount` - Transaction amount
- `transaction_type` - Type (inflow, outflow)
- `status` - Status (pending, success, failed)
- `transaction_reference` - Reference number
- `gateway_reference` - Gateway reference
- `sender_name` - Sender name
- `sender_bank` - Sender bank
- `timestamp` - Transaction timestamp
- `description` - Description

---

### Loan

**Purpose:** Loan records

**Fields:**
- `user` - Borrower (Foreign Key to OjaUser)
- `amount` - Loan amount
- `interest_rate` - Interest rate
- `duration_days` - Loan duration
- `status` - Status (pending, approved, disbursed, repaid, defaulted)
- `disbursement_date` - Disbursement date
- `repayment_date` - Repayment date
- `created_at` - Creation timestamp

---

### Gig

**Purpose:** Gig listings

**Fields:**
- `employer` - Employer (Foreign Key to OjaUser)
- `worker` - Assigned worker (Foreign Key to OjaUser)
- `title` - Gig title
- `description` - Description
- `skills_required` - Required skills
- `location` - Location
- `pay_rate` - Pay rate
- `status` - Status (open, matched, pending_escrow, in_progress, completed, paid)
- `escrow_transaction_ref` - Escrow reference
- `escrow_amount` - Escrow amount
- `rating` - Worker rating
- `review` - Review text
- `created_at` - Creation timestamp
- `completed_at` - Completion timestamp

---

### AjoGroup

**Purpose:** Ajo savings groups

**Fields:**
- `name` - Group name
- `admin` - Group admin (Foreign Key to OjaUser)
- `contribution_amount` - Contribution amount
- `cycle_duration_days` - Cycle duration
- `max_members` - Maximum members
- `current_cycle` - Current cycle number
- `status` - Status (active, completed)
- `created_at` - Creation timestamp

---

### AjoCycle

**Purpose:** Ajo rotation cycles

**Fields:**
- `group` - Group (Foreign Key to AjoGroup)
- `cycle_number` - Cycle number
- `start_date` - Start date
- `end_date` - End date
- `winner` - Cycle winner (Foreign Key to OjaUser)
- `collected_amount` - Total collected
- `status` - Status (active, completed, defaulted)

---

### AjoContribution

**Purpose:** Individual contributions

**Fields:**
- `cycle` - Cycle (Foreign Key to AjoCycle)
- `user` - Contributor (Foreign Key to OjaUser)
- `amount` - Contribution amount
- `status` - Status (pending, paid, failed)
- `contribution_date` - Contribution date

---

### PaymentLink

**Purpose:** Payment links for transactions

**Fields:**
- `user` - User (Foreign Key to OjaUser)
- `transaction_ref` - Transaction reference
- `amount` - Amount
- `description` - Description
- `checkout_url` - Checkout URL
- `status` - Status (pending, paid, expired)
- `created_at` - Creation timestamp
- `paid_at` - Payment timestamp

---

### PaymentLinkItem

**Purpose:** Line items for payment links

**Fields:**
- `payment_link` - Payment link (Foreign Key to PaymentLink)
- `product` - Product (Foreign Key to Product)
- `quantity` - Quantity
- `price_at_time` - Price at time of order

---

### ScoreHistory

**Purpose:** OjaScore history tracking

**Fields:**
- `user` - User (Foreign Key to OjaUser)
- `score` - Score value
- `timestamp` - Timestamp

---

### Notification

**Purpose:** User notifications

**Fields:**
- `user` - User (Foreign Key to OjaUser)
- `message` - Notification message
- `is_read` - Read status
- `created_at` - Creation timestamp

---

## URL Configuration

### Root URLs (`ajopass/urls.py`)

```python
urlpatterns = [
    path('', views.LandingView.as_view(), name='landing'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('mamatally/', views.MamatallyDashboardView.as_view(), name='mamatally'),
    path('products/', views.ProductView.as_view(), name='products'),
    path('inventory/', views.InventoryView.as_view(), name='inventory'),
    path('loans/', views.LoanView.as_view(), name='loans'),
    path('gig-marketplace/', views.GigListView.as_view(), name='gig_marketplace'),
    path('post-gig/', views.PostGigView.as_view(), name='post_gig'),
    path('apply-gig/<int:gig_id>/', views.ApplyGigView.as_view(), name='apply_gig'),
    path('gig-status/<int:gig_id>/', views.GigStatusView.as_view(), name='gig_status'),
    path('hiring-marketplace/', views.HiringMarketplaceView.as_view(), name='hiring_marketplace'),
    path('seeker-marketplace/', views.SeekerMarketplaceView.as_view(), name='seeker_marketplace'),
    path('ajo-create/', views.AjoCreateView.as_view(), name='ajo_create'),
    path('ajo-dashboard/', views.AjoDashboardView.as_view(), name='ajo_dashboard'),
    path('ajo-join/<int:group_id>/', views.AjoJoinView.as_view(), name='ajo_join'),
    path('ajo-contribute/<int:cycle_id>/', views.AjoContributeView.as_view(), name='ajo_contribute'),
    path('payment-link/checkout/<str:ref>/', views.InitiateBmoniDepositView.as_view(), name='payment_checkout'),
    path('payment-link/verify/<str:ref>/', views.VerifyPaymentView.as_view(), name='payment_verify'),
    path('bmoni/webhook/', views.BMONIWebhookView.as_view(), name='bmoni_webhook'),
    path('bmoni-kyc/', views.BMONIKYCView.as_view(), name='bmoni_kyc'),
    path('storefront/<str:username>/', views.StorefrontView.as_view(), name='storefront'),
    path('storefront/order/', views.StorefrontOrderView.as_view(), name='storefront_order'),
    path('admin/', admin.site.urls),
]
```

---

## Views and Controllers

### Authentication Views (`auth_views.py`)

#### RegisterView
**Purpose:** Handle user registration with BMONI integration

**Methods:**
- `get(request)` - Render registration form
- `post(request)` - Process registration

**Key Logic:**
1. Validate required fields
2. Check for duplicate phone
3. Create local user with mock VBA
4. Attempt BMONI user creation
5. Handle 409 conflicts
6. Generate Ethereum wallet
7. Sign challenge with EIP-191
8. Create BMONI wallet
9. Start Nigerian onboarding
10. Fetch deposit accounts
11. Update user with real VBA
12. Log user in

**Response:** JSON with user details

---

#### LoginView
**Purpose:** Authenticate users with phone + PIN

**Methods:**
- `get(request)` - Render login form
- `post(request)` - Process login

**Key Logic:**
1. Validate phone and PIN
2. Authenticate user
3. Create session
4. Redirect to dashboard

**Response:** Redirect to dashboard or error

---

#### ProfileView
**Purpose:** Display user profile and transaction history

**Methods:**
- `get(request)` - Render profile

**Key Logic:**
1. Fetch user transactions
2. Calculate wallet balance
3. Get OjaScore tier
4. Fetch score history
5. Render profile with context

**Context:**
- User details
- Recent transactions
- Wallet balance
- Score tier
- Score history graph
- Products (for merchants)
- Active gigs (for seekers)

---

### Merchant Views (`merchant_views.py`)

#### MamatallyDashboardView
**Purpose:** Main dashboard for merchants

**Methods:**
- `get(request)` - Render dashboard

**Key Logic:**
1. Fetch user's products
2. Get recent sales
3. Calculate daily revenue
4. Check BMONI sync status
5. Check wallet existence
6. Link VBA if missing
7. Get sales trends
8. Generate restock alerts
9. Generate AI report
10. Render dashboard

**Context:**
- User details
- Inventory
- Recent sales
- Daily revenue list
- Sales trends
- Restock alerts
- AI report
- Virtual account details
- Wallet balance

---

### Gig Views (`gig_views.py`)

#### GigListView
**Purpose:** Browse available gigs

**Methods:**
- `get(request)` - Render gig list

**Key Logic:**
1. Fetch open gigs
2. Filter by location/skills if specified
3. Render gig marketplace

---

#### PostGigView
**Purpose:** Post new gig (employers)

**Methods:**
- `get(request)` - Render gig posting form
- `post(request)` - Process gig posting

**Key Logic:**
1. Validate gig details
2. Create gig record
3. Generate escrow reference
4. Create payment link
5. Render success

---

#### ApplyGigView
**Purpose:** Apply for gig (seekers)

**Methods:**
- `post(request, gig_id)` - Process application

**Key Logic:**
1. Check if gig exists
2. Create application record
3. Notify employer
4. Return success

---

#### GigStatusView
**Purpose:** Update gig status (employers)

**Methods:**
- `post(request, pk)` - Process status update

**Key Logic:**
1. Validate gig ownership
2. Update status based on action
3. Handle escrow funding
4. Handle payout processing
5. Create transactions
6. Send notifications
7. Update OjaScore

**Actions:**
- `started` - Mark work as started
- `completed` - Mark work as done, trigger payout
- `cancelled` - Cancel gig

---

### Ajo Views (`ajo_views.py`)

#### AjoCreateView
**Purpose:** Create new Ajo group

**Methods:**
- `get(request)` - Render creation form
- `post(request)` - Process group creation

**Key Logic:**
1. Validate group details
2. Create AjoGroup record
3. Create first AjoCycle
4. Add creator as member
5. Render success

---

#### AjoDashboardView
**Purpose:** View Ajo groups

**Methods:**
- `get(request)` - Render dashboard

**Key Logic:**
1. Fetch user's groups
2. Fetch active cycles
3. Calculate contribution status
4. Render dashboard

---

### Payment Views (`payment_views.py`)

#### InitiateBmoniDepositView
**Purpose:** Display BMONI deposit account for payment

**Methods:**
- `get(request, ref)` - Render checkout page

**Key Logic:**
1. Find payment link by reference
2. Fetch user's BMONI deposit account
3. Display account details
4. Render checkout page

**Context:**
- Payment link details
- BMONI account number
- Bank name
- Amount
- Description

---

#### VerifyPaymentView
**Purpose:** Manual payment verification (development)

**Methods:**
- `post(request, ref)` - Verify payment

**Key Logic:**
1. Find payment link
2. Update status to paid
3. Process order (if applicable)
4. Decrement inventory
5. Create transactions
6. Send notifications

---

#### BMONIWebhookView
**Purpose:** Handle BMONI webhooks

**Methods:**
- `post(request)` - Process webhook

**Key Logic:**
1. Verify HMAC signature
2. Parse webhook payload
3. Find payment link by reference
4. Update payment status
5. Process order
6. Create transactions
7. Update wallet balance
8. Send notifications

**Security:**
- HMAC signature verification
- Payload validation
- Idempotency handling

---

## Services and Helpers

### BMONIService (`bmoni_service.py`)

**Purpose:** BMONI API integration

**Key Methods:**

#### User Management
- `list_users(page, limit)` - List all users
- `find_user_by_email_or_phone(email, phone)` - Find existing user
- `create_user(user_data)` - Create new user
- `get_user(bmoni_user_id)` - Get user profile
- `delete_user(bmoni_user_id)` - Delete user

#### Wallet Management
- `request_owner_proof_challenge(user_id, currency, owner_address)` - Get challenge
- `create_managed_wallet(user_id, challenge_id, signature, owner_address)` - Create wallet
- `create_wallet_simple(user_id, currency)` - Simplified wallet creation
- `get_wallets(user_id)` - Get user wallets
- `get_balances(user_id)` - Get wallet balances
- `get_transactions(user_id, smart_wallet_id)` - Get transactions

#### Onboarding
- `get_onboarding_status(user_id)` - Get onboarding status
- `start_nigeria_onboarding(user_id, bvn, ngn_wallet_address)` - Activate Nigerian rail

#### KYC
- `get_kyc_options(user_id)` - Get KYC options
- `get_kyc_occupations(user_id, search)` - Get occupations
- `patch_kyc(user_id, payload)` - Submit KYC data
- `upload_kyc_document_identification(user_id, file, ...)` - Upload ID document
- `activate_kyc(user_id)` - Activate KYC

#### Bank Accounts
- `verify_nigerian_account(user_id, account_number, bank_code)` - Verify account
- `get_or_create_nigerian_withdrawal_account(...)` - Create withdrawal account
- `get_deposit_accounts(user_id, currency)` - Get deposit accounts
- `link_nigeria_vba(user_id, smart_wallet_id, bank_account_id)` - Link VBA
- `list_nigerian_banks(user_id)` - List supported banks

#### Withdrawals
- `initiate_nigeria_withdrawal(user_id, wallet_id, bank_account_id, amount)` - Initiate withdrawal
- `submit_proposal_signature(user_id, proposal_id, signature)` - Submit signature

#### HTTP Helpers
- `_get(url, timeout, retries, backoff)` - GET request with retry
- `_post(url, payload, timeout, retries, backoff)` - POST request with retry
- `_post_multipart(url, file, data, ...)` - Multipart POST
- `_error(url, exc)` - Error handling

---

### CryptoUtils (`crypto_utils.py`)

**Purpose:** Cryptographic operations for Ethereum wallets

**Key Classes:**

#### EthereumWallet
- `generate_private_key()` - Generate random private key
- `private_key_to_public_key(private_key_hex)` - Derive public key
- `public_key_to_address(public_key_bytes)` - Derive Ethereum address
- `generate_wallet()` - Generate complete wallet
- `sign_message(private_key_hex, message)` - EIP-191 signing
- `sign_challenge(private_key_hex, challenge_message)` - Sign BMONI challenge

#### ServerWalletManager
- `create_wallet_for_user()` - Generate wallet for user
- `sign_bmoni_challenge(private_key_hex, challenge_message)` - Sign challenge

**Cryptographic Details:**
- Curve: SECP256k1
- Signing: EIP-191 personal_sign
- Hashing: Keccak-256
- Signature: 65 bytes (r + s + v)
- Recovery ID: Calculated via public key recovery

---

### GeminiService (`gemini_service.py`)

**Purpose:** AI integration for matching and analytics

**Key Methods:**
- `match_gigs(seeker_profile, available_gigs)` - Match gigs to seekers
- `generate_business_insights(user_data)` - Generate business insights
- `optimize_loan_offer(user_profile)` - Optimize loan pricing

**AI Capabilities:**
- Natural language processing for gig descriptions
- Skill matching and compatibility scoring
- Location-based recommendations
- Behavioral pattern analysis

---

### OjaScore (`oja_score.py`)

**Purpose:** Alternative credit scoring engine

**Key Methods:**
- `calculate_ojascore(user)` - Calculate credit score
- `get_tier(score)` - Convert score to tier
- `recalculate_ojascore(user_id)` - Force recalculation

**Scoring Factors:**
- Transaction frequency (weight: 30%)
- Average transaction amount (weight: 20%)
- Payment consistency (weight: 25%)
- Account age (weight: 15%)
- Debt-to-income ratio (weight: 10%)

**Score Calculation:**
```
Base Score: 300
+ Transaction Frequency Score (0-200)
+ Transaction Amount Score (0-150)
+ Payment Consistency Score (0-200)
+ Account Age Score (0-100)
+ Debt-to-Income Score (0-50)
= Final Score (0-1000)
```

---

### LoanEngine (`loan_engine.py`)

**Purpose:** Loan calculation and eligibility

**Key Methods:**
- `calculate_eligibility(user)` - Determine loan eligibility
- `generate_offer(user, amount)` - Generate loan offer
- `calculate_monthly_repayment(amount, rate, duration)` - Calculate repayment
- `get_monthly_turnover(user)` - Get monthly turnover

**Eligibility Criteria:**
- Minimum OjaScore: 400
- Minimum account age: 30 days
- Minimum monthly turnover: ₦10,000
- No defaulted loans
- Debt-to-income ratio < 50%

**Loan Amount Formula:**
```
Max Loan = Monthly Turnover × 2 × (OjaScore / 1000)
Min Loan = ₦5,000
Max Cap = ₦500,000
```

---

### Analytics (`analytics.py`)

**Purpose:** Business analytics and insights

**Key Methods:**
- `get_sales_trends(user, days)` - Analyze sales trends
- `generate_restock_alerts(user, lookback_days, horizon_days)` - Generate restock alerts
- `calculate_revenue_metrics(user)` - Calculate revenue metrics

**Sales Trends:**
- Daily revenue over period
- Growth rate calculation
- Seasonal pattern detection
- Top-selling products

**Restock Alerts:**
- Products with low stock
- Predicted stockout dates
- Recommended order quantities
- Supplier suggestions

---

## Templates

### Base Templates

#### `base.html`
**Purpose:** Main template with navigation and styling

**Features:**
- TailwindCSS integration
- Google Fonts (Satoshi, DM Sans)
- Material Icons
- Responsive navigation
- User authentication state
- Notification bell

**Blocks:**
- `title` - Page title
- `content` - Main content
- `scripts` - Additional scripts

---

#### `public_base.html`
**Purpose:** Base template for public pages

**Features:**
- Simplified navigation
- Landing page styling
- No authentication required

---

### Authentication Templates

#### `onboarding.html`
**Purpose:** User registration form

**Fields:**
- First name, last name, middle name
- Phone number
- Email
- BVN
- Date of birth
- Gender
- Address
- PIN
- Role selection

**Features:**
- Real-time validation
- BVN format check
- Phone number format
- PIN strength indicator

---

#### `login.html`
**Purpose:** Login form

**Fields:**
- Phone number
- PIN

**Features:**
- Remember me checkbox
- Forgot PIN link
- Registration link

---

#### `profile.html`
**Purpose:** User profile dashboard

**Sections:**
- User information card
- OjaScore display with tier
- Wallet balance
- Recent transactions
- Score history graph
- Quick actions

---

### Dashboard Templates

#### `mamatally.html`
**Purpose:** Merchant dashboard

**Sections:**
- Revenue overview (today, month)
- Inventory summary
- Low stock alerts
- Recent sales
- Sales trends chart
- AI insights panel
- BMONI account details

**Features:**
- Real-time data updates
- Interactive charts
- Quick action buttons
- Notification badges

---

#### `trader_dashboard.html`
**Purpose:** Trader-specific dashboard

**Sections:**
- Sales overview
- Product performance
- Inventory status
- Transaction history

---

### Gig Templates

#### `gigmarketplace.html`
**Purpose:** Gig browsing interface

**Features:**
- Gig cards with details
- Filter by location/skills
- Search functionality
- Apply buttons
- Gig status indicators

---

#### `postgig.html`
**Purpose:** Gig posting form

**Fields:**
- Gig title
- Description
- Skills required
- Location
- Pay rate
- Deadline

**Features:**
- Rich text editor
- Skills autocomplete
- Location picker
- Pay rate calculator

---

#### `hiring_marketplace.html`
**Purpose:** Employer gig management

**Sections:**
- Posted gigs
- Applications received
- Active gigs
- Completed gigs

---

#### `seeker_marketplace.html`
**Purpose:** Seeker gig interface

**Sections:**
- Recommended gigs
- Applied gigs
- Active gigs
- Completed gigs

---

### Ajo Templates

#### `ajocreate.html`
**Purpose:** Ajo group creation form

**Fields:**
- Group name
- Contribution amount
- Cycle duration
- Max members

**Features:**
- Contribution calculator
- Cycle preview
- Member limit slider

---

#### `ajodashboard.html`
**Purpose:** Ajo group dashboard

**Sections:**
- Group overview
- Current cycle status
- Member list
- Contribution history
- Payout schedule

---

#### `ajogroupdetails.html`
**Purpose:** Detailed group view

**Sections:**
- Group information
- Cycle timeline
- Member contributions
- Payout history

---

### Payment Templates

#### `payment_checkout.html`
**Purpose:** Payment checkout page

**Sections:**
- Order summary
- BMONI account details
- Payment instructions
- Timer for expiration
- Copy account number button

**Features:**
- Real-time status updates
- Countdown timer
- Payment confirmation

---

#### `payment_success.html`
**Purpose:** Payment success page

**Sections:**
- Success message
- Transaction details
- Next steps
- Return to dashboard

---

#### `payment_pending.html`
**Purpose:** Payment pending page

**Sections:**
- Pending message
- Payment instructions
- Status check button

---

#### `payment_failed.html`
**Purpose:** Payment failed page

**Sections:**
- Failure message
- Retry payment button
- Contact support

---

### Other Templates

#### `loans.html`
**Purpose:** Loan application interface

**Sections:**
- Current OjaScore
- Loan eligibility
- Application form
- Active loans
- Repayment schedule

---

#### `productsinventry.html`
**Purpose:** Product management

**Sections:**
- Product list
- Add product form
- Stock levels
- Low stock alerts

---

#### `customerstorefront.html`
**Purpose:** Public storefront

**Sections:**
- Business information
- Product catalog
- Shopping cart
- Checkout form

---

## API Integrations

### BMONI API

**Purpose:** Embedded banking infrastructure

**Authentication:**
- API Key in header: `x-api-key`
- Base URL: `https://embedded-dev.bmoni.com` (sandbox)

**Key Endpoints:**

#### User Management
```
POST /v1/users
- Create new user
- Body: firstName, lastName, email, phoneNumber, bvn, address fields
- Response: user object with bmoniUserId

GET /v1/users?page=1&limit=20
- List all users under partner
- Response: users array with pagination

GET /v1/users/{userId}
- Get user profile
- Response: user object

DELETE /v1/users/{userId}
- Delete user account
- Response: success message
```

#### Wallet Management
```
POST /v1/users/{userId}/smart-wallets/owner-proof-challenges
- Request signing challenge
- Body: currency, userOwnerAddress
- Response: challengeId, message

POST /v1/users/{userId}/smart-wallets/create-managed
- Create managed wallet
- Body: currency, ownerProofChallengeId, ownerProofSignature, userOwnerAddress
- Response: wallet object with walletAddress

GET /v1/users/{userId}/smart-wallets/account/wallets
- List user wallets
- Response: wallets array

GET /v1/users/{userId}/smart-wallets/account/balances
- Get wallet balances
- Response: balances per currency
```

#### Onboarding
```
POST /v1/users/{userId}/onboarding/start-nigeria
- Activate Nigerian rail
- Body: bvn, ngnWalletAddress, ngnWalletIndex
- Response: onboarding status

GET /v1/users/{userId}/onboarding/status
- Get onboarding status
- Response: status per rail
```

#### KYC
```
GET /v1/users/{userId}/kyc/options
- Get KYC field options
- Response: options object

PATCH /v1/users/{userId}/kyc
- Submit KYC data
- Body: personal, address, employment fields
- Response: updated KYC status

POST /v1/users/{userId}/kyc/documents/identification
- Upload ID document
- Body: multipart/form-data with file
- Response: document status
```

#### Bank Accounts
```
POST /v1/users/{userId}/bank-accounts/verify-nigerian-account
- Verify Nigerian bank account
- Body: accountNumber, bankCode
- Response: account holder name

POST /v1/users/{userId}/bank-accounts/withdrawal-accounts/nigeria
- Create withdrawal account
- Body: accountNumber, bankCode, bankName, accountHolderName
- Response: bankAccountId

GET /v1/users/{userId}/bank-accounts/deposit-accounts/{currency}
- Get deposit accounts (VBA)
- Response: accounts array with accountNumber, bankName
```

#### Withdrawals
```
POST /v1/users/{userId}/withdrawal/wallet/nigeria
- Initiate withdrawal
- Body: sourceSmartWalletId, bankAccountId, fromAmount
- Response: proposalId, signPayload

POST /v1/users/{userId}/smart-wallets/proposals/{proposalId}/sign
- Submit proposal signature
- Body: signature
- Response: updated proposal status
```

#### Webhooks
```
POST /bmoni/webhook/
- Transaction confirmation
- Headers: x-bmoni-signature (HMAC)
- Body: transaction details
- Response: 200 OK
```

**Cryptographic Requirements:**
- Ethereum wallet generation (SECP256k1)
- EIP-191 personal_sign format
- Keccak-256 hashing
- 65-byte signatures (r + s + v)
- Recovery ID calculation

---

### Google Gemini API

**Purpose:** AI-powered matching and analytics

**Authentication:**
- API Key in environment variable
- Base URL: `https://generativelanguage.googleapis.com`

**Usage:**
- Gig matching: Analyze seeker profile against gig requirements
- Business insights: Generate recommendations from sales data
- Loan optimization: Determine optimal pricing based on risk

**Prompt Engineering:**
- Context: User profile, transaction history, gig details
- Task: Match, analyze, or optimize
- Output: Structured JSON response

---

## Security

### Authentication
- PIN-based authentication (4-6 digits)
- Session management via Django auth
- CSRF protection on all forms
- Session timeout configuration

### API Security
- HMAC signature verification for BMONI webhooks
- API keys stored in environment variables
- Request rate limiting
- Retry logic with exponential backoff

### Data Security
- BVN and KYC documents encrypted at rest
- Private keys for wallets stored securely
- No live financial data in development
- Test data only policy

### Input Validation
- All user inputs validated and sanitized
- SQL injection prevention via Django ORM
- XSS protection via template escaping
- File upload validation

### Cryptographic Security
- Real Ethereum wallet generation
- Proper EIP-191 signing
- Keccak-256 hashing (not SHA3-256)
- Recovery ID calculation for signatures

---

## Deployment

### Environment Variables

```bash
# BMONI API
BMONI_API_KEY=your_bmoni_api_key
BMONI_BASE_URL=https://embedded-dev.bmoni.com
BMONI_WEBHOOK_SECRET=your_webhook_secret

# Google Gemini
GEMINI_API_KEY=your_gemini_api_key

# Site Configuration
SITE_BASE_URL=https://ojapass.onrender.com
DEBUG=False
ALLOWED_HOSTS=ojapass.onrender.com

# Database
DATABASE_URL=postgresql://user:password@host:port/dbname

# Secret Key
SECRET_KEY=your_django_secret_key
```

### Deployment Steps

1. **Prepare Code:**
   - Ensure all migrations applied
   - Collect static files
   - Update environment variables

2. **Database Setup:**
   - Create PostgreSQL database
   - Run migrations
   - Create superuser

3. **Configure Webhook:**
   - Set BMONI webhook URL
   - Verify HMAC secret
   - Test webhook endpoint

4. **Deploy to Render:**
   - Connect GitHub repository
   - Configure build and start commands
   - Set environment variables
   - Deploy

5. **Post-Deployment:**
   - Test registration flow
   - Verify BMONI integration
   - Test payment processing
   - Monitor webhook delivery

---

## Conclusion

This documentation provides a comprehensive overview of the OjaPass system, covering all features, user flows, technical components, and integrations. The system is designed to provide financial inclusion to Nigeria's informal economy through alternative credit scoring, embedded banking, and AI-powered services.

**Key Achievements:**
- Complete BMONI integration with real cryptographic operations
- Alternative credit scoring (OjaScore) without formal documents
- AI-powered gig matching and business analytics
- Digital Ajo savings groups
- Comprehensive payment processing
- Full user journey from registration to loan disbursement

**Technical Highlights:**
- Real Ethereum wallet generation and signing
- EIP-191 compliant signature generation
- Keccak-256 hashing for Ethereum compatibility
- HMAC webhook signature verification
- Bayesian credit scoring algorithm
- AI integration with Google Gemini

**Future Enhancements:**
- Mobile app (React Native)
- Enhanced AI models
- Additional payment methods
- Insurance products
- Partnership integrations

---

**Document Version:** 1.0
**Last Updated:** July 30, 2026
**Author:** OjaPass Development Team
