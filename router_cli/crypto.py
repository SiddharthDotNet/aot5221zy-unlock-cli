"""OpenSSL-compatible router backup encryption."""

import hashlib
import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

FIRMWARE_KEY = "EwhJaD44DfprDOs7OXx9jzAtLg5PKtD8"


def evp_bytes_to_key(password: bytes, salt: bytes):
    d, d_i = b"", b""
    while len(d) < 48:
        d_i = hashlib.md5(d_i + password + salt).digest()
        d += d_i
    return d[:32], d[32:48]


def encrypt_config_bytes(data: bytes, password: str) -> bytes:
    salt = os.urandom(8)
    key, iv = evp_bytes_to_key(password.encode("utf-8"), salt)
    pad_len = 16 - (len(data) % 16)
    data = data + bytes([pad_len] * pad_len)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(data) + encryptor.finalize()
    return b"Salted__" + salt + encrypted


def decrypt_config_bytes(data: bytes, password: str) -> bytes:
    if data[:8] != b"Salted__":
        raise ValueError(
            "File does not have the expected 'Salted__' header - not an OpenSSL-encrypted backup."
        )
    salt = data[8:16]
    encrypted = data[16:]
    if not encrypted or len(encrypted) % 16:
        raise ValueError("Incomplete encrypted backup.")
    key, iv = evp_bytes_to_key(password.encode("utf-8"), salt)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted_padded = decryptor.update(encrypted) + decryptor.finalize()
    pad_len = decrypted_padded[-1]
    if not 1 <= pad_len <= 16 or decrypted_padded[-pad_len:] != bytes([pad_len]) * pad_len:
        raise ValueError("Invalid backup padding. Check the file and password.")
    return decrypted_padded[:-pad_len]
