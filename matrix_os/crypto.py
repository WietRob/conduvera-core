from __future__ import annotations
import os
import base64
from dataclasses import dataclass
from typing import Optional
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PBKDF2_ITERATIONS = 200_000
SALT_LEN = 16
NONCE_LEN = 12
MAGIC = b"MXOS1\x00"

@dataclass
class EncryptionResult:
    salt: bytes
    nonce: bytes
    ciphertext: bytes  # includes tag (AESGCM appends it)


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS)
    return kdf.derive(password.encode("utf-8"))


def encrypt_bytes(data: bytes, password: str) -> EncryptionResult:
    salt = os.urandom(SALT_LEN)
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    nonce = os.urandom(NONCE_LEN)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return EncryptionResult(salt=salt, nonce=nonce, ciphertext=ciphertext)


def decrypt_bytes(salt: bytes, nonce: bytes, ciphertext: bytes, password: str) -> bytes:
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def encrypt_file(input_path: str, output_path: str, password: str) -> None:
    with open(input_path, "rb") as f:
        data = f.read()
    result = encrypt_bytes(data, password)
    with open(output_path, "wb") as f:
        f.write(MAGIC)
        f.write(result.salt)
        f.write(result.nonce)
        f.write(result.ciphertext)


def decrypt_file(input_path: str, output_path: str, password: str) -> None:
    with open(input_path, "rb") as f:
        blob = f.read()
    if not blob.startswith(MAGIC):
        raise ValueError("Not a Matrix.OS encrypted file or wrong format")
    salt = blob[len(MAGIC):len(MAGIC)+SALT_LEN]
    nonce = blob[len(MAGIC)+SALT_LEN:len(MAGIC)+SALT_LEN+NONCE_LEN]
    ciphertext = blob[len(MAGIC)+SALT_LEN+NONCE_LEN:]
    plaintext = decrypt_bytes(salt, nonce, ciphertext, password)
    with open(output_path, "wb") as f:
        f.write(plaintext)


def hash_bytes(data: bytes, algo: str = "sha256") -> str:
    algo = algo.lower()
    if algo == "sha256":
        digest = hashes.Hash(hashes.SHA256())
    elif algo == "sha1":
        digest = hashes.Hash(hashes.SHA1())
    elif algo == "blake2b":
        digest = hashes.Hash(hashes.BLAKE2b(64))
    else:
        raise ValueError(f"Unsupported hash algo: {algo}")
    digest.update(data)
    return digest.finalize().hex()


def hash_file(path: str, algo: str = "sha256") -> str:
    if algo.lower() == "blake2b":
        hasher = hashes.Hash(hashes.BLAKE2b(64))
    elif algo.lower() == "sha1":
        hasher = hashes.Hash(hashes.SHA1())
    else:
        hasher = hashes.Hash(hashes.SHA256())
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.finalize().hex()
