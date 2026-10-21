import base64
import json
import unittest
import urllib.parse

from mi_scale_exporter.auth import AuthResult
from mi_scale_exporter.cloud import CloudError, XiaomiCloudClient
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


class FakeErrorOpener(FakeOpener):
    def open(self, request, timeout=None):
        form = urllib.parse.parse_qs(request.data.decode())
        nonce = base64.b64decode(form["_nonce"][0])
        signed_nonce = gen_signed_nonce(SSECURITY, nonce)
        payload = json.dumps({"code": 100, "message": "bad request"}).encode()
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

    def test_page_tail_not_dict(self):
        first = [item(i) for i in range(19)] + [None]
        opener = FakeOpener([first])
        auth = AuthResult(123, "token", SSECURITY, opener, "serviceToken=abc")
        records = XiaomiCloudClient(auth).get_raw_records()
        self.assertEqual(len(records), 19)
        self.assertEqual(len(opener.calls), 1)

    def test_data_can_be_dict(self):
        record = item(0)
        record["data"] = {"weight": "63.15", "time": "1755927448000"}
        opener = FakeOpener([[record]])
        auth = AuthResult(123, "token", SSECURITY, opener, "serviceToken=abc")
        records = XiaomiCloudClient(auth).get_raw_records()
        self.assertEqual(len(records), 1)

    def test_api_error(self):
        opener = FakeErrorOpener([[]])
        auth = AuthResult(123, "token", SSECURITY, opener, "serviceToken=abc")
        with self.assertRaises(CloudError):
            XiaomiCloudClient(auth).get_raw_records()

    def test_since_until_filter(self):
        base = 1755927448000
        records = [item(i) for i in range(10)]
        opener = FakeOpener([records])
        auth = AuthResult(123, "token", SSECURITY, opener, "serviceToken=abc")
        result = XiaomiCloudClient(auth).get_raw_records(
            since_ms=base - 5000,
            until_ms=base - 2000,
        )
        self.assertEqual([r["createTime"] for r in result], [base - 2000, base - 3000, base - 4000, base - 5000])


if __name__ == "__main__":
    unittest.main()
