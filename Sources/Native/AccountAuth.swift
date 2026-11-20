import AppKit
import CryptoKit
import Foundation
import Network
import Security

/// Account credentials are kept in the macOS Keychain, separately from the
/// legacy provider settings file. The file never receives access or refresh
/// tokens.
struct OpenAIAccountToken: Codable, Equatable {
    let accessToken: String
    let refreshToken: String?
    let idToken: String?
    let clientID: String
    let expiresAt: Date?
}

enum AccountCredentialStore {
    private static let service = "com.jasper.transcription-desktop.account"
    private static let account = "openai"

    static func loadOpenAI() -> OpenAIAccountToken? {
        var item: CFTypeRef?
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return nil }
        return try? JSONDecoder().decode(OpenAIAccountToken.self, from: data)
    }

    static func saveOpenAI(_ token: OpenAIAccountToken) throws {
        let data = try JSONEncoder().encode(token)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        let attrs: [String: Any] = [kSecValueData as String: data, kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly]
        let status = SecItemUpdate(query as CFDictionary, attrs as CFDictionary)
        if status == errSecItemNotFound {
            var add = query
            attrs.forEach { add[$0.key] = $0.value }
            guard SecItemAdd(add as CFDictionary, nil) == errSecSuccess else { throw TFailure(message: "无法保存 OpenAI 登录凭证。") }
        } else if status != errSecSuccess {
            throw TFailure(message: "无法保存 OpenAI 登录凭证。")
        }
    }

    static func deleteOpenAI() {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account]
        SecItemDelete(query as CFDictionary)
    }
}

enum OpenAIAccountAuth {
    private static let authorizeEndpoint = "https://auth.openai.com/api/accounts/authorize"
    private static let tokenEndpoint = "https://auth.openai.com/api/accounts/oauth/token"
    private static let resource = "https://api.openai.com/v1"

    @MainActor
    static func signIn() async throws -> OpenAIAccountToken {
        let verifier = randomString(length: 64)
        let challenge = Data(SHA256.hash(data: Data(verifier.utf8))).base64URLEncoded
        let state = randomString(length: 32)
        let nonce = randomString(length: 32)
        let hostID: String = {
            if let existing = UserDefaults.standard.string(forKey: "openAIHostID") { return existing }
            let value = "urn:uuid:\(UUID().uuidString.lowercased())"
            UserDefaults.standard.set(value, forKey: "openAIHostID")
            return value
        }()

        let listener = try LoopbackCallbackListener()
        try await listener.start()
        let redirect = listener.redirectURI
        var components = URLComponents(string: authorizeEndpoint)!
        components.queryItems = [
            URLQueryItem(name: "client_id", value: "dynamic_agent_client"),
            URLQueryItem(name: "agent_name_hint", value: "语音转写"),
            URLQueryItem(name: "ext_agent_host_id", value: hostID),
            URLQueryItem(name: "response_type", value: "code"),
            URLQueryItem(name: "scope", value: "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"),
            URLQueryItem(name: "resource", value: resource),
            URLQueryItem(name: "redirect_uri", value: redirect),
            URLQueryItem(name: "state", value: state),
            URLQueryItem(name: "nonce", value: nonce),
            URLQueryItem(name: "code_challenge_method", value: "S256"),
            URLQueryItem(name: "code_challenge", value: challenge),
        ]
        guard let url = components.url else { throw TFailure(message: "无法开始 OpenAI 登录。") }
        NSWorkspace.shared.open(url)
        let callback: Callback
        do {
            callback = try await withTaskCancellationHandler(operation: {
                try await withThrowingTaskGroup(of: Callback.self) { group in
                    group.addTask { try await listener.wait() }
                    group.addTask {
                        try await Task.sleep(nanoseconds: 180_000_000_000)
                        throw TFailure(message: "OpenAI 登录等待超时，请重试。")
                    }
                    defer { group.cancelAll() }
                    guard let result = try await group.next() else {
                        throw TFailure(message: "OpenAI 登录没有返回结果，请重试。")
                    }
                    return result
                }
            }, onCancel: { listener.cancel() })
        } catch {
            listener.cancel()
            throw error
        }
        guard callback.state == state else { throw TFailure(message: "OpenAI 登录校验失败，请重试。") }

        let callbackClientID = callback.clientID?.trimmingCharacters(in: .whitespacesAndNewlines)
        let issuedClientID = (callbackClientID?.isEmpty == false ? callbackClientID : nil)
            ?? UserDefaults.standard.string(forKey: "openAIClientID")
            ?? "dynamic_agent_client"
        let body = [
            "grant_type": "authorization_code",
            "client_id": issuedClientID,
            "code": callback.code,
            "code_verifier": verifier,
            "redirect_uri": redirect,
            "resource": resource,
        ]
        var request = URLRequest(url: URL(string: tokenEndpoint)!, timeoutInterval: 30)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        request.httpBody = formBody(body)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw TFailure(message: "OpenAI 登录没有完成，请重试。") }
        struct Reply: Decodable { let access_token: String; let refresh_token: String?; let id_token: String?; let expires_in: Double?; let client_id: String? }
        let reply = try JSONDecoder().decode(Reply.self, from: data)
        let clientID = reply.client_id ?? issuedClientID
        UserDefaults.standard.set(clientID, forKey: "openAIClientID")
        let token = OpenAIAccountToken(accessToken: reply.access_token, refreshToken: reply.refresh_token, idToken: reply.id_token, clientID: clientID, expiresAt: reply.expires_in.map { Date().addingTimeInterval($0 - 60) })
        try AccountCredentialStore.saveOpenAI(token)
        return token
    }

    static func accountID(from token: String) -> String? {
        let parts = token.split(separator: ".")
        guard parts.count > 1 else { return nil }
        var encoded = String(parts[1]).replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        encoded += String(repeating: "=", count: (4 - encoded.count % 4) % 4)
        guard let data = Data(base64Encoded: encoded, options: .ignoreUnknownCharacters),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let auth = json["https://api.openai.com/auth"] as? [String: Any] else { return nil }
        return auth["chatgpt_account_id"] as? String
    }

    static func validToken() async throws -> OpenAIAccountToken {
        guard let token = AccountCredentialStore.loadOpenAI() else { throw TFailure(message: "请先在设置里的账号页面登录 ChatGPT。") }
        if token.expiresAt.map({ $0 > Date() }) != false { return token }
        guard let refresh = token.refreshToken else { throw TFailure(message: "OpenAI 登录已过期，请重新登录。") }
        var request = URLRequest(url: URL(string: tokenEndpoint)!, timeoutInterval: 30)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        let fields = ["grant_type": "refresh_token", "client_id": token.clientID, "refresh_token": refresh, "resource": resource]
        request.httpBody = formBody(fields)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw TFailure(message: "OpenAI 登录已过期，请重新登录。") }
        struct Reply: Decodable { let access_token: String; let refresh_token: String?; let id_token: String?; let expires_in: Double? }
        let reply = try JSONDecoder().decode(Reply.self, from: data)
        let renewed = OpenAIAccountToken(accessToken: reply.access_token, refreshToken: reply.refresh_token ?? refresh, idToken: reply.id_token ?? token.idToken, clientID: token.clientID, expiresAt: reply.expires_in.map { Date().addingTimeInterval($0 - 60) })
        try AccountCredentialStore.saveOpenAI(renewed)
        return renewed
    }

    static func runResponses(system: String, input: String, model: String, effort: String?, onDelta: @escaping @Sendable (String) async -> Void) async throws -> String {
        let token = try await validToken()
        var request = URLRequest(url: URL(string: "https://api.openai.com/v1/responses")!, timeoutInterval: 180)
        request.httpMethod = "POST"
        request.setValue("Bearer \(token.accessToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        if let accountID = accountID(from: token.accessToken) ?? token.idToken.flatMap(accountID(from:)) {
            request.setValue(accountID, forHTTPHeaderField: "chatgpt-account-id")
        }
        request.setValue("responses=experimental", forHTTPHeaderField: "OpenAI-Beta")
        var body: [String: Any] = ["model": model, "instructions": system, "input": input, "stream": true, "store": false]
        if let effort { body["reasoning"] = ["effort": effort] }
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (bytes, response) = try await URLSession.shared.bytes(for: request)
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        var output = ""
        var plain = ""
        var ended = false
        var completedEvent = false
        for try await line in bytes.lines {
            try Task.checkCancellation()
            guard line.hasPrefix("data:") else {
                plain += line
                continue
            }
            let payload = line.dropFirst(5).trimmingCharacters(in: .whitespaces)
            if payload == "[DONE]" {
                ended = true
                break
            }
            guard let root = (try? JSONSerialization.jsonObject(with: Data(payload.utf8))) as? [String: Any] else { continue }
            if let error = root["error"] as? [String: Any], let message = error["message"] as? String { throw TFailure(message: "OpenAI 总结服务出错：\(message)") }
            if root["type"] as? String == "response.completed" { completedEvent = true }
            if root["type"] as? String == "response.output_text.delta", let delta = root["delta"] as? String { output += delta; await onDelta(delta) }
        }
        guard code == 200 else {
            let message = ((try? JSONSerialization.jsonObject(with: Data(plain.utf8))) as? [String: Any])
                .flatMap { ($0["error"] as? [String: Any])?["message"] as? String }
            throw TFailure(message: "OpenAI 总结服务返回错误（\(code)）。" + (message.map { "\($0)" } ?? ""))
        }
        if output.isEmpty,
           let root = (try? JSONSerialization.jsonObject(with: Data(plain.utf8))) as? [String: Any],
           let value = root["output_text"] as? String {
            output = value
            completedEvent = true
            await onDelta(value)
        }
        if !ended && !completedEvent { throw TFailure(message: "OpenAI 总结连接提前结束，请重试。") }
        guard !output.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw TFailure(message: "OpenAI 没有返回总结内容，请重试。") }
        return output.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func formBody(_ fields: [String: String]) -> Data {
        let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~")
        let encoded = fields.map { key, value in
            let k = key.addingPercentEncoding(withAllowedCharacters: allowed) ?? key
            let v = value.addingPercentEncoding(withAllowedCharacters: allowed) ?? value
            return "\(k)=\(v)"
        }.joined(separator: "&")
        return Data(encoded.utf8)
    }

    private static func randomString(length: Int) -> String { (0..<length).map { _ in String("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789".randomElement()!) }.joined() }
}

private struct Callback {
    let code: String
    let state: String
    let clientID: String?
}

private final class CallbackStartGate: @unchecked Sendable {
    private let lock = NSLock()
    private var finished = false

    func resolve(_ result: Result<Void, Error>, continuation: CheckedContinuation<Void, Error>) {
        lock.lock()
        guard !finished else { lock.unlock(); return }
        finished = true
        lock.unlock()
        continuation.resume(with: result)
    }
}

private final class LoopbackCallbackListener {
    let listener: NWListener
    private(set) var redirectURI = ""
    private let lock = NSLock()
    private var waitContinuation: CheckedContinuation<Callback, Error>?
    private var waitFinished = false

    init() throws {
        listener = try NWListener(using: .tcp, on: 0)
    }

    func start() async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            let gate = CallbackStartGate()
            listener.stateUpdateHandler = { [weak self] state in
                switch state {
                case .ready:
                    guard let self, let port = self.listener.port else {
                        gate.resolve(.failure(TFailure(message: "无法打开登录回调端口。")), continuation: continuation); return
                    }
                    self.redirectURI = "http://127.0.0.1:\(port)/auth/callback"
                    gate.resolve(.success(()), continuation: continuation)
                case .failed(let error): gate.resolve(.failure(TFailure(message: "无法打开登录回调端口：\(error.localizedDescription)")), continuation: continuation)
                default: break
                }
            }
            listener.start(queue: .global(qos: .userInitiated))
        }
    }

    func cancel() {
        listener.cancel()
        resolve(.failure(CancellationError()))
    }

    func wait() async throws -> Callback {
        try await withTaskCancellationHandler(operation: {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Callback, Error>) in
                lock.lock()
                if waitFinished {
                    lock.unlock()
                    continuation.resume(throwing: CancellationError())
                } else {
                    waitContinuation = continuation
                    lock.unlock()
                    listener.newConnectionHandler = { [weak self] connection in
                        guard let self else { return }
                        connection.start(queue: .global(qos: .userInitiated))
                        self.receive(connection, buffer: Data())
                    }
                }
            }
        }, onCancel: { [weak self] in
            self?.cancel()
        })
    }

    private func receive(_ connection: NWConnection, buffer: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 8192) { [weak self] data, _, done, error in
            guard let self else { connection.cancel(); return }
            var buffer = buffer
            if let data { buffer.append(data) }
            if buffer.range(of: Data("\r\n\r\n".utf8)) == nil, !done, error == nil, buffer.count < 16_384 {
                self.receive(connection, buffer: buffer)
                return
            }
            defer { connection.cancel() }
            guard error == nil, let request = String(data: buffer, encoding: .utf8),
                  let line = request.components(separatedBy: "\r\n").first else {
                self.resolve(.failure(TFailure(message: "OpenAI 登录回调无效。")))
                return
            }
            let fields = line.split(separator: " ", omittingEmptySubsequences: true)
            guard fields.count >= 2, fields[0] == "GET",
                  let target = URL(string: "http://127.0.0.1\(fields[1])"),
                  target.path == "/auth/callback" else {
                self.resolve(.failure(TFailure(message: "OpenAI 登录回调地址无效。")))
                return
            }
            let query = URLComponents(url: target, resolvingAgainstBaseURL: false)?.queryItems ?? []
            if let failure = query.first(where: { $0.name == "error" })?.value {
                let detail = query.first(where: { $0.name == "error_description" })?.value
                self.resolve(.failure(TFailure(message: "OpenAI 登录未完成：\(detail ?? failure)")))
                return
            }
            guard let code = query.first(where: { $0.name == "code" })?.value,
                  let state = query.first(where: { $0.name == "state" })?.value else {
                self.resolve(.failure(TFailure(message: "OpenAI 登录缺少授权信息。")))
                return
            }
            let clientID = query.first(where: { $0.name == "client_id" })?.value
            let html = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n<html><body>登录完成，可以关闭此页面。</body></html>"
            connection.send(content: html.data(using: .utf8), completion: .contentProcessed { _ in })
            self.resolve(.success(Callback(code: code, state: state, clientID: clientID)))
        }
    }

    private func resolve(_ result: Result<Callback, Error>) {
        lock.lock()
        guard !waitFinished else { lock.unlock(); return }
        waitFinished = true
        let continuation = waitContinuation
        waitContinuation = nil
        lock.unlock()
        listener.cancel()
        continuation?.resume(with: result)
    }
}

private extension Data {
    var base64URLEncoded: String { base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
}
