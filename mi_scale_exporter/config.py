"""Credential storage and defaults."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .cloud import DEFAULT_MODEL, DEFAULT_REGION


class ConfigError(RuntimeError):
    pass


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
    path.parent.mkdir(parents=True, exist_ok=True)
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
) -> Any:
    """Resolve CLI > environment > config > default."""
    if args_value not in (None, ""):
        return args_value
    env_value = os.environ.get(env_name)
    if env_value not in (None, ""):
        return env_value
    value = config.get(name)
    if value not in (None, ""):
        return value
    return default


def resolve_connection_settings(args: Any, config: Dict[str, Any]) -> Dict[str, Any]:
    user_id = get_setting("user_id", getattr(args, "user_id", None), config, "XIAOMI_USER_ID")
    pass_token = get_setting(
        "pass_token", getattr(args, "pass_token", None), config, "XIAOMI_PASS_TOKEN"
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
    return {
        "user_id": int(user_id) if user_id not in (None, "") else None,
        "pass_token": str(pass_token) if pass_token not in (None, "") else None,
        "region": str(region).strip().lower(),
        "model": str(model).strip(),
    }
