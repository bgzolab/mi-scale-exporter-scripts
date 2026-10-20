import base64
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from mi_scale_exporter import auth


class AuthTest(unittest.TestCase):
    def test_parse_jsonp(self):
        payload = {"result": "ok", "userId": 123}
        self.assertEqual(auth.parse_login_json("&&&START&&&" + json.dumps(payload)), payload)

    def test_parse_empty(self):
        self.assertEqual(auth.parse_login_json(""), {})

    def test_login_with_pass_token(self):
        ssecurity = base64.b64encode(b"x" * 32).decode()
        state = {"port": 0}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith("/pass/serviceLogin"):
                    body = "&&&START&&&" + json.dumps(
                        {
                            "result": "ok",
                            "ssecurity": ssecurity,
                            "location": f"http://127.0.0.1:{state['port']}/sts",
                            "userId": 123,
                            "passToken": "pt",
                        }
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body.encode())
                elif self.path.startswith("/sts"):
                    self.send_response(200)
                    self.send_header("Set-Cookie", "serviceToken=abc; Path=/")
                    self.send_header("Set-Cookie", "userId=123; Path=/")
                    self.end_headers()
                    self.wfile.write(b"ok")
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        state["port"] = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(
                auth,
                "ACCOUNT_SERVICE_LOGIN",
                f"http://127.0.0.1:{server.server_port}/pass/serviceLogin?_json=true&sid=xiaomiio",
            ):
                result = auth.login_with_pass_token(123, "pt", timeout=5)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(result.user_id, 123)
        self.assertEqual(result.pass_token, "pt")
        self.assertIn("serviceToken=abc", result.cookie_header)
        self.assertEqual(result.ssecurity, b"x" * 32)


if __name__ == "__main__":
    unittest.main()
