import hashlib
import importlib
import secrets
import ecdsa
from ecdsa import SigningKey, VerifyingKey, SECP256k1

# Deferred Keccak backend support so runtime imports succeed even after a package install.
_keccak = None

def _get_keccak_256():
    global _keccak
    if _keccak is not None:
        return _keccak

    # Try pysha3 first.
    try:
        _sha3 = importlib.import_module('sha3')
        def _keccak_256(data=b""):
            k = _sha3.keccak_256()
            if data:
                k.update(data)
            return k
        _keccak = _keccak_256
        return _keccak
    except Exception:
        pass

    # Try pycryptodome. (Recommended on Windows — no C compiler needed.)
    try:
        _pycryptodome_keccak = importlib.import_module('Crypto.Hash.keccak')
        def _keccak_256(data=b""):
            k = _pycryptodome_keccak.new(digest_bits=256)
            if data:
                k.update(data)
            return k
        _keccak = _keccak_256
        return _keccak
    except Exception:
        pass

    # Try OpenSSL-backed hashlib if available.
    try:
        hashlib.new('keccak256')
        def _keccak_256(data=b""):
            k = hashlib.new('keccak256')
            if data:
                k.update(data)
            return k
        _keccak = _keccak_256
        return _keccak
    except Exception:
        _keccak = None
        return None


def _require_keccak_256():
    keccak_impl = _get_keccak_256()
    if keccak_impl is None:
        raise RuntimeError(
            "Keccak-256 implementation not found. Install 'pycryptodome' "
            "(recommended on Windows: pip install pycryptodome) or 'pysha3'."
        )
    return keccak_impl


class EthereumWallet:
    """Utility class for Ethereum wallet operations."""

    @staticmethod
    def generate_private_key():
        """Generate a random Ethereum private key."""
        return secrets.token_hex(32)

    @staticmethod
    def private_key_to_public_key(private_key_hex):
        """Derive public key from private key."""
        # Normalize hex string (allow leading 0x)
        if isinstance(private_key_hex, str) and private_key_hex.startswith('0x'):
            private_key_hex = private_key_hex[2:]
        private_key_bytes = bytes.fromhex(private_key_hex)
        private_key = SigningKey.from_string(private_key_bytes, curve=SECP256k1)
        public_key = private_key.get_verifying_key()
        return public_key.to_string()

    @staticmethod
    def public_key_to_address(public_key_bytes):
        """
        Derive Ethereum address from public key.

        NOTE: this MUST use real Keccak-256, not SHA3-256 — they differ
        (different padding), and using the wrong one silently produces an
        address that does not correspond to this key at all. Previously
        this fell back to hashlib.sha3_256 when no Keccak backend was
        available; that fallback has been removed on purpose — it's safer
        to fail loudly here than to hand back a wrong-but-plausible-looking
        address.
        """
        # Take the last 20 bytes of the Keccak-256 hash of the public key
        # Remove the first byte (0x04 prefix) from uncompressed public key
        if len(public_key_bytes) == 65:
            public_key_bytes = public_key_bytes[1:]  # Remove 0x04 prefix
        keccak_impl = _require_keccak_256()
        keccak_hash = keccak_impl(public_key_bytes).hexdigest()
        address = "0x" + keccak_hash[-40:]
        return address

    @staticmethod
    def generate_wallet():
        """Generate a complete Ethereum wallet (private key, public key, address)."""
        private_key_hex = EthereumWallet.generate_private_key()
        public_key_bytes = EthereumWallet.private_key_to_public_key(private_key_hex)
        address = EthereumWallet.public_key_to_address(public_key_bytes)
        return {
            "private_key": "0x" + private_key_hex,
            "public_key": public_key_bytes.hex(),
            "address": address
        }

    @staticmethod
    def sign_message(private_key_hex, message):
        """
        Sign a message using EIP-191 personal_sign format.
        Returns a 65-byte signature (r + s + v).

        `v` (the recovery id) is computed properly by recovering both
        candidate public keys from the signature and matching against the
        actual signer's public key — NOT hardcoded, since only one of the
        two possible recovery ids is correct for any given signature. A
        hardcoded v would cause ~50% of signatures to fail recovery
        verification on the receiving end (e.g. BMONI) with no obvious
        cause.
        """
        # Accept keys with or without 0x prefix
        if isinstance(private_key_hex, str) and private_key_hex.startswith('0x'):
            private_key_hex = private_key_hex[2:]

        try:
            private_key_bytes = bytes.fromhex(private_key_hex)
            private_key = SigningKey.from_string(private_key_bytes, curve=SECP256k1)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid private key hex: {e}")

        public_key_bytes = private_key.get_verifying_key().to_string()

        # EIP-191: "\x19Ethereum Signed Message:\n" + len(message) + message
        prefix = b"\x19Ethereum Signed Message:\n"
        if isinstance(message, str):
            message = message.encode('utf-8')
        message_length = str(len(message)).encode('utf-8')
        eip191_message = prefix + message_length + message

        # Hash the message using Keccak-256 (Ethereum uses Keccak, not SHA3)
        keccak_impl = _require_keccak_256()
        message_hash = keccak_impl(eip191_message).digest()

        # Sign the hash (canonical low-s form)
        signature = private_key.sign_digest(
            message_hash, sigencode=ecdsa.util.sigencode_string_canonize
        )
        r = signature[:32]
        s = signature[32:64]

        # Determine the correct recovery id by recovering both candidate
        # public keys and matching against the real one.
        recovery_id = None
        try:
            candidates = VerifyingKey.from_public_key_recovery_with_digest(
                signature, message_hash, curve=SECP256k1,
                sigdecode=ecdsa.util.sigdecode_string
            )
            for i, candidate in enumerate(candidates):
                if candidate.to_string() == public_key_bytes:
                    recovery_id = i
                    break
        except Exception as e:
            raise RuntimeError(f"Could not recover public key candidates from signature: {e}")

        if recovery_id is None:
            raise RuntimeError(
                "Could not determine ECDSA recovery id — recovered public "
                "key candidates did not match the signer's public key."
            )

        v = bytes([27 + recovery_id])

        # Combine r + s + v (65 bytes total)
        full_signature = r + s + v
        return "0x" + full_signature.hex()

    @staticmethod
    def sign_challenge(private_key_hex, challenge_message):
        """
        Sign a BMONI owner-proof challenge message.
        """
        return EthereumWallet.sign_message(private_key_hex, challenge_message)


# Server-side wallet manager for development
class ServerWalletManager:
    """
    Manages server-side wallet generation for BMONI integration.

    NOTE: generating and holding private keys server-side (even for
    "development") means whoever has access to wherever these are stored
    can move funds from any wallet created this way. Fine for sandbox
    testing; do not carry this pattern into production without a proper
    key-management approach (HSM/KMS, encryption at rest, or moving
    signing to the client entirely).
    """

    @staticmethod
    def create_wallet_for_user():
        """Generate and store a wallet for a user."""
        wallet = EthereumWallet.generate_wallet()
        return wallet

    @staticmethod
    def sign_bmoni_challenge(private_key_hex, challenge_message):
        """Sign a BMONI challenge message."""
        return EthereumWallet.sign_challenge(private_key_hex, challenge_message)