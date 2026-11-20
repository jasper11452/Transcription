import AppKit
import Foundation
import Security
import SwiftUI
import WebKit

struct DoubaoASRParams: Codable, Equatable {
    let cookies: [String: String]
    let deviceId: String
    let webId: String

    var cookieHeader: String {
        cookies.keys.sorted().compactMap { key in
            guard let value = cookies[key], !value.isEmpty else { return nil }
            return "\(key)=\(value)"
        }.joined(separator: "; ")
    }

    var usable: Bool {
        !deviceId.isEmpty && !webId.isEmpty &&
        (cookies["sessionid"]?.isEmpty == false || cookies["sessionid_ss"]?.isEmpty == false)
    }
}

enum DoubaoCredentialStore {
    private static let service = "com.jasper.transcription-desktop.account"
    private static let account = "doubao-asr"

    static func load() -> DoubaoASRParams? {
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
        return try? JSONDecoder().decode(DoubaoASRParams.self, from: data)
    }

    static func save(_ params: DoubaoASRParams) throws {
        guard params.usable else { throw TFailure(message: "豆包登录信息不完整，请在登录窗口重新登录。") }
        let data = try JSONEncoder().encode(params)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        let attrs: [String: Any] = [
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        ]
        let status = SecItemUpdate(query as CFDictionary, attrs as CFDictionary)
        if status == errSecItemNotFound {
            var add = query
            attrs.forEach { add[$0.key] = $0.value }
            guard SecItemAdd(add as CFDictionary, nil) == errSecSuccess else {
                throw TFailure(message: "无法保存豆包登录信息。")
            }
        } else if status != errSecSuccess {
            throw TFailure(message: "无法保存豆包登录信息。")
        }
    }

    static func delete() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
    }
}

enum DoubaoWebAuth {
    static var isConfigured: Bool { DoubaoCredentialStore.load()?.usable == true }
    static var statusText: String { isConfigured ? "已登录" : "未登录" }

    @MainActor
    static func extract(from webView: WKWebView) async throws -> DoubaoASRParams {
        let cookies: [HTTPCookie] = await withCheckedContinuation { (continuation: CheckedContinuation<[HTTPCookie], Never>) in
            webView.configuration.websiteDataStore.httpCookieStore.getAllCookies { continuation.resume(returning: $0) }
        }
        let scoped = cookies.filter { $0.domain == "doubao.com" || $0.domain.hasSuffix(".doubao.com") }
        guard scoped.contains(where: { $0.name == "sessionid" || $0.name == "sessionid_ss" }) else {
            throw TFailure(message: "还没有检测到豆包登录状态，请先在窗口中完成登录。")
        }
        let deviceId = try await webID(in: webView, key: "samantha_web_web_id")
        let webId = try await webID(in: webView, key: "__tea_cache_tokens_497858")
        let cookieValues = Dictionary(scoped.map { ($0.name, $0.value) }, uniquingKeysWith: { _, newest in newest })
        let params = DoubaoASRParams(cookies: cookieValues, deviceId: deviceId, webId: webId)
        guard params.usable else { throw TFailure(message: "豆包登录信息还没准备好，请刷新页面后重试。") }
        return params
    }

    @MainActor
    private static func webID(in webView: WKWebView, key: String) async throws -> String {
        let raw = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Any?, Error>) in
            webView.evaluateJavaScript("localStorage.getItem('\(key)')") { value, error in
                if let error { continuation.resume(throwing: error) }
                else { continuation.resume(returning: value) }
            }
        }
        let value: String? = {
            guard let text = raw as? String,
                  let data = text.data(using: .utf8),
                  let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
            if let value = object["web_id"] as? String { return value }
            return (object["web_id"] as? NSNumber)?.stringValue
        }()
        guard let value, !value.isEmpty else {
            throw TFailure(message: "豆包设备信息还没准备好，请刷新页面后重试。")
        }
        return value
    }
}

struct DoubaoLoginView: View {
    let onComplete: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var webView: WKWebView?
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        VStack(spacing: 0) {
            DoubaoLoginWebView(webView: $webView)
                .frame(minWidth: 760, minHeight: 560)
            Divider()
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("在豆包页面完成登录后，点击“登录完成”。")
                    Text("登录信息只保存在这台 Mac 的钥匙串中。")
                        .font(.callout).foregroundStyle(.secondary)
                }
                Spacer()
                if let error { Text(error).font(.callout).foregroundStyle(.red).lineLimit(2) }
                Button("取消") { dismiss() }
                Button("登录完成") { complete() }
                    .buttonStyle(.borderedProminent)
                    .disabled(webView == nil || busy)
            }
            .padding(14)
        }
        .frame(width: 900, height: 660)
    }

    private func complete() {
        guard let webView else { return }
        busy = true
        error = nil
        Task { @MainActor in
            do {
                try AccountCredentialStore.saveDoubao(try await DoubaoWebAuth.extract(from: webView))
                onComplete()
                dismiss()
            } catch {
                self.error = error.localizedDescription
            }
            busy = false
        }
    }
}

private struct DoubaoLoginWebView: NSViewRepresentable {
    @Binding var webView: WKWebView?

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.uiDelegate = context.coordinator
        view.load(URLRequest(url: URL(string: "https://www.doubao.com/chat")!))
        DispatchQueue.main.async { webView = view }
        return view
    }

    func updateNSView(_ view: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                     for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            if navigationAction.targetFrame == nil { webView.load(navigationAction.request) }
            return nil
        }
    }
}

struct DoubaoAccountControls: View {
    let onChanged: () -> Void
    @State private var loggedIn = DoubaoWebAuth.isConfigured
    @State private var showLogin = false

    var body: some View {
        HStack {
            Label(loggedIn ? "已登录" : "未登录", systemImage: loggedIn ? "checkmark.circle.fill" : "person.crop.circle.badge.xmark")
                .foregroundStyle(loggedIn ? .green : .secondary)
            Spacer()
            if loggedIn {
                Button("重新登录") { showLogin = true }
                Button("退出登录", role: .destructive) {
                    DoubaoCredentialStore.delete()
                    loggedIn = false
                    onChanged()
                }
            } else {
                Button("登录豆包") { showLogin = true }
                    .buttonStyle(.borderedProminent)
            }
        }
        .sheet(isPresented: $showLogin) {
            DoubaoLoginView {
                loggedIn = true
                onChanged()
            }
        }
        .onAppear { loggedIn = DoubaoWebAuth.isConfigured }
    }
}

private final class DoubaoWebASRSession: @unchecked Sendable {
    private let params: DoubaoASRParams
    private let language: String
    private let pcm: Data
    private let stateQueue = DispatchQueue(label: "doubao-web-asr-session")
    private var session: URLSession?
    private var socket: URLSessionWebSocketTask?
    private var timeout: Task<Void, Never>?
    private var completion: ((Result<Heard, Error>) -> Void)?
    private var text = ""
    private var completed = false
    private var cancelRequested = false
    private var sendOffset = 0
    private var tailSent = false

    init(params: DoubaoASRParams, language: String, wav: Data) {
        self.params = params
        self.language = language.isEmpty ? "zh" : language
        self.pcm = Self.pcmData(from: wav)
    }

    func start(_ completion: @escaping (Result<Heard, Error>) -> Void) {
        let accepted = stateQueue.sync { () -> Bool in
            guard !completed, self.completion == nil else { return false }
            self.completion = completion
            return true
        }
        guard accepted else { return }
        stateQueue.async { [weak self] in
            guard let self, !self.completed else { return }
            if self.cancelRequested {
                self.finish(.failure(CancellationError()))
                return
            }
            self.open()
        }
    }

    func cancel() {
        stateQueue.async { [weak self] in
            guard let self else { return }
            guard !self.completed else { return }
            guard self.completion != nil else {
                self.cancelRequested = true
                return
            }
            self.finish(.failure(CancellationError()))
        }
    }

    private func open() {
        var components = URLComponents(string: "wss://ws-samantha.doubao.com/samantha/audio/asr")!
        components.queryItems = [
            URLQueryItem(name: "version_code", value: "20800"),
            URLQueryItem(name: "language", value: language),
            URLQueryItem(name: "device_platform", value: "web"),
            URLQueryItem(name: "aid", value: "497858"),
            URLQueryItem(name: "real_aid", value: "497858"),
            URLQueryItem(name: "pkg_type", value: "release_version"),
            URLQueryItem(name: "device_id", value: params.deviceId),
            URLQueryItem(name: "pc_version", value: "3.12.3"),
            URLQueryItem(name: "web_id", value: params.webId),
            URLQueryItem(name: "tea_uuid", value: params.webId),
            URLQueryItem(name: "region", value: ""),
            URLQueryItem(name: "sys_region", value: ""),
            URLQueryItem(name: "samantha_web", value: "1"),
            URLQueryItem(name: "use-olympus-account", value: "1"),
            URLQueryItem(name: "web_tab_id", value: UUID().uuidString),
            URLQueryItem(name: "format", value: "pcm"),
        ]
        guard let url = components.url else {
            finish(.failure(TFailure(message: "豆包转写地址无效。")))
            return
        }
        var request = URLRequest(url: url, timeoutInterval: 10)
        request.setValue(params.cookieHeader, forHTTPHeaderField: "Cookie")
        request.setValue("https://www.doubao.com", forHTTPHeaderField: "Origin")
        request.setValue("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36", forHTTPHeaderField: "User-Agent")
        let session = URLSession(configuration: .ephemeral)
        self.session = session
        let socket = session.webSocketTask(with: request)
        self.socket = socket
        socket.resume()
        receive(socket)
        timeout = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 45_000_000_000)
            guard !Task.isCancelled else { return }
            self?.fail(TFailure(message: "豆包转写等待超时，请重试。"))
        }
        socket.sendPing { [weak self] error in
            self?.stateQueue.async {
                guard let self, !self.completed else { return }
                if error != nil {
                    self.finish(.failure(TFailure(message: "无法连接豆包转写服务，请检查网络或重新登录。")))
                } else {
                    self.sendNext()
                }
            }
        }
    }

    private func fail(_ error: Error) {
        stateQueue.async { [weak self] in
            self?.finish(.failure(error))
        }
    }

    private func sendNext() {
        guard !completed, let socket else { return }
        if sendOffset < pcm.count {
            let end = min(sendOffset + 16_384, pcm.count)
            let packet = Data(pcm[sendOffset..<end])
            sendOffset = end
            socket.send(.data(packet)) { [weak self] error in
                self?.stateQueue.async {
                    guard let self, !self.completed else { return }
                    if error != nil { self.finish(.failure(TFailure(message: "豆包转写上传失败，请重试。"))) }
                    else { self.sendNext() }
                }
            }
            return
        }
        guard !tailSent else { return }
        tailSent = true
        socket.send(.data(Data(repeating: 0, count: 6_400))) { [weak self] error in
            self?.stateQueue.async {
                guard let self, !self.completed, error != nil else { return }
                self.finish(.failure(TFailure(message: "豆包转写上传失败，请重试。")))
            }
        }
    }

    private func receive(_ socket: URLSessionWebSocketTask) {
        socket.receive { [weak self] result in
            self?.stateQueue.async {
                guard let self, !self.completed else { return }
                switch result {
                case .failure:
                    self.finish(.failure(TFailure(message: "豆包转写连接中断，请重试或重新登录。")))
                case .success(let message):
                    switch message {
                    case .string(let value): self.handle(value)
                    case .data(let data): if let value = String(data: data, encoding: .utf8) { self.handle(value) }
                    @unknown default: break
                    }
                    if !self.completed { self.receive(socket) }
                }
            }
        }
    }

    private func handle(_ value: String) {
        guard let data = value.data(using: .utf8),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        let code = (root["code"] as? NSNumber)?.intValue ?? 0
        if code != 0 {
            let message = (root["message"] as? String ?? "").lowercased()
            let authFailure = [709599054, 710012001, 710022013].contains(code)
                || ["cookie", "auth", "login", "session", "unauthorized", "expired"].contains { message.contains($0) }
            if authFailure {
                finish(.failure(TFailure(message: "豆包登录已失效，请重新登录。")))
            } else {
                finish(.failure(TFailure(message: "豆包转写服务返回错误，请稍后重试。")))
            }
            return
        }
        switch root["event"] as? String {
        case "result":
            if let result = root["result"] as? [String: Any],
               let value = (result["Text"] as? String) ?? (result["text"] as? String),
               !value.isEmpty { text = value }
        case "finish":
            if let result = root["result"] as? [String: Any],
               let value = (result["Text"] as? String) ?? (result["text"] as? String),
               !value.isEmpty { text = value }
            finish(.success((text.trimmingCharacters(in: .whitespacesAndNewlines), [])))
        default: break
        }
    }

    private func finish(_ result: Result<Heard, Error>) {
        guard !completed else { return }
        completed = true
        let completion = self.completion
        self.completion = nil
        timeout?.cancel()
        socket?.cancel(with: .normalClosure, reason: nil)
        session?.invalidateAndCancel()
        session = nil
        socket = nil
        completion?(result)
    }

    private static func pcmData(from wav: Data) -> Data {
        guard wav.count > 12 else { return wav }
        var offset = 12
        while offset + 8 <= wav.count {
            let id = String(data: wav.subdata(in: offset..<(offset + 4)), encoding: .ascii) ?? ""
            let size = Int(wav[offset + 4]) | (Int(wav[offset + 5]) << 8) | (Int(wav[offset + 6]) << 16) | (Int(wav[offset + 7]) << 24)
            let start = offset + 8
            guard size >= 0, start <= wav.count else { break }
            let end = min(wav.count, start + size)
            if id == "data" { return wav.subdata(in: start..<end) }
            offset = end + (size % 2)
        }
        return wav.count > 44 ? wav.subdata(in: 44..<wav.count) : wav
    }

}

enum DoubaoWebASR {
    static func transcribe(wav: Data, language: String, hotwords: [String]) async throws -> Heard {
        guard let params = DoubaoCredentialStore.load(), params.usable else {
            throw TFailure(message: "请先在设置里登录豆包。")
        }
        guard wav.count <= 64 * 1024 * 1024 else {
            throw TFailure(message: "豆包单段音频太大，请缩短录音后重试。")
        }
        let session = DoubaoWebASRSession(params: params, language: language, wav: wav)
        return try await withTaskCancellationHandler(operation: {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Heard, Error>) in
                session.start { result in continuation.resume(with: result) }
            }
        }, onCancel: {
            session.cancel()
        })
    }
}

extension AccountCredentialStore {
    static func loadDoubao() -> DoubaoASRParams? { DoubaoCredentialStore.load() }
    static func saveDoubao(_ params: DoubaoASRParams) throws { try DoubaoCredentialStore.save(params) }
}
