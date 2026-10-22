# mi-scale-exporter-scripts

Export Xiaomi body-composition scale measurements from Xiaomi Cloud to CSV or JSON. Designed for the Xiaomi Body Composition Scale S800 (`xiaomi.scales.ms116`, CN), with support for other Xiaomi scale models.

No Bluetooth, root, or Home Assistant is required. Log in once, then pull your measurement history directly from Xiaomi Cloud.

> This is an unofficial tool that uses Xiaomi's private app API. Use it only with your own account and data.

## Features

- QR-code login or existing `userId` / `passToken`
- Credentials stored locally with `0600` permissions
- Automatic `.env` loading
- Pagination and duplicate removal
- CSV / JSON export
- Optional S800 segmental body-composition fields
- Python 3.9+ with no runtime dependencies

## Quick start

```bash
# Log in (prints a QR code or login URL)
python3 mi_scale_export.py login

# Export all measurements to CSV
python3 mi_scale_export.py export -o weights.csv

# Export JSON with S800 segmental data
python3 mi_scale_export.py export --json --full -o weights.json

# Export measurements since a given date
python3 mi_scale_export.py export --since 2025-01-01 -o weights-2025.csv
```

You can also install the command:

```bash
pip install -e .
mi-scale-export login
mi-scale-export export -o weights.csv
```

For an in-terminal QR code, install the optional dependency or use `qrencode`:

```bash
pip install 'mi-scale-exporter[qr]'
# or: sudo apt install qrencode
```

## Authentication

`login` prints a Xiaomi account URL. Scan it with the Xiaomi app, or open it on a phone where the account is already signed in.

If you already have a browser session, pass the cookies directly:

```bash
python3 mi_scale_export.py login \
  --user-id 123456789 \
  --pass-token 'V1:...'
```

Credentials are saved to:

```text
~/.config/mi-scale-exporter/credentials.json
```

The file is created with mode `0600`. It contains a token that grants access to your Xiaomi account, so do not commit or share it.

### Environment variables

`export` also reads:

| Variable | Description |
| --- | --- |
| `XIAOMI_USER_ID` | Xiaomi account user ID |
| `XIAOMI_PASS_TOKEN` | Xiaomi pass token |
| `XIAOMI_REGION` | Account region; default `cn` |
| `XIAOMI_SCALE_MODEL` | Scale model; default `xiaomi.scales.ms116` |

A local `.env` file is loaded automatically. Both key/value and the raw two-line format are accepted:

```dotenv
XIAOMI_USER_ID=123456789
XIAOMI_PASS_TOKEN=V1:....
```

```text
123456789
V1:....
```

Set `MI_SCALE_NO_ENV=1` to disable automatic `.env` loading.

> Avoid passing `--pass-token` on the command line on shared hosts or CI. Prefer `.env`, environment variables, or the credential file.

## Supported models

The defaults are:

```text
region = cn
model  = xiaomi.scales.ms116   # Xiaomi Body Composition Scale S800
```

Other commonly used models:

- `yunmai.scales.ms103` (S400)
- `yunmai.scales.ms104` (S400)
- `yunmai.scales.ms107` (S400)
- `xiaomi.scales.ms113` (S200)
- `yunmai.scales.ms106` (S200)
- `yunmai.scales.ms3001` (older 8-electrode model)

Check the exact model in the Xiaomi Home app under the scale's device information. Override it with `--model`:

```bash
python3 mi_scale_export.py export --model yunmai.scales.ms103 -o s400.csv
```

## Output

The default CSV columns are:

```text
date, weight_kg, bmi, body_fat_pct, body_water_pct, bone_mass_kg,
metabolic_age, muscle_mass_kg, protein_mass_kg, visceral_fat,
basal_metabolism_kcal, body_score, heart_rate_bpm,
skeletal_muscle_mass_kg, physique_rating, height_cm,
user, source, model, from_source
```

`--full` adds S800 segmental data such as arm/leg/trunk muscle and fat values, segmental scores, limb BMI, recommended calorie intake, and body type.

Timestamps use the local timezone by default. Use `--utc` for UTC. CSV files are written as UTF-8 with a BOM for Excel compatibility.

JSON output contains flat fields by default. With `--full`, it also includes `extras` and `raw` objects.

### Useful options

| Option | Purpose |
| --- | --- |
| `--since` / `--until` | Limit the export by date or ISO-8601 time |
| `--limit N` | Fetch only the newest N matching records |
| `--raw` | Write the raw Xiaomi Cloud records as JSON |
| `--utc` | Use UTC timestamps |
| `--no-dedupe` | Keep duplicate records |
| `--debug` | Print pagination and cookie-name diagnostics |

## How it works

The script logs in to the Xiaomi account service, obtains a service session, and calls the same cloud endpoint used by the Xiaomi Home app to read scale measurements. It paginates through the history, parses the common Xiaomi scale record formats, removes duplicates, and writes CSV or JSON.

## Limitations

- This project uses an unofficial Xiaomi API and may stop working if Xiaomi changes it.
- S800 support targets the CN region and `xiaomi.scales.ms116`. Other models and regions are best-effort.
- Measurements must already be present in Xiaomi Cloud. Complete a measurement in the Xiaomi Home / Mi Fitness app first.
- The tool only exports data. It does not upload to Garmin; use [SmartScaleConnect](https://github.com/AlexxIT/SmartScaleConnect) or import the CSV into another tool.
- Account login requests are not retried automatically. If Xiaomi's account service has a transient failure, rerun the command. Pagination requests are retried.

## Development

```bash
python3 -m unittest discover -s tests -v
```

## Contributing

Issues and pull requests are welcome. Please run the test suite before opening a PR.

## License

AGPL-3.0. See [LICENCE](LICENCE) for details.

Inspired by [lswiderski/mi-scale-exporter](https://github.com/lswiderski/mi-scale-exporter) and [AlexxIT/SmartScaleConnect](https://github.com/AlexxIT/SmartScaleConnect).

This project is not affiliated with Xiaomi.
