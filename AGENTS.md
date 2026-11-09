# Transcript

本机网页版转录工具：音视频 → `txt` + `srt`。FastAPI 单进程（模型常驻）+ Vite 前端。**离线为默认，在线需显式开启。** 详见 `README.md`、`PRODUCT.md`、`DESIGN.md`。

## 它现在的角色

这是**转写质量和功能的参考实现**。后继者：`/Users/jasper/Documents/Projects/asr-desktop`（原生 macOS）和 `/Users/jasper/Documents/meeting-live-notes`（Rust 重写的文件转录）。做那两个项目时，以这里为基准对照：字幕断句（`src/transcript/align.py`）、总结提示词、热词分组、设置项。本目录现在更多是对照和备份，不要把新功能优先做在这里，除非用户明确要求。

## 常用命令

```bash
uv sync
(cd frontend && npm ci && npm run build)    # 源码运行需要 Node 22.12+
uv run transcript                           # 起服务并自动打开浏览器
```

全量验证按这个顺序：

```bash
(cd frontend && npm run build && npm test)
uv run pytest
uv run ruff check
uv run ruff format --check
```

## 目录

- `src/transcript/`：后端（`align.py` 对齐与断句、`cli.py` 入口、`web/` 服务与静态产物）
- `frontend/`：Vite 前端（`npm run build` 产物放到 `src/transcript/web/static/dist`）
- `tests/`：pytest；`.acceptances/` 验收记录；`legacy/`、`modernized/`、`spikes/`、`analysis/` 历史与实验
- `state.db`、`uploads/`：真实任务数据，**测试不要碰**

## 本项目的硬规则

- **密钥只从 `~/.config/transcript/config.env` 读取**，不读 shell 里的同名环境变量；页面和日志只显示掩码尾号，永不回显明文，不打印。
- **离线为默认**；在线引擎（百炼、OpenRouter、必剪 bcut）必须由用户显式选择。必剪会把音频上传到 B 站存储，要说明。
- 热词写在 `~/.config/transcript/glossary.txt`，按 `## 组名` 分组，直接写正确写法，不要求写成“错词=正确词”。
- 新功能补隔离测试，不碰真实 `state.db` 和密钥。
- 改总结相关逻辑要同时验证流式输出和最终结果；模型配置尊重 `config.env`。
