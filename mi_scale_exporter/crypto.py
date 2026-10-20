"""Crypto helpers for the unofficial Xiaomi Cloud app API.

The Xiaomi app API signs and encrypts request parameters with a per-session
``ssecurity`` value.  The implementation mirrors the well-known Go/C# clients
used by SmartScaleConnect and yet-another-xiaomi-cloud-client.
"""

from __future__ import annotations

import base64
import hashlib
import os
import struct
import time
from typing import Dict, Optional, Tuple


def gen_nonce(now: Optional[float] = None) -> bytes:
    """Return a 12-byte nonce: 8 random bytes + minutes since epoch (BE)."""
    ts = int(time.time() if now is None else now)
    return os.urandom(8) + struct.pack(">I", (ts // 60) & 0xFFFFFFFF)


def gen_signed_nonce(ssecurity: bytes, nonce: bytes) -> bytes:
    return hashlib.sha256(ssecurity + nonce).digest()


def rc4_crypt(key: bytes, data: bytes) -> bytes:
    """RC4 with the first 1024 keystream bytes dropped (Xiaomi's variant)."""
    state = list(range(256))
    j = 0
    for i in range(256):
        j = (j + state[i] + key[i % len(key)]) & 0xFF
        state[i], state[j] = state[j], state[i]

    i = 0
    j = 0
    # Drop 1024 bytes of keystream.
    for _ in range(1024):
        i = (i + 1) & 0xFF
        j = (j + state[i]) & 0xFF
        state[i], state[j] = state[j], state[i]
        _ = state[(state[i] + state[j]) & 0xFF]

    out = bytearray(len(data))
    for n, byte in enumerate(data):
        i = (i + 1) & 0xFF
        j = (j + state[i]) & 0xFF
        state[i], state[j] = state[j], state[i]
        out[n] = byte ^ state[(state[i] + state[j]) & 0xFF]
    return bytes(out)


def gen_signature(method: str, path: str, values: Dict[str, str], signed_nonce: bytes) -> str:
    """Build the base64 SHA-1 signature used by the Xiaomi app API."""
    text = f"{method}&{path}&data={values.get('data', '')}"
    if values.get("rc4_hash__"):
        text += f"&rc4_hash__={values['rc4_hash__']}"
    text += "&" + base64.b64encode(signed_nonce).decode()
    return base64.b64encode(hashlib.sha1(text.encode()).digest()).decode()


def encrypt_request(
    path: str,
    data_json: str,
    ssecurity: bytes,
    nonce: Optional[bytes] = None,
) -> Tuple[Dict[str, str], bytes]:
    """Return form values for a signed/encrypted Xiaomi app request."""
    nonce = gen_nonce() if nonce is None else nonce
    signed_nonce = gen_signed_nonce(ssecurity, nonce)

    values: Dict[str, str] = {"data": data_json}
    values["rc4_hash__"] = gen_signature("POST", path, values, signed_nonce)

    for key in list(values):
        values[key] = base64.b64encode(
            rc4_crypt(signed_nonce, values[key].encode())
        ).decode()

    values["signature"] = gen_signature("POST", path, values, signed_nonce)
    values["_nonce"] = base64.b64encode(nonce).decode()
    return values, signed_nonce


def decrypt_response(payload: str, signed_nonce: bytes) -> bytes:
    return rc4_crypt(signed_nonce, base64.b64decode(payload))
