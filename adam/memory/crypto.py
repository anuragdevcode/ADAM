"""Authenticated encryption engine for conversation memory at rest using standard AES-256-GCM.

Provides field-level authenticated encryption for conversational turns, session summaries,
and user preferences using standard AES-GCM (via the `cryptography` library).
Supports key versioning and key separation via MEMORY_ENCRYPTION_KEY.
"""

import base64
import hashlib
import json
import os
import secrets
from typing import Any, Dict, Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from adam.config import get_memory_encryption_key, get_signing_secret


class MemoryCryptoError(Exception):
    """Raised when encryption or decryption fails (e.g., tampering, corrupt ciphertext, invalid key)."""
    pass


class AuthenticatedCipher:
    """Authenticated field-level cipher using standard AES-256-GCM with key versioning.

    Format of encrypted token:
        Base64( VERSION [1 byte] + NONCE [12 bytes] + CIPHERTEXT_AND_TAG [N + 16 bytes] )
    """

    CURRENT_VERSION = 1

    def __init__(
        self,
        key: Optional[bytes] = None,
        key_ring: Optional[Dict[int, bytes]] = None,
        active_version: int = CURRENT_VERSION,
    ):
        self.active_version = active_version
        self._key_ring: Dict[int, bytes] = {}

        if key_ring:
            for v, k in key_ring.items():
                self._key_ring[v] = self._normalize_key(k)
        elif key:
            self._key_ring[self.active_version] = self._normalize_key(key)
        else:
            default_key = get_memory_encryption_key().encode("utf-8")
            self._key_ring[self.active_version] = self._normalize_key(default_key)

    @staticmethod
    def _normalize_key(key: bytes) -> bytes:
        """Ensure key is exactly 32 bytes (256 bits) for AES-256-GCM."""
        if len(key) == 32:
            return key
        return hashlib.sha256(b"ADAM-AES256-MEMORY-KEY:" + key).digest()

    def encrypt(self, plaintext: str, version: Optional[int] = None) -> str:
        """Encrypt plaintext string into base64 authenticated ciphertext token using AES-GCM."""
        if not isinstance(plaintext, str):
            raise TypeError("Plaintext must be a string")

        target_version = version or self.active_version
        key = self._key_ring.get(target_version)
        if not key:
            raise MemoryCryptoError(f"No key available for encryption version {target_version}")

        data = plaintext.encode("utf-8")
        nonce = secrets.token_bytes(12)  # Standard 96-bit nonce for AES-GCM
        aesgcm = AESGCM(key)
        ciphertext_and_tag = aesgcm.encrypt(nonce, data, None)

        version_byte = bytes([target_version & 0xFF])
        raw = version_byte + nonce + ciphertext_and_tag
        return base64.b64encode(raw).decode("ascii")

    def decrypt(self, token: str) -> str:
        """Decrypt base64 token and verify integrity. Raises MemoryCryptoError on tampering."""
        if not isinstance(token, str):
            raise TypeError("Token must be a string")

        try:
            raw = base64.b64decode(token.encode("ascii"))
        except Exception as e:
            raise MemoryCryptoError(f"Invalid base64 encoding: {e}") from e

        # 1 byte version + 12 bytes nonce + 16 bytes minimum AES-GCM tag = 29 bytes
        if len(raw) < 29:
            raise MemoryCryptoError("Ciphertext payload is truncated or invalid")

        version = raw[0]
        nonce = raw[1:13]
        ciphertext_and_tag = raw[13:]

        key = self._key_ring.get(version)
        if not key:
            # Check for legacy token format migration
            try:
                return self._decrypt_legacy(raw)
            except Exception:
                raise MemoryCryptoError(f"Unknown key version: {version}")

        aesgcm = AESGCM(key)
        try:
            decrypted = aesgcm.decrypt(nonce, ciphertext_and_tag, None)
        except InvalidTag as e:
            raise MemoryCryptoError("Integrity check failed: ciphertext has been modified or wrong key") from e
        except Exception as e:
            raise MemoryCryptoError(f"Decryption failed: {e}") from e

        try:
            return decrypted.decode("utf-8")
        except UnicodeDecodeError as e:
            raise MemoryCryptoError(f"Decoded data is not valid UTF-8: {e}") from e

    def _decrypt_legacy(self, raw: bytes) -> str:
        """Decrypt legacy SHA-256 CTR + HMAC token to allow seamless migration to AES-GCM."""
        import hmac
        if len(raw) < 48:
            raise MemoryCryptoError("Ciphertext payload is truncated")
        iv = raw[:16]
        tag = raw[16:48]
        ciphertext = raw[48:]

        keys_to_try = [
            get_memory_encryption_key().encode("utf-8"),
            get_signing_secret().encode("utf-8"),
            b"adam-uk-gov-default-auth-secret-key-2026",
            b"adam-uk-gov-default-memory-encryption-key-2026",
        ]
        for k in self._key_ring.values():
            keys_to_try.append(k)

        for raw_k in keys_to_try:
            derived = hashlib.sha256(raw_k).digest()
            enc_key = derived[:16]
            mac_key = derived[16:]
            expected_tag = hmac.new(mac_key, iv + ciphertext, hashlib.sha256).digest()
            if hmac.compare_digest(tag, expected_tag):
                keystream = b""
                counter = 0
                while len(keystream) < len(ciphertext):
                    keystream += hashlib.sha256(enc_key + iv + counter.to_bytes(4, "big")).digest()
                    counter += 1
                data = bytes(a ^ b for a, b in zip(ciphertext, keystream[:len(ciphertext)]))
                return data.decode("utf-8")

        raise MemoryCryptoError("Legacy ciphertext integrity check failed")


    def reencrypt(self, token: str, target_version: Optional[int] = None) -> str:
        """Decrypt token using its version key and re-encrypt under target_version (or active_version)."""
        plaintext = self.decrypt(token)
        return self.encrypt(plaintext, version=target_version)

    def encrypt_json(self, data: Any, version: Optional[int] = None) -> str:
        """Serialize data to JSON and encrypt."""
        return self.encrypt(json.dumps(data, ensure_ascii=False), version=version)

    def decrypt_json(self, token: str) -> Any:
        """Decrypt token and parse as JSON."""
        plaintext = self.decrypt(token)
        try:
            return json.loads(plaintext)
        except json.JSONDecodeError as e:
            raise MemoryCryptoError(f"Decrypted text is not valid JSON: {e}") from e


_DEFAULT_CIPHER: Optional[AuthenticatedCipher] = None


def get_cipher() -> AuthenticatedCipher:
    """Singleton getter for default memory cipher."""
    global _DEFAULT_CIPHER
    if _DEFAULT_CIPHER is None:
        _DEFAULT_CIPHER = AuthenticatedCipher()
    return _DEFAULT_CIPHER


def reset_cipher():
    """Reset cipher singleton (useful for test isolation when keys change)."""
    global _DEFAULT_CIPHER
    _DEFAULT_CIPHER = None
