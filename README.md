# 语音转写 Demo（Next.js 14 + TypeScript + Tailwind）

本项目提供一个完整可运行的转写（ASR）演示：
- 前端页面支持上传音频/视频文件，选择语言/模型/提示词
- 后端 API 接收文件并调用 BCut ASR 接口完成转写
- 内置上传大小限制、基础文件类型校验、简单的速率限制

## 快速开始

1. 安装依赖

```bash
npm install
```

2. 配置环境变量（可复制 .env.example 为 .env.local 并填入值）

必须：
- BCUT_BASE_URL（如 https://api.bcut.ai）
- BCUT_API_KEY

可选：
- BCUT_TRANSCRIBE_PATH（默认 /v1/transcribe）
- BCUT_LANGUAGE、BCUT_MODEL、BCUT_PROMPT（默认参数）
- BCUT_TIMEOUT_MS（默认 120000 毫秒）
- UPLOAD_MAX_MB（默认 100MB）
- RATE_LIMIT_RPM（默认 60 次/分钟）

3. 启动开发服务器

```bash
npm run dev
```

访问 http://localhost:3000 进行体验。

## 主要脚本

- 开发：`npm run dev`
- 构建：`npm run build`
- 启动：`npm run start`
- 格式化：`npm run format`
- 检查格式：`npm run format:check`
- Lint：`npm run lint`
- 类型检查：`npm run typecheck`

## API 说明

- POST /api/transcribe
  - Content-Type: multipart/form-data
  - 字段：
    - file: 必填，音频/视频文件
    - language: 可选，如 zh、en、auto
    - model: 可选
    - prompt: 可选，最长 1000 字符
  - 响应（成功）：
    ```json
    {
      "text": "... 识别文本 ...",
      "metadata": {
        "provider": "bcut",
        "jobId": "...",
        "language": "...",
        "duration": 123.45,
        "model": "...",
        "confidence": 0.99,
        "raw": { "...BCut原始返回..." },
        "file": { "path": "...", "name": "...", "size": 1234, "type": "audio/mpeg" }
      }
    }
    ```
  - 响应（失败）：
    ```json
    { "error": "错误信息", "details": "可选的详细信息" }
    ```

- GET /api/transcribe
  - 用于健康检查与查看基础配置：最大上传大小、速率限制、支持的文件类型等。

## 支持的文件类型

详见 `lib/constants.ts`：
- 常见音频：mp3、wav、webm、ogg、m4a、aac、flac
- 常见视频：mp4、webm、ogg

前端上传 input 的 accept 会与后端校验保持一致。

## 目录结构

- app/ 前端页面与 API Route（App Router）
- lib/ 公共库：BCut 调用、配置、常量
- data/uploads/ 上传文件持久化目录

## 优化点

- 使用严格的 TypeScript 设置、ESLint + Prettier 规范
- 后端：
  - 基于文件扩展名与 MIME 的双重校验
  - 可配置的上传大小限制与速率限制
  - 环境变量集中管理（lib/config.ts），默认值清晰
  - 错误信息避免泄露敏感信息
- 前端：
  - 简洁易用的上传表单，支持可选参数
  - 结果展示与元数据查看

如需进一步优化（如断点续传、服务端流式转写、云存储对接等），可在此基础上扩展。
