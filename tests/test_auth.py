import base64
import json
import threading
import unittest
from http.cookiejar import Cookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from mi_scale_exporter import auth


def make_cookie(name, value, domain, path="/"):
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=True,
        domain_initial_dot=domain.startswith("."),
        path=path,
        path_specified=True,
        secure=False,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )


class PollResponse:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class PollOpener:
    def __init__(self, bodies):
        self.bodies = iter(bodies)
        self.calls = 0

    def open(self, request, timeout=None):
        self.calls += 1
        return PollResponse(next(self.bodies))


class BrokenReadResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        raise ConnectionResetError("connection reset while reading")


class BrokenReadOpener:
    handlers = []

    def open(self, request, timeout=None):
        return BrokenReadResponse()


class FlakyPollOpener(PollOpener):
    def __init__(self, bodies, failures=1):
        super().__init__(bodies)
        self.failures = failures

    def open(self, request, timeout=None):
        self.calls += 1
        if self.failures:
            self.failures -= 1
            return BrokenReadResponse()
        return PollResponse(next(self.bodies))


class AuthTest(unittest.TestCase):
    def test_parse_jsonp(self):
        payload = {"result": "ok", "userId": 123}
        self.assertEqual(auth.parse_login_json("&&&START&&&" + json.dumps(payload)), payload)

    def test_parse_empty(self):
        self.assertEqual(auth.parse_login_json(""), {})

    def test_parse_non_dict(self):
        with self.assertRaises(auth.LoginResponseError):
            auth.parse_login_json("[1, 2, 3]")

    def test_open_json_wraps_read_error(self):
        with self.assertRaises(auth.AuthError):
            auth._open_json(BrokenReadOpener(), object(), 5)

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

    def test_cookie_header_is_scoped_to_mi_domains(self):
        opener = auth._build_opener()
        for handler in opener.handlers:
            jar = getattr(handler, "cookiejar", None)
            if jar is not None:
                jar.set_cookie(make_cookie("passToken", "account-secret", ".account.xiaomi.com"))
                jar.set_cookie(make_cookie("serviceToken", "service-secret", ".sts.api.io.mi.com"))
                jar.set_cookie(make_cookie("userId", "123", ".sts.api.io.mi.com"))
                jar.set_cookie(
                    make_cookie("pathScoped", "app-only", ".sts.api.io.mi.com", path="/app")
                )
                break

        scoped = auth._cookie_header(opener, "mi.com", target_path="/eco/scale/getData")
        self.assertIn("serviceToken=service-secret", scoped)
        self.assertIn("userId=123", scoped)
        self.assertNotIn("account-secret", scoped)
        self.assertNotIn("app-only", scoped)
        self.assertIn("app-only", auth._cookie_header(opener, "mi.com", target_path="/app/eco"))

    def test_poll_qr_login_retries_on_bad_html(self):
        opener = PollOpener(
            [
                b"<html>bad gateway</html>",
                json.dumps({"userId": 123, "passToken": "pt"}).encode(),
            ]
        )
        challenge = auth.QrChallenge(
            login_url="https://example.invalid/login",
            qr_url="https://example.invalid/qr",
            poll_url="https://example.invalid/poll",
            timeout=10,
            agent="test-agent",
        )
        with patch.object(auth, "_finish_login", return_value="finished") as finish, patch.object(
            auth.time, "sleep", return_value=None
        ):
            result = auth.poll_qr_login(opener, challenge, max_wait=10)

        self.assertEqual(result, "finished")
        self.assertEqual(opener.calls, 2)
        finish.assert_called_once()

    def test_poll_qr_login_retries_on_network_error(self):
        opener = FlakyPollOpener(
            [json.dumps({"userId": 123, "passToken": "pt"}).encode()],
            failures=1,
        )
        challenge = auth.QrChallenge(
            login_url="https://example.invalid/login",
            qr_url="https://example.invalid/qr",
            poll_url="https://example.invalid/poll",
            timeout=10,
            agent="test-agent",
        )
        with patch.object(auth, "_finish_login", return_value="finished"), patch.object(
            auth.time, "sleep", return_value=None
        ):
            result = auth.poll_qr_login(opener, challenge, max_wait=10)
        self.assertEqual(result, "finished")
        self.assertEqual(opener.calls, 2)

    def test_poll_qr_login_rejects_error_response(self):
        opener = PollOpener(
            [
                json.dumps(
                    {"result": "error", "description": "二维码已过期"}
                ).encode()
            ]
        )
        challenge = auth.QrChallenge(
            login_url="https://example.invalid/login",
            qr_url="https://example.invalid/qr",
            poll_url="https://example.invalid/poll",
            timeout=10,
            agent="test-agent",
        )
        with self.assertRaises(auth.AuthError) as ctx:
            auth.poll_qr_login(opener, challenge, max_wait=10)
        self.assertIn("二维码已过期", str(ctx.exception))

    def test_poll_qr_login_timeout(self):
        challenge = auth.QrChallenge(
            login_url="https://example.invalid/login",
            qr_url="https://example.invalid/qr",
            poll_url="https://example.invalid/poll",
            timeout=10,
            agent="test-agent",
        )
        with self.assertRaises(auth.AuthError) as ctx:
            auth.poll_qr_login(PollOpener([]), challenge, max_wait=0)
        self.assertIn("超时", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
