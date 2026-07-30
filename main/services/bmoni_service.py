import requests
import time
from django.conf import settings
from .crypto_utils import EthereumWallet, ServerWalletManager

class BMONIService:
    @staticmethod
    def get_headers():
        return {
            "x-api-key": settings.BMONI_API_KEY,
            "Content-Type": "application/json"
        }

    @staticmethod
    def list_users(page=1, limit=20):
        url = f"{settings.BMONI_BASE_URL}/v1/users"
        params = {"page": page, "limit": limit}
        try:
            response = requests.get(url, headers=BMONIService.get_headers(), params=params, timeout=10)
            response.raise_for_status()
            return {"success": True, "data": response.json()}
        except requests.exceptions.RequestException as e:
            return BMONIService._error(url, e)

    @staticmethod
    def find_user_by_email_or_phone(email=None, phone=None):
        if not email and not phone:
            return None
        for page in range(1, 6):
            result = BMONIService.list_users(page=page, limit=100)
            if not result.get("success"):
                continue
            users = result.get("data", {}).get("users", [])
            for user in users:
                if email and user.get("email") == email:
                    return user
                if phone:
                    user_phone = user.get("phoneNumber", "")
                    search_phone = phone.lstrip("+")
                    user_phone_normalized = user_phone.lstrip("+")
                    if user_phone_normalized == search_phone:
                        return user
                    if search_phone.startswith("0"):
                        search_phone = "+234" + search_phone[1:]
                    if user_phone_normalized == search_phone:
                        return user
            if len(users) < 100:
                break
        return None

    @staticmethod
    def create_user(user_data):
        url = f"{settings.BMONI_BASE_URL}/v1/users"
        phone = user_data.get('phone')
        if phone and not phone.startswith('+'):
            phone = f"+234{phone.lstrip('0')}"
        payload = {
            "firstName": user_data.get('firstName'),
            "email": user_data.get('email'),
            "phoneNumber": phone,
        }
        if user_data.get('lastName'):
            payload["lastName"] = user_data.get('lastName')
        if user_data.get('middleName'):
            payload["middleName"] = user_data.get('middleName')
        if user_data.get('bvn'):
            payload["bvn"] = user_data.get('bvn')
        if user_data.get('address'):
            payload["addressStreet"] = user_data.get('address')
        if user_data.get('city'):
            payload["addressCity"] = user_data.get('city')
        if user_data.get('state'):
            payload["addressState"] = user_data.get('state')
        if user_data.get('country'):
            payload["addressCountry"] = user_data.get('country')
        return BMONIService._post(url, payload)

    @staticmethod
    def get_user(bmoni_user_id):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{bmoni_user_id}"
        return BMONIService._get(url)

    @staticmethod
    def delete_user(bmoni_user_id):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{bmoni_user_id}"
        try:
            response = requests.delete(url, headers=BMONIService.get_headers(), timeout=10)
            response.raise_for_status()
            return {"success": True, "data": response.json() if response.content else None}
        except requests.exceptions.RequestException as e:
            return BMONIService._error(url, e)

    @staticmethod
    def request_owner_proof_challenge(user_id, currency, owner_address):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/smart-wallets/owner-proof-challenges"
        payload = {"currency": currency, "userOwnerAddress": owner_address}
        return BMONIService._post(url, payload)

    @staticmethod
    def create_managed_wallet(user_id, challenge_id, signature, owner_address):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/smart-wallets/create-managed"
        payload = {"challengeId": challenge_id, "signature": signature, "ownerAddress": owner_address}
        return BMONIService._post(url, payload)

    @staticmethod
    def create_wallet_simple(user_id, currency="CNGN"):
        wallet = ServerWalletManager.create_wallet_for_user()
        owner_address = wallet["address"]
        private_key = wallet["private_key"]
        challenge_result = BMONIService.request_owner_proof_challenge(user_id, currency, owner_address)
        if challenge_result.get('success'):
            challenge_data = challenge_result.get('data', {})
            challenge_id = challenge_data.get('challengeId')
            challenge_message = challenge_data.get('message')
            signature = ServerWalletManager.sign_bmoni_challenge(private_key, challenge_message)
            return BMONIService._post(
                f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/smart-wallets/create-managed",
                {
                    "currency": currency,
                    "ownerProofChallengeId": challenge_id,
                    "ownerProofSignature": signature,
                    "userOwnerAddress": owner_address
                }
            )
        return challenge_result

    @staticmethod
    def get_wallets(user_id):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/smart-wallets/account/wallets"
        return BMONIService._get(url)

    @staticmethod
    def get_balances(user_id):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/smart-wallets/account/balances"
        return BMONIService._get(url)

    @staticmethod
    def get_transactions(user_id, smart_wallet_id):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/transactions"
        return BMONIService._get(url)

    @staticmethod
    def get_onboarding_status(user_id):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/onboarding/status"
        return BMONIService._get(url)

    @staticmethod
    def start_nigeria_onboarding(user_id, bvn, ngn_wallet_address, ngn_wallet_index=0):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/onboarding/start-nigeria"
        payload = {"bvn": bvn, "ngnWalletAddress": ngn_wallet_address, "ngnWalletIndex": ngn_wallet_index}
        return BMONIService._post(url, payload)

    @staticmethod
    def get_kyc_options(user_id):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/kyc/options"
        return BMONIService._get(url)

    @staticmethod
    def get_kyc_occupations(user_id, search=None):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/kyc/occupations"
        params = {"search": search} if search else None
        try:
            response = requests.get(url, headers=BMONIService.get_headers(), params=params, timeout=10)
            response.raise_for_status()
            return {"success": True, "data": response.json()}
        except requests.exceptions.RequestException as e:
            return BMONIService._error(url, e)

    @staticmethod
    def bvn_lookup(user_id, bvn):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/kyc/bvn-lookup/{bvn}"
        return BMONIService._get(url)

    @staticmethod
    def nin_lookup(user_id, nin):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/kyc/nin-lookup/{nin}"
        return BMONIService._get(url)

    @staticmethod
    def upload_kyc_document_identification(user_id, file_obj, doc_type, document_number, issuing_country, expiration_date=None, issue_date=None):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/kyc/documents/identification"
        data = {"type": doc_type, "documentNumber": document_number, "issuingCountry": issuing_country}
        if expiration_date:
            data["expirationDate"] = expiration_date
        if issue_date:
            data["issueDate"] = issue_date
        return BMONIService._post_multipart(url, file_obj, data)

    @staticmethod
    def upload_kyc_document_proof_of_address(user_id, file_obj, doc_type):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/kyc/documents/proof-of-address"
        data = {"type": doc_type}
        return BMONIService._post_multipart(url, file_obj, data)

    @staticmethod
    def upload_kyc_document_biometric(user_id, file_obj):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/kyc/documents/biometric"
        return BMONIService._post_multipart(url, file_obj, {})

    @staticmethod
    def patch_kyc(user_id, payload):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/kyc"
        try:
            response = requests.patch(url, json=payload, headers=BMONIService.get_headers(), timeout=15)
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError:
                data = None
            return {"success": True, "data": data}
        except requests.exceptions.RequestException as e:
            return BMONIService._error(url, e)

    @staticmethod
    def get_kyc_readiness(user_id):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/kyc/readiness"
        return BMONIService._get(url)

    @staticmethod
    def get_kyc_status(user_id):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/kyc/status"
        return BMONIService._get(url)

    @staticmethod
    def activate_kyc(user_id, sumsub_level_name=None):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/kyc/activate"
        payload = {}
        if sumsub_level_name:
            payload["sumsubLevelName"] = sumsub_level_name
        return BMONIService._post(url, payload)

    @staticmethod
    def verify_nigerian_account(user_id, account_number, bank_code):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/bank-accounts/verify-nigerian-account"
        payload = {"accountNumber": account_number, "bankCode": bank_code}
        return BMONIService._post(url, payload)

    @staticmethod
    def get_or_create_nigerian_withdrawal_account(user_id, account_number, bank_code, bank_name, account_holder_name):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/bank-accounts/withdrawal-accounts/nigeria"
        payload = {"accountNumber": account_number, "bankCode": bank_code, "bankName": bank_name, "accountHolderName": account_holder_name}
        return BMONIService._post(url, payload)

    @staticmethod
    def get_deposit_accounts(user_id, currency="NGN"):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/bank-accounts/deposit-accounts/{currency}"
        return BMONIService._get(url)

    @staticmethod
    def link_nigeria_vba(user_id, smart_wallet_id, bank_account_id):
        """
        Link an EXISTING Nigerian bank account record (its id — see
        get_or_create_nigerian_withdrawal_account) to a smart wallet for
        onramp routing. This requires a real bankAccountId; it does not
        provision a brand-new VBA on its own. To provision the wallet's
        own deposit VBA during registration, use start_nigeria_onboarding
        + get_deposit_accounts instead — that's the correct flow for a
        freshly created wallet with no bank account record yet.
        """
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/onramp/vba/nigeria"
        return BMONIService._post(url, {"bankAccountId": bank_account_id})

    @staticmethod
    def list_nigerian_banks(user_id):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/bank-accounts/nigerian-banks"
        return BMONIService._get(url)

    @staticmethod
    def initiate_nigeria_withdrawal(user_id, source_smart_wallet_id, bank_account_id, from_amount):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/withdrawal/wallet/nigeria"
        payload = {"sourceSmartWalletId": source_smart_wallet_id, "bankAccountId": bank_account_id, "fromAmount": str(from_amount)}
        return BMONIService._post(url, payload)

    @staticmethod
    def submit_proposal_signature(user_id, proposal_id, signature):
        url = f"{settings.BMONI_BASE_URL}/v1/users/{user_id}/smart-wallets/proposals/{proposal_id}/sign"
        payload = {"signature": signature}
        return BMONIService._post(url, payload)

    @staticmethod
    def _get(url, timeout=10, retries=2, backoff=1.5):
        last_error = None
        for attempt in range(retries + 1):
            try:
                response = requests.get(url, headers=BMONIService.get_headers(), timeout=timeout)
                response.raise_for_status()
                return {"success": True, "data": response.json()}
            except requests.exceptions.RequestException as e:
                last_error = e
                status = getattr(e.response, "status_code", None)
                if status in (502, 503, 504) and attempt < retries:
                    time.sleep(backoff * (attempt + 1))
                    continue
                break
        return BMONIService._error(url, last_error)

    @staticmethod
    def _post(url, payload, timeout=30, retries=2, backoff=1.5):
        last_error = None
        for attempt in range(retries + 1):
            try:
                response = requests.post(url, json=payload, headers=BMONIService.get_headers(), timeout=timeout)
                response.raise_for_status()
                try:
                    data = response.json()
                except ValueError:
                    data = None
                return {"success": True, "data": data}
            except requests.exceptions.RequestException as e:
                last_error = e
                status = getattr(e.response, "status_code", None)
                if status in (502, 503, 504) and attempt < retries:
                    time.sleep(backoff * (attempt + 1))
                    continue
                break
        return BMONIService._error(url, last_error)

    @staticmethod
    def _post_multipart(url, file_obj, data=None, timeout=60, retries=2, backoff=1.5):
        last_error = None
        for attempt in range(retries + 1):
            try:
                headers = {"x-api-key": settings.BMONI_API_KEY}
                close_after = False
                if isinstance(file_obj, str):
                    f = open(file_obj, "rb")
                    close_after = True
                else:
                    f = file_obj
                files = {"file": (getattr(f, "name", "upload"), f)}
                response = requests.post(url, files=files, data=data or {}, headers=headers, timeout=timeout)
                if close_after:
                    f.close()
                response.raise_for_status()
                try:
                    result = response.json()
                except ValueError:
                    result = None
                return {"success": True, "data": result}
            except requests.exceptions.RequestException as e:
                last_error = e
                status = getattr(e.response, "status_code", None)
                if status in (502, 503, 504) and attempt < retries:
                    time.sleep(backoff * (attempt + 1))
                    continue
                break
        return BMONIService._error(url, last_error)

    @staticmethod
    def _error(url, exc):
        status_code = None
        body = None
        if getattr(exc, "response", None) is not None:
            status_code = exc.response.status_code
            try:
                body = exc.response.text
            except Exception:
                body = None
        print(f"[BMONI] Request error for {url}: {exc}")
        if body:
            print(f"[BMONI] Response body: {body}")
        return {"success": False, "error": str(exc), "status_code": status_code, "response_body": body}