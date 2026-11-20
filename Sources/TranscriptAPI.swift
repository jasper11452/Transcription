import Foundation

// MARK: - Models (the parts of Transcript's JSON the app shows)

struct TFailure: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

struct TTask: Decodable, Identifiable, Hashable {
    let id: Int
    let name: String
    let title: String?
    let sourcePath: String?
    let mode: String
    let status: String
    let progress: Double?
    let engine: String?
    let durationS: Double?
    let error: String?
    let createdAt: String?
    let stage: String?
    let running: Bool
    let cancelling: Bool?
    let resumable: Bool?
    let txtPath: String?
    let srtPath: String?
    let srcExists: Bool?

    var displayTitle: String {
        let raw = (title?.isEmpty == false ? title : nil) ?? name
        return raw.replacingOccurrences(of: #"^[0-9a-f]{6,}-"#, with: "", options: .regularExpression)
    }
    var isDone: Bool { status == "done" }
    var isFailed: Bool { status == "failed" }
    var isActive: Bool { !isDone && !isFailed }
    var percent: Double { min(max(progress ?? 0, 0), 100) }
    var date: Date? { createdAt.flatMap(TTask.parse) }

    var engineName: String {
        if mode == "offline" { return "本机" }
        switch (engine ?? "").split(separator: ":").first.map(String.init) ?? "" {
        case "doubao": return "云端 · 豆包"
        case "dashscope": return "云端 · 百炼"
        case "openrouter": return "云端 · OpenRouter"
        case "bcut": return "云端 · 必剪"
        default: return "云端"
        }
    }

    private static func parse(_ text: String) -> Date? {
        let plain = ISO8601DateFormatter()
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return plain.date(from: text) ?? fractional.date(from: text)
    }
}

struct TChunk: Decodable, Identifiable {
    let idx: Int
    let status: String
    let text: String?
    var id: Int { idx }
}

struct TDetail: Decodable {
    let task: TTask
    let chunks: [TChunk]
}

struct TKeyField: Decodable, Identifiable {
    let attr: String
    let label: String
    let status: String
    let configured: Bool
    var id: String { attr }
}

struct TEngine: Decodable, Identifiable {
    let id: String
    let ready: Bool
}

struct TStatus: Decodable {
    let onlineEngines: [TEngine]
    let keyFields: [TKeyField]
}

struct TSummary: Decodable {
    let enabled: Bool
    let status: String
    let available: Bool
    let content: String?
    let reasoning: String?
    let error: String?
    var pending: Bool { enabled && (status == "waiting" || status == "running") }
    var markdown: String { content ?? "" }
}

struct TEstimate: Decodable {
    let ok: Bool
    let durationS: Double?
    let estimatedCostUsd: Double?
    let error: String?
}

// MARK: - Subtitles

struct Cue: Identifiable, Equatable {
    let id: Int
    let stamp: String          // "00:00:00,000 --> 00:00:03,060", kept verbatim: the timeline is not editable
    let start: Double
    var text: String
}

func parseSRT(_ source: String) -> [Cue] {
    let normalized = source.replacingOccurrences(of: "\r\n", with: "\n")
    var cues: [Cue] = []
    for block in normalized.components(separatedBy: "\n\n") {
        let lines = block.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
            .filter { !$0.hasPrefix("# ") }
        guard let arrow = lines.firstIndex(where: { $0.contains("-->") }) else { continue }
        let stamp = lines[arrow].trimmingCharacters(in: .whitespaces)
        let text = lines[(arrow + 1)...].joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        cues.append(Cue(id: cues.count, stamp: stamp, start: seconds(String(stamp.split(separator: " ").first ?? "")), text: text))
    }
    return cues
}

func serializeSRT(_ cues: [Cue]) -> String {
    cues.enumerated().map { "\($0.offset + 1)\n\($0.element.stamp)\n\($0.element.text)\n" }.joined(separator: "\n")
}

private func seconds(_ stamp: String) -> Double {
    let parts = stamp.replacingOccurrences(of: ",", with: ".").split(separator: ":").compactMap { Double($0) }
    return parts.count == 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] : 0
}

func clock(_ seconds: Double) -> String {
    let total = Int(seconds.rounded())
    let (h, m, s) = (total / 3600, total % 3600 / 60, total % 60)
    return h > 0 ? String(format: "%d:%02d:%02d", h, m, s) : String(format: "%d:%02d", m, s)
}

// MARK: - Client (the UI's one door to the engine)

struct TranscriptClient {
    private let backend = Backend.shared

    func tasks() async throws -> [TTask] { await backend.tasks() }
    func detail(_ id: Int) async throws -> TDetail { try await backend.detail(id) }

    func status() async throws -> TStatus {
        func field(_ attr: String, _ env: String, _ label: String) -> TKeyField {
            let key = ConfigEnv.read(env)
            return TKeyField(attr: attr, label: label, status: key.map { "已配置 ····" + $0.suffix(4) } ?? "未配置", configured: key != nil)
        }
        let dash = ConfigEnv.read("DASHSCOPE_API_KEY") != nil
        return TStatus(onlineEngines: [TEngine(id: "doubao", ready: DoubaoWebAuth.isConfigured), TEngine(id: "dashscope", ready: dash)],
                       keyFields: [field("dashscope_api_key", "DASHSCOPE_API_KEY", "百炼 API 密钥"), field("openrouter_api_key", "OPENROUTER_API_KEY", "总结服务密钥（OpenRouter 或兼容）")])
    }

    func create(path: String, mode: String, language: String, engine: String, speakers: Bool = false, hotwords: [String]? = nil) async throws -> Int {
        try await backend.create(path: path, mode: mode, language: language, engine: engine, speakers: speakers, hotwords: hotwords)
    }

    func estimate(path: String, mode: String, engine: String) async throws -> TEstimate {
        do { return TEstimate(ok: true, durationS: try await AudioIO.duration(of: URL(fileURLWithPath: path)), estimatedCostUsd: nil, error: nil) }
        catch { return TEstimate(ok: false, durationS: nil, estimatedCostUsd: nil, error: error.localizedDescription) }
    }

    func cancel(_ id: Int) async throws { await backend.cancel(id) }
    func resume(_ id: Int) async throws { await backend.resume(id) }
    func delete(_ id: Int) async throws { await backend.delete(id) }
    func deleteInactive(_ ids: [Int]) async -> (deleted: [Int], skipped: [Int]) { await backend.deleteInactive(ids) }
    func file(_ id: Int, kind: String) async throws -> String { try await backend.file(id, kind: kind) }
    func saveTranscript(_ id: Int, text: String) async throws { try await backend.saveTranscript(id, text: text) }
    func saveCues(_ id: Int, srt: String) async throws { try await backend.saveCues(id, srt: srt) }
    func renameSpeakers(_ id: Int, replacements: [String: String]) async throws { try await backend.renameSpeakers(id, replacements: replacements) }
    func summary(_ id: Int) async throws -> TSummary { await backend.summary(id) }
    func enableSummary(_ id: Int, prompt: String? = nil) async throws -> TSummary { try await backend.enableSummary(id, prompt: prompt) }
    func chat(_ id: Int) async -> TranscriptChatConversation { await backend.chat(id) }
    func sendChat(_ id: Int, question: String) async throws -> TranscriptChatConversation { try await backend.sendChat(id, question: question) }
    func retryChat(_ id: Int, turnID: UUID) async throws -> TranscriptChatConversation { try await backend.retryChat(id, turnID: turnID) }
    func stopChat(_ id: Int) async { await backend.stopChat(id) }
    func clearChat(_ id: Int) async { await backend.clearChat(id) }

    func glossary() async throws -> String { (try? String(contentsOf: AppPaths.layout.glossary, encoding: .utf8)) ?? "" }
    func saveGlossary(_ text: String) async throws {
        try FileManager.default.createDirectory(at: AppPaths.layout.glossary.deletingLastPathComponent(), withIntermediateDirectories: true)
        try text.write(to: AppPaths.layout.glossary, atomically: true, encoding: .utf8)
    }

    func saveKey(attr: String, value: String) async throws {
        ConfigEnv.save(attr == "openrouter_api_key" ? "OPENROUTER_API_KEY" : "DASHSCOPE_API_KEY", value)
    }

    func audioURL(_ id: Int) -> URL { URL(fileURLWithPath: "/dev/null") }
}
