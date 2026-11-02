"""接口契约测试：字段名、校验、状态码、以及"页面能不能真的看到东西"。

这些用例的重点不是覆盖率，而是**钉住前后端之间的字段契约**：
字段改名、状态码改动、错误格式从 `{"error": ...}` 变回 `{"detail": ...}` 都会在这里红。
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from transcript.config import Config
from transcript.glossary import parse_glossary
from transcript.render import parse_srt
from transcript.store import Store
from transcript.summary import MAX_HOT_WORD_GROUPS, SummaryManager
from transcript.web.frontend import DIST_DIR

WAV_SECONDS = 0.2


def make_wav(path: Path, seconds: float = WAV_SECONDS) -> Path:
    """写一个真能过 ffprobe 的小 wav。

    假文件（几个字节）会在 `audio_mod.probe` 就被挡下，测不到后面的分支。
    """
    rate = 8000
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(b"\x00\x00" * int(rate * seconds))
    return path


# ---------- 页面与静态资源 ----------


def test_页面两个入口都返回构建产物(client: TestClient) -> None:
    for url, entry in (("/", "index.html"), ("/t/1", "task.html")):
        resp = client.get(url)
        assert resp.status_code == 200, url
        assert "text/html" in resp.headers["content-type"]
        # 页面必须引用挂在 /static/dist 下的资源；换成 /assets/ 就会 404（实测过）
        assert "/static/dist/assets/" in resp.text
        assert entry != ""  # 只是让两个分支都写清楚在测哪个入口


def test_manifest_引用的资源都能被服务(client: TestClient) -> None:
    manifest = json.loads((DIST_DIR / ".vite" / "manifest.json").read_text())
    for entry in ("index.html", "task.html"):
        assert manifest[entry]["isEntry"] is True
    names = sorted({a["file"] for a in manifest.values()})
    assert names, "manifest 里没有任何资源"
    for name in names:
        resp = client.get(f"/static/dist/{name}")
        assert resp.status_code == 200, name
        assert len(resp.content) > 0, name


def test_不服务开发目录里的旧静态页(client: TestClient) -> None:
    """旧 static/*.html 留着做参考，但不能再被服务出去——两套页面会互相打架。"""
    assert client.get("/static/app.js").status_code == 404
    assert client.get("/static/dist/../app.js").status_code == 404


# ---------- 状态 ----------


def test_status_的密钥只给掩码尾号(client: TestClient, config: Config) -> None:
    config.dashscope_api_key = "sk-secret-dash-1234"
    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "sk-secret-dash-1234" not in resp.text
    assert body["credentials"]["dashscope_api_key"] == "已配置（尾号 1234）"
    assert body["credentials"]["openrouter_api_key"] == "未配置"
    assert body["online_ready"] is True
    # 输入框占位符：只给固定长度的点 + 尾号，中间一律掩盖
    fields = {f["attr"]: f for f in body["key_fields"]}
    assert fields["dashscope_api_key"]["masked"] == "••••••••1234"
    assert fields["openrouter_api_key"]["masked"] == ""


def test_密钥字段集合从引擎表派生(client: TestClient) -> None:
    fields = client.get("/api/status").json()["key_fields"]
    attrs = [f["attr"] for f in fields]
    assert "dashscope_api_key" in attrs
    assert "openrouter_api_key" in attrs
    assert len(attrs) == len(set(attrs)), "同一把钥匙不能在页面出现两次"
    for field in fields:
        assert field["label"], "每个字段都要有中文标签"
        assert set(field) >= {"attr", "env", "label", "status", "masked", "configured"}


def test_status_带默认值给控制台(client: TestClient) -> None:
    defaults = client.get("/api/status").json()["defaults"]
    # 在线模式必须由使用者显式开启。
    assert defaults["mode"] == "offline"
    assert defaults["artifact"] in {"txt", "srt"}
    assert defaults["language"]
    assert defaults["online_engine"] in {"auto", "dashscope", "openrouter", "bcut"}


def test_首页把启动状态内联进_HTML(client: TestClient, config: Config) -> None:
    """首屏不能等 /api/status 回来才画。

    侧栏「在线密钥」在拿到状态前只能画个占位框，拿到后长成密钥字段，会把下面的
    区块往下顶，实测 CLS 0.011～0.020 全来自这里。所以状态得跟着 HTML 一起到。
    """
    config.dashscope_api_key = "sk-secret-dash-1234"
    for path in ("/", "/t/1"):
        resp = client.get(path)
        assert resp.status_code == 200
        html = resp.text
        assert "window.__BOOT__=" in html, f"{path} 没内联启动状态"
        # 内联的仍然是掩码，不是明文
        assert "sk-secret-dash-1234" not in html
        assert "••••••••1234" in html
        # 页面本身还是构建产物
        assert "/static/dist/assets/" in html

    boot = json.loads(
        client.get("/").text.split("window.__BOOT__=", 1)[1].split(";</script>", 1)[0]
    )
    assert boot["task"] is None, "控制台不该背一个任务"
    assert boot["status"]["defaults"]["mode"] == "offline"
    fields = {f["attr"]: f for f in boot["status"]["key_fields"]}
    assert fields["dashscope_api_key"]["masked"] == "••••••••1234"
    assert boot["status"]["online_engines"], "引擎表也得跟着到，否则下拉首帧是空的"
    # 侧栏任务表内联：不内联的话进页后还要等一次 /api/tasks 往返。
    assert isinstance(boot["tasks"], list), "侧栏任务表也得跟着 HTML 一起到"


def test_任务页把任务本身也内联进_HTML(client: TestClient, store: Store) -> None:
    """不内联的话，加载中渲染的是另一套顶栏，任务一到就换掉：徽章横移 200px 以上。"""
    task_id = store.create_task(
        name="内联样例", source_path="/tmp/x.m4a", mode="offline", artifact="srt"
    )
    html = client.get(f"/t/{task_id}").text
    boot = json.loads(html.split("window.__BOOT__=", 1)[1].split(";</script>", 1)[0])
    assert boot["task"] is not None
    assert boot["task"]["task"]["id"] == task_id
    assert boot["task"]["task"]["name"] == "内联样例"
    assert boot["task"]["chunks"] == []
    # 没这条任务（或任务号不合法）时不内联，交给前端渲染提示页
    assert (
        json.loads(
            client.get("/t/9999").text.split("window.__BOOT__=", 1)[1].split(";</script>", 1)[0]
        )["task"]
        is None
    )
    assert (
        json.loads(
            client.get("/t/abc").text.split("window.__BOOT__=", 1)[1].split(";</script>", 1)[0]
        )["task"]
        is None
    )


def test_内联_JSON_不会提前终结脚本块() -> None:
    from transcript.web.app import _inline_json

    raw = _inline_json({"note": "</script><script>alert(1)</script>", "中文": "保留"})
    assert "<" not in raw, "内联 JSON 里不能出现裸的 <"
    assert json.loads(raw) == {"note": "</script><script>alert(1)</script>", "中文": "保留"}


# ---------- 任务列表 ----------


def test_空库的列表是空数组不是报错(client: TestClient) -> None:
    body = client.get("/api/tasks").json()
    assert body == {"tasks": []}


def test_列表带注解字段(client: TestClient, store: Store, tmp_path: Path) -> None:
    src = tmp_path / "a.m4a"
    src.write_bytes(b"x")
    task_id = store.create_task(
        name="a", source_path=str(src), mode="offline", artifact="srt", engine="offline:x"
    )
    store.update_task(task_id, status="done", txt_path=str(tmp_path / "a.txt"))
    (tmp_path / "a.txt").write_text("正文", encoding="utf-8")

    task = client.get("/api/tasks").json()["tasks"][0]
    # 前端按这些字段决定按钮能不能点；缺一个就是"看着能点、点了报错"
    for key in (
        "is_terminal",
        "running",
        "cancelling",
        "resumable",
        "txt_exists",
        "srt_exists",
        "src_exists",
    ):
        assert key in task, key
    assert task["is_terminal"] is True
    assert task["txt_exists"] is True
    assert task["srt_exists"] is False
    assert task["src_exists"] is True
    assert task["resumable"] is False


def test_产物路径还在但文件已被清理时_exists_为假(
    client: TestClient, store: Store, tmp_path: Path
) -> None:
    """僵尸按钮的回归测试：路径记在库里、文件却没了，按钮必须当场变灰。"""
    missing = tmp_path / "gone.txt"
    task_id = store.create_task(
        name="a", source_path=str(tmp_path / "a.m4a"), mode="offline", artifact="txt"
    )
    store.update_task(task_id, status="done", txt_path=str(missing))

    task = client.get(f"/api/tasks/{task_id}").json()["task"]
    assert task["txt_path"] == str(missing)
    assert task["txt_exists"] is False


def test_limit_被夹在_1_到_200(client: TestClient, store: Store) -> None:
    for i in range(3):
        store.create_task(
            name=f"t{i}", source_path=f"/tmp/t{i}.m4a", mode="offline", artifact="txt"
        )
    assert len(client.get("/api/tasks?limit=0").json()["tasks"]) == 1
    assert len(client.get("/api/tasks?limit=999").json()["tasks"]) == 3


# ---------- 单任务 ----------


def test_任务详情带分片读数(client: TestClient, store: Store, tmp_path: Path) -> None:
    task_id = store.create_task(
        name="a", source_path=str(tmp_path / "a.m4a"), mode="offline", artifact="srt"
    )
    store.upsert_chunk(task_id, idx=0, start=0.0, end=60.0, status="done", text="甲乙丙")
    store.upsert_chunk(task_id, idx=1, start=60.0, end=120.0, status="failed", error="超时")

    body = client.get(f"/api/tasks/{task_id}").json()
    assert body["task"]["id"] == task_id
    assert {"running", "resumable", "cancelling"} <= set(body)
    assert [c["idx"] for c in body["chunks"]] == [0, 1]
    assert body["chunks"][0]["chars"] == 3
    assert body["chunks"][1]["error"] == "超时"


@pytest.mark.parametrize("url", ["/api/tasks/999", "/api/tasks/999/output?kind=txt"])
def test_不存在的任务返回_404_且错误是_error_字段(client: TestClient, url: str) -> None:
    resp = client.get(url)
    assert resp.status_code == 404
    assert "任务不存在" in resp.json()["error"]


def test_地址里不是数字的任务号也回页面(client: TestClient) -> None:
    """手敲地址、旧书签会出现这种路径。

    这里必须回 200 + task.html：非 2xx 的 JSON 响应会被浏览器直接渲染成一段 JSON，
    用户看到的就是一页校验错误，而不是能带他回控制台的提示页。
    地址对不对由前端判断（见 frontend/src/entries/task.tsx 的 BrokenPath）。
    """
    resp = client.get("/t/not-a-number")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "/static/dist/assets/" in resp.text
    assert client.get("/t/12/").status_code == 200


# ---------- 建任务校验 ----------


@pytest.mark.parametrize(
    ("field", "value", "hint"),
    [
        ("mode", "fast", "mode"),
        ("artifact", "json", "artifact"),
        ("online_engine", "whisper", "online_engine"),
    ],
)
def test_非法枚举值被挡在门口(
    client: TestClient, tmp_path: Path, field: str, value: str, hint: str
) -> None:
    audio = make_wav(tmp_path / "a.wav")
    payload = {
        "source_path": str(audio),
        "mode": "offline",
        "artifact": "srt",
        "online_engine": "auto",
        field: value,
    }
    resp = client.post("/api/tasks", data=payload)
    assert resp.status_code == 400
    assert hint in resp.json()["error"]


def test_文件不存在时给中文报错(client: TestClient, tmp_path: Path) -> None:
    resp = client.post(
        "/api/tasks", data={"source_path": str(tmp_path / "nope.m4a"), "mode": "offline"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"].strip(), "错误信息不能是空的"


def test_不是音视频的文件被挡下(client: TestClient, tmp_path: Path) -> None:
    """后缀对、内容错的文件不能进队列：否则要等到跑完才报错。"""
    junk = tmp_path / "a.m4a"
    junk.write_bytes(b"not audio at all")
    resp = client.post("/api/tasks", data={"source_path": str(junk), "mode": "offline"})
    assert resp.status_code == 400
    assert resp.json()["error"].strip()


def test_在线缺密钥时不进队列(client: TestClient, tmp_path: Path) -> None:
    audio = make_wav(tmp_path / "a.wav")
    resp = client.post(
        "/api/tasks",
        data={
            "source_path": str(audio),
            "mode": "online",
            "artifact": "srt",
            "online_engine": "openrouter",
        },
    )
    assert resp.status_code == 400
    assert "OPENROUTER_API_KEY" in resp.json()["error"]
    assert client.get("/api/tasks").json()["tasks"] == [], "校验失败不能留下任务记录"


# ---------- 生命周期 ----------


def test_对不在跑的任务取消是_409(client: TestClient, store: Store) -> None:
    task_id = store.create_task(name="a", source_path="/tmp/a.m4a", mode="offline", artifact="txt")
    resp = client.post(f"/api/tasks/{task_id}/cancel")
    assert resp.status_code == 409
    assert "不在运行中" in resp.json()["error"]


def test_删除只删记录_不动盘上文件(client: TestClient, store: Store, tmp_path: Path) -> None:
    txt = tmp_path / "keep.txt"
    txt.write_text("别动我", encoding="utf-8")
    task_id = store.create_task(name="a", source_path="/tmp/a.m4a", mode="offline", artifact="txt")
    store.update_task(task_id, status="done", txt_path=str(txt))

    assert client.delete(f"/api/tasks/{task_id}").json() == {"deleted": task_id}
    assert client.get(f"/api/tasks/{task_id}").status_code == 404
    assert txt.read_text(encoding="utf-8") == "别动我"


def test_删除正在跑的任务被挡下(client: TestClient, store: Store) -> None:
    """用例直接在"同一个" manager 上构造 running，不真起线程。"""
    task_id = store.create_task(name="a", source_path="/tmp/a.m4a", mode="offline", artifact="txt")
    manager = client.app.state.jobs
    try:
        with manager._lock:  # noqa: SLF001 - 只为构造状态，不跑真任务
            manager._running.add(task_id)
        resp = client.delete(f"/api/tasks/{task_id}")
        assert resp.status_code == 409
        assert "不能删除" in resp.json()["error"]
    finally:
        with manager._lock:  # noqa: SLF001
            manager._running.discard(task_id)


# ---------- 产物与音频 ----------


def test_output_截断并给出标记(client: TestClient, store: Store, tmp_path: Path) -> None:
    txt = tmp_path / "big.txt"
    txt.write_text("字" * 200_001, encoding="utf-8")
    task_id = store.create_task(name="a", source_path="/tmp/a.m4a", mode="offline", artifact="txt")
    store.update_task(task_id, status="done", txt_path=str(txt))

    body = client.get(f"/api/tasks/{task_id}/output?kind=txt").json()
    assert body["truncated"] is True
    assert len(body["content"]) == 200_000


@pytest.mark.parametrize("kind", ["txt", "srt"])
def test_output_file_读取和下载都保留完整字节(
    client: TestClient, store: Store, tmp_path: Path, kind: str
) -> None:
    output = tmp_path / f"会议文稿.{kind}"
    # 超过预览上限，并覆盖中文、CRLF 和最后一行，不能通过重新拼 Blob 丢失字节。
    data = ("第一句话。第二句话。\r\n" * 20_000 + "全文末尾✓\n").encode("utf-8")
    output.write_bytes(data)
    task_id = store.create_task(name="a", source_path="/tmp/a.m4a", mode="offline", artifact=kind)
    store.update_task(task_id, status="done", **{f"{kind}_path": str(output)})

    preview = client.get(f"/api/tasks/{task_id}/output?kind={kind}").json()
    assert preview["truncated"] is True
    assert len(preview["content"]) == 200_000
    for download in (False, True):
        resp = client.get(
            f"/api/tasks/{task_id}/output/file",
            params={"kind": kind, "download": str(download).lower()},
        )
        assert resp.status_code == 200
        assert resp.content == data
        assert resp.text.endswith("全文末尾✓\n")
        assert resp.headers["content-type"] == "text/plain; charset=utf-8"
        assert resp.headers["cache-control"] == "no-store"
        if download:
            assert resp.headers["content-disposition"].startswith("attachment;")
            assert "filename*=utf-8''" in resp.headers["content-disposition"]
        else:
            assert "content-disposition" not in resp.headers


def test_output_file_缺任务缺产物和非法类型都返回404(
    client: TestClient, store: Store, tmp_path: Path
) -> None:
    assert client.get("/api/tasks/999999/output/file").json() == {"error": "任务不存在"}
    task_id = store.create_task(name="a", source_path="/tmp/a.m4a", mode="offline", artifact="txt")
    for kind in ("txt", "srt", "raw", "../../config.env"):
        resp = client.get(f"/api/tasks/{task_id}/output/file", params={"kind": kind})
        assert resp.status_code == 404
        assert "error" in resp.json()
    store.update_task(task_id, txt_path=str(tmp_path / "missing.txt"))
    resp = client.get(f"/api/tasks/{task_id}/output/file")
    assert resp.status_code == 404
    assert "已被移动或删除" in resp.json()["error"]


def test_output_的_kind_不对时明确报错(client: TestClient, store: Store) -> None:
    task_id = store.create_task(name="a", source_path="/tmp/a.m4a", mode="offline", artifact="txt")
    resp = client.get(f"/api/tasks/{task_id}/output?kind=srt")
    assert resp.status_code == 404
    assert "srt" in resp.json()["error"]


def test_产物被删后_output_报清楚(client: TestClient, store: Store, tmp_path: Path) -> None:
    task_id = store.create_task(name="a", source_path="/tmp/a.m4a", mode="offline", artifact="txt")
    store.update_task(task_id, status="done", txt_path=str(tmp_path / "gone.txt"))
    resp = client.get(f"/api/tasks/{task_id}/output?kind=txt")
    assert resp.status_code == 404
    assert "已被移动或删除" in resp.json()["error"]


def test_音频按扩展名给_MIME(client: TestClient, store: Store, tmp_path: Path) -> None:
    """m4a 给 octet-stream 浏览器会拒播；这里钉住映射。

    内容写真实 wav 字节：只要扩展名对应，FileResponse 不管内容。
    """
    body = make_wav(tmp_path / "src.wav").read_bytes()
    for suffix, expected in ((".m4a", "audio/mp4"), (".mp3", "audio/mpeg"), (".wav", "audio/wav")):
        src = tmp_path / f"a{suffix}"
        src.write_bytes(body)
        task_id = store.create_task(name="a", source_path=str(src), mode="offline", artifact="txt")
        resp = client.get(f"/api/tasks/{task_id}/audio")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith(expected), suffix


def test_原文件没了音频请求_404(client: TestClient, store: Store, tmp_path: Path) -> None:
    task_id = store.create_task(
        name="a", source_path=str(tmp_path / "gone.m4a"), mode="offline", artifact="txt"
    )
    resp = client.get(f"/api/tasks/{task_id}/audio")
    assert resp.status_code == 404
    assert "已被移动或删除" in resp.json()["error"]


# ---------- 热词词表 ----------


def test_词表读写真跑一趟(client: TestClient, config: Config) -> None:
    assert client.get("/api/glossary").json()["text"] == ""
    saved = client.put("/api/glossary", data={"text": "艾麦 -> 爱迈\n佳绿 => 家禄\n"})
    assert saved.status_code == 200
    assert saved.json()["rule_count"] == 2

    body = client.get("/api/glossary").json()
    assert [r["wrong"] for r in body["rules"]] == ["艾麦", "佳绿"]
    assert body["text"].startswith("艾麦")
    assert config.glossary_path.read_text(encoding="utf-8").startswith("艾麦")


def test_坏行不落盘且指出第几行(client: TestClient, config: Config) -> None:
    # 裸热词是合法写法（不再报错）；真正的坏行是“只有一个方向”的替换规则。
    resp = client.put("/api/glossary", data={"text": "好行 -> 替换\n坏行 -> \n"})
    assert resp.status_code == 400
    assert "第 2 行" in resp.json()["error"] or "2" in resp.json()["error"]
    assert not config.glossary_path.exists(), "校验失败时不能写半个文件进去"


# ---------- 凭据 ----------


def test_写密钥后再读只回掩码(client: TestClient, config: Config) -> None:
    resp = client.post(
        "/api/credentials",
        json={"keys": {"dashscope_api_key": "sk-abcdefgh9876"}, "clear": []},
    )
    assert resp.status_code == 200
    assert "sk-abcdefgh9876" not in resp.text
    assert "sk-abcdefgh9876" in config.config_path.read_text(encoding="utf-8")
    engines = {e["id"]: e for e in resp.json()["online_engines"]}
    assert engines["dashscope"]["ready"] is True
    assert engines["openrouter"]["ready"] is False
    cleared = client.post("/api/credentials", json={"clear": ["dashscope_api_key"]})
    engines = {e["id"]: e for e in cleared.json()["online_engines"]}
    assert engines["dashscope"]["ready"] is False


def test_配置文件权限保持_600(client: TestClient, config: Config) -> None:
    client.post("/api/credentials", json={"keys": {"dashscope_api_key": "sk-x1234"}, "clear": []})
    assert oct(config.config_path.stat().st_mode)[-3:] == "600"


# ---------- Agent 总结 ----------


def test_总结接口_状态与未配置密钥的_400(client: TestClient, store: Store, config: Config) -> None:
    task_id = store.create_task(name="a", source_path="/tmp/a.m4a", mode="offline", artifact="srt")

    payload = client.get(f"/api/tasks/{task_id}/summary").json()
    assert payload["enabled"] is False
    assert payload["available"] is False
    assert payload["status"] == "disabled"
    assert payload["content"] is None
    assert payload["model"] == config.summary_model

    resp = client.post(f"/api/tasks/{task_id}/summary")
    assert resp.status_code == 400
    assert "OpenRouter" in resp.json()["error"]


def test_静态产物_只有带哈希的_assets_能长缓存(client: TestClient) -> None:
    """assets 文件名带内容哈希，可以 immutable；dist 根的 theme.js 名字固定，不能跟着长缓存。"""
    built = next((DIST_DIR / "assets").glob("*.js"))
    response = client.get(f"/static/dist/assets/{built.name}")
    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]

    theme = client.get("/static/dist/theme.js")
    assert theme.status_code == 200
    assert "immutable" not in theme.headers.get("cache-control", "")


def test_总结增量返回_只给上次之后新增的尾巴(config: Config, store: Store) -> None:
    """页面带着已收到的长度来，后端只回尾巴：长总结不能每轮整份重下。"""
    config.openrouter_api_key = "test-key"
    task_id = store.create_task(name="a", source_path="/tmp/a.m4a", mode="offline", artifact="srt")
    manager = SummaryManager(config, store)
    manager._partial[task_id] = {"content": '{"title":"x"', "reasoning": "先想"}

    full = manager.payload(task_id)
    assert full["partial"]["content"] == '{"title":"x"'
    assert full["partial"]["reasoning"] == "先想"
    assert full["partial"]["content_length"] == 12

    tail = manager.payload(task_id, since=9, reasoning_since=1)
    assert tail["partial"]["content"] == '"x"'
    assert tail["partial"]["reasoning"] == "想"
    assert tail["partial"]["content_length"] == 12

    # 游标超过现有长度（例如总结重开）时退化到空尾巴，长度对齐交给页面判断
    assert manager.payload(task_id, since=999)["partial"]["content"] == ""
    assert manager.payload(task_id, since=999)["partial"]["content_length"] == 12


def test_总结接口_任务不存在返回_404(client: TestClient) -> None:
    assert client.get("/api/tasks/99999/summary").status_code == 404
    assert client.post("/api/tasks/99999/summary").status_code == 404


def test_开启总结_任务未完成时保持等待(config: Config, store: Store, client: TestClient) -> None:
    """显式授权只改总结自己的状态，不影响转录任务本身。"""
    config.openrouter_api_key = "test-key"
    task_id = store.create_task(name="a", source_path="/tmp/a.m4a", mode="offline", artifact="srt")

    payload = client.post(f"/api/tasks/{task_id}/summary").json()
    assert payload["enabled"] is True
    assert payload["available"] is True
    assert payload["status"] == "waiting"

    task = client.get(f"/api/tasks/{task_id}").json()["task"]
    assert task["status"] == "running"  # create_task 的默认态：总结不改变转录任务本身


def test_保存校对结果_同时重写字幕与文稿(client: TestClient, store: Store, tmp_path: Path) -> None:
    """在线编辑只改正文：srt 与 txt 一起落盘，时间轴不许动。"""
    srt_path = tmp_path / "a.srt"
    txt_path = tmp_path / "a.txt"
    srt_path.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\n旧字幕\n\n"
        "2\n00:00:02,000 --> 00:00:04,000\n第二句\n",
        encoding="utf-8",
    )
    txt_path.write_text("旧字幕第二句\n", encoding="utf-8")
    task_id = store.create_task(name="a", source_path="/tmp/a.m4a", mode="offline", artifact="srt")
    store.update_task(task_id, status="done", srt_path=str(srt_path), txt_path=str(txt_path))

    edited = (
        "1\n00:00:00,000 --> 00:00:02,000\n新字幕\n\n"
        "2\n00:00:02,000 --> 00:00:04,000\n第二句\n"
    )
    resp = client.put(f"/api/tasks/{task_id}/artifacts", json={"srt": edited})
    assert resp.status_code == 200, resp.text
    assert "新字幕" in srt_path.read_text(encoding="utf-8")
    assert txt_path.read_text(encoding="utf-8") == "新字幕第二句\n"
    assert client.get(f"/api/tasks/{task_id}").json()["task"]["chars"] == 6

    # 少一行：拒绝保存，磁盘保持原样
    before = srt_path.read_text(encoding="utf-8")
    bad_rows = client.put(
        f"/api/tasks/{task_id}/artifacts",
        json={"srt": "1\n00:00:00,000 --> 00:00:02,000\n只有一行\n"},
    )
    assert bad_rows.status_code == 400
    assert srt_path.read_text(encoding="utf-8") == before

    # 改时间轴：拒绝
    shifted = edited.replace("00:00:02,000 --> 00:00:04,000", "00:00:03,000 --> 00:00:05,000")
    assert client.put(f"/api/tasks/{task_id}/artifacts", json={"srt": shifted}).status_code == 400

    # 正文清空：拒绝
    empty = edited.replace("第二句", " ")
    assert client.put(f"/api/tasks/{task_id}/artifacts", json={"srt": empty}).status_code == 400


def test_保存校对结果_同文不同句不会改错行(
    client: TestClient, store: Store, tmp_path: Path
) -> None:
    """两句正文一模一样时，改第二句不能把第一句替换掉。"""
    srt_path = tmp_path / "dup.srt"
    txt_path = tmp_path / "dup.txt"
    srt_path.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\n好的\n\n"
        "2\n00:00:02,000 --> 00:00:04,000\n好的\n",
        encoding="utf-8",
    )
    txt_path.write_text("好的好的\n", encoding="utf-8")
    task_id = store.create_task(name="dup", source_path="/tmp/d.m4a", mode="offline", artifact="srt")
    store.update_task(task_id, status="done", srt_path=str(srt_path), txt_path=str(txt_path))

    edited = (
        "1\n00:00:00,000 --> 00:00:02,000\n好的\n\n"
        "2\n00:00:02,000 --> 00:00:04,000\n对的\n"
    )
    assert client.put(f"/api/tasks/{task_id}/artifacts", json={"srt": edited}).status_code == 200
    assert txt_path.read_text(encoding="utf-8") == "好的对的\n"


def test_保存校对结果_注释留痕不被正文替换波及(
    client: TestClient, store: Store, tmp_path: Path
) -> None:
    """热词留痕和正文含同样的词时，只改正文里的那一处。"""
    srt_path = tmp_path / "note.srt"
    txt_path = tmp_path / "note.txt"
    srt_path.write_text(
        "# 热词替换：砹脉 → 艾脉\n\n"
        "1\n00:00:00,000 --> 00:00:02,000\n砹脉\n\n"
        "2\n00:00:02,000 --> 00:00:04,000\n第二句\n",
        encoding="utf-8",
    )
    txt_path.write_text("# 热词替换：砹脉 → 艾脉\n砹脉第二句\n", encoding="utf-8")
    task_id = store.create_task(name="note", source_path="/tmp/n.m4a", mode="offline", artifact="srt")
    store.update_task(task_id, status="done", srt_path=str(srt_path), txt_path=str(txt_path))

    edited = (
        "# 热词替换：砹脉 → 艾脉\n\n"
        "1\n00:00:00,000 --> 00:00:02,000\n#话题\n\n"
        "2\n00:00:02,000 --> 00:00:04,000\n改过了\n"
    )
    assert client.put(f"/api/tasks/{task_id}/artifacts", json={"srt": edited}).status_code == 200
    assert txt_path.read_text(encoding="utf-8") == "# 热词替换：砹脉 → 艾脉\n#话题改过了\n"
    assert "#话题" in srt_path.read_text(encoding="utf-8")


def test_全文编辑文稿_按原时间轴重新切句(client: TestClient, store: Store, tmp_path: Path) -> None:
    """全文是唯一真相；srt 跟着对齐回原时间轴，不新增/移动时间码。"""
    srt_path = tmp_path / "full.srt"
    txt_path = tmp_path / "full.txt"
    srt_path.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\n第一句\n\n"
        "2\n00:00:02,000 --> 00:00:04,000\n第二句\n\n"
        "3\n00:00:04,000 --> 00:00:06,000\n第三句\n",
        encoding="utf-8",
    )
    txt_path.write_text("第一句第二句第三句\n", encoding="utf-8")
    task_id = store.create_task(name="full", source_path="/tmp/f.m4a", mode="offline", artifact="srt")
    store.update_task(task_id, status="done", srt_path=str(srt_path), txt_path=str(txt_path))

    resp = client.put(
        f"/api/tasks/{task_id}/transcript",
        json={"text": "第一句改过了\n第二句\n第三句"},
    )
    assert resp.status_code == 200, resp.text
    assert txt_path.read_text(encoding="utf-8") == "第一句改过了\n第二句\n第三句\n"
    segments = parse_srt(srt_path.read_text(encoding="utf-8"))
    assert [segment.text for segment in segments] == ["第一句改过了", "第二句", "第三句"]
    assert [round(segment.start, 1) for segment in segments] == [0.0, 2.0, 4.0]

    # 删掉一整句：时间轴不挪，文字不能丢
    resp = client.put(f"/api/tasks/{task_id}/transcript", json={"text": "第一句改过了\n第三句"})
    assert resp.status_code == 200, resp.text
    joined = "".join(segment.text for segment in parse_srt(srt_path.read_text(encoding="utf-8")))
    assert joined == "第一句改过了第三句"

    # 空文稿拒绝保存
    assert client.put(f"/api/tasks/{task_id}/transcript", json={"text": "  "}).status_code == 400


# ---------- 模型清单（设置页的下拉） ----------


def test_模型清单_未配置密钥时提示可手填(client: TestClient, config: Config) -> None:
    config.openrouter_api_key = ""
    resp = client.get("/api/summary-models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["models"] == []
    assert "密钥" in body["error"]


def test_模型清单_整理上游字段并按_id_排序(
    client: TestClient, config: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    config.openrouter_api_key = "test-key"

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "data": [
                    {
                        "id": "z-ai/glm-5.3-flash",
                        "name": "Z.ai: GLM 5.3 Flash",
                        "context_length": 1048576,
                        "supported_parameters": ["reasoning", "tools"],
                        "pricing": {"prompt": "0.000001"},
                    },
                    {"id": "deepseek/deepseek-chat"},
                    {"name": "没有 id 的条目"},
                ]
            }

    monkeypatch.setattr("transcript.web.app.httpx.get", lambda *a, **k: FakeResponse())
    body = client.get("/api/summary-models").json()

    assert body["error"] is None
    assert [m["id"] for m in body["models"]] == ["deepseek/deepseek-chat", "z-ai/glm-5.3-flash"]
    glm = body["models"][1]
    assert glm["reasoning"] is True
    assert glm["context_length"] == 1048576
    assert glm["price_per_million_prompt"] == pytest.approx(1.0)
    # 上游缺字段时给安全默认值，页面不会崩
    assert body["models"][0]["reasoning"] is False
    assert body["models"][0]["price_per_million_prompt"] is None


def test_保存设置的热词写进词表且保留替换规则(
    client: TestClient, config: Config, tmp_path: Path
) -> None:
    """热词只写正确写法；保存时不能吃掉已有的 `错词 -> 正确词` 规则和注释。"""
    config.openrouter_api_key = "test-key"
    config.glossary_path.write_text("# 我的词表\n艾麦 -> 砹脉\n\n老热词\n", encoding="utf-8")

    payload = client.put(
        "/api/summary-settings",
        json={
            "model": "z-ai/glm-5.3-flash",
            "base_url": "https://openrouter.ai/api/v1",
            "prompt": "重点写决策",
            "hot_words": ["小新", "选号侠", "小新"],
        },
    ).json()

    # 返回的是“规范写法”集合：裸热词 + 替换规则的右值
    assert payload["hot_words"] == ["小新", "选号侠", "砹脉"]
    assert payload["glossary_path"] == str(config.glossary_path)
    text = config.glossary_path.read_text(encoding="utf-8")
    assert "# 我的词表" in text
    assert "艾麦 -> 砹脉" in text
    assert "老热词" not in text
    assert {r.wrong for r in parse_glossary(text)} == {"艾麦"}

    # 再读一次接口：热词从词表里解析回来
    assert client.get("/api/summary-settings").json()["hot_words"] == ["小新", "选号侠", "砹脉"]


def test_热词里的非法写法被挡下(client: TestClient, config: Config) -> None:
    config.openrouter_api_key = "test-key"
    body = {
        "model": "z-ai/glm-5.3-flash",
        "base_url": "https://openrouter.ai/api/v1",
        "prompt": "",
    }
    resp = client.put("/api/summary-settings", json={**body, "hot_words": ["小心=小新"]})
    assert resp.status_code == 400
    assert "=" in resp.json()["error"]


def test_热词分组保存后保留规则并保持组顺序(client: TestClient, config: Config) -> None:
    config.openrouter_api_key = "test-key"
    config.glossary_path.write_text("## 产品\n旧词\n\n艾麦 -> 砹脉\n", encoding="utf-8")
    body = {
        "model": "z-ai/glm-5.3-flash",
        "base_url": "https://openrouter.ai/api/v1",
        "prompt": "重点写决策",
    }
    payload = client.put(
        "/api/summary-settings",
        json={
            **body,
            "hot_word_groups": [
                {"name": "产品", "words": ["小新"]},
                {"name": "客户", "words": ["选号侠", "小新"]},
                {"name": "", "words": ["旧词"]},
            ],
        },
    ).json()

    # 未分组词条写在最前面，否则解析时会被算进最后一个命名分组。
    assert payload["hot_word_groups"] == [
        {"name": "", "words": ["旧词"]},
        {"name": "产品", "words": ["小新"]},
        {"name": "客户", "words": ["选号侠"]},
    ]
    assert payload["max_hot_word_groups"] > 0
    text = config.glossary_path.read_text(encoding="utf-8")
    assert "## 产品" in text and "## 客户" in text
    assert "艾麦 -> 砹脉" in text
    assert {rule.wrong for rule in parse_glossary(text)} == {"艾麦"}
    assert payload["hot_words"] == ["旧词", "小新", "选号侠", "砹脉"]
    # 再读一次接口：分组从词表里解析回来
    assert (
        client.get("/api/summary-settings").json()["hot_word_groups"] == payload["hot_word_groups"]
    )


def test_热词保存不吃用户注释且重复保存幂等(client: TestClient, config: Config) -> None:
    """用户自己写的 `# 热词：…` 也是注释；重写只清本工具的表头，重复保存不能累积空行。"""
    config.openrouter_api_key = "test-key"
    config.glossary_path.write_text(
        "# 我的词表\n# 热词：公司名统一写法，别删我\n艾麦 -> 砹脉\n", encoding="utf-8"
    )
    body = {
        "model": "z-ai/glm-5.3-flash",
        "base_url": "https://openrouter.ai/api/v1",
        "prompt": "",
        "hot_word_groups": [{"name": "产品", "words": ["小新"]}],
    }
    for _ in range(3):
        assert client.put("/api/summary-settings", json=body).status_code == 200
        text = config.glossary_path.read_text(encoding="utf-8")
        assert "# 热词：公司名统一写法，别删我" in text
        assert "艾麦 -> 砹脉" in text
        assert text.count("## 产品") == 1
        assert "\n\n\n" not in text


@pytest.mark.parametrize(
    "groups",
    [
        [{"name": "产品", "words": []}, {"name": "产品", "words": ["小新"]}],
        [{"name": "产品#1", "words": []}],
        [{"name": "", "words": ["小新"]}, {"name": "", "words": ["选号侠"]}],
        [{"name": f"组{i}", "words": []} for i in range(MAX_HOT_WORD_GROUPS + 1)],
    ],
)
def test_非法热词分组被挡下(client: TestClient, config: Config, groups: list) -> None:
    config.openrouter_api_key = "test-key"
    body = {
        "model": "z-ai/glm-5.3-flash",
        "base_url": "https://openrouter.ai/api/v1",
        "prompt": "",
    }
    resp = client.put("/api/summary-settings", json={**body, "hot_word_groups": groups})
    assert resp.status_code == 400
    assert not config.glossary_path.exists()


def test_空的分组行不占名额(client: TestClient, config: Config) -> None:
    """设置页默认带一个空的「未分组」行；它不能把刚好满额的分组推成超限。"""
    config.openrouter_api_key = "test-key"
    groups = [{"name": f"组{i}", "words": []} for i in range(MAX_HOT_WORD_GROUPS)]
    resp = client.put(
        "/api/summary-settings",
        json={
            "model": "z-ai/glm-5.3-flash",
            "base_url": "https://openrouter.ai/api/v1",
            "prompt": "",
            "hot_word_groups": [*groups, {"name": "", "words": []}],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["hot_word_groups"] == groups
