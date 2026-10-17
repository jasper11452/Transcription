"""CLI：四个子命令的解析、预估与运行路径。"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from transcript_reimagined.config import Config
from transcript_reimagined.domain import AudioInfo
from transcript_reimagined.orchestrate import RunResult

cli = importlib.import_module("transcript_reimagined.cli.main")


def test_parser_has_the_four_subcommands():
    parser = cli.build_parser()
    for command in ("serve", "run", "check", "init-config"):
        assert command in parser._subparsers._group_actions[0].choices  # noqa: SLF001


def test_run_defaults():
    args = cli.build_parser().parse_args(["run", "a.wav"])
    assert args.mode == "offline"
    assert args.artifact == "txt"
    assert args.online_engine == "auto"
    assert args.language == "zh"


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        config_path=tmp_path / "config.env",
        state_db=tmp_path / "state.db",
        glossary_path=tmp_path / "glossary.txt",
        output_dir=tmp_path / "output",
    )


def test_estimate_prints_duration_and_cost(tmp_path: Path, config: Config, monkeypatch, capsys):
    source = tmp_path / "a.wav"
    source.write_bytes(b"x")
    monkeypatch.setattr(cli.Config, "load", classmethod(lambda _cls, _path=None: config))
    from transcript_reimagined.ingest import audio as audio_mod

    info = AudioInfo(source, 3600.0, 1, "wav", 16000, 1, True)
    monkeypatch.setattr(audio_mod, "probe", lambda _p: info)
    code = cli.cmd_run(
        SimpleNamespace(
            config=None,
            file=str(source),
            mode="online",
            artifact="srt",
            online_engine="openrouter",
            language="zh",
            estimate=True,
        )
    )
    assert code == 0
    assert "预估" in capsys.readouterr().out


def test_run_prints_products(tmp_path: Path, config: Config, monkeypatch, capsys):
    source = tmp_path / "a.wav"
    source.write_bytes(b"x")
    monkeypatch.setattr(cli.Config, "load", classmethod(lambda _cls, _path=None: config))
    txt = tmp_path / "a.txt"

    class FakePipeline:
        def __init__(self, *_a, **_k):
            pass

        def run(self, *_a, **_k):
            return RunResult(
                task_id=1,
                status="done",
                engine="fake",
                txt_path=txt,
                raw_path=tmp_path / "a.raw.json",
                chars=2,
                audio_seconds=1.0,
                cost_usd=0.0,
            )

    monkeypatch.setattr(cli, "Pipeline", FakePipeline)
    code = cli.cmd_run(
        SimpleNamespace(
            config=None,
            file=str(source),
            mode="offline",
            artifact="txt",
            online_engine="auto",
            language="zh",
            estimate=False,
        )
    )
    assert code == 0
    assert "完成（2 字" in capsys.readouterr().out


def test_check_reports_environment(tmp_path: Path, config: Config, monkeypatch, capsys):
    monkeypatch.setattr(cli.Config, "load", classmethod(lambda _cls, _path=None: config))
    from transcript_reimagined.ingest import audio as audio_mod

    monkeypatch.setattr(audio_mod, "require_ffmpeg", lambda: None)
    cli.cmd_check(SimpleNamespace(config=None, probe=None, probe_engine="all"))
    output = capsys.readouterr().out
    assert "环境自检" in output
    assert "ffmpeg/ffprobe：可用" in output
    assert "可选在线引擎" in output
    assert str(config.state_db) in output


def test_main_returns_one_on_transcript_error(monkeypatch, capsys):
    def boom(_args):
        raise_cls()
        return 0

    from transcript_reimagined.domain import FatalError

    def raise_cls():
        raise FatalError("配置坏了")

    parser = cli.build_parser()
    monkeypatch.setattr(parser, "parse_args", lambda _args=None: SimpleNamespace(func=boom, command="check"))
    monkeypatch.setattr(cli, "build_parser", lambda: parser)
    assert cli.main(["check"]) == 1
    assert "配置坏了" in capsys.readouterr().err
