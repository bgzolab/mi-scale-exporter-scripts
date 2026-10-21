"""Command-line interface for mi-scale-exporter."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from . import __version__
from .auth import (
    AuthError,
    AuthResult,
    login_with_pass_token,
    poll_qr_login,
    start_qr_login,
)
from .cloud import (
    DEFAULT_MODEL,
    DEFAULT_REGION,
    SUPPORTED_REGIONS,
    CloudError,
    XiaomiCloudClient,
)
from .config import (
    ENV_TOKEN_KEYS,
    ENV_USER_KEYS,
    ConfigError,
    default_config_path,
    get_env,
    get_setting,
    load_config,
    load_env_file,
    resolve_connection_settings,
    save_config,
)
from .export import (
    open_output,
    output_format,
    parse_time,
    to_ms,
    write_csv,
    write_json,
    write_raw_json,
)
from .parser import dedupe_measurements, parse_records

EPILOG = """\
示例:
  mi-scale-export login
  mi-scale-export export -o weights.csv
  mi-scale-export export --json --full -o weights.json
  mi-scale-export export --since 2025-01-01 --full -o weights.csv
  mi-scale-export export --raw -o raw.json

默认区域为 cn，默认型号为 S800 的 xiaomi.scales.ms116。
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mi-scale-export",
        description="从小米云导出小米体脂秤数据（S800 / S400，CN）",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    login = subparsers.add_parser(
        "login",
        help="登录小米账号并保存凭证（默认二维码登录）",
        description="默认使用二维码登录；也可以传入浏览器 Cookie 中的 userId/passToken。",
    )
    _add_connection_args(login)
    login.add_argument("--no-save", action="store_true", help="不写入配置文件，仅打印结果")
    login.add_argument("--timeout", type=float, default=30.0, help="单次请求超时秒数")

    export = subparsers.add_parser(
        "export",
        help="从小米云拉取并导出测量记录",
        description="从小米云拉取体脂秤记录，输出 CSV 或 JSON。",
    )
    _add_connection_args(export)
    export.add_argument("-o", "--output", default="-", help="输出文件；- 表示 stdout（默认）")
    export.add_argument("--format", choices=["csv", "json"], help="输出格式；默认按扩展名推断")
    export.add_argument("--json", action="store_true", help="等价于 --format json")
    export.add_argument("--raw", action="store_true", help="输出小米云原始记录（JSON，便于调试）")
    export.add_argument("--full", action="store_true", help="输出 S800 分段数据等扩展字段")
    export.add_argument("--since", help="只保留该时间之后的记录（YYYY-MM-DD 或 ISO-8601）")
    export.add_argument("--until", help="只保留该时间之前的记录（YYYY-MM-DD 或 ISO-8601）")
    export.add_argument("--limit", type=int, help="最多拉取最新 N 条记录")
    export.add_argument("--max-pages", type=int, default=1000, help="最多请求页数（防止死循环）")
    export.add_argument("--no-dedupe", action="store_true", help="不去重（默认保留同一时间最完整的记录）")
    export.add_argument("--utc", action="store_true", help="时间输出为 UTC（默认本地时区）")
    export.add_argument("--timeout", type=float, default=30.0, help="单次请求超时秒数")
    export.add_argument("--debug", action="store_true", help="输出分页等调试信息")

    return parser


def _add_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--user-id", help="小米账号 userId（也可用 XIAOMI_USER_ID）")
    parser.add_argument("--pass-token", help="小米账号 passToken（也可用 XIAOMI_PASS_TOKEN）")
    parser.add_argument(
        "--region",
        choices=["cn", "de", "i2", "ru", "sg", "us"],
        help=f"账号区域，默认 {DEFAULT_REGION}",
    )
    parser.add_argument(
        "--model",
        help=f"体脂秤型号，S800 为 xiaomi.scales.ms116（默认 {DEFAULT_MODEL}）",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help=f"凭证文件路径，默认 {default_config_path()}",
    )


def _info(message: str) -> None:
    print(message, file=sys.stderr)


def _error(message: str) -> None:
    print(f"错误: {message}", file=sys.stderr)


def _warn_json_suffix(fmt: str, output: Optional[str]) -> None:
    if fmt == "json" and output not in (None, "-") and not output.lower().endswith(".json"):
        _info("提示: 输出格式为 JSON，当前文件名不是 .json 后缀")


def _print_qr(login_url: str, qr_url: str) -> None:
    _info("")
    _info("请用手机上的小米账号扫码，或在手机浏览器中打开下面的链接：")
    _info(login_url)
    _info("")
    _info(f"二维码图片: {qr_url}")
    _info("")

    if shutil.which("qrencode"):
        try:
            completed = subprocess.run(
                ["qrencode", "-t", "ANSIUTF8", login_url],
                check=False,
                stdout=sys.stderr,
            )
            if completed.returncode == 0:
                return
        except OSError:
            pass

    try:
        import qrcode  # type: ignore

        qr = qrcode.QRCode(border=1)
        qr.add_data(login_url)
        qr.make(fit=True)
        qr.print_ascii(invert=True, out=sys.stderr)
    except Exception:
        _info("提示: 安装 qrencode 或 `pip install 'mi-scale-exporter[qr]'` 可直接在终端显示二维码。")


def _load_config(args: argparse.Namespace) -> dict:
    return load_config(getattr(args, "config", None))


def _save_credentials(
    args: argparse.Namespace,
    result: AuthResult,
    region: str,
    model: str,
) -> Optional[Path]:
    if args.no_save:
        return None
    config_path = args.config or default_config_path()
    existing = load_config(config_path)
    existing.update(
        {
            "user_id": result.user_id,
            "pass_token": result.pass_token,
            "region": region,
            "model": model,
        }
    )
    return save_config(existing, config_path)


def command_login(args: argparse.Namespace) -> int:
    try:
        config = _load_config(args)
    except ConfigError as exc:
        _error(str(exc))
        return 1
    region = str(
        get_setting("region", args.region, config, "XIAOMI_REGION", DEFAULT_REGION)
    ).strip().lower()
    model = str(
        get_setting("model", args.model, config, "XIAOMI_SCALE_MODEL", DEFAULT_MODEL)
    ).strip()
    if region not in SUPPORTED_REGIONS:
        _error(f"不支持的区域 {region!r}，可选: {', '.join(sorted(SUPPORTED_REGIONS))}")
        return 2

    user_id = args.user_id or get_env(ENV_USER_KEYS)
    pass_token = args.pass_token or get_env(ENV_TOKEN_KEYS)
    if isinstance(user_id, str):
        user_id = user_id.strip()
    if isinstance(pass_token, str):
        pass_token = pass_token.strip()

    if bool(user_id) != bool(pass_token):
        _error("--user-id 和 --pass-token 必须同时提供")
        return 2

    try:
        if user_id and pass_token:
            _info("正在用 userId/passToken 登录小米账号...")
            result = login_with_pass_token(int(user_id), str(pass_token), timeout=args.timeout)
        else:
            opener, challenge = start_qr_login(timeout=args.timeout)
            _print_qr(challenge.login_url, challenge.qr_url)
            _info("等待手机确认登录...")
            result = poll_qr_login(opener, challenge, on_wait=lambda: _info("."))
    except (AuthError, ValueError) as exc:
        _error(str(exc))
        return 1

    try:
        saved = _save_credentials(args, result, region, model)
    except (ConfigError, OSError) as exc:
        _error(f"保存凭证失败: {exc}")
        return 1
    if saved:
        _info(f"登录成功，凭证已保存到 {saved}")
        _info(f"user_id: {result.user_id}")
        _info(f"region:  {region}")
        _info(f"model:   {model}")
    else:
        _info("登录成功（未保存凭证）")
        _info(f"user_id={result.user_id}")
        _info(f"pass_token={result.pass_token}")
    return 0


def command_export(args: argparse.Namespace) -> int:
    try:
        config = _load_config(args)
    except ConfigError as exc:
        _error(str(exc))
        return 1

    try:
        settings = resolve_connection_settings(args, config)
    except ValueError as exc:
        _error(f"凭证格式错误: {exc}")
        return 2

    user_id = settings["user_id"]
    pass_token = settings["pass_token"]
    region = settings["region"]
    model = settings["model"]

    if not user_id or not pass_token:
        _error("未找到小米账号凭证。")
        _info("请先运行 `mi-scale-export login`，或设置环境变量 XIAOMI_USER_ID / XIAOMI_PASS_TOKEN。")
        return 2

    if args.limit is not None and args.limit < 1:
        _error("--limit 必须大于 0")
        return 2
    if args.max_pages < 1:
        _error("--max-pages 必须大于 0")
        return 2

    try:
        since_ms = to_ms(parse_time(args.since)) if args.since else None
        until_ms = to_ms(parse_time(args.until, end_of_day=True)) if args.until else None
    except ValueError as exc:
        _error(str(exc))
        return 2
    if since_ms is not None and until_ms is not None and since_ms > until_ms:
        _error("--since 不能晚于 --until")
        return 2

    if args.raw:
        fmt = "json"
        if args.format == "csv":
            _info("提示: --raw 会忽略 --format csv，实际输出 JSON")
    else:
        fmt = output_format(args.output, "json" if args.json else args.format)
    _warn_json_suffix(fmt, args.output)

    try:
        _info("正在登录小米云...")
        auth = login_with_pass_token(user_id, pass_token, timeout=args.timeout)
        if args.debug:
            _info(f"[debug] cookies: {', '.join(auth.cookie_names())}")
        # Xiaomi may rotate the pass token during serviceLogin.  Update the
        # local cache only when this login actually used the cached account.
        cached_user_id = config.get("user_id")
        same_account = cached_user_id is not None and str(cached_user_id) == str(user_id)
        if same_account and config.get("pass_token") and auth.pass_token != config.get("pass_token"):
            try:
                config["pass_token"] = auth.pass_token
                save_config(config, args.config or default_config_path())
                _info("已更新本地 passToken 缓存")
            except (ConfigError, OSError) as exc:
                _info(f"警告: 无法更新 passToken 缓存: {exc}")
        client = XiaomiCloudClient(
            auth,
            region=region,
            model=model,
            timeout=args.timeout,
            debug=args.debug,
        )
        _info(f"正在拉取数据（region={region}, model={model}）...")
        raw_records = client.get_raw_records(
            since_ms=since_ms,
            until_ms=until_ms,
            limit=args.limit,
            max_pages=args.max_pages,
        )
    except (AuthError, CloudError, ValueError) as exc:
        _error(str(exc))
        return 1

    if args.raw:
        handle, should_close = open_output(args.output, "json")
        try:
            write_raw_json(handle, raw_records)
        finally:
            if should_close:
                handle.close()
        _info(f"已导出 {len(raw_records)} 条原始记录 -> {args.output}")
        return 0

    measurements = parse_records(raw_records)
    if not args.no_dedupe:
        measurements = dedupe_measurements(measurements)
    else:
        measurements.sort(key=lambda m: m.measured_at_ms)

    if not measurements:
        _info("没有找到可导出的测量记录。请确认型号是否正确、账号下是否有该体脂秤的数据。")

    handle, should_close = open_output(args.output, fmt)
    try:
        if fmt == "json":
            write_json(handle, measurements, full=args.full, utc=args.utc)
        else:
            write_csv(handle, measurements, full=args.full, utc=args.utc)
    finally:
        if should_close:
            handle.close()

    _info(f"已导出 {len(measurements)} 条记录 -> {args.output}")
    if measurements:
        first = measurements[0].measured_at.astimezone(None).isoformat(timespec="seconds")
        last = measurements[-1].measured_at.astimezone(None).isoformat(timespec="seconds")
        _info(f"时间范围: {first} .. {last}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not os.environ.get("MI_SCALE_NO_ENV"):
        try:
            load_env_file()
        except ConfigError as exc:
            _error(str(exc))
            return 1
    try:
        if args.command == "login":
            return command_login(args)
        if args.command == "export":
            return command_export(args)
    except KeyboardInterrupt:
        _info("已取消")
        return 130
    parser.error("未知命令")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
