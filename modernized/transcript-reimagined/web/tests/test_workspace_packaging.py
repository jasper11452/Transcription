"""workspace 包的构建元数据必须可被 hatchling 解析。

UAT 跑 `uv sync --all-packages` 时才发现：`post/` 与 `runner/` 的 `dependencies`
被写进了 `[project.scripts]` 表 —— TOML 语法合法，测试用 PYTHONPATH 导入也完全
正常，但打包时 hatchling 会把 `dependencies` 当成脚本名并以
`Object reference ... must be a string` 拒绝构建。这里按同样方式解析每个
`pyproject.toml`，钉住这一类静默错误。
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECTS = [ROOT / "pyproject.toml", *sorted(ROOT.glob("*/pyproject.toml"))]


def test_project_scripts_are_all_strings():
    for path in PYPROJECTS:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        scripts = data.get("project", {}).get("scripts", {})
        bad = [key for key, value in scripts.items() if not isinstance(value, str)]
        assert not bad, (
            f"{path.relative_to(ROOT)} 的 [project.scripts] 含非字符串值：{bad} —— "
            "通常是把 dependencies 之类的键写进了 scripts 表"
        )


def test_workspace_members_declare_dependencies_as_lists():
    root = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    members = root["tool"]["uv"]["workspace"]["members"]
    assert members, "workspace 成员列表为空"
    for member in members:
        data = tomllib.loads((ROOT / member / "pyproject.toml").read_text(encoding="utf-8"))
        project = data["project"]
        assert isinstance(project.get("dependencies", []), list), member
        assert project["name"].startswith("transcript-"), member


def test_wheel_package_root_is_the_namespace_root():
    """editable 安装会把包根的父目录放进 sys.path。

    包根写成 `src/transcript_reimagined/<成员>` 时，安装后的顶层命名空间只会
    解析到该目录，其他成员（以及 web 的 `cli`）全部 import 失败 —— 测试因为
    `conftest_support` 注入了全部 `src/` 而看不见。UAT 跑 `uv sync --all-packages`
    后 `python -m transcript_reimagined.cli.main` 失败，才暴露这一点。
    """
    root = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for member in root["tool"]["uv"]["workspace"]["members"]:
        data = tomllib.loads((ROOT / member / "pyproject.toml").read_text(encoding="utf-8"))
        wheel = data["tool"]["hatch"]["build"]["targets"]["wheel"]
        assert wheel["packages"] == ["src/transcript_reimagined"], (
            f"{member}/pyproject.toml 的 wheel 包根必须是 "
            "['src/transcript_reimagined']（PEP 420 命名空间根）"
        )
