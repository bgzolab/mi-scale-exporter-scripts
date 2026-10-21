"""Client for the unofficial Xiaomi Cloud scale-data endpoint."""

from __future__ import annotations

import http.client
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from .auth import AuthResult, generate_agent
from .crypto import decrypt_response, encrypt_request

CN_BASE_URL = "https://api.io.mi.com/app"
GLOBAL_BASE_URL = "https://{region}.api.io.mi.com/app"
SUPPORTED_REGIONS = {"cn", "de", "i2", "ru", "sg", "us"}
DEFAULT_MODEL = "xiaomi.scales.ms116"  # Xiaomi Mijia S800
DEFAULT_REGION = "cn"
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 0.5


class CloudError(RuntimeError):
    """Raised when Xiaomi Cloud rejects a request or returns invalid data."""


def _int_or_none(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _timestamp_ms(value: Any) -> Optional[int]:
    number = _int_or_none(value)
    if number is None:
        return None
    if number > 10**12:
        return number
    if number > 10**9:
        return number * 1000
    return None


def _hashable(value: Any) -> Any:
    """Make nested JSON values usable in a set/dict key."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return value


class XiaomiCloudClient:
    def __init__(
        self,
        auth: AuthResult,
        region: str = DEFAULT_REGION,
        model: str = DEFAULT_MODEL,
        timeout: float = 30.0,
        debug: bool = False,
    ) -> None:
        region = (region or DEFAULT_REGION).lower()
        if region not in SUPPORTED_REGIONS:
            raise CloudError(
                f"不支持的区域 {region!r}，可选: {', '.join(sorted(SUPPORTED_REGIONS))}"
            )
        self.auth = auth
        self.region = region
        self.model = model
        self.timeout = timeout
        self.debug = debug

    # ------------------------------------------------------------------ HTTP
    def _api_url(self, path: str) -> str:
        if self.region == "cn":
            return CN_BASE_URL + path
        return GLOBAL_BASE_URL.format(region=self.region) + path

    def _debug_log(self, message: str) -> None:
        if self.debug:
            print(f"[debug] {message}", file=sys.stderr)

    def _request(self, path: str, params: Dict[str, Any]) -> Any:
        data_json = json.dumps(params, separators=(",", ":"), ensure_ascii=False)
        values, signed_nonce = encrypt_request(path, data_json, self.auth.ssecurity)
        body = urllib.parse.urlencode(values).encode("utf-8")

        request = urllib.request.Request(
            self._api_url(path),
            data=body,
            headers={
                "User-Agent": generate_agent(),
                "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": self.auth.cookie_header_for("mi.com", target_path=path),
                "MIOT-REQUEST-MODEL": self.model,
                "Accept": "*/*",
            },
            method="POST",
        )

        raw = b""
        succeeded = False
        last_network_error: Optional[Exception] = None
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                with self.auth.opener.open(request, timeout=self.timeout) as response:
                    raw = response.read()
                succeeded = True
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
                if exc.code in (429, 502, 503, 504) and attempt < RETRY_ATTEMPTS:
                    last_network_error = exc
                    self._debug_log(
                        f"HTTP {exc.code}，第 {attempt}/{RETRY_ATTEMPTS - 1} 次重试"
                    )
                    time.sleep(RETRY_DELAY_SECONDS * attempt)
                    continue
                raise CloudError(f"小米云 HTTP {exc.code}: {detail}") from exc
            except (OSError, http.client.HTTPException) as exc:
                # urllib wraps connect errors in URLError, but read-time
                # failures can surface as raw ConnectionResetError or
                # BadStatusLine / IncompleteRead.
                last_network_error = exc
                if attempt >= RETRY_ATTEMPTS:
                    break
                self._debug_log(f"网络错误，第 {attempt}/{RETRY_ATTEMPTS - 1} 次重试: {exc}")
                time.sleep(RETRY_DELAY_SECONDS * attempt)

        if not succeeded:
            raise CloudError(f"无法连接小米云: {last_network_error}") from last_network_error
        if not raw:
            raise CloudError("小米云返回了空响应")

        try:
            plaintext = decrypt_response(raw.decode("utf-8").strip(), signed_nonce)
            payload = json.loads(plaintext)
        except Exception as exc:
            raise CloudError("小米云响应解密失败，可能是登录状态已失效") from exc

        if not isinstance(payload, dict):
            raise CloudError("小米云返回了意外的响应结构")
        code = payload.get("code")
        if str(code) != "0":
            message = payload.get("message") or payload.get("description") or f"code={code}"
            raise CloudError(f"小米云返回错误: {message}")

        return payload.get("result")

    # ------------------------------------------------------------------ data
    def get_raw_records(
        self,
        since_ms: Optional[int] = None,
        until_ms: Optional[int] = None,
        limit: Optional[int] = None,
        max_pages: int = 1000,
    ) -> List[dict]:
        """Fetch raw scale records, newest first.

        Xiaomi's endpoint returns at most 20 records per page.  Pagination uses
        the ``createTime`` of the 20th record as the next ``beginTime``.
        """
        if limit is not None and limit <= 0:
            return []

        now_ms = int(time.time() * 1000)
        # ``beginTime`` means "records older than this".  Starting at --until
        # avoids downloading newer records that will be filtered out anyway.
        ts = min(now_ms, until_ms + 1) if until_ms is not None else now_ms
        if since_ms is not None and ts <= since_ms:
            return []
        records: List[dict] = []
        seen = set()

        for page in range(max_pages):
            if self.region == "cn":
                params = {
                    "param": {"endTime": 1, "beginTime": ts},
                    "model": self.model,
                    "uid": self.auth.user_id,
                    "did": 0,
                }
                result = self._request("/eco/scale/getData", params)
            else:
                params = {
                    "endTime": 1,
                    "beginTime": ts,
                    "model": self.model,
                    "uid": str(self.auth.user_id),
                    "did": 0,
                    "accountId": 0,
                }
                result = self._request("/eco/common/scale/getUserDataByPage", params)

            if not isinstance(result, list):
                raise CloudError(f"小米云返回了意外的数据结构: {type(result).__name__}")
            if not result:
                break

            self._debug_log(f"第 {page + 1} 页: {len(result)} 条记录")

            oldest = None
            for item in result:
                if not isinstance(item, dict):
                    continue
                key = (
                    item.get("createTime"),
                    item.get("did"),
                    item.get("fromSource"),
                    _hashable(item.get("data")),
                )
                if key in seen:
                    continue
                seen.add(key)
                records.append(item)
                created = _timestamp_ms(item.get("createTime"))
                if created is not None and (oldest is None or created < oldest):
                    oldest = created

            if limit is not None and len(records) >= limit:
                records = records[:limit]
                break

            if since_ms is not None and oldest is not None and oldest < since_ms:
                break

            if len(result) < 20:
                break

            last_item = result[19]
            next_ts = _timestamp_ms(last_item.get("createTime")) if isinstance(last_item, dict) else None
            if next_ts is None or next_ts <= 0 or next_ts >= ts:
                self._debug_log("分页时间戳没有前进，停止以避免死循环")
                break
            ts = next_ts

        if since_ms is not None or until_ms is not None:
            before = len(records)
            records = [
                item for item in records if _timestamp_ms(item.get("createTime")) is not None
            ]
            dropped = before - len(records)
            if dropped:
                self._debug_log(f"过滤掉 {dropped} 条没有有效 createTime 的记录")
        if until_ms is not None:
            records = [
                item
                for item in records
                if (created := _timestamp_ms(item.get("createTime"))) is not None
                and created <= until_ms
            ]
        if since_ms is not None:
            records = [
                item
                for item in records
                if (created := _timestamp_ms(item.get("createTime"))) is not None
                and created >= since_ms
            ]
        return records
