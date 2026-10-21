"""Credential storage and defaults."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .cloud import DEFAULT_MODEL, DEFAULT_REGION

# Process environment only accepts prefixed names to avoid clashing with
# unrelated CI / container variables such as ACCOUNT or USER_ID.
ENV_USER_KEYS = ("XIAOMI_USER_ID", "XIAOMI_ACCOUNT", "MI_USER_ID")
ENV_TOKEN_KEYS = ("XIAOMI_PASS_TOKEN", "MI_PASS_TOKEN")
# The .env file is project-local, so the shorter aliases are safe there.
ENV_FILE_USER_KEYS = ENV_USER_KEYS + ("ACCOUNT", "USER_ID")
ENV_FILE_TOKEN_KEYS = ENV_TOKEN_KEYS + ("PASS_TOKEN",)


def get_env(names: tuple, default: Any = None, validator=None) -> Any:
    for name in names:
        value = os.environ.get(name)
        if value not in (None, "") and (validator is None or validator(value)):
            return value
    return default


class ConfigError(RuntimeError):
    pass


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _first_valid_entry(entries: Dict[str, str], names: tuple, validator) -> Optional[str]:
    for name in names:
        value = entries.get(name)
        if value and validator(value):
            return value
    return None


def looks_like_pass_token(value: str) -> bool:
    return value.startswith("V1:") or value.startswith("V2:") or len(value) >= 64


def load_env_file(path: Optional[Path] = None) -> Dict[str, str]:
    """Load Xiaomi credentials from a local ``.env`` file.

    Supported formats::

        XIAOMI_USER_ID=123456789
        XIAOMI_PASS_TOKEN=V1:....

    or the raw two-line format::

        123456789
        V1:....

    Existing environment variables are never overwritten.
    """
    path = path or (Path.cwd() / ".env")
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConfigError(f"无法读取 {path}: {exc}") from exc

    entries: Dict[str, str] = {}
    raw_lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if match:
            entries[match.group(1)] = _strip_quotes(match.group(2))
        else:
            raw_lines.append(_strip_quotes(line))

    # Validate while iterating aliases, so a bad XIAOMI_* value can fall back
    # to a valid ACCOUNT / USER_ID / PASS_TOKEN entry in the same file.
    user_id = _first_valid_entry(entries, ENV_FILE_USER_KEYS, str.isdigit)
    pass_token = _first_valid_entry(entries, ENV_FILE_TOKEN_KEYS, looks_like_pass_token)

    # The user's .env may be just two raw lines: account, then pass token.
    # Require a numeric account and a plausible token so an unrelated .env
    # cannot be mistaken for credentials.
    if user_id is None and pass_token is None and len(raw_lines) >= 2:
        first, second = raw_lines[0], raw_lines[1]
        if first.isdigit() and looks_like_pass_token(second):
            user_id, pass_token = first, second
        elif second.isdigit() and looks_like_pass_token(first):
            user_id, pass_token = second, first

    if user_id:
        os.environ.setdefault("XIAOMI_USER_ID", user_id)
    if pass_token:
        os.environ.setdefault("XIAOMI_PASS_TOKEN", pass_token)
    return {"user_id": user_id or "", "pass_token": pass_token or ""}


def default_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        root = Path(base)
    else:
        root = Path.home() / ".config"
    return root / "mi-scale-exporter" / "credentials.json"


def load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    path = path or default_config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"无法读取配置文件 {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件格式错误: {path}")
    return data


def save_config(data: Dict[str, Any], path: Optional[Path] = None) -> Path:
    path = path or default_config_path()
    created_dir = not path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt" and (created_dir or path.parent == default_config_path().parent):
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
    payload = dict(data)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    fd, tmp_name = tempfile.mkstemp(prefix=".credentials-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return path


def get_setting(
    name: str,
    args_value: Any,
    config: Dict[str, Any],
    env_name: str,
    default: Any = None,
    validator=None,
) -> Any:
    """Resolve CLI > environment > config > default."""
    if args_value not in (None, ""):
        return args_value
    if isinstance(env_name, (tuple, list)):
        env_value = get_env(tuple(env_name), validator=validator)
    else:
        env_value = os.environ.get(env_name)
    if env_value not in (None, "") and (validator is None or validator(env_value)):
        return env_value
    value = config.get(name)
    if value not in (None, ""):
        return value
    return default


def resolve_connection_settings(args: Any, config: Dict[str, Any]) -> Dict[str, Any]:
    user_id = get_setting(
        "user_id", getattr(args, "user_id", None), config, ENV_USER_KEYS,
        validator=str.isdigit,
    )
    pass_token = get_setting(
        "pass_token", getattr(args, "pass_token", None), config, ENV_TOKEN_KEYS,
        validator=looks_like_pass_token,
    )
    region = get_setting(
        "region", getattr(args, "region", None), config, "XIAOMI_REGION", DEFAULT_REGION
    )
    model = get_setting(
        "model", getattr(args, "model", None), config, "XIAOMI_SCALE_MODEL", DEFAULT_MODEL
    )
    if isinstance(user_id, str):
        user_id = user_id.strip()
    if isinstance(pass_token, str):
        pass_token = pass_token.strip()
    if user_id not in (None, "") and not str(user_id).isdigit():
        raise ValueError("userId 必须是数字")
    return {
        "user_id": int(user_id) if user_id not in (None, "") else None,
        "pass_token": str(pass_token) if pass_token not in (None, "") else None,
        "region": str(region).strip().lower(),
        "model": str(model).strip(),
    }
