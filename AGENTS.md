# asr-desktop（语音转写 · macOS）

原生 Swift（SwiftUI + MLX）的单窗口转写应用：拖入录音，转写，校对，导出。没有 Python，没有后台服务。macOS 14+，Apple 芯片。产品说明、流水线见 `README.md`。

## 常用命令

```bash
bash Scripts/fetch-deps.sh     # 拉 mlx-swift、mlx-audio-swift 到 Vendor/ 并打补丁（首次）
bash build.sh                  # build/语音转写.app
bash build.sh --dmg            # dist/语音转写.dmg
bash Scripts/test-summary-streaming.sh               # 总结流式：本地 SSE → 真实 Backend → 落盘、取消重试
python3 Scripts/test-engine-review-regressions.py    # 引擎评审回归
python3 Tests/run-workspace-editing-regressions.py   # 文稿/字幕编辑回归
```

## 目录

- `Sources/`：界面与状态（`Views`、`TranscriptViews`、`SettingsViews`、`WorkspaceModel`、`MarkdownDocument/View`）
- `Sources/Native/`：后端（`Backend` 任务与总结、`Engine` 识别流水线、`Audio`、`Downloader` 模型下载、`LocalServer` 本地 OpenAI 兼容服务 `127.0.0.1:18475`、`ConfigEnv`）
- `Tests/`：Swift 测试和回归脚本；`Runtime/`：安装说明与许可
- `Vendor/`、`build/`、`dist/` 是拉取或生成的产物，不手改

## 本项目的硬规则

- **转写质量和功能以 `/Users/jasper/Documents/Transcript` 为基准**，重做界面不能丢：字幕断句（移植自它的 `src/transcript/align.py`）、总结提示词契约、热词分组、LLM/转写服务设置。动手前先对照列出，做完逐项对齐。
- **设置入口必须一眼可见**（侧栏齿轮 + ⌘,），不因“简洁”藏起来。模型管理单独一页，转写页只选模型。
- **总结是流式的**：正文边生成边显示，思考过程默认折叠；最终 Markdown 要保留层级和颜色区分。验收要同时看流式过程和最终成稿。
- **密钥只在 `~/.config/transcript/config.env`**，不写进代码，不打印；查进程用 `pgrep -l`，不要 `pgrep -f`（会把环境变量里的密钥打出来）。
- **验收看已安装的那一版**：装机后确认安装版本和运行进程是同一版，再重启复测。
- 内存：转写时加载模型约 3.9GB，安静 2 分钟后释放；改动不能让常驻内存变大。
- 应用数据在 `~/Library/Application Support/语音转写/`，测试不要碰真实任务记录，用 `-DataRoot` 指向临时目录。
