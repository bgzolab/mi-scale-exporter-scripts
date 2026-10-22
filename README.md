# mi-scale-exporter-scripts

[![Contributors](https://img.shields.io/github/contributors/bgzolab/mi-scale-exporter-scripts.svg?style=for-the-badge)](https://github.com/bgzolab/mi-scale-exporter-scripts/graphs/contributors)
[![Stargazers](https://img.shields.io/github/stars/bgzolab/mi-scale-exporter-scripts.svg?style=for-the-badge)](https://github.com/bgzolab/mi-scale-exporter-scripts/stargazers)
[![Issues](https://img.shields.io/github/issues/bgzolab/mi-scale-exporter-scripts.svg?style=for-the-badge)](https://github.com/bgzolab/mi-scale-exporter-scripts/issues)
[![Licence](https://img.shields.io/github/license/bgzolab/mi-scale-exporter-scripts.svg?style=for-the-badge)](https://github.com/bgzolab/mi-scale-exporter-scripts/blob/main/LICENCE)

从**小米云**导出小米体脂秤测量数据的小脚本，默认针对 **小米体脂秤 S800（`xiaomi.scales.ms116`，CN 区域）**，也兼容 S400 等型号。

不需要蓝牙、不需要 root、不需要把秤接到 Home Assistant。登录一次小米账号后，脚本会直接调用小米云接口拉取历史记录，输出 CSV / JSON。

> 这是非官方工具，使用的是小米 App 的私有接口。接口可能随时变化，请仅用于导出自己的数据。

## 先调研：有没有现成项目？

有，而且不止一个。结论是：**如果你只需要“把小米云数据拉下来”，本脚本已经够用；如果你要自动同步到 Garmin，优先看 SmartScaleConnect。**

| 项目 | 能做什么 | 对 S800 的支持 | 评价 |
| --- | --- | --- | --- |
| [lswiderski/mi-scale-exporter](https://github.com/lswiderski/mi-scale-exporter) | 手机 App；后来增加了小米云拉取，可再上传 Garmin | 作者在 [issue #39](https://github.com/lswiderski/mi-scale-exporter/issues/39) 中说明 S400/S800 的实验性云支持 | 你手机上用的应该就是它的云功能；移动端体验好，但不方便脚本化/批量导出 |
| [lswiderski/WebBodyComposition](https://github.com/lswiderski/WebBodyComposition) | Web 版，`/cloud/xiaomiCloud` 页面支持 userId + passToken 从小米云拉数据 | 页面里明确列出了 `S800 - xiaomi.scales.ms116` | 和本脚本原理相同；适合临时用，不适合放进定时任务 |
| [AlexxIT/SmartScaleConnect](https://github.com/AlexxIT/SmartScaleConnect) | Go CLI，支持小米、Mi Fitness、Zepp、Garmin、CSV、JSON 等互相同步 | 源码已包含 S800 字段解析；[PR #17](https://github.com/AlexxIT/SmartScaleConnect/pull/17) 仍在开放，用于补全 S800 分段字段 | **最成熟的现成方案**。需要 Garmin 同步或 Home Assistant 集成时建议直接用 |
| [RobertWojtowicz/export2garmin](https://github.com/RobertWojtowicz/export2garmin) | 小米秤数据同步到 Garmin，支持 Docker/树莓派 | 主要验证 S400；S800 未确认 | 偏重 BLE/网关和 Garmin，部署较重 |
| [PiotrMachowski/Xiaomi-cloud-tokens-extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor) | 从小米云提取设备 token / BLE key | 不拉体脂数据 | 只解决“拿 token”，不解决“导数据” |
| [XiaoMi/ha_xiaomi_home](https://github.com/XiaoMi/ha_xiaomi_home) | 米家官方 Home Assistant 集成 | S800 适配仍在讨论（[#1721](https://github.com/XiaoMi/ha_xiaomi_home/discussions/1721)） | 适合 HA 实时接入，不适合历史数据导出 |

本仓库的定位：**核心功能零第三方依赖、面向 S800 的轻量导出脚本**。它把 mi-scale-exporter / WebBodyComposition 使用的登录与云接口流程用 Python 重写，并补上了 S800 的字段解析。

## 快速开始

要求：Python 3.9+，无需 `pip install`（只用标准库）。下面的 `python3 -m mi_scale_exporter` 也可以简写为 `./mi_scale_export.py`。

```bash
# 1. 登录（二维码；和 Web 版“Get Pass Token”一样）
python3 -m mi_scale_exporter login

# 2. 导出最近的全部记录为 CSV
python3 -m mi_scale_exporter export -o weights.csv

# 3. 导出 JSON，并包含 S800 分段肌肉/脂肪等扩展字段
python3 -m mi_scale_exporter export --json --full -o weights.json

# 4. 只看 2025 年之后
python3 -m mi_scale_exporter export --since 2025-01-01 -o weights-2025.csv

# 5. 先看原始返回，排查型号/字段问题
python3 -m mi_scale_exporter export --raw -o raw.json
```

也可以安装成命令：

```bash
pip install -e .
mi-scale-export login
mi-scale-export export -o weights.csv
```

### 二维码登录

`login` 会打印一个 `https://ak.account.xiaomi.com/...` 链接。用手机上的小米账号扫码（或在手机浏览器打开该链接）即可。

如果终端里没有二维码，可以安装可选依赖或使用系统工具：

```bash
pip install 'mi-scale-exporter[qr]'   # 终端 ASCII 二维码
# 或者
sudo apt install qrencode             # 脚本会自动调用 qrencode
```

### 使用浏览器里已有的 passToken

如果你已经在浏览器登录过小米账号，也可以直接把 Cookie 里的 `userId` 和 `passToken` 交给脚本：

```bash
python3 -m mi_scale_exporter login \
  --user-id 123456789 \
  --pass-token '粘贴 passToken'
```

或者直接用环境变量 / `.env` 文件：

```bash
export XIAOMI_USER_ID=123456789
export XIAOMI_PASS_TOKEN='...'
python3 -m mi_scale_exporter export -o weights.csv
```

也可以把凭证放在当前目录的 `.env` 里，脚本会自动读取（shell 里已有的环境变量优先）：

```dotenv
XIAOMI_USER_ID=123456789
XIAOMI_PASS_TOKEN=V1:....
```

或者按“账号一行、passToken 一行”的原始格式：

```text
123456789
V1:....
```

`.env` 已被 `.gitignore` 忽略，不会误提交。也支持 `ACCOUNT` / `USER_ID` / `PASS_TOKEN` 这些文件内别名（会校验格式）。如果不想自动读取 `.env`，设置 `MI_SCALE_NO_ENV=1`。

> 在共享主机或 CI 上，尽量不要通过 `--pass-token` 命令行参数传凭证（会进入 shell history / 进程列表）；优先使用 `.env`、环境变量或凭证文件。

凭证默认保存到：

```
~/.config/mi-scale-exporter/credentials.json
```

文件权限为 `0600`。里面包含可以直接访问小米账号的 passToken，请不要提交到 Git。

## 支持的型号

默认：

```
region = cn
model  = xiaomi.scales.ms116   # 小米体脂秤 S800
```

其他常见型号（可在米家 App → 体脂秤 → 设置 → 设备信息 中查看）：

- `yunmai.scales.ms103`
- `yunmai.scales.ms104`
- `yunmai.scales.ms107`
- `xiaomi.scales.ms113`（S200）
- `yunmai.scales.ms106`（S200）
- `yunmai.scales.ms3001`（小米八电极体脂秤，2022 款）

用 `--model` 覆盖：

```bash
python3 -m mi_scale_exporter export --model yunmai.scales.ms103 -o s400.csv
```

如果型号填错，最常见的结果是“没有找到可导出的测量记录”，而不是报错。

## 输出字段

CSV 默认包含：

```
date, weight_kg, bmi, body_fat_pct, body_water_pct, bone_mass_kg,
metabolic_age, muscle_mass_kg, protein_mass_kg, visceral_fat,
basal_metabolism_kcal, body_score, heart_rate_bpm,
skeletal_muscle_mass_kg, physique_rating, height_cm,
user, source, model, from_source
```

`--full` 额外输出 S800 的分段数据，例如：

- 左右手臂/左右腿/躯干的肌肉量、肌肉率、肌肉评分
- 左右手臂/左右腿/躯干的脂肪量、脂肪率、脂肪评分
- 四肢 BMI、推荐热量摄入、体类型等

`date` 默认使用本地时区（ISO-8601，带偏移）；`--utc` 可改为 UTC。CSV 使用 UTF-8 with BOM，方便 Excel 直接打开。

JSON 默认输出扁平字段；`--full` 还会附带 `extras` 和 `raw`，方便二次处理。

## 工作原理

1. 通过小米账号的二维码登录（或 passToken）拿到 `ssecurity` 和服务 Cookie。
2. 调用小米云接口：
   - CN：`POST https://api.io.mi.com/app/eco/scale/getData`
   - 其他区域：`POST https://{region}.api.io.mi.com/app/eco/common/scale/getUserDataByPage`
3. 请求参数按小米 App 的方式做 SHA-1 签名 + RC4（drop 1024）加密；响应同样解密。
4. 每页 20 条，按 `createTime` 向前翻页，直到没有更多数据。
5. 解析 `fromSource=1/2/3` 三种记录格式。S800 实测是 `fromSource=2`，字段直接放在 `data` 里；部分型号/固件会走 `fromSource=3` 的 `bodyResData`。
6. 同一时间、同一用户、同一体重的记录默认去重，保留字段最完整的一条。

## 常见问题

**登录时报“登录验证失败”**

passToken 过期或复制不完整。重新运行 `login`，用二维码登录。

如果是网络抖动或小米账号服务临时 5xx，直接重跑一次命令即可。导出分页请求会自动重试，账号登录请求为了保持流程简单不自动重试。

**没有数据**

- 确认 `--model` 与米家 App 里的“设备型号”完全一致。
- 确认账号区域是 `cn`（S800 目前只有中国版）。
- 先在米家 App 里完成一次测量，并确认 App 能看到数据。
- 用 `--raw` 看接口是否返回了记录。

**会和小米 App 冲突吗？**

不会主动踢掉手机登录；脚本只是复用云端会话。如果小米账号触发了风控/二次验证，优先使用二维码登录。

**能把数据同步到 Garmin 吗？**

本脚本只负责导出。需要 Garmin 同步时，建议使用 [SmartScaleConnect](https://github.com/AlexxIT/SmartScaleConnect)，或把本脚本输出的 CSV 再导入其他工具。

## 开发

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖了：

- 与 SmartScaleConnect 的 Go 实现逐字节对比的加密/签名向量
- S800 `fromSource=2/3`、S400 `fromSource=1` 的解析
- 分页、去重、配置权限、`.env` 读取

## Contributing

Any contributions made are **greatly appreciated**.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'feat(module): add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

All code is licensed under the AGPL-3.0 license. See `LICENCE` for more information.

## 免责声明

本项目与小米无关。使用非官方接口可能违反服务条款，也可能因小米接口变更而失效。请只导出你自己的数据，并自行承担风险。
