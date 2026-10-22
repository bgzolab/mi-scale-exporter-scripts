# AGENTS.md

## Project

Python 3.9+ CLI/package that exports Xiaomi body-composition scale data from Xiaomi Cloud to CSV or JSON. Defaults are the S800 (`xiaomi.scales.ms116`) in the `cn` region. Runtime code uses only the standard library; `qrcode` is optional for terminal QR rendering.

## Commands

- Full test suite: `python3 -m unittest discover -s tests -v`
- Single test: `python3 -m unittest tests.test_parser.ParserTest.test_s800_source2 -v`
- One test module: `python3 -m unittest discover -s tests -p 'test_cloud.py' -v`
- CLI help: `python3 mi_scale_export.py --help`
- Install console script: `pip install -e .` then `mi-scale-export ...`

There is no lint, typecheck, or formatter configuration in this repo. Do not invent commands for them.

## Layout

- `mi_scale_export.py` — convenience entrypoint; calls `mi_scale_exporter/cli.py:main`.
- `cli.py` — argparse, `login` / `export` commands, output wiring.
- `config.py` — XDG credential file, environment variables, `.env` loading.
- `auth.py` — QR / passToken login and cookie scoping.
- `cloud.py` — signed/encrypted Xiaomi app API, pagination, retries.
- `crypto.py` — SHA-1 request signing and RC4 drop-1024.
- `parser.py` — raw record normalization and `fromSource` handling.
- `export.py` — CSV/JSON writers and time parsing.
- `tests/` mirrors these modules; most tests use fake openers or local HTTP servers, not real Xiaomi credentials.

## Constraints and gotchas

- Preserve Python 3.9 compatibility. The code uses `from __future__ import annotations`; avoid 3.10+ syntax at runtime.
- Keep runtime dependencies at zero unless there is a strong reason. Do not replace stdlib HTTP with `requests`.
- `tests/test_crypto.py` contains a byte-for-byte vector cross-checked against SmartScaleConnect's Go implementation. Any change to signing or encryption must keep it passing.
- S800 CN records observed in this project use `fromSource=2` with fields directly in `data`. The parser also supports `fromSource=1` and `3`; do not assume `fromSource=3` or `bodyResData`.
- `DEFAULT_MODEL`, `DEFAULT_REGION`, and `SUPPORTED_REGIONS` in `cloud.py` are the source of truth for CLI defaults and choices.
- `.env` is auto-loaded in `cli.main` unless `MI_SCALE_NO_ENV=1`. CLI tests set that flag; keep it when adding CLI tests.
- `.env` accepts both key/value and raw two-line formats (account, then passToken). Never print or commit passTokens/cookies. `--debug` intentionally prints cookie names only.
- `--limit` counts only records that survive `--since` / `--until` filtering inside the pagination loop. Preserve that ordering when changing `get_raw_records`.
- `cloud._request` retries 429/5xx and read-time network errors three times. Account login requests intentionally do not retry; document or discuss before changing that trade-off.
- Credential writes are atomic: file mode `0600`, default config directory `0700`. Do not replace `save_config` with a plain write or log credentials.
- Never stage real data or secrets. Ignored paths include `.env`, `credentials.json`, `exports/`, `weights*.csv/json`, and `raw*.json`.
- The license is AGPL-3.0 via `LICENCE` (British spelling). Do not add a separate MIT `LICENSE`.
- `README.md` is English and user-facing. Keep it product documentation, not a research/iteration log.
- `.github/workflows/opencode-*.yml` is inherited from `bgzolab/template` and runs a read-only PR review. Do not modify it for feature work.
- Commit messages follow the existing Conventional Commit style: `feat:`, `fix:`, `docs:`, `test:`.
