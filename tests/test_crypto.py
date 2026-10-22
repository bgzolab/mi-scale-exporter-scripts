import base64
import unittest

from mi_scale_exporter.crypto import (
    encrypt_request,
    gen_signed_nonce,
    rc4_crypt,
)

# Generated with the Go implementation in AlexxIT/SmartScaleConnect.
SSECURITY = b"0123456789abcdef0123456789abcdef"
NONCE = bytes(range(12))
DATA = '{"param":{"endTime":1,"beginTime":1700000000000},"model":"xiaomi.scales.ms116","uid":123456789,"did":0}'
EXPECTED_SN = "0iQ2q5G3xk4MTKf+yvY8oglLNZ8QbpSSvdR/786Wm8o="
EXPECTED_RC4 = (
    "aZ8ryWd1t3SG5T4rPTG4a0NUgMMKai2Epdhaqsno0NZtv3ycKfaRALzFx34GMP29"
    "Sa/iQ1uC0fgd3TB6IwUqNP9ZCbm+9lUKUOK8ine+/x7SMS49AWw+IZxyRtJPsqpa0hEALII+Ow=="
)
EXPECTED_DATA = EXPECTED_RC4
EXPECTED_HASH = "J80+wVN/qSPL3S4AIDeYb2d/+4pBNVmAuIpU+Q=="
EXPECTED_SIG = "JqYt0QsN7qtJwHU0vPt4zeC0RbU="


class CryptoVectorTest(unittest.TestCase):
    def test_signed_nonce(self):
        self.assertEqual(base64.b64encode(gen_signed_nonce(SSECURITY, NONCE)).decode(), EXPECTED_SN)

    def test_rc4(self):
        self.assertEqual(base64.b64encode(rc4_crypt(gen_signed_nonce(SSECURITY, NONCE), DATA.encode())).decode(), EXPECTED_RC4)

    def test_request_matches_go_client(self):
        values, _ = encrypt_request("/eco/scale/getData", DATA, SSECURITY, nonce=NONCE)
        self.assertEqual(values["data"], EXPECTED_DATA)
        self.assertEqual(values["rc4_hash__"], EXPECTED_HASH)
        self.assertEqual(values["signature"], EXPECTED_SIG)
        self.assertEqual(values["_nonce"], base64.b64encode(NONCE).decode())

    def test_rc4_roundtrip(self):
        key = b"some-key"
        plaintext = "小米体脂秤 S800".encode()
        self.assertEqual(rc4_crypt(key, rc4_crypt(key, plaintext)), plaintext)


if __name__ == "__main__":
    unittest.main()
