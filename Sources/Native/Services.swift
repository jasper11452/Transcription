import Foundation

/// One cloud service: where its key, base URL and model live in `config.env`, and their defaults.
struct Service: Identifiable, Hashable {
    let id: String
    let name: String
    let keyEnv: String?          // nil: the service needs no key
    let baseEnv: String
    let defaultBase: String
    let modelEnv: String
    let defaultModel: String
    let keyURL: String?

    var key: String { keyEnv.flatMap(ConfigEnv.read) ?? (id == "openai" ? AccountCredentialStore.loadOpenAI()?.accessToken : nil) ?? "" }
    var configured: Bool {
        switch id {
        case "openai": return AccountCredentialStore.loadOpenAI() != nil
        default: return keyEnv == nil || !key.isEmpty
        }
    }
    var readyForTranscription: Bool { id == "doubao" ? DoubaoWebAuth.isConfigured : configured }
    var model: String { ConfigEnv.read(modelEnv) ?? defaultModel }
    /// A base URL is one endpoint: a comma would mean a list, so such a value falls back to the default.
    var base: String {
        let raw = (ConfigEnv.read(baseEnv) ?? "").trimmingCharacters(in: CharacterSet(charactersIn: "/ "))
        if raw.isEmpty || raw.contains(",") || URL(string: raw)?.scheme == nil { return defaultBase }
        return id == "local" && !Service.isLoopback(raw) ? defaultBase : raw
    }
    /// The local service only ever listens on this Mac.
    static func isLoopback(_ raw: String) -> Bool {
        guard let url = URL(string: raw), url.scheme == "http", let host = url.host else { return false }
        return ["127.0.0.1", "localhost", "::1"].contains(host) && (url.port ?? 80) > 0
    }
    /// Where `GET /models` answers (DashScope keeps it on its OpenAI-compatible path).
    var modelsBase: String { id == "dashscope" ? base.replacingOccurrences(of: "/api/v1", with: "/compatible-mode/v1") : base }

    static let dashscope = Service(id: "dashscope", name: "百炼", keyEnv: "DASHSCOPE_API_KEY", baseEnv: "DASHSCOPE_BASE",
                                   defaultBase: "https://dashscope.aliyuncs.com/api/v1", modelEnv: "DASHSCOPE_MODEL",
                                   defaultModel: "qwen-audio-3.1-asr-flash", keyURL: "https://bailian.console.aliyun.com/?tab=model#/api-key")
    static let doubao = Service(id: "doubao", name: "豆包 · 登录即用", keyEnv: nil, baseEnv: "DOUBAO_BASE",
                                defaultBase: "https://www.doubao.com", modelEnv: "DOUBAO_MODEL",
                                defaultModel: "web-asr", keyURL: "https://www.doubao.com/chat")
    static let openrouter = Service(id: "openrouter", name: "OpenRouter", keyEnv: "OPENROUTER_ASR_KEY", baseEnv: "OPENROUTER_ASR_BASE",
                                    defaultBase: "https://openrouter.ai/api/v1", modelEnv: "OPENROUTER_ASR_MODEL",
                                    defaultModel: "google/gemini-2.5-flash", keyURL: "https://openrouter.ai/settings/keys")
    static let bcut = Service(id: "bcut", name: "必剪", keyEnv: nil, baseEnv: "BCUT_BASE",
                              defaultBase: "https://member.bilibili.com/x/bcut/rubick-interface", modelEnv: "BCUT_MODEL",
                              defaultModel: "8", keyURL: nil)
    static let openrouterSummary = Service(id: "summary", name: "OpenRouter", keyEnv: "OPENROUTER_API_KEY", baseEnv: "OPENROUTER_BASE",
                                 defaultBase: "https://openrouter.ai/api/v1", modelEnv: "SUMMARY_MODEL",
                                 defaultModel: "z-ai/glm-5.3-flash", keyURL: "https://openrouter.ai/settings/keys")
    static let openAI = Service(id: "openai", name: "OpenAI · ChatGPT 账号", keyEnv: nil, baseEnv: "OPENAI_BASE",
                                defaultBase: "https://api.openai.com/v1", modelEnv: "OPENAI_MODEL",
                                defaultModel: "gpt-4.1-mini", keyURL: nil)
    static var summary: Service { UserDefaults.standard.string(forKey: "summaryProvider") == "openai" ? openAI : openrouterSummary }

    /// This app's own OpenAI-compatible endpoint: its address, the key other apps must send, and the model it uses by default.
    static let local = Service(id: "local", name: "OpenAI 兼容本地服务", keyEnv: "LOCAL_SERVER_KEY", baseEnv: "LOCAL_SERVER_BASE",
                               defaultBase: "http://127.0.0.1:\(AppPaths.serverPort)/v1", modelEnv: "LOCAL_SERVER_MODEL",
                               defaultModel: LocalModel.asr, keyURL: nil)

    static let cloud = [doubao, dashscope, openrouter, bcut]
    static func resolveCloud(_ id: String?) -> Service? {
        let value = id?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if value.isEmpty || value == "auto" { return dashscope }
        return cloud.first { $0.id == value }
    }
    static func cloud(_ id: String?) -> Service { cloud.first { $0.id == id } ?? dashscope }
}

typealias Heard = (text: String, words: [(text: String, start: Double, end: Double)])

// MARK: - OpenRouter (or any OpenAI-compatible chat endpoint that takes `input_audio`)

enum OpenRouterASR {
    static func transcribe(wav: Data, language: String, hotwords: [String]) async throws -> Heard {
        let s = Service.openrouter
        guard !s.key.isEmpty else { throw TFailure(message: "还没有 OpenRouter 密钥。到设置里填入。") }
        var request = URLRequest(url: URL(string: s.base + "/chat/completions")!, timeoutInterval: 300)
        request.httpMethod = "POST"
        request.setValue("Bearer \(s.key)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var ask = "逐字转写这段音频。只输出听到的原话，加上合适的标点，不要总结、翻译或解释。"
        if let name = MLXEngine.languageName(language) { ask += "语言：\(name)。" }
        if !hotwords.isEmpty { ask += "可能出现的专有名词：" + hotwords.joined(separator: "、") + "。" }
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "model": s.model, "temperature": 0,
            "messages": [["role": "user", "content": [
                ["type": "text", "text": ask],
                ["type": "input_audio", "input_audio": ["data": wav.base64EncodedString(), "format": "wav"]],
            ]]],
        ])
        let (data, response) = try await URLSession.shared.data(for: request)
        try Task.checkCancellation()
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        guard status == 200 else {
            let message = (root["error"] as? [String: Any])?["message"] as? String ?? ""
            if status == 401 { throw TFailure(message: "OpenRouter 没有接受这个密钥。到设置里检查一下。") }
            throw TFailure(message: "OpenRouter 请求失败（\(status)）：\(message)。确认模型 \(s.model) 支持音频输入。")
        }
        return (try responseText(root), [])
    }

    /// HTTP success can still contain an incomplete or filtered transcription.
    static func responseText(_ root: [String: Any]) throws -> String {
        guard let choice = (root["choices"] as? [[String: Any]])?.first else {
            throw TFailure(message: "OpenRouter 没有返回转写结果。请重试。")
        }
        switch choice["finish_reason"] as? String {
        case "length": throw TFailure(message: "OpenRouter 转写达到输出上限，这一段尚未完成。请缩短音频或换用输出上限更高的模型后重试。")
        case "content_filter": throw TFailure(message: "OpenRouter 的内容过滤中断了这一段转写。请换用其他模型或服务后重试。")
        default: break
        }
        guard let text = (choice["message"] as? [String: Any])?["content"] as? String else {
            throw TFailure(message: "OpenRouter 没有返回转写文本。确认所选模型支持音频输入。")
        }
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

// MARK: - Bilibili 必剪 (bcut): upload, commit, create task, poll

enum BcutASR {
    static func transcribe(file: Data, format: String, stage: (String) -> Void, cancelled: () -> Bool) async throws -> Heard {
        let s = Service.bcut, model = Int(s.model) ?? 8
        func checkCancellation() throws {
            try Task.checkCancellation()
            if cancelled() { throw CancellationError() }
        }
        func call(_ path: String, method: String = "POST", body: [String: Any]? = nil, query: String = "") async throws -> [String: Any] {
            try checkCancellation()
            var request = URLRequest(url: URL(string: s.base + path + query)!, timeoutInterval: 60)
            request.httpMethod = method
            request.setValue("Bilibili/1.0.0 (https://www.bilibili.com)", forHTTPHeaderField: "User-Agent")
            if let body {
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.httpBody = try JSONSerialization.data(withJSONObject: body)
            }
            let (data, _) = try await URLSession.shared.data(for: request)
            try checkCancellation()
            let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
            guard (root["code"] as? NSNumber)?.intValue == 0, let out = root["data"] as? [String: Any] else {
                throw TFailure(message: "必剪请求失败：\(root["message"] as? String ?? "没有返回数据")")
            }
            return out
        }
        stage("上传音频")
        let made = try await call("/resource/create", body: ["type": 2, "name": "audio.\(format)", "size": file.count, "ResourceFileType": format, "model_id": model])
        guard let urls = made["upload_urls"] as? [String], let per = (made["per_size"] as? NSNumber)?.intValue, per > 0 else { throw TFailure(message: "必剪没有给出上传地址。") }
        var etags: [String] = []
        for (i, url) in urls.enumerated() {
            try checkCancellation()
            var put = URLRequest(url: URL(string: url)!, timeoutInterval: 300)
            put.httpMethod = "PUT"
            let (_, response) = try await URLSession.shared.upload(for: put, from: file.subdata(in: i * per..<min(file.count, (i + 1) * per)))
            try checkCancellation()
            etags.append((response as? HTTPURLResponse)?.value(forHTTPHeaderField: "Etag") ?? "")
        }
        let done = try await call("/resource/create/complete", body: ["InBossKey": made["in_boss_key"] ?? "", "ResourceId": made["resource_id"] ?? "",
                                                                       "Etags": etags.joined(separator: ","), "UploadId": made["upload_id"] ?? "", "model_id": model])
        guard let resource = done["download_url"] as? String else { throw TFailure(message: "必剪上传没有完成。") }
        let task = try await call("/task", body: ["resource": resource, "model_id": model])
        guard let taskID = task["task_id"] as? String else { throw TFailure(message: "必剪没有创建识别任务。") }
        stage("云端识别中")
        while true {
            try checkCancellation()
            try await Task.sleep(for: .seconds(2))
            try checkCancellation()
            let r = try await call("/task/result", method: "GET", query: "?model_id=7&task_id=\(taskID)")
            switch (r["state"] as? NSNumber)?.intValue ?? 0 {
            case 4:
                let result = (try? JSONSerialization.jsonObject(with: Data((r["result"] as? String ?? "{}").utf8))) as? [String: Any] ?? [:]
                let utterances = result["utterances"] as? [[String: Any]] ?? []
                func sec(_ v: Any?) -> Double { ((v as? NSNumber)?.doubleValue ?? 0) / 1000 }
                var words: [(text: String, start: Double, end: Double)] = []
                for u in utterances {
                    let ws = u["words"] as? [[String: Any]] ?? []
                    if ws.isEmpty { words.append((u["transcript"] as? String ?? "", sec(u["start_time"]), sec(u["end_time"]))) }
                    for w in ws { words.append((w["label"] as? String ?? "", sec(w["start_time"]), sec(w["end_time"]))) }
                }
                // Each utterance ends a sentence, so the subtitles break where the speaker paused.
                let text = utterances.map { ($0["transcript"] as? String ?? "").trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
                    .map { t in t.last.map { "。！？.!?".contains($0) } == true ? t : t + ((t.last?.unicodeScalars.first?.value ?? 0) > 0x2E80 ? "。" : ". ") }.joined()
                return (text, words)
            case 3: throw TFailure(message: "必剪识别失败：\(r["remark"] as? String ?? "")")
            default: continue
            }
        }
    }
}
