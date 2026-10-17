from cryptography.fernet import Fernet
import base64
import hashlib


def _derive_fernet_key(raw_key: bytes) -> bytes:
    digest = hashlib.sha256(raw_key).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(plaintext: str, key: bytes) -> bytes:
    f = Fernet(_derive_fernet_key(key))
    return f.encrypt(plaintext.encode())


def decrypt_secret(ciphertext: bytes, key: bytes) -> str:
    f = Fernet(_derive_fernet_key(key))
    return f.decrypt(ciphertext).decode()
