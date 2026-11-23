# `diar` — 说话人分离（仅离线路径）

承载 `legacy/transcript/src/transcript/diar.py`。这是 **C8 的唯一落点**：经人裁定
「接通成端到端功能」，但边界严格限定为「把已经写好的东西接通」，不新增能力。

## 两个必须写明的边界

1. **仅离线**：遗留只在 `mode == "offline"` 时才做分离；在线引擎返回的 `Segment`
   里 `speaker` 恒为 `None`。在线路径保持 `None`，并有测试断言。
2. **ABI 与构建哈希耦合**：`libnemo_speech_asr_c.dylib` 来自
   `NeMoSpeech/main-97a15af`，预设字符串 `b"v3-offline"` 与 10 字段 `_ModelCfg`
   结构体与该构建静默耦合。测试用 **stub dylib** 真正执行 ctypes 调用，并用常量
   `DIAR_ABI_VERSION` 把哈希钉住；真实库存在时另有一条 smoke 测试。

## 公开面

| 名字 | 作用 |
|---|---|
| `diarize(wav_path, lib_path=..., model_path=...)` | 返回 `(start_s, end_s, speaker_int)` |
| `assign_speaker(segments, diar_segs)` | 按重叠时长投票，写入 `segment.speaker = "speaker_N"` |
| `DIAR_ABI_VERSION` | 硬编码的第三方构建哈希 |
| `DEFAULT_DIAR_LIB` / `DEFAULT_DIAR_MODEL` | 本机默认路径（来自 `config`） |
