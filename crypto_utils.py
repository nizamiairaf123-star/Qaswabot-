"""
crypto_utils.py — Encrypt/Decrypt subscriber Dhan credentials
Uses Fernet symmetric encryption
"""

from cryptography.fernet import Fernet
from config import ENCRYPTION_KEY


def _get_fernet() -> Fernet:
    key = ENCRYPTION_KEY
    if not key:
        raise ValueError("ENCRYPTION_KEY not set in .env")
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()


def generate_key() -> str:
    """Run once to generate key — save to .env as ENCRYPTION_KEY."""
    return Fernet.generate_key().decode()
