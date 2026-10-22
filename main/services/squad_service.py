"""Squad (GTCO/HabariPay) sandbox integration — dynamic virtual accounts.

Replaces BMONI for the GBfoods hackathon. Flow per payment:

  1. InitiateBmoniDepositView (now Squad-backed) calls
     SquadService.initiate_dynamic_account(email, amount, transaction_ref)
     -> returns a 10-digit dynamic VA + bank name.
  2. Payer transfers to the VA (real bank app in prod, Squad demo app /
     simulate endpoint in sandbox).
  3. SquadWebhookView confirms via webhook -> _confirm_transaction().
  4. Sandbox shortcut: SimulateBmoniDepositView calls
     SquadService.simulate_payment() then confirms locally.

Docs: https://squadinc.gitbook.io/virtual-accounts/reference/dynamic-virtual-account-v2
Sandbox base: https://sandbox-api-d.squadco.com
Live base:    https://api-d.squadco.com
"""
import hashlib
import hmac
import time

import requests
from django.conf import settings


def _base_url():
    return getattr(settings, "SQUAD_BASE_URL", "https://sandbox-api-d.squadco.com").rstrip("/")


def _secret_key():
    return getattr(settings, "SQUAD_SECRET_KEY", "") or ""


class SquadService:
    @staticmethod
    def is_configured():
        key = _secret_key()
        return bool(key and key.startswith("sandbox_sk_") or key.startswith("sk_"))

    @staticmethod
    def get_headers():
        return {
            "Authorization": f"Bearer {_secret_key()}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Dynamic VA
    # ------------------------------------------------------------------
    @staticmethod
    def initiate_dynamic_account(email, amount_naira, transaction_ref, duration_seconds=3600):
        """Create a per-transaction dynamic VA.

        Squad expects amount in Kobo (integer). duration is seconds before expiry.
        """
        url = f"{_base_url()}/virtual-account/initiate-dynamic-virtual-account"
        try:
            amount_kobo = int(float(amount_naira) * 100)
        except Exception:
            return {"success": False, "error": f"Invalid amount: {amount_naira}"}
        payload = {
            "email": email,
            "amount": amount_kobo,
            "transaction_ref": transaction_ref,
            "duration": int(duration_seconds),
        }
        return SquadService._post(url, payload)

    @staticmethod
    def get_dynamic_transaction(transaction_ref):
        url = f"{_base_url()}/virtual-account/get-dynamic-virtual-account-transactions/{transaction_ref}"
        return SquadService._get(url)

    # ------------------------------------------------------------------
    # Inline checkout (transaction/initiate) — works on any sandbox key,
    # no profiling needed. Returns a Squad-hosted checkout_url the payer
    # opens to pay via card / bank / transfer / USSD.
    # ------------------------------------------------------------------
    @staticmethod
    def initiate_checkout(email, amount_naira, transaction_ref, callback_url,
                          customer_name=None, payment_channels=None, metadata=None):
        url = f"{_base_url()}/transaction/initiate"
        try:
            amount_kobo = int(float(amount_naira) * 100)
        except Exception:
            return {"success": False, "error": f"Invalid amount: {amount_naira}"}
        payload = {
            "email": email,
            "amount": amount_kobo,
            "currency": "NGN",
            "initiate_type": "inline",
            "transaction_ref": transaction_ref,
            "callback_url": callback_url,
        }
        if customer_name:
            payload["customer_name"] = customer_name
        if payment_channels:
            payload["payment_channels"] = payment_channels
        else:
            payload["payment_channels"] = ["card", "bank", "transfer", "ussd"]
        if metadata:
            payload["metadata"] = metadata
        return SquadService._post(url, payload)

    @staticmethod
    def verify_transaction(transaction_ref):
        """Server-side status check. data.transaction_status is one of
        pending / success / failed (amounts in kobo)."""
        url = f"{_base_url()}/transaction/verify/{transaction_ref}"
        return SquadService._get(url)

    @staticmethod
    def transaction_is_successful(verify_result) -> bool:
        data = (verify_result or {}).get("data") or {}
        status = str(data.get("transaction_status") or data.get("status") or "").lower()
        return status in ("success", "successful", "completed", "paid", "approved")

    # ------------------------------------------------------------------
    # Dynamic VA (needs Squad profiling — kept for after the account is
    # profiled; checkout above is the primary path until then).
    # ------------------------------------------------------------------
    @staticmethod
    def simulate_payment(virtual_account_number, amount_naira):
        """Push a test credit to a dynamic VA. Sandbox only."""
        url = f"{_base_url()}/virtual-account/simulate/payment"
        payload = {
            "virtual_account_number": str(virtual_account_number),
            "amount": str(amount_naira),
            "dva": True,
        }
        return SquadService._post(url, payload)

    # ------------------------------------------------------------------
    # Webhook verification — x-squad-signature is HMAC SHA512 of raw body
    # signed with the secret key.
    # ------------------------------------------------------------------
    @staticmethod
    def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
        secret = _secret_key()
        if not secret:
            print("[SQUAD WEBHOOK] WARNING: SQUAD_SECRET_KEY not set — skipping check")
            return True
        if not signature:
            return False
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(signature.strip(), expected.strip())

    # ------------------------------------------------------------------
    # HTTP helpers (retry on 502/503/504 like BMONIService)
    # ------------------------------------------------------------------
    @staticmethod
    def _get(url, timeout=12, retries=1, backoff=1.5):
        last_error = None
        for attempt in range(retries + 1):
            try:
                resp = requests.get(url, headers=SquadService.get_headers(), timeout=timeout)
                resp.raise_for_status()
                return SquadService._normalize(resp.json())
            except requests.exceptions.RequestException as e:
                last_error = e
                status = getattr(e.response, "status_code", None)
                if status in (502, 503, 504) and attempt < retries:
                    time.sleep(backoff * (attempt + 1))
                    continue
                break
        return SquadService._error(url, last_error)

    @staticmethod
    def _post(url, payload, timeout=20, retries=1, backoff=1.5):
        last_error = None
        for attempt in range(retries + 1):
            try:
                resp = requests.post(url, json=payload, headers=SquadService.get_headers(), timeout=timeout)
                resp.raise_for_status()
                try:
                    data = resp.json()
                except ValueError:
                    data = None
                return SquadService._normalize(data)
            except requests.exceptions.RequestException as e:
                last_error = e
                status = getattr(e.response, "status_code", None)
                if status in (502, 503, 504) and attempt < retries:
                    time.sleep(backoff * (attempt + 1))
                    continue
                break
        return SquadService._error(url, last_error)

    @staticmethod
    def _normalize(data):
        """Squad returns {status, success, message, data}. Normalise to
        {success, data, message} so views can treat it like BMONI responses."""
        if not isinstance(data, dict):
            return {"success": False, "error": "Empty response from Squad", "data": data}
        ok = data.get("success")
        if ok is None:
            status = data.get("status")
            ok = status in (200, 201) if status is not None else False
        if ok:
            return {"success": True, "data": data.get("data", data), "message": data.get("message")}
        return {
            "success": False,
            "error": data.get("message") or "Squad request failed",
            "data": data.get("data"),
            "response_body": str(data)[:2000],
        }

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
        print(f"[SQUAD] Request error for {url}: {exc}")
        if body:
            print(f"[SQUAD] Response body: {body[:2000]}")
        return {"success": False, "error": str(exc), "status_code": status_code, "response_body": body}


def extract_squad_account(initiate_result):
    """Pull {account_number, bank_name, account_name} out of an initiate response,
    tolerating Squad's varying key names."""
    data = (initiate_result or {}).get("data") or {}
    # Squad nests differently per version — check common shapes.
    candidates = [data]
    for key in ("data", "virtual_account", "virtualAccount", "account"):
        nested = data.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)
    merged = {}
    for c in candidates:
        merged.update(c)
    account_number = (
        merged.get("virtual_account_number")
        or merged.get("account_number")
        or merged.get("accountNumber")
        or merged.get("accountNo")
    )
    bank_name = merged.get("bank_name") or merged.get("bankName") or "Squad (GTCO)"
    account_name = merged.get("account_name") or merged.get("accountName") or ""
    return account_number, bank_name, account_name
