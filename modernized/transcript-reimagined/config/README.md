# `config` — 配置与用户文件

承载 `legacy/transcript/src/transcript/config.py`。这一层做文件 I/O：读 `config.env`、
读旧版 `summary-settings.json`、写凭据/提示词/词表。

## 公开面

| 名字 | 作用 |
|---|---|
| `Config` | 运行配置；所有值都有默认，缺文件也能跑离线路径 |
| `Config.load(path=None)` | 按「`config.env` > 旧版设置文件 > 内建默认」装载 |
| `ConfigError` | 配置无效；继承 `FatalError` 与 `ValueError`，启动时可见 |
| `atomic_write(path, text, mode=0o600)` | **唯一**的用户文件写入通道：临时文件 + `os.replace` + 权限 |
| `save_credentials(path, updates)` | 写 `config.env`：保留注释与其他行、拒绝空白/等号/控制字符 |
| `write_config_template(path=None)` | 生成模板；已存在则不覆盖 |
| `mask(secret)` / `mask_preview(secret)` | 只暴露尾号；短于 8 位一律不暴露尾部 |
| `DEFAULT_*` | 默认路径、模型名与 Base URL |

## 两条容易做错的语义

1. **「空值 = 保留」是 API 层的事，不是写文件层的事。** `save_credentials` 把空串当作
   「清空这一项」（`KEY=`）；调用方必须在调用前过滤掉空输入，才符合 `RULE-040`。
2. **数值解析不再吞异常。** `CHUNK_MAX_S=12O` 会抛 `ConfigError` 并在消息里列全所有
   无效项，而不是静默回退默认值（`RULE-105` 的人裁定）。

## 有意的行为变更（已署名）

- **短密钥不显示尾号。** 遗留实现 `secret[-4:]` 对长度 ≤4 的密钥会把密钥整个打印出来。
  重建版对长度 ≤8 的密钥只显示 `****`。真实 API 密钥远长于 8 位，正常路径不变。见
  `../../DEVIATIONS.md`。
