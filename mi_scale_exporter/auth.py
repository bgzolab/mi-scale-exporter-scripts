"""Xiaomi account login helpers.

Two authentication modes are supported:

* ``login_with_pass_token`` – use the ``userId``/``passToken`` cookies that a
  logged-in browser session already has.
* ``start_qr_login`` / ``poll_qr_login`` – the same QR-code flow used by the
  Xiaomi Home app and the web version of mi-scale-exporter.

Only the standard library is required.
"""

from __future__ import annotations

import base64
import http.client
import json
import random
import string
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

LOGIN_PREFIX = "&&&START&&&"
ACCOUNT_SERVICE_LOGIN = "https://account.xiaomi.com/pass/serviceLogin?_json=true&sid=xiaomiio"
ACCOUNT_LONG_POLLING = "https://account.xiaomi.com/longPolling/loginUrl"
STS_CALLBACK = "https://sts.api.io.mi.com/sts"


class AuthError(RuntimeError):
    """Raised when Xiaomi rejects or cannot complete a login."""


class LoginResponseError(AuthError):
    """Raised when an account endpoint returns a non-JSON transient response."""


@dataclass
class AuthResult:
    user_id: int
    pass_token: str
    ssecurity: bytes
    opener: urllib.request.OpenerDirector
    cookie_header: str

    def cookie_header_for(self, domain_suffix: str = "mi.com", target_path: str = "/") -> str:
        """Return a Cookie header scoped to the Xiaomi app API hosts."""
        return _cookie_header(self.opener, domain_suffix=domain_suffix, target_path=target_path)

    def cookie_names(self) -> list[str]:
        """Cookie names only, useful for debugging without leaking values."""
        return [part.split("=", 1)[0] for part in self.cookie_header.split("; ") if part]


@dataclass
class QrChallenge:
    login_url: str
    qr_url: str
    poll_url: str
    timeout: int = 300
    agent: str = ""


def generate_agent() -> str:
    """Generate a User-Agent similar to the Xiaomi Home Android app."""
    agent_id = "".join(random.choice(string.ascii_uppercase[:5]) for _ in range(13))
    random_text = "".join(random.choice(string.ascii_lowercase) for _ in range(18))
    return f"{random_text}-{agent_id} APP/com.xiaomi.mihome APPV/10.5.201"


def parse_login_json(text: str) -> dict:
    """Strip Xiaomi's ``&&&START&&&`` JSONP prefix and parse the payload."""
    text = text.strip()
    if text.startswith(LOGIN_PREFIX):
        text = text[len(LOGIN_PREFIX) :]
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        preview = text[:200].replace("\n", " ")
        raise LoginResponseError(f"小米账号返回了无法解析的响应: {preview!r}") from exc
    if not isinstance(parsed, dict):
        raise LoginResponseError(
            f"小米账号返回了意外的响应结构: {type(parsed).__name__}"
        )
    return parsed


def _build_opener() -> urllib.request.OpenerDirector:
    jar = urllib.request.HTTPCookieProcessor()
    return urllib.request.build_opener(jar)


def _open_json(opener: urllib.request.OpenerDirector, request: urllib.request.Request, timeout: float) -> dict:
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AuthError(f"小米账号 HTTP {exc.code}: {body[:200]}") from exc
    except (OSError, http.client.HTTPException) as exc:
        raise AuthError(f"无法连接小米账号服务: {exc}") from exc
    return parse_login_json(body)


def _domain_matches(domain: str, suffix: str) -> bool:
    domain = domain.lstrip(".").lower()
    suffix = suffix.lstrip(".").lower()
    return domain == suffix or domain.endswith("." + suffix)


def _path_matches(request_path: str, cookie_path: str) -> bool:
    """RFC 6265 path-match: /app matches /app and /app/..., not /apple."""
    cookie_path = cookie_path or "/"
    if request_path == cookie_path:
        return True
    if not request_path.startswith(cookie_path):
        return False
    return cookie_path.endswith("/") or request_path[len(cookie_path)] == "/"


def _cookie_header(
    opener: urllib.request.OpenerDirector,
    domain_suffix: Optional[str] = None,
    target_path: str = "/",
) -> str:
    """Return cookies as a Cookie header, optionally scoped by domain/path.

    Xiaomi stores the service cookies on ``.sts.api.io.mi.com`` while the app
    API lives on ``api.io.mi.com``.  Both are under ``mi.com``; the account
    cookies on ``account.xiaomi.com`` / ``.xiaomi.com`` do not need to be sent
    to the API.
    """
    pairs: dict[str, str] = {}
    for handler in opener.handlers:
        jar = getattr(handler, "cookiejar", None)
        if jar is None:
            continue
        for cookie in jar:
            if domain_suffix and not _domain_matches(cookie.domain, domain_suffix):
                continue
            if target_path and not _path_matches(target_path, cookie.path or "/"):
                continue
            pairs[cookie.name] = cookie.value
    return "; ".join(f"{name}={value}" for name, value in pairs.items())


def _finish_login(
    opener: urllib.request.OpenerDirector,
    data: dict,
    fallback_user_id: int,
    fallback_pass_token: str,
    timeout: float,
    agent: Optional[str] = None,
) -> AuthResult:
    result = data.get("result")
    if result not in (None, "ok"):
        message = data.get("description") or data.get("desc") or data.get("message") or result
        raise AuthError(f"小米账号登录失败: {message}")

    ssecurity_b64 = data.get("ssecurity")
    if not ssecurity_b64:
        raise AuthError("小米账号响应中没有 ssecurity，登录未完成")
    try:
        ssecurity = base64.b64decode(ssecurity_b64)
    except Exception as exc:
        raise AuthError("小米账号返回的 ssecurity 不是有效的 base64") from exc

    location = data.get("location")
    if not location:
        raise AuthError("小米账号响应中没有跳转地址，登录未完成")

    headers = {"User-Agent": agent or generate_agent()}
    try:
        with opener.open(urllib.request.Request(location, headers=headers), timeout=timeout) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AuthError(f"获取小米服务凭证失败 (HTTP {exc.code}): {body[:200]}") from exc
    except (OSError, http.client.HTTPException) as exc:
        raise AuthError(f"获取小米服务凭证失败: {exc}") from exc

    cookie_header = _cookie_header(opener)
    if not cookie_header:
        raise AuthError("登录成功但未获得服务 Cookie，请重试")

    user_id = int(data.get("userId") or fallback_user_id)
    pass_token = str(data.get("passToken") or fallback_pass_token)
    return AuthResult(
        user_id=user_id,
        pass_token=pass_token,
        ssecurity=ssecurity,
        opener=opener,
        cookie_header=cookie_header,
    )


def login_with_pass_token(
    user_id: int,
    pass_token: str,
    timeout: float = 30.0,
) -> AuthResult:
    """Exchange ``userId`` + ``passToken`` cookies for a service session."""
    if not user_id:
        raise AuthError("userId 不能为空")
    if not pass_token:
        raise AuthError("passToken 不能为空")

    opener = _build_opener()
    agent = generate_agent()
    request = urllib.request.Request(
        ACCOUNT_SERVICE_LOGIN,
        headers={
            "User-Agent": agent,
            "Cookie": f"userId={user_id}; passToken={pass_token}",
        },
    )
    data = _open_json(opener, request, timeout)
    if data.get("result") != "ok":
        message = data.get("description") or data.get("desc") or data.get("message") or "passToken 已失效"
        raise AuthError(f"小米账号登录失败: {message}")
    return _finish_login(opener, data, user_id, pass_token, timeout, agent=agent)


def start_qr_login(timeout: float = 30.0) -> Tuple[urllib.request.OpenerDirector, QrChallenge]:
    """Start Xiaomi's QR-code login and return the challenge to display/poll."""
    opener = _build_opener()
    agent = generate_agent()
    params = {
        "_qrsize": "480",
        "qs": "?sid=xiaomiio&_json=true",
        "callback": STS_CALLBACK,
        "_hasLogo": "false",
        "sid": "xiaomiio",
        "serviceParam": "",
        "_locale": "zh_CN",
        "_dc": str(int(time.time() * 1000)),
    }
    url = ACCOUNT_LONG_POLLING + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": agent})
    data = _open_json(opener, request, timeout)

    login_url = data.get("loginUrl")
    qr_url = data.get("qr")
    poll_url = data.get("lp")
    if not login_url or not poll_url:
        raise AuthError("无法创建小米账号二维码登录会话")

    return opener, QrChallenge(
        login_url=login_url,
        qr_url=qr_url or login_url,
        poll_url=poll_url,
        timeout=int(data.get("timeout") or 300),
        agent=agent,
    )


def poll_qr_login(
    opener: urllib.request.OpenerDirector,
    challenge: QrChallenge,
    on_wait: Optional[Callable[[], None]] = None,
    max_wait: Optional[float] = None,
) -> AuthResult:
    """Poll the QR login endpoint until the phone confirms the login."""
    deadline = time.time() + (max_wait if max_wait is not None else challenge.timeout)
    last_error: Optional[Exception] = None

    while time.time() < deadline:
        remaining = max(1.0, deadline - time.time())
        request = urllib.request.Request(
            challenge.poll_url,
            headers={"User-Agent": challenge.agent or generate_agent()},
        )
        try:
            with opener.open(request, timeout=min(40.0, remaining)) as response:
                body = response.read().decode("utf-8", errors="replace")
            data = parse_login_json(body) if body.strip() else {}
            if data.get("userId") and data.get("passToken"):
                return _finish_login(opener, data, 0, "", 30.0, agent=challenge.agent)
            if data.get("result") not in (None, "ok") and data.get("code") not in (None, 0):
                message = data.get("description") or data.get("desc") or data.get("message")
                if message:
                    raise AuthError(f"二维码登录失败: {message}")
        except LoginResponseError as exc:
            # A transient proxy/gateway HTML page should not abort a login the
            # user may already have confirmed on their phone.
            last_error = exc
        except AuthError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            last_error = exc

        if on_wait:
            on_wait()
        time.sleep(1.5)

    detail = f"（最后一次错误: {last_error}）" if last_error else ""
    raise AuthError(f"二维码登录超时，请重新运行 login{detail}")
