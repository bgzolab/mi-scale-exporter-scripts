import base64
import json
import unittest
import urllib.parse

from mi_scale_exporter.auth import AuthResult
from mi_scale_exporter.cloud import XiaomiCloudClient
from mi_scale_exporter.crypto import gen_signed_nonce, rc4_crypt


class FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeOpener:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def open(self, request, timeout=None):
        form = urllib.parse.parse_qs(request.data.decode())
        nonce = base64.b64decode(form["_nonce"][0])
        signed_nonce = gen_signed_nonce(SSECURITY, nonce)
        params = json.loads(rc4_crypt(signed_nonce, base64.b64decode(form["data"][0])).decode())
        self.calls.append(params)
        result = self.pages[len(self.calls) - 1]
        payload = json.dumps({"code": 0, "message": "ok", "result": result}).encode()
        encrypted = base64.b64encode(rc4_crypt(signed_nonce, payload))
        return FakeResponse(encrypted)


SSECURITY = b"0123456789abcdef0123456789abcdef"


def item(index):
    return {
        "model": "xiaomi.scales.ms116",
        "createTime": 1755927448000 - index * 1000,
        "did": "blt.3.test",
        "fromSource": 3,
        "data": json.dumps(
            {
                "weight": str(60 + index / 10),
                "time": str(1755927448000 - index * 1000),
                "bodyResData": json.dumps({"bfp": "16.5"}),
            }
        ),
    }


class CloudTest(unittest.TestCase):
    def test_pagination(self):
        first = [item(i) for i in range(20)]
        second = [item(i) for i in range(20, 25)]
        opener = FakeOpener([first, second])
        auth = AuthResult(
            user_id=123,
            pass_token="token",
            ssecurity=SSECURITY,
            opener=opener,
            cookie_header="serviceToken=abc",
        )
        client = XiaomiCloudClient(auth, region="cn", model="xiaomi.scales.ms116")
        records = client.get_raw_records()
        self.assertEqual(len(records), 25)
        self.assertEqual(len(opener.calls), 2)
        self.assertEqual(opener.calls[0]["uid"], 123)
        self.assertEqual(opener.calls[0]["model"], "xiaomi.scales.ms116")
        self.assertEqual(opener.calls[1]["param"]["beginTime"], first[19]["createTime"])

    def test_limit(self):
        opener = FakeOpener([[item(i) for i in range(20)], [item(i) for i in range(20, 30)]])
        auth = AuthResult(123, "token", SSECURITY, opener, "serviceToken=abc")
        client = XiaomiCloudClient(auth)
        records = client.get_raw_records(limit=5)
        self.assertEqual(len(records), 5)
        self.assertEqual(len(opener.calls), 1)


if __name__ == "__main__":
    unittest.main()
