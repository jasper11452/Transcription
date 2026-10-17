"""命令行入口。

两种用法：
- `transcript`            起本机服务（默认只绑 127.0.0.1）并自动打开浏览器；
- `transcript run <文件>` 不起服务，直接在终端跑一次并打印产物路径（便于脚本化与验收）。

`check` 做环境自检：密钥尾号、模型是否就绪、ffmpeg 是否可用。
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser
from pathlib import Path

from transcript_reimagined.config import Config, write_config_template
from transcript_reimagined.domain import TranscriptError
from transcript_reimagined.engines import ONLINE_ENGINES, build_engine, engine_catalog
from transcript_reimagined.orchestrate import Pipeline, Progress, estimate_cost
from transcript_reimagined.state import Store

DEFAULT_PORT = 8765

# 可探测的在线引擎：auto 是"按产物选"的策略，不是引擎
PROBE_ENGINES: tuple[str, ...] = tuple(e for e in ONLINE_ENGINES if e != "auto")


def _print_progress(progress: Progress) -> None:
    total = f" [{progress.current}/{progress.total}]" if progress.total else ""
    print(f"  {progress.stage}{total} {progress.message}", flush=True)


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from transcript_reimagined.web import DIST_DIR, FRONTEND_DIR, create_app, ensure_frontend

    config = Config.load(Path(args.config).expanduser() if args.config else None)
    store = Store(config.state_db)
    # CLI 负责构建生命周期：缺/过期产物就重建（wheel 安装没有源码则只校验产物）
    ensure_frontend(FRONTEND_DIR, DIST_DIR)
    app = create_app(config, store, validate_frontend=False)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Transcript 已启动：{url}")
    print(f"  离线模型：{config.offline_model}")
    print(
        f"  配置：{config.config_path}"
        f"（在线引擎可用 {sum(1 for e in engine_catalog(config) if e['ready'])}/{len(engine_catalog(config))}）"
    )
    if warning := config.warn_if_world_readable():
        print(f"  ⚠️  {warning}")
    if args.open_browser:
        threading.Thread(
            target=lambda: (time.sleep(1.0), webbrowser.open(url)), daemon=True
        ).start()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config = Config.load(Path(args.config).expanduser() if args.config else None)
    store = Store(config.state_db)
    source = Path(args.file).expanduser()
    if args.estimate:
        from transcript_reimagined.ingest import audio as audio_mod

        info = audio_mod.probe(source)
        cost = estimate_cost(
            args.mode, args.artifact, info.duration, online_engine=args.online_engine
        )
        estimate = f"${cost:.4f}" if cost is not None else "（该引擎单价未固定）"
        print(f"{source.name}: {info.duration:.1f}s / {info.megabytes:.1f}MB → 预估 {estimate}")
        return 0

    print(f"转写 {source}（{args.mode} → {args.artifact}，在线引擎 {args.online_engine}）")
    pipeline = Pipeline(config, store, on_event=_print_progress)
    result = pipeline.run(
        source,
        mode=args.mode,
        artifact=args.artifact,
        language=args.language,
        online_engine=args.online_engine,
    )
    if result.status != "done":
        print(f"失败：{result.error}", file=sys.stderr)
        return 1
    print(f"\n完成（{result.chars} 字，{result.audio_seconds:.0f}s 音频）")
    for label, path in (
        ("txt", result.txt_path),
        ("srt", result.srt_path),
        ("raw", result.raw_path),
    ):
        if path:
            print(f"  {label}: {path}")
    if result.cost_usd:
        print(f"  费用：${result.cost_usd:.4f}")
    if result.changes:
        print("  词表替换：" + "，".join(c.describe() for c in result.changes))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """环境自检：先把"配置本身是否可用"验证掉，再去查任务为什么失败。"""
    from transcript_reimagined.ingest import audio as audio_mod

    config = Config.load(Path(args.config).expanduser() if args.config else None)
    print("环境自检")
    print(
        f"  配置文件：{config.config_path}（{'存在' if config.config_path.exists() else '不存在'}）"
    )
    print(f"  百炼：{config.credential_status()['dashscope_api_key']}")
    print(f"  OpenRouter：{config.credential_status()['openrouter_api_key']}")
    print(f"  默认在线引擎：{config.online_engine}")
    if warning := config.warn_if_world_readable():
        print(f"  ⚠️  {warning}")

    try:
        audio_mod.require_ffmpeg()
        print("  ffmpeg/ffprobe：可用")
    except TranscriptError as exc:
        print(f"  ✗ {exc}")

    for label, module, model in (
        ("mlx-whisper", "mlx_whisper", config.timing_model),
        ("mlx-audio", "mlx_audio", config.offline_model),
    ):
        try:
            __import__(module)
            print(f"  {label}：可用（{model}）")
        except ImportError as exc:
            print(f"  ✗ {label} 不可用：{exc}")

    store = Store(config.state_db)
    print(f"  状态库：{config.state_db}")
    print(f"  累计：{store.stats()}")
    print("  可选在线引擎：")
    for engine in engine_catalog(config):
        cap = f"单次≤{engine['max_chunk_s']:.0f}s" if engine["max_chunk_s"] else "无时长声明"
        print(f"    - {engine['id']:11s} {cap:12s} {engine['label']}")

    if args.probe:
        sample = Path(args.probe)
        kinds = PROBE_ENGINES if args.probe_engine == "all" else (args.probe_engine,)
        for kind in kinds:
            try:
                engine = build_engine(kind, config, artifact="srt")
            except ValueError as exc:
                print(f"  ✗ {kind}：{exc}")
                continue
            try:
                result = engine.transcribe(sample, language="zh")
                stamps = f"{len(result.segments)} 段时间戳" if result.segments else "无时间戳"
                print(f"  ✓ {engine.name}：{stamps} · {len(result.text)} 字 · {result.text[:30]}…")
            except TranscriptError as exc:
                print(f"  ✗ {engine.name}：{exc}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="transcript", description="本机转录工具（离线优先）")
    parser.add_argument("--config", help="配置文件路径（默认 ~/.config/transcript/config.env）")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="起本机服务（默认命令）")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--host", default="127.0.0.1", help="默认只绑本机；改动前先想清楚")
    serve.add_argument("--no-browser", dest="open_browser", action="store_false", default=True)
    serve.set_defaults(func=cmd_serve)

    run = sub.add_parser("run", help="不起服务，直接转写一个文件")
    run.add_argument("file")
    run.add_argument("--mode", choices=["offline", "online"], default="offline")
    run.add_argument("--artifact", choices=["txt", "srt"], default="txt")
    run.add_argument(
        "--online-engine",
        choices=list(ONLINE_ENGINES),
        default="auto",
        help="auto=txt→百炼、srt→OpenRouter；也可指定 dashscope/openrouter/bcut",
    )
    run.add_argument("--language", default="zh")
    run.add_argument("--estimate", action="store_true", help="只显示时长与费用预估，不执行")
    run.set_defaults(func=cmd_run)

    check = sub.add_parser("check", help="环境自检")
    check.add_argument("--probe", help="用这个音频真实调用一次在线引擎")
    check.add_argument(
        "--probe-engine",
        choices=["all", *PROBE_ENGINES],
        default="all",
        help="只探测指定引擎（默认全部）",
    )
    check.set_defaults(func=cmd_check)

    init = sub.add_parser("init-config", help="生成配置模板（chmod 600）")
    init.set_defaults(func=lambda a: print(f"已写入 {write_config_template()}") or 0)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        # 默认行为：起服务并打开浏览器（这是"按需启动"的入口）
        args = parser.parse_args(["serve"])
    try:
        return int(args.func(args) or 0)
    except TranscriptError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已停止")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
