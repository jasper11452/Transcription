import Foundation
import MLX
import MLXAudioCore
import MLXAudioSTT
import MLXAudioVAD

enum LocalModel {
    static let asr = "mlx-community/Qwen3-ASR-1.7B-8bit"
    static let aligner = "mlx-community/Qwen3-ForcedAligner-0.6B-8bit"
    static let vad = "mlx-community/silero-vad-v6"
    static let diar = "mlx-community/diar_streaming_sortformer_4spk-v2.1-fp16"
    static let asrLite = "mlx-community/Qwen3-ASR-0.6B-8bit"
}

/// Loads the models on demand and lets go of them after a quiet spell, so an idle app stays small.
final class MLXEngine: @unchecked Sendable {
    private var asr: Qwen3ASRModel?
    private var asrRepo = ""
    private var diar: SortformerModel?
    private var aligner: Qwen3ForcedAlignerModel?
    private var vad: SileroVAD?
    private var busy = 0
    private var releaser: Task<Void, Never>?
    private let lock = NSLock()

    /// MLX keeps freed buffers for reuse; capped, it stops hoarding gigabytes between steps at no cost to speed.
    init() { Memory.cacheLimit = 512 << 20 }

    private func scheduleRelease() {
        releaser?.cancel()
        releaser = Task { [weak self] in
            try? await Task.sleep(for: .seconds(120))
            guard !Task.isCancelled, let self else { return }
            self.releaseIfIdle()
        }
    }

    private func beginUse() {
        lock.lock(); busy += 1; releaser?.cancel(); lock.unlock()
    }

    private func endUse() {
        lock.lock(); busy -= 1; lock.unlock()
        scheduleRelease()
    }

    private func releaseIfIdle() {
        lock.lock(); defer { lock.unlock() }
        guard busy == 0 else { return }
        asr = nil; aligner = nil; vad = nil; diar = nil
        Memory.clearCache()
    }

    /// Use the selected recognizer consistently with the UI's readiness check.
    @MainActor static func asrChoice() -> String { ModelStore.shared.selectedRecognizer }

    private func loadASR(_ repo: String) async throws {
        if asr == nil || asrRepo != repo { asr = try await Qwen3ASRModel.fromModelDirectory(AppPaths.modelDir(repo)); asrRepo = repo }
    }

    static func languageName(_ code: String) -> String? {
        ["zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean"][code]
    }

    /// Short dictation clips for other apps (Spokenly and friends): text only, no subtitles.
    func quick(_ samples: [Float], language: String?, repo: String? = nil) async throws -> String {
        beginUse()
        defer { Memory.clearCache(); endUse() }
        let chosen: String
        if let repo { chosen = repo } else { chosen = await MLXEngine.asrChoice() }
        // Dictation needs only its recognizer, not VAD or subtitle alignment.
        guard await ModelStore.shared.isReady(chosen) else { throw TFailure(message: "本机模型还没下载。") }
        try Task.checkCancellation()
        try await loadASR(chosen)
        try Task.checkCancellation()
        let duration = Double(samples.count) / 16000
        let all = MLXArray(samples)
        var parts: [String] = []
        for chunk in planChunks([], duration: duration, minS: 20, maxS: 40) {
            try Task.checkCancellation()
            let a = Int(chunk.start * 16000), b = min(samples.count, Int(chunk.end * 16000))
            guard b - a >= 8000 else { continue }
            parts.append(asr!.generate(audio: all[a..<b], maxTokens: 8192, temperature: 0, context: "", language: language, chunkDuration: 1200).text.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        try Task.checkCancellation()
        return parts.filter { !$0.isEmpty }.joined(separator: " ")
    }

    func process(_ rec: Rec, hooks: Hooks) async throws -> (txt: String, srt: String, duration: Double) {
        beginUse()
        defer { Memory.clearCache(); endUse() }

        func checkCancellation() throws {
            try Task.checkCancellation()
            if hooks.cancelled() { throw CancellationError() }
        }
        try checkCancellation()
        hooks.stage("读取音频")
        let source = URL(fileURLWithPath: rec.sourcePath)
        var samples = try await AudioIO.decode(source)
        try checkCancellation()
        let count = samples.count
        let duration = Double(count) / Double(AudioIO.rate)
        guard duration > 0.5 else { throw TFailure(message: "录音太短，没有可转写的内容。") }
        let glossary = Glossary(file: AppPaths.layout.glossary)
        let hotwords = rec.hotwordsSnapshot ?? glossary.hotwords
        let language = Self.languageName(rec.language)
        let local = rec.mode == "offline"
        let recognizer = await Self.asrChoice()
        if local, !(await ModelStore.shared.offlineReady(for: recognizer)) { throw TFailure(message: "本机模型还没下载。到设置里的“本机模型”下载，或改用云端。") }
        try checkCancellation()
        let service: Service
        if local {
            service = Service.dashscope
        } else {
            guard let resolved = Service.resolveCloud(rec.engine) else {
                throw TFailure(message: "未知的云端转写服务，请重新选择后重试。")
            }
            service = resolved
        }
        let key = service.key
        if !local, !service.readyForTranscription {
            throw TFailure(message: service.id == "doubao" ? "请先在设置里登录豆包，或改用其他转写服务。" : "还没有\(service.name)密钥。到设置里填入，或改用本机。")
        }

        hooks.progress(2)
        hooks.stage("分析语音")
        let all = MLXArray(samples)
        // Local work reads only the MLX copy, so the Swift one goes (about 230 MB per hour of audio).
        if local { samples = [] }
        // Cloud work can fall back to duration cuts without any downloaded models.
        // 必剪 takes the whole recording and never needs VAD.
        let wholeFile = !local && service.id == "bcut"
        let vadReady = await ModelStore.shared.isReady(LocalModel.vad)
        try checkCancellation()
        var spans: [(Double, Double)] = []
        if rec.segments == nil && !wholeFile && (local || vadReady) {
            do {
                if vad == nil { vad = try SileroVAD.fromModelDirectory(AppPaths.modelDir(LocalModel.vad)) }
                let stamps = try vad!.getSpeechTimestamps(all, sampleRate: AudioIO.rate)
                spans = mergeGaps(stamps.map { (Double($0.start) / 16000, Double($0.end) / 16000) }.filter { $0.1 - $0.0 >= 0.25 }, maxGap: 0.4)
            } catch {
                if local { throw error }
                // A missing or unusable optional VAD must not block a configured cloud service.
            }
        }
        try checkCancellation()
        let chunks = rec.segments ?? (wholeFile ? [Chunk(start: 0, end: duration)] : planChunks(spans, duration: duration, minS: local ? 20 : 60, maxS: local ? 40 : 120))
        // Save the layout before the first checkpoint so model availability cannot
        // change what an existing checkpoint index means on a later attempt.
        await hooks.plan?(chunks)
        try checkCancellation()
        hooks.progress(5)
        // A cloud service without word times borrows the local aligner's clock when it is on disk.
        let alignerReady = await ModelStore.shared.isReady(LocalModel.aligner)
        try checkCancellation()
        let borrowClock = !local && ["openrouter", "doubao"].contains(service.id) && alignerReady
        if borrowClock, aligner == nil {
            aligner = try await Qwen3ForcedAlignerModel.fromModelDirectory(AppPaths.modelDir(LocalModel.aligner))
            try checkCancellation()
        }
        if local {
            if asr == nil || aligner == nil { hooks.stage("加载模型") }
            try await loadASR(recognizer)
            try checkCancellation()
            if aligner == nil {
                aligner = try await Qwen3ForcedAlignerModel.fromModelDirectory(AppPaths.modelDir(LocalModel.aligner))
                try checkCancellation()
            }
        }

        // Old checkpoints have no layout metadata; rebuilding them once is safer
        // than attaching their text to a new set of audio ranges.
        let reusable = rec.segments == nil ? [] : rec.parts ?? []
        var finished = Dictionary(uniqueKeysWithValues: reusable.map { ($0.index, $0) })
        for (index, chunk) in chunks.enumerated() {
            try checkCancellation()
            hooks.stage("识别 \(index + 1) / \(chunks.count)")
            if finished[index] != nil { hooks.progress(5 + 94 * Double(index + 1) / Double(chunks.count)); continue }
            let a = Int(chunk.start * 16000), b = min(count, Int(chunk.end * 16000))
            var text = ""
            var aligned: [TimedChar] = []
            if b - a >= 8000 {
                if local {
                    let part = all[a..<b]
                    text = asr!.generate(audio: part, maxTokens: 8192, temperature: 0, context: hotwords.joined(separator: "，"),
                                         language: language, chunkDuration: 1200).text.trimmingCharacters(in: .whitespacesAndNewlines)
                    try checkCancellation()
                    text = glossary.apply(text)
                    if !text.isEmpty {
                        let result = aligner!.generate(audio: part, text: text, language: language ?? "Chinese")
                        aligned = timedChars(result.items.map { ($0.text, $0.startTime + chunk.start, $0.endTime + chunk.start) })
                    }
                } else {
                    let heard: Heard
                    switch service.id {
                    case "doubao": heard = try await DoubaoWebASR.transcribe(wav: AudioIO.wav(samples[a..<b]), language: rec.language, hotwords: hotwords)
                    case "openrouter": heard = try await OpenRouterASR.transcribe(wav: AudioIO.wav(samples[a..<b]), language: rec.language, hotwords: hotwords)
                    case "bcut":
                        let ext = source.pathExtension.lowercased()
                        let original = ["mp3", "wav", "m4a", "flac", "aac"].contains(ext) ? try? Data(contentsOf: source) : nil
                        heard = try await BcutASR.transcribe(file: original ?? AudioIO.wav(samples[a..<b]), format: original == nil ? "wav" : ext,
                                                             stage: hooks.stage, cancelled: hooks.cancelled)
                    default: heard = try await Cloud.dashscope(wav: AudioIO.wav(samples[a..<b]), key: key, language: rec.language)
                    }
                    try checkCancellation()
                    text = glossary.apply(heard.text)
                    aligned = timedChars(heard.words.map { ($0.text, $0.start + chunk.start, $0.end + chunk.start) })
                    if aligned.isEmpty, borrowClock, !text.isEmpty {
                        let result = aligner!.generate(audio: all[a..<b], text: text, language: language ?? "Chinese")
                        aligned = timedChars(result.items.map { ($0.text, $0.startTime + chunk.start, $0.endTime + chunk.start) })
                    }
                }
            }
            try checkCancellation()
            let made = text.isEmpty ? [] : cues(for: text, aligned: aligned, from: chunk.start, to: chunk.end)
            let part = Part(index: index, text: text, cues: made.map { CueRec(start: $0.start, end: $0.end, text: $0.text, speaker: nil) })
            try checkCancellation()
            finished[index] = part
            await hooks.part(part)
            hooks.progress(5 + 94 * Double(index + 1) / Double(chunks.count))
        }
        try checkCancellation()
        let ordered = finished.values.sorted { $0.index < $1.index }
        var cueList = ordered.flatMap(\.cues)
        guard !cueList.isEmpty || ordered.contains(where: { !$0.text.isEmpty }) else { throw TFailure(message: "没有听到人声。换一段更清晰的录音试试。") }

        // Who spoke when, if asked and available: each subtitle goes to the speaker it overlaps most.
        var names: [Int: String] = [:]
        if rec.speakers == true, local, await ModelStore.shared.isReady(LocalModel.diar) {
            try checkCancellation()
            hooks.stage("区分说话人")
            if diar == nil { diar = try SortformerModel.fromModelDirectory(AppPaths.modelDir(LocalModel.diar)) }
            // Streamed in short chunks: the one-shot pass attends over the whole recording and runs out of GPU memory on long ones.
            var segments: [DiarizationSegment] = []
            for try await out in diar!.generateStream(audio: all, sampleRate: 16000, threshold: 0.5, minDuration: 0.3, mergeGap: 0.5) {
                try checkCancellation()
                segments += out.segments
            }
            try checkCancellation()
            for i in cueList.indices {
                var weight: [Int: Double] = [:]
                for seg in segments { weight[seg.speaker, default: 0] += max(0, min(cueList[i].end, Double(seg.end)) - max(cueList[i].start, Double(seg.start))) }
                if let best = weight.max(by: { $0.value < $1.value }), best.value > 0 { cueList[i].speaker = best.key }
            }
            for cue in cueList { if let id = cue.speaker, names[id] == nil { names[id] = "说话人\(names.count + 1)" } }
        }
        let labelled = names.count > 1
        var subtitles: [TCue] = []
        var paragraphs: [String] = []
        var last: Int?
        for cue in cueList {
            var text = cue.text
            // Every subtitle names its speaker: a cue is read on its own, often after a jump.
            if labelled, let id = cue.speaker { text = "\(names[id] ?? "")：" + text }
            if labelled, let id = cue.speaker, id != last {
                paragraphs.append("\(names[id] ?? "")：" + cue.text)
            } else if labelled, !paragraphs.isEmpty {
                let joiner = (paragraphs[paragraphs.count - 1].last.map { $0.unicodeScalars.first!.value > 0x2E80 } ?? true) ? "" : " "
                paragraphs[paragraphs.count - 1] += joiner + cue.text
            }
            if cue.speaker != nil { last = cue.speaker }
            subtitles.append(TCue(start: cue.start, end: cue.end, text: text))
        }
        if !labelled { paragraphs = ordered.map(\.text).filter { !$0.isEmpty } }
        let output = try TranscriptionOutput.write(source: source, taskID: rec.id,
            root: AppPaths.layout.dataDir.appendingPathComponent("outputs", isDirectory: true),
            text: paragraphs.joined(separator: "\n\n") + "\n", subtitles: renderSRT(subtitles),
            checkCancellation: checkCancellation)
        return (output.txt.path, output.srt.path, duration)
    }
}

enum Cloud {
    static var endpoint: URL { URL(string: Service.dashscope.base + "/services/aigc/multimodal-generation/generation")! }

    static var model: String { Service.dashscope.model }

    /// The native multimodal endpoint with a base64 data URL; it answers with character-level times (ms),
    /// so cloud subtitles get a real clock instead of an estimate. One request takes at most 300 s of audio.
    static func dashscope(wav: Data, key: String, language: String, model: String = Cloud.model) async throws -> (text: String, words: [(text: String, start: Double, end: Double)]) {
        var request = URLRequest(url: endpoint, timeoutInterval: 300)
        request.httpMethod = "POST"
        request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var options: [String: Any] = ["enable_itn": true]
        if !language.isEmpty { options["language"] = language }
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "model": model,
            "input": ["messages": [["role": "user", "content": [["audio": "data:audio/wav;base64," + wav.base64EncodedString()]]]]],
            "parameters": ["format": "wav", "asr_options": options],
        ])
        let (data, response) = try await URLSession.shared.data(for: request)
        try Task.checkCancellation()
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        if status != 200 {
            let message = root["message"] as? String ?? "", code = root["code"] as? String ?? ""
            if message == "ASR_RESPONSE_HAVE_NO_WORDS" || code == "ASR_RESPONSE_HAVE_NO_WORDS" { return ("", []) }
            if status == 401 { throw TFailure(message: "百炼没有接受这个密钥。到设置里检查一下。") }
            if code == "AUDIO_DURATION_TOO_LONG" { throw TFailure(message: "这段音频超过百炼单次 5 分钟的上限。") }
            if message.contains("Model not exist") || code == "ModelNotFound" { throw TFailure(message: "百炼没有找到模型 \(model)。到设置里检查模型名。") }
            throw TFailure(message: "百炼请求失败（\(status)）：\(message)")
        }
        // The real result is nested once more inside `output`; read both levels in case the shape shifts.
        let outer = root["output"] as? [String: Any] ?? [:]
        let inner = outer["output"] as? [String: Any] ?? outer
        var sentences: [[String: Any]] = []
        for v in [inner["sentence"], outer["sentence"]] {
            if let one = v as? [String: Any] { sentences = [one]; break }
            if let many = v as? [[String: Any]], !many.isEmpty { sentences = many; break }
        }
        var words: [(text: String, start: Double, end: Double)] = []
        for sentence in sentences {
            for word in sentence["words"] as? [[String: Any]] ?? [] {
                let t = (word["text"] as? String ?? "").trimmingCharacters(in: .whitespaces)
                guard !t.isEmpty else { continue }
                func ms(_ k: String) -> Double { ((word[k] as? NSNumber)?.doubleValue ?? 0) / 1000 }
                words.append((t, ms("begin_time"), ms("end_time")))
            }
        }
        var text = (inner["text"] as? String ?? outer["text"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty { text = sentences.map { $0["text"] as? String ?? "" }.joined() }
        if text.isEmpty { text = firstText(in: root).trimmingCharacters(in: .whitespacesAndNewlines) }
        return (text, words)
    }

    private static func firstText(in value: Any) -> String {
        if let d = value as? [String: Any] {
            if let t = d["text"] as? String { return t }
            for (_, v) in d.sorted(by: { $0.key < $1.key }) { let t = firstText(in: v); if !t.isEmpty { return t } }
        } else if let a = value as? [Any] { for v in a { let t = firstText(in: v); if !t.isEmpty { return t } } }
        return ""
    }
}
