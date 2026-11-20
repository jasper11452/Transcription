# 语音转写 · macOS

一个窗口：拖入录音，转写，校对，导出。原生 Swift，没有 Python，没有后台服务。

- **安装包** 约 30 MB 的应用 + 首次打开时下载的 3.7 GB 本机模型（只需一次，可暂停续传，自动在官方源和镜像之间择优）。
- **内存** 空闲时约 260 MB；转写时加载模型约 3.9 GB，安静 2 分钟后自动释放。
- **要求** macOS 14+，Apple 芯片。

## 使用

把录音或视频拖进窗口（可一次多个，按顺序排队），也可以直接点击「开始录音」采集麦克风；停止后录音会进入同一条转写队列。然后在同一行选引擎（本机 · 离线 / 云端 · 百炼）和语言，开始。转写中显示阶段、已用时间和预计剩余，并实时滚出已识别的文字；可以停止，失败或中途退出的任务从最后完成的一段继续。本机模式下可打开「区分说话人」（需先在设置里下载 236 MB 的 Sortformer，最多 4 人）。转写时电脑不会睡眠，完成后（应用在后台时）有系统通知，Dock 图标显示进度。语言默认「自动识别」，中英夹杂也行。

完成后在「文稿」「字幕」之间切换。文稿和字幕可直接修改，⌘F 查找替换，改动后「保存修改」，txt 和 srt 一起更新（时间轴不变）。点字幕时间码从那里播放。「总结」和「文稿对话」可以分别打开，右侧栏支持连续拖动宽度，窗口变窄时对话栏临时覆盖右侧。总结和对话都支持 Markdown 流式输出，思考过程默认折叠。对话回复里的引用角标可以跳回原文并临时高亮。每个项目保存一条会话，停止或失败时保留已生成内容，重试使用当前已保存文稿和 LLM 设置。

侧栏支持使用 ⌘ 或 ⇧ 多选项目。批量导出一次选择 TXT 或 SRT，未完成项目会在结果中列出跳过原因，同名文件会自动编号。批量删除会确认并跳过正在转录的项目。新建转录时可以多选热词组，首次默认全选，之后记住上次选择；提交时保存热词快照，旧项目重试沿用原快照。

访达里右键音频 →「打开方式」→ 语音转写，文件直接进新建页。

设置（⌘,）：转写服务（默认引擎、语言、本机识别模型标准/轻量、豆包登录、云端密钥）、本机模型（下载、暂停、换源）、词库（热词和「错词 -> 正确词」替换）、LLM（总结与对话服务、模型、思考等级、提示词）、高级（外观、阅读宽度、OpenAI 兼容本地服务）。思考等级按服务地址和模型分别保存，选择「服务默认」时不会向服务发送思考参数。

### 账号登录

设置里的「账号」提供 OpenAI 官方 **Sign in with ChatGPT**：在系统浏览器完成授权后，应用通过 PKCE 本机回调取得账号令牌，令牌只存 macOS 钥匙串，不写入 `config.env`。这条通道面向 OpenAI 的 ChatGPT 额度和 Responses API，不等同于 OpenAI API Key；当前百炼、OpenRouter 和 DeepSeek 仍按各自 API 接入。

同一页也支持「登录豆包」：应用内打开豆包网页，完成登录后只提取豆包域的会话 Cookie 和设备标识，保存到 macOS 钥匙串；Cookie 不写入 `config.env`、任务记录或日志。转写时通过豆包网页使用的流式 WebSocket 发送 16 kHz 单声道 PCM，接收中间结果并把最终文本交给现有转写队列（当前界面不会在录音尚未结束时显示 partial 文本）。此通道不是豆包公开 API，页面协议、登录态和服务条款变化都可能导致需要重新登录或暂时不可用；设置里仍保留百炼、OpenRouter 和必剪等现有接入。

### 云端接口取舍

调研了 [doubao-murmur](https://github.com/lilong7676/doubao-murmur) 的 WSS 逆向说明，以及 [doubao-say](https://github.com/quanru/doubao-say) 和 [doubao-free-api](https://github.com/5201213/doubao-free-api) 的网页登录态复用方式。它们都依赖豆包网页 Cookie 和设备参数，不是稳定的公开 API。火山引擎的[官方实时语音识别接口](https://docs.volcengine.com/docs/edge-intelligence/call-doubao-automatic-speech-recognition-model-with-real-time-api?lang=zh)仍要求 API Key；阿里云千问的[官方实时语音识别文档](https://help.aliyun.com/en/model-studio/qwen-asr-realtime-interaction-process#1)也要求 `DASHSCOPE_API_KEY`。因此本应用把“登录即用”限定为豆包网页通道，千问和官方豆包接口继续走现有密钥配置。

DeepSeek 目前没有面向第三方桌面客户端的官方账号 OAuth。其他开源客户端（Cherry Studio、LobeChat、Jan）也将 DeepSeek 实现为 API Key 或兼容接口；应用内因此只提供直达 DeepSeek API 控制台的入口，不读取或复用网页登录 Cookie。

## OpenAI 兼容本地服务

应用打开时，`http://127.0.0.1:18475` 提供 OpenAI 风格的 `POST /v1/audio/transcriptions`、`GET /v1/models`、`GET /health`，供 Spokenly 等工具使用。模型名含 `/` 走本机，否则带上 Authorization 转发到百炼。可在设置 › 高级里关闭。

## 流水线

解码（AVFoundation，音频和视频都行）→ Silero VAD 找语音 → 在静音处切成 20–40 秒的段 → Qwen3-ASR 逐段识别（热词作为上下文）→ Qwen3-ForcedAligner 给每个字打时间 → 按句生成字幕 → （可选）Sortformer 区分说话人 → 词库替换 → 写 txt 和 srt。云端识别按 60–120 秒分段；没有本机语音检测模型时按时长切分，必剪直接处理完整文件。分段方案与检查点一起保存，重试时复用原来的音频范围。

## 构建

```bash
bash Scripts/fetch-deps.sh   # 拉取 mlx-swift 和 mlx-audio-swift 到 Vendor/，并打一个小补丁
xcodebuild -downloadComponent MetalToolchain   # 第一次需要，约 840 MB
bash build.sh                # build/语音转写.app
bash build.sh --dmg          # dist/语音转写.dmg
```

没有 Developer ID，签名是 ad-hoc，首次打开见 `Runtime/安装说明.txt`。

## 数据

应用数据在 `~/Library/Application Support/语音转写/`（任务记录、模型）。如果机器上有旧的 Transcript（`~/Documents/Transcript/state.db`），历史记录只读导入，密钥和词库沿用 `~/.config/transcript/`。`-DataRoot <目录>` 把一切指向一个空目录，用来演练首次运行。

界面在 macOS 26 及以后使用液态玻璃（胶囊按钮、悬浮播放条、首次欢迎卡片），更早的系统自动回退为半透明填充。
