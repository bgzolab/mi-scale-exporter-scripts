import base64
import json
import os
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from mi_scale_exporter import auth, cli, cloud
from mi_scale_exporter.crypto import gen_signed_nonce, rc4_crypt

SSECURITY = b"0123456789abcdef0123456789abcdef"


def record(index):
    timestamp = 1755927448000 - index * 1000
    return {
        "model": "xiaomi.scales.ms116",
        "createTime": timestamp,
        "did": "blt.3.test",
        "fromSource": 3,
        "data": json.dumps(
            {
                "weight": str(63.15 - index / 10),
                "bmi": "20.8",
                "heartRate": 72,
                "time": str(timestamp),
                "user": {"name": "Alice", "height": 174},
                "bodyResData": json.dumps(
                    {
                        "bfp": "16.5",
                        "bwp": "61.8",
                        "bmc": "2.9",
                        "ma": "35.0",
                        "slm": "49.8",
                        "pm": "10.3",
                        "vfl": "4.0",
                        "bmr": "1508.0",
                        "sbc": "79.0",
                        "smm": "28.6",
                        "bt": "4.0",
                        "ram": "2.7",
                    }
                ),
            }
        ),
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/pass/serviceLogin"):
            body = "&&&START&&&" + json.dumps(
                {
                    "result": "ok",
                    "ssecurity": base64.b64encode(SSECURITY).decode(),
                    "location": f"http://127.0.0.1:{self.server.server_port}/sts",
                    "userId": 123,
                    "passToken": "pt",
                }
            )
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body.encode())
        elif self.path.startswith("/sts"):
            self.send_response(200)
            self.send_header("Set-Cookie", "serviceToken=abc; Path=/")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode())
        nonce = base64.b64decode(form["_nonce"][0])
        signed_nonce = gen_signed_nonce(SSECURITY, nonce)
        result = [record(0), record(1)]
        payload = json.dumps({"code": 0, "message": "ok", "result": result}).encode()
        encrypted = base64.b64encode(rc4_crypt(signed_nonce, payload))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(encrypted)

    def log_message(self, *args):
        pass


class CliTest(unittest.TestCase):
    def test_export_csv_end_to_end(self):
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp) / "weights.csv"
                config = Path(tmp) / "credentials.json"
                with patch.object(
                    auth,
                    "ACCOUNT_SERVICE_LOGIN",
                    f"http://127.0.0.1:{server.server_port}/pass/serviceLogin?_json=true&sid=xiaomiio",
                ), patch.object(cloud, "CN_BASE_URL", f"http://127.0.0.1:{server.server_port}/app"), patch.dict(
                    os.environ, {"MI_SCALE_NO_ENV": "1"}
                ):
                    code = cli.main(
                        [
                            "export",
                            "--user-id",
                            "123",
                            "--pass-token",
                            "pt",
                            "--config",
                            str(config),
                            "-o",
                            str(output),
                        ]
                    )
                self.assertEqual(code, 0)
                text = output.read_text(encoding="utf-8-sig")
                self.assertIn("weight_kg", text)
                self.assertIn("63.15", text)
                self.assertIn("Alice", text)
                self.assertIn("16.5", text)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
