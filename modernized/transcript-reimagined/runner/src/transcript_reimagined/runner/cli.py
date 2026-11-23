"""``transcript-run`` —— Phase 1 纵向切片的命令行入口。

用法::

    transcript-run <metadata.json> --out <dir> [--glossary <glossary.txt>]
                   [--artifact txt|srt] [--stem <name>] [--json]

退出码：``0`` 成功；``2`` 元数据/参数问题；``3`` 产物被拒绝（例如要 srt 而引擎没有时间戳）。
产物被拒绝时**不写任何文件**（``RULE-061`` / ``NFR-3`` 的形态）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .metadata import MetadataError
from .products import ProductError
from .run import RunRequest, run

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_PRODUCT_REFUSED = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transcript-run",
        description="读一份音频元数据 JSON，规划分片、套词表、渲染并写出 txt/srt/raw.json。",
    )
    parser.add_argument(
        "metadata",
        help="音频元数据 JSON 的路径；'-' 表示从标准输入读",
    )
    parser.add_argument("--out", default="out", help="输出目录（默认 out）")
    parser.add_argument("--glossary", help="词表文件路径（缺省则不做替换）")
    parser.add_argument("--artifact", choices=("txt", "srt"), help="覆盖元数据里的 artifact")
    parser.add_argument("--stem", help="产物文件名（默认取元数据里的源文件名）")
    parser.add_argument("--json", action="store_true", help="以 JSON 打印运行结果")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.metadata == "-":
        request = RunRequest(
            metadata_text=sys.stdin.read(),
            out_dir=Path(args.out),
            glossary_path=Path(args.glossary) if args.glossary else None,
            artifact=args.artifact,
            stem=args.stem,
        )
    else:
        request = RunRequest(
            metadata_path=Path(args.metadata),
            out_dir=Path(args.out),
            glossary_path=Path(args.glossary) if args.glossary else None,
            artifact=args.artifact,
            stem=args.stem,
        )

    try:
        result = run(request)
    except ProductError as exc:
        print(f"产物被拒绝：{exc}", file=sys.stderr)
        return EXIT_PRODUCT_REFUSED
    except (MetadataError, OSError, ValueError) as exc:
        print(f"无法运行：{exc}", file=sys.stderr)
        return EXIT_USAGE

    if args.json:
        print(
            json.dumps(
                {
                    "files": result.files,
                    "chunk_count": len(result.chunks),
                    "glossary_changes": [
                        {"wrong": c.wrong, "right": c.right, "count": c.count}
                        for c in result.changes
                    ],
                    "trace": result.trace,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for line in result.trace:
            print(line)
        for kind, path in sorted(result.files.items()):
            print(f"{kind}: {path}")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
