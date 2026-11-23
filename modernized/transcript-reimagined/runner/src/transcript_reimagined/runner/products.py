"""产物的选择与落盘 —— **单点决策**。

架构 §2 点名了 legacy 的落盘缺陷：产物是**两次独立的 ``_write`` 调用**，``artifact``
只把关了一半（``RULE-061``，带 ``Suspected defect``）。人已裁定「对，但顺手补齐」，
本模块就是那次裁定的落点：

- ``artifact=srt`` 且引擎没有时间戳 → 拒绝，**一个文件都不写**（保留 legacy 行为）；
- ``artifact=txt`` → 只写 ``.txt``，**不写** ``.srt``（legacy 会多写一个空 srt —— 这是
  人已署名确认的行为变更，见 ``LEGACY_DEVIATIONS.md``）；
- ``artifact=srt`` → 照旧写 ``.txt`` 与 ``.srt`` 两个产物。

每个文件只从这里被写出，调用方拿不到「自己拼一个路径」的机会。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ALLOWED_ARTIFACTS = ("txt", "srt")


class ProductError(RuntimeError):
    """产物不可产出：请求非法，或引擎不提供时间戳却要 srt。"""


@dataclass(frozen=True)
class ProductPaths:
    """一次运行产出的三个文件。``None`` 表示按裁定**不该存在**的那个产物。"""

    txt: Path | None
    srt: Path | None
    raw_json: Path

    def written(self) -> dict[str, str]:
        """真正写出去的文件（跳过 ``None``），供 CLI 打印与测试断言。"""
        return {
            key: str(value)
            for key, value in (("txt", self.txt), ("srt", self.srt), ("raw_json", self.raw_json))
            if value is not None
        }


def select_products(
    out_dir: Path,
    stem: str,
    *,
    artifact: str,
    has_timestamps: bool,
    engine: str = "",
) -> ProductPaths:
    """决定这次运行**该有**哪些产物。这是唯一的落盘决策点。"""
    if artifact not in ALLOWED_ARTIFACTS:
        raise ProductError(f"artifact 只能是 {' / '.join(ALLOWED_ARTIFACTS)}，收到：{artifact!r}")

    if artifact == "srt" and not has_timestamps:
        where = f"引擎 {engine} " if engine else "引擎 "
        raise ProductError(f"{where}不提供时间戳，无法产出 srt（请改用离线或 mai-transcribe-2）")

    return ProductPaths(
        txt=out_dir / f"{stem}.txt",
        srt=out_dir / f"{stem}.srt" if artifact == "srt" else None,
        raw_json=out_dir / f"{stem}.raw.json",
    )


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_products(
    paths: ProductPaths,
    *,
    txt_content: str,
    srt_content: str,
    raw_payload: dict,
) -> ProductPaths:
    """把产物写到磁盘，返回实际写出的路径。

    先写 ``.txt``/``.srt`` 再写 ``.raw.json``：raw 记录里带上产物路径，
    因此它必须是最后一个落地的文件。
    """
    if paths.txt is not None:
        _write(paths.txt, txt_content)
    if paths.srt is not None:
        _write(paths.srt, srt_content)
    _write(paths.raw_json, json.dumps(raw_payload, ensure_ascii=False, indent=2))
    return paths
