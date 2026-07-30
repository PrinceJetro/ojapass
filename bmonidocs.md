Open SearchSearch
Keyboard Shortcut:Control⌃ k

Introduction

Health
Open Group

Users
Close Group

Create a new user
HTTP Method: POST

List partner users
HTTP Method: GET

Get user profile
HTTP Method: GET

Update user
HTTP Method: PATCH

Delete user account
HTTP Method: DEL

KYC
Open Group

Onboarding
Open Group

Exchange
Open Group

Smart Wallets
Open Group

Withdrawal
Open Group

Cards
Open Group

Bank Accounts
Open Group

Deposit
Open Group

VBAs
Open Group

Transactions
Open Group

Announcements
Open Group

Employer Link
Open Group

Employer Link (internal)
Open Group

Webhooks
Open Group

Location
Open Group

EU (SEPA)
Open Group

LATAM Cash
Open Group

LATAM Mexico
Open Group

Bank Payouts
Open Group

Payment
Open Group

Models
Open Group
Open API Client
Powered by Scalar

v1.0
OpenAPI 3.0.0
BMoni Embedded API

Download OpenAPI Document

Download OpenAPI Document
Embeddable API that lets partners access BMoni wallet and card services. Provides user management, KYC, wallets, smart (multi-sig) wallets, cards, bank accounts, transactions, deposits, and withdrawals.


Authentication
SelectAuth Type
No authentication selected
Client Libraries
HTTP HTTP/1.1
Health (Collapsed)​Copy link
HealthOperations
get
/v1/health
Show More
Users ​Copy link
UsersOperations
post
/v1/users
get
/v1/users
get
/v1/users/{userId}
patch
/v1/users/{userId}
delete
/v1/users/{userId}
Create a new user​Copy link

Auth Required
Creates user in BMoni, submits KYC data, and stores locally. The partner is derived automatically from the API key used. For Nigerian users, provide a BVN to auto-fill lastName, middleName, address, and dateOfBirth from the BVN record. Explicitly provided values always take precedence over BVN data.

Body
·CreateUserInput
required
application/json
emailCopy link to email
Type:string
required
Example
firstNameCopy link to firstName
Type:string
required
Example
phoneNumberCopy link to phoneNumber
Type:string
required
Example
E.164 formatted phone number

addressCityCopy link to addressCity
Type:string
Example
addressCountryCopy link to addressCountry
Type:string
Example
addressPostalCodeCopy link to addressPostalCode
Type:string
Example
addressStateCopy link to addressState
Type:string
Example
addressStreetCopy link to addressStreet
Type:string
Example
Street address

bvnCopy link to bvn
Type:string
Example
Nigerian Bank Verification Number. When provided, lastName, middleName, address, and dateOfBirth are auto-filled from the BVN record. Explicitly provided values take precedence.

employeeIdCopy link to employeeId
Type:string
Example
Partner employee identifier

employerNameCopy link to employerName
Type:string
Example
identityIdCopy link to identityId
Type:string
Example
External identity identifier from the calling client

Show additional propertiesfor Request Body
Responses

201
User created
application/json

400
Validation failed
application/json

401
Missing or invalid API key
application/json

409
User already exists
application/json

500
Internal server error
application/json
Request Example forpost/v1/users
HTTP HTTP/1.1
POST /v1/users HTTP/1.1
Host: replace.me
Content-Type: application/json
x-api-key: YOUR_SECRET_TOKEN

{"employeeId":"EMP-2024-00142","identityId":"BKY-ID-00789","firstName":"Chiamaka","lastName":"Okafor","middleName":"Ngozi","email":"chiamaka.okafor@example.com","phoneNumber":"+2348012345678","bvn":"22345678901","monthlySalary":"450000.00","employerName":"Acme Corporation Ltd","occupation":"Software Engineer","addressStreet":"15 Admiralty Way","addressCity":"Lagos","addressState":"Lagos","addressCountry":"Nigeria","addressPostalCode":"101241"}


Test Request
(post /v1/users)
Status:201
Status:400
Status:401
Status:409
Status:500
{
  "user": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "partnerName": "BMONI QA",
    "employeeId": "EMP-2024-00142",
    "identityId": "BKY-ID-00789",
    "bmoniUserId": "bmoni-user-uuid-001",
    "firstName": "Chiamaka",
    "lastName": "Okafor",
    "middleName": "Ngozi",
    "email": "chiamaka.okafor@example.com",
    "phoneNumber": "+2348012345678",
    "employerName": "Acme Corporation Ltd",
    "occupation": "Software Engineer",
    "monthlySalary": "450000.00",
    "linkedAt": null,
    "createdAt": "2026-07-29T19:51:03.771Z",
    "updatedAt": "2026-07-29T19:51:03.771Z"
  }
}

User created

List partner users​Copy link

Auth Required
Returns all users created under the partner associated with the API key, plus employees linked to the partner via the employer-link flow. Linked employees carry a non-null linkedAt and a null phoneNumber (they signed up in the BMONI app themselves).

Query Parameters
pageCopy link to page
Type:number
min:  
1
Default
Example
Page number to return

limitCopy link to limit
Type:number
min:  
1
max:  
100
Default
Example
Maximum number of users to return

Responses

200
Users under the authenticated partner
application/json

401
Missing or invalid API key
application/json

500
Internal server error
application/json
Request Example forget/v1/users
HTTP HTTP/1.1
GET /v1/users HTTP/1.1
Host: replace.me
x-api-key: YOUR_SECRET_TOKEN




Test Request
(get /v1/users)
Status:200
Status:401
Status:500
{
  "users": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "partnerName": "BMONI QA",
      "employeeId": "EMP-2024-00142",
      "identityId": "BKY-ID-00789",
      "bmoniUserId": "bmoni-user-uuid-001",
      "firstName": "Chiamaka",
      "lastName": "Okafor",
      "middleName": "Ngozi",
      "email": "chiamaka.okafor@example.com",
      "phoneNumber": "+2348012345678",
      "employerName": "Acme Corporation Ltd",
      "occupation": "Software Engineer",
      "monthlySalary": "450000.00",
      "linkedAt": null,
      "createdAt": "2026-07-29T19:51:03.771Z",
      "updatedAt": "2026-07-29T19:51:03.771Z"
    }
  ],
  "total": 124,
  "page": 1,
  "limit": 20
}

Users under the authenticated partner

Get user profile​Copy link

Auth Required
Returns the stored profile for the given user. Also resolves employees linked via the employer-link flow (non-null linkedAt).

Path Parameters
userIdCopy link to userId
Type:string
required
The bmoniUserId field from the user. The same value is shared across endpoints in this reference while you try different operations.

Responses

200
User profile
application/json

401
Missing or invalid API key
application/json

403
User does not belong to this partner

404
User not found
application/json

500
Internal server error
application/json
Request Example forget/v1/users/{userId}
HTTP HTTP/1.1
GET /v1/users/%7BuserId%7D HTTP/1.1
Host: replace.me
x-api-key: YOUR_SECRET_TOKEN




Test Request
(get /v1/users/{userId})
Status:200
Status:401
Status:403
Status:404
Status:500
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "partnerName": "BMONI QA",
  "employeeId": "EMP-2024-00142",
  "identityId": "BKY-ID-00789",
  "bmoniUserId": "bmoni-user-uuid-001",
  "firstName": "Chiamaka",
  "lastName": "Okafor",
  "middleName": "Ngozi",
  "email": "chiamaka.okafor@example.com",
  "phoneNumber": "+2348012345678",
  "employerName": "Acme Corporation Ltd",
  "occupation": "Software Engineer",
  "monthlySalary": "450000.00",
  "linkedAt": null,
  "createdAt": "2026-07-29T19:51:03.771Z",
  "updatedAt": "2026-07-29T19:51:03.771Z"
}

User profile

Update user​Copy link

Auth Required
Path Parameters
userIdCopy link to userId
Type:string
required
The bmoniUserId field from the user. The same value is shared across endpoints in this reference while you try different operations.

Body
·UpdateUserInput
required
application/json
displayNameCopy link to displayName
Type:string
Example
employerNameCopy link to employerName
Type:string
Example
firstNameCopy link to firstName
Type:string
Example
identityIdCopy link to identityId
Type:string
Example
External identity identifier from the calling client

lastNameCopy link to lastName
Type:string
Example
Optional. Auto-filled from BVN when available.

middleNameCopy link to middleName
Type:string
Example
monthlySalaryCopy link to monthlySalary
Type:string
Example
occupationCopy link to occupation
Type:string
Example
Responses

200
User updated
application/json

400
Validation failed
application/json

401
Missing or invalid API key
application/json

403
User does not belong to this partner

500
Internal server error
application/json
Request Example forpatch/v1/users/{userId}
HTTP HTTP/1.1
PATCH /v1/users/%7BuserId%7D HTTP/1.1
Host: replace.me
Content-Type: application/json
x-api-key: YOUR_SECRET_TOKEN

{"identityId":"BKY-ID-00789","firstName":"Chiamaka","lastName":"Okafor","middleName":"Ngozi","monthlySalary":"450000.00","employerName":"Acme Corporation Ltd","occupation":"Software Engineer","displayName":"Chiamaka Okafor"}


Test Request
(patch /v1/users/{userId})
Status:200
Status:400
Status:401
Status:403
Status:500
{
  "success": true,
  "message": "User updated",
  "user": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "partnerName": "BMONI QA",
    "employeeId": "EMP-2024-00142",
    "identityId": "BKY-ID-00789",
    "bmoniUserId": "bmoni-user-uuid-001",
    "firstName": "Chiamaka",
    "lastName": "Okafor",
    "middleName": "Ngozi",
    "email": "chiamaka.okafor@example.com",
    "phoneNumber": "+2348012345678",
    "employerName": "Acme Corporation Ltd",
    "occupation": "Software Engineer",
    "monthlySalary": "450000.00",
    "linkedAt": null,
    "createdAt": "2026-07-29T19:51:03.771Z",
    "updatedAt": "2026-07-29T19:51:03.771Z"
  }
}

User updated

Delete user account​Copy link

Auth Required
Path Parameters
userIdCopy link to userId
Type:string
required
The bmoniUserId field from the user. The same value is shared across endpoints in this reference while you try different operations.

Responses

200
User removed in BMoni and locally
application/json

401
Missing or invalid API key
application/json

403
User does not belong to this partner

500
Internal server error
application/json
Request Example fordelete/v1/users/{userId}
HTTP HTTP/1.1
DELETE /v1/users/%7BuserId%7D HTTP/1.1
Host: replace.me
x-api-key: YOUR_SECRET_TOKEN




Test Request
(delete /v1/users/{userId})
Status:200
Status:401
Status:403
Status:500
{
  "success": true,
  "message": "User deleted"
}

User removed in BMoni and locally

KYC (Collapsed)​Copy link
KYCOperations
get
/v1/users/{userId}/kyc/occupations
get
/v1/users/{userId}/kyc/options
get
/v1/users/{userId}/kyc
patch
/v1/users/{userId}/kyc
get
/v1/users/{userId}/kyc/bvn-lookup/{bvn}
get
/v1/users/{userId}/kyc/readiness
get
/v1/users/{userId}/kyc/usd-readiness
get
/v1/users/{userId}/kyc/status
post
/v1/users/{userId}/kyc/retry
get
/v1/users/{userId}/kyc/nin-lookup/{nin}
post
/v1/users/{userId}/kyc/activate
post
/v1/users/{userId}/kyc/documents/identification
post
/v1/users/{userId}/kyc/documents/proof-of-address
post
/v1/users/{userId}/kyc/documents/biometric
Show More
Onboarding (Collapsed)​Copy link
OnboardingOperations
post
/v1/users/{userId}/onboarding/start-nigeria
post
/v1/users/{userId}/onboarding/start-canada
post
/v1/users/{userId}/onboarding/start-monerium
post
/v1/users/{userId}/onboarding/start-mexico
post
/v1/users/{userId}/onboarding/start-usa
get
/v1/users/{userId}/onboarding/status
Show More
Exchange (Collapsed)​Copy link
ExchangeOperations
get
/v1/users/{userId}/exchange/rate/{from}/{to}
post
/v1/users/{userId}/exchange/convert
post
/v1/users/{userId}/exchange/quote
Show More
Smart Wallets (Collapsed)​Copy link
Smart WalletsOperations
post
/v1/users/{userId}/smart-wallets/owner-proof-challenges
post
/v1/users/{userId}/smart-wallets/create-managed
get
/v1/users/{userId}/smart-wallets/account/wallets
get
/v1/users/{userId}/smart-wallets/account/balances
get
/v1/users/{userId}/smart-wallets/{smartWalletId}
get
/v1/users/{userId}/smart-wallets/{smartWalletId}/balance
post
/v1/users/{userId}/smart-wallets/proposals/{proposalId}/sign
get
/v1/users/{userId}/smart-wallets/{smartWalletId}/transactions
get
/v1/users/{userId}/smart-wallets/{smartWalletId}/transactions/{transactionId}
post
/v1/users/{userId}/smart-wallets/{smartWalletId}/offramp/nigeria
post
/v1/users/{userId}/smart-wallets/{smartWalletId}/migrate-to-safe
post
/v1/users/{userId}/smart-wallets/{smartWalletId}/onramp/vba/nigeria
delete
/v1/users/{userId}/smart-wallets/{smartWalletId}/onramp/vba/nigeria
post
/v1/users/{userId}/smart-wallets/{smartWalletId}/onramp/vba/eu
delete
/v1/users/{userId}/smart-wallets/{smartWalletId}/onramp/vba/eu
post
/v1/users/{userId}/smart-wallets/{smartWalletId}/onramp/vba/usd/provision
post
/v1/users/{userId}/smart-wallets/{smartWalletId}/onramp/vba/usd
delete
/v1/users/{userId}/smart-wallets/{smartWalletId}/onramp/vba/usd
post
/v1/users/{userId}/smart-wallets/account/send
get
/v1/smart-wallets/supported-currencies
Show More
Withdrawal (Collapsed)​Copy link
WithdrawalOperations
post
/v1/users/{userId}/smart-wallets/proposals/{proposalId}/sign
get
/v1/users/{userId}/bank-accounts/withdrawal-accounts
get
/v1/users/{userId}/bank-accounts/withdrawal-accounts/{currency}
post
/v1/users/{userId}/withdrawal/wallet/nigeria
get
/v1/users/{userId}/withdrawal/smart-wallet/crypto/supported/{currency}
post
/v1/users/{userId}/withdrawal/smart-wallet/crypto
post
/v1/users/{userId}/withdrawal/card
Show More
Cards (Collapsed)​Copy link
CardsOperations
post
/v1/users/{userId}/cards
get
/v1/users/{userId}/cards/status
post
/v1/users/{userId}/cards/sensitive-data
post
/v1/users/{userId}/cards/{cardId}/activate/request
post
/v1/users/{userId}/cards/{cardId}/activate/confirm
put
/v1/users/{userId}/cards/{cardId}/status
post
/v1/users/{userId}/cards/{cardId}/reset
get
/v1/users/{userId}/cards/{cardId}/transactions
put
/v1/users/{userId}/cards/{cardId}/set-limit
get
/v1/users/{userId}/cards/{cardId}/limits
put
/v1/users/{userId}/cards/{cardId}/pin
put
/v1/users/{userId}/cards/{cardId}/deactivate
get
/v1/users/{userId}/smart-wallets/{smartWalletId}/cards
get
/v1/users/{userId}/smart-wallets/{smartWalletId}/cards/{cardId}
get
/v1/users/{userId}/smart-wallets/{smartWalletId}/cards/{cardId}/sensitive
Show More
Bank Accounts (Collapsed)​Copy link
Bank AccountsOperations
get
/v1/users/{userId}/bank-accounts
post
/v1/users/{userId}/bank-accounts/withdrawal-accounts/nigeria
get
/v1/users/{userId}/bank-accounts/nigerian-banks
post
/v1/users/{userId}/bank-accounts/verify-nigerian-account
put
/v1/users/{userId}/bank-accounts/deposit-accounts/{accountId}/deactivate
put
/v1/users/{userId}/bank-accounts/withdrawal-accounts/nigeria/{accountId}/deactivate
Show More
Deposit (Collapsed)​Copy link
DepositOperations
get
/v1/users/{userId}/bank-accounts/deposit-accounts
get
/v1/users/{userId}/bank-accounts/deposit-accounts/{currency}
post
/v1/users/{userId}/deposit/wallet
post
/v1/users/{userId}/deposit/card
get
/v1/deposit/supported-assets
Show More
VBAs (Collapsed)​Copy link
VBAsOperations
get
/v1/users/{userId}/vba/usd
Show More
Transactions (Collapsed)​Copy link
TransactionsOperations
post
/v1/users/{userId}/transactions/receipt/pdf
post
/v1/users/{userId}/transactions/group-wallet/receipt/pdf
get
/v1/users/{userId}/transactions/user/{otherUserId}
get
/v1/users/{userId}/transactions/{smartWalletId}/{transactionId}/fees
get
/v1/users/{userId}/transactions/{smartWalletId}
Show More
Announcements (Collapsed)​Copy link
AnnouncementsOperations
get
/v1/users/{userId}/announcements
get
/v1/users/{userId}/announcements/unread
post
/v1/users/{userId}/announcements/read
Show More
Employer Link (Collapsed)​Copy link
Employer LinkOperations
post
/v1/partners/employees/invite
post
/v1/partners/employees/batch
get
/v1/partners/employees
delete
/v1/partners/employees/{id}
Show More
Employer Link (internal) (Collapsed)​Copy link
Employer Link (internal)Operations
post
/v1/internal/employees/link
post
/v1/internal/employees/vba
Show More
Webhooks (Collapsed)​Copy link
WebhooksOperations
post
/v1/webhooks/config
get
/v1/webhooks/config
patch
/v1/webhooks/config
post
/v1/webhooks/config/rotate-secret
post
/v1/webhooks/events
get
/v1/webhooks/events
Show More
Location (Collapsed)​Copy link
LocationOperations
get
/v1/location/countries
get
/v1/location/countries/{countryCode}
get
/v1/location/countries/{countryCode}/subdivisions
get
/v1/location/subdivisions/{subdivisionCode}/cities
Show More
