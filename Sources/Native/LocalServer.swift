import Foundation
import Network

/// OpenAI-style transcription endpoint on localhost, for Spokenly and other tools. Lives only while the app is open.
final class LocalServer: @unchecked Sendable {
    static let shared = LocalServer()
    private var listener: NWListener?
    private let queue = DispatchQueue(label: "local-server")
    private let engine = MLXEngine()
    private static let maxRequestBytes = 64 << 20
    private static let maxHeaderBytes = 64 << 10

    var running: Bool { listener != nil }
    /// Why the last start failed (usually another program on the port), shown in Settings.
    private(set) var failure: String?

    private var pending: DispatchWorkItem?
    /// Port and path prefix come from the configured base URL (`http://127.0.0.1:18475/v1` by default).
    private var address: URL { URL(string: Service.local.base)! }
    private var prefix: String { address.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")).isEmpty ? "" : "/" + address.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")) }

    func start() throws {
        guard listener == nil else { return }
        let port = address.port ?? AppPaths.serverPort
        let params = NWParameters.tcp
        params.requiredInterfaceType = .loopback
        let l = try NWListener(using: params, on: NWEndpoint.Port(rawValue: UInt16(port))!)
        failure = nil
        l.newConnectionHandler = { [weak self] c in self?.accept(c) }
        l.stateUpdateHandler = { [weak self] state in
            guard case .failed = state else { return }
            DispatchQueue.main.async {
                self?.failure = "端口 \(port) 被其他程序占用，换一个端口。"
                self?.stop()
            }
        }
        l.start(queue: queue)
        listener = l
    }

    func stop() { listener?.cancel(); listener = nil }

    /// Picks up a new address once typing pauses, if the service is on.
    func restartSoon() {
        pending?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self, self.running else { return }
            self.stop(); try? self.start()
        }
        pending = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8, execute: work)
    }

    /// Every model a caller can name: both local models, then each configured cloud service under its model ID.
    private var offered: [(id: String, service: Service?)] {
        // Cloud models spend your credit, so other apps reach them only once the service is configured.
        [(LocalModel.asr, nil), (LocalModel.asrLite, nil)]
            + (Service.local.key.isEmpty ? [] : Service.cloud.filter(\.readyForTranscription).map { ($0.id == "bcut" ? "bcut" : $0.model, $0) })
    }

    // MARK: HTTP

    private func accept(_ c: NWConnection) {
        c.start(queue: queue)
        read(c, Data())
    }

    private func read(_ c: NWConnection, _ buffer: Data) {
        c.receive(minimumIncompleteLength: 1, maximumLength: 1 << 20) { [weak self] data, _, done, error in
            guard let self else { return }
            var buf = buffer
            if let data { buf.append(data) }
            switch Self.parse(buf) {
            case .request(let request):
                Task { await self.respond(c, request) }
            case .invalid(let status, let message):
                self.send(c, status, self.json(["error": ["message": message]]))
            case .incomplete:
                if done || error != nil || buf.count > Self.maxRequestBytes {
                    self.send(c, 400, self.json(["error": ["message": "请求不完整。"]]))
                } else {
                    self.read(c, buf)
                }
            }
        }
    }

    struct Request { let method: String; let path: String; let headers: [String: String]; let body: Data }
    private enum ParseResult { case incomplete, request(Request), invalid(Int, String) }

    private static func parse(_ data: Data) -> ParseResult {
        guard data.count <= maxRequestBytes else { return .invalid(413, "请求体太大。") }
        guard let end = data.range(of: Data("\r\n\r\n".utf8)) else {
            return data.count > maxHeaderBytes ? .invalid(431, "请求头太大。") : .incomplete
        }
        guard end.lowerBound <= maxHeaderBytes else { return .invalid(431, "请求头太大。") }
        let head = String(decoding: data[..<end.lowerBound], as: UTF8.self).components(separatedBy: "\r\n")
        let first = head[0].split(separator: " ", omittingEmptySubsequences: true)
        guard first.count == 3, first[2].hasPrefix("HTTP/") else { return .invalid(400, "请求行无效。") }
        var headers: [String: String] = [:]
        for line in head.dropFirst() {
            guard let i = line.firstIndex(of: ":") else { return .invalid(400, "请求头无效。") }
            let key = String(line[..<i]).trimmingCharacters(in: .whitespaces).lowercased()
            guard !key.isEmpty, headers[key] == nil else { return .invalid(400, "请求头无效。") }
            headers[key] = line[line.index(after: i)...].trimmingCharacters(in: .whitespaces)
        }
        let rawLength = headers["content-length"] ?? "0"
        guard let length = Int(rawLength.trimmingCharacters(in: .whitespaces)), length >= 0 else {
            return .invalid(400, "Content-Length 无效。")
        }
        guard length <= maxRequestBytes else { return .invalid(413, "请求体太大。") }
        let body = data[end.upperBound...]
        guard body.count >= length else { return .incomplete }
        return .request(Request(method: String(first[0]), path: String(first[1]), headers: headers, body: Data(body.prefix(length))))
    }

    private func send(_ c: NWConnection, _ status: Int, _ body: Data, type: String = "application/json") {
        let reason: String
        switch status {
        case 200: reason = "OK"
        case 400: reason = "Bad Request"
        case 401: reason = "Unauthorized"
        case 404: reason = "Not Found"
        case 413: reason = "Payload Too Large"
        case 431: reason = "Request Header Fields Too Large"
        case 499: reason = "Client Closed Request"
        case 503: reason = "Service Unavailable"
        default: reason = "Error"
        }
        let head = "HTTP/1.1 \(status) \(reason)\r\nContent-Type: \(type); charset=utf-8\r\nContent-Length: \(body.count)\r\nConnection: close\r\n\r\n"
        c.send(content: Data(head.utf8) + body, completion: .contentProcessed { _ in c.cancel() })
    }

    /// With an access key set, callers must send it as a bearer token.
    /// Web pages never get in (no Origin header, Host must be this Mac, which also stops DNS rebinding).
    private func authorized(_ r: Request) -> Bool {
        guard r.headers["origin"] == nil else { return false }
        let host = (r.headers["host"] ?? "").replacingOccurrences(of: #":\d+$"#, with: "", options: .regularExpression).lowercased()
        guard ["127.0.0.1", "localhost", "[::1]"].contains(host) else { return false }
        let key = Service.local.key
        guard !key.isEmpty else { return true }
        let sent = Array((r.headers["authorization"] ?? "").utf8), want = Array("Bearer \(key)".utf8)
        guard sent.count == want.count else { return false }
        return zip(sent, want).reduce(0) { $0 | ($1.0 ^ $1.1) } == 0
    }

    private func deny(_ c: NWConnection) { send(c, 401, json(["error": ["message": "访问密钥不对。到 设置 → 高级 里查看。"]])) }

    private func json(_ object: Any) -> Data { (try? JSONSerialization.data(withJSONObject: object)) ?? Data() }

    private func respond(_ c: NWConnection, _ r: Request) async {
        switch (r.method, r.path.split(separator: "?").first.map(String.init) ?? "") {
        case ("GET", "/health"): send(c, 200, json(["status": "ok", "service": "语音转写"]))
        case ("GET", prefix + "/models"):
            guard authorized(r) else { return deny(c) }
            send(c, 200, json(["object": "list", "data": offered.map { ["id": $0.id, "object": "model", "owned_by": $0.service?.name ?? "本机"] }]))
        case ("POST", prefix + "/audio/transcriptions"):
            guard authorized(r) else { return deny(c) }
            do {
                let form = try Multipart.parse(r.body, contentType: r.headers["content-type"] ?? "")
                guard let file = form.file else { return send(c, 400, json(["error": ["message": "缺少音频文件"]])) }
                let language = form.fields["language"] ?? ""
                guard language.count <= 64 else { return send(c, 400, json(["error": ["message": "语言参数太长。"]])) }
                let asked = form.fields["model"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                let pick: (id: String, service: Service?)?
                if asked.isEmpty {
                    pick = offered.first { $0.id == Service.local.model } ?? offered.first
                } else {
                    pick = offered.first { $0.id == asked }
                }
                guard let pick else { return send(c, 400, json(["error": ["message": "未知模型 \(asked)。请先查看 GET /models。"]])) }
                let ext = URL(fileURLWithPath: form.filename ?? "a.wav").pathExtension
                let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + "." + (ext.isEmpty ? "wav" : ext))
                try file.write(to: tmp)
                defer { try? FileManager.default.removeItem(at: tmp) }
                let samples = try await AudioIO.decode(tmp)
                let text: String
                switch pick.service?.id {
                case nil:
                    guard await ModelStore.shared.isReady(pick.id) else { return send(c, 503, json(["error": ["message": "本机模型还没下载。"]])) }
                    text = try await engine.quick(samples, language: MLXEngine.languageName(language), repo: pick.id)
                case "doubao": text = try await DoubaoWebASR.transcribe(wav: AudioIO.wav(samples[...]), language: language, hotwords: []).text
                case "openrouter": text = try await OpenRouterASR.transcribe(wav: AudioIO.wav(samples[...]), language: language, hotwords: []).text
                case "bcut": text = try await BcutASR.transcribe(file: AudioIO.wav(samples[...]), format: "wav", stage: { _ in }, cancelled: { false }).text
                case "dashscope": text = try await Cloud.dashscope(wav: AudioIO.wav(samples[...]), key: Service.dashscope.key, language: language, model: pick.id).text
                default: return send(c, 400, json(["error": ["message": "模型服务不支持。"]]))
                }
                switch form.fields["response_format"] ?? "json" {
                case "text": send(c, 200, Data(text.utf8), type: "text/plain")
                case "json": send(c, 200, json(["text": text]))
                default: send(c, 400, json(["error": ["message": "不支持的 response_format。"]]))
                }
            } catch {
                let status: Int
                if error is Multipart.Error { status = 400 }
                else if error is CancellationError { status = 499 }
                else if error.localizedDescription.contains("密钥") || error.localizedDescription.contains("登录") { status = 401 }
                else if error.localizedDescription.contains("模型还没下载") { status = 503 }
                else { status = 500 }
                send(c, status, json(["error": ["message": error.localizedDescription]]))
            }
        default: send(c, 404, json(["error": ["message": "not found"]]))
        }
    }
}

enum Multipart {
    struct Form { var fields: [String: String] = [:]; var file: Data?; var filename: String? }
    enum Error: LocalizedError {
        case invalid(String)
        var errorDescription: String? {
            switch self { case .invalid(let message): return message }
        }
    }

    static func parse(_ body: Data, contentType: String) throws -> Form {
        let parameters = contentType.split(separator: ";", omittingEmptySubsequences: true).map { $0.trimmingCharacters(in: .whitespaces) }
        guard parameters.first?.lowercased() == "multipart/form-data",
              let rawBoundary = parameters.dropFirst().first(where: { $0.lowercased().hasPrefix("boundary=") })?.dropFirst("boundary=".count) else {
            throw Error.invalid("Content-Type 不是有效的 multipart/form-data。")
        }
        let boundaryText = rawBoundary.trimmingCharacters(in: CharacterSet(charactersIn: "\" "))
        guard !boundaryText.isEmpty, boundaryText.count <= 70 else { throw Error.invalid("multipart boundary 无效。") }
        let opening = Data(("--" + boundaryText + "\r\n").utf8)
        let delimiter = Data(("\r\n--" + boundaryText).utf8)
        let headerEnd = Data("\r\n\r\n".utf8)
        let lineEnd = Data("\r\n".utf8)
        guard body.starts(with: opening) else { throw Error.invalid("multipart 内容不完整。") }

        func parameter(_ name: String, in header: String) -> String? {
            let pattern = "(?:^|;)\\s*" + name + "\\s*=\\s*(?:\"([^\"]*)\"|([^;\\s]*))"
            guard let expression = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]),
                  let match = expression.firstMatch(in: header, range: NSRange(header.startIndex..., in: header)) else { return nil }
            for index in 1...2 {
                let range = match.range(at: index)
                if range.location != NSNotFound, let swiftRange = Range(range, in: header) { return String(header[swiftRange]) }
            }
            return nil
        }

        var form = Form()
        var cursor = opening.count
        var count = 0
        while cursor < body.count {
            guard let hit = body.range(of: delimiter, in: cursor..<body.count),
                  let split = body.range(of: headerEnd, in: cursor..<hit.lowerBound) else {
                throw Error.invalid("multipart 内容不完整。")
            }
            let header = String(decoding: body[cursor..<split.lowerBound], as: UTF8.self)
            guard let name = parameter("name", in: header) else { throw Error.invalid("multipart 字段缺少 name。") }
            let content = Data(body[split.upperBound..<hit.lowerBound])
            if let filename = parameter("filename", in: header) {
                guard form.file == nil else { throw Error.invalid("只能上传一个音频文件。") }
                form.file = content
                form.filename = URL(fileURLWithPath: filename).lastPathComponent
            } else {
                form.fields[name] = String(decoding: content, as: UTF8.self)
            }
            count += 1
            guard count <= 128 else { throw Error.invalid("multipart 字段太多。") }
            cursor = hit.upperBound
            if body.count >= cursor + 2, Data(body[cursor..<(cursor + 2)]) == Data("--".utf8) { break }
            guard body.count >= cursor + 2, Data(body[cursor..<(cursor + 2)]) == lineEnd else {
                throw Error.invalid("multipart 边界无效。")
            }
            cursor += 2
        }
        return form
    }
}
