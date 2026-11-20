import CryptoKit
import Foundation

/// Plain downloads from a Hugging Face compatible host: resumable, with an idle timeout so a stalled source is noticed.
enum HubDownloader {
    struct Item { let name: String; let size: Int64; let sha256: String? }
    struct Plan { let items: [Item]; let revision: String }

    private static func session() -> URLSession {
        let c = URLSessionConfiguration.ephemeral
        c.timeoutIntervalForRequest = 40
        c.waitsForConnectivity = false
        return URLSession(configuration: c)
    }

    static func plan(repo: String, endpoint: String) async throws -> Plan {
        var request = URLRequest(url: URL(string: "\(endpoint)/api/models/\(repo)?blobs=true")!, timeoutInterval: 30)
        request.setValue("语音转写", forHTTPHeaderField: "User-Agent")
        let (data, _) = try await session().data(for: request)
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any], let files = root["siblings"] as? [[String: Any]] else {
            throw TFailure(message: "network: 读不到模型清单")
        }
        let revision = (root["sha"] as? String) ?? "main"
        let items: [Item] = files.compactMap { f in
            guard let name = f["rfilename"] as? String, isSafe(name), !name.hasPrefix("."), !name.hasSuffix(".md"), !name.hasSuffix(".py"), !name.contains("example") else { return nil }
            let sha = (f["lfs"] as? [String: Any])?["sha256"] as? String
            return Item(name: name, size: (f["size"] as? NSNumber)?.int64Value ?? 0, sha256: sha)
        }
        return Plan(items: items, revision: revision.allSatisfy { $0.isHexDigit } || revision == "main" ? revision : "main")
    }

    /// File names come from a host we do not control: relative, no `..`, no odd characters.
    private static func isSafe(_ name: String) -> Bool {
        !name.isEmpty && !name.hasPrefix("/") && !name.contains("\\") && !name.contains("\0")
            && !name.split(separator: "/").contains("..") && !name.split(separator: "/").contains(".")
    }

    private static func sha256(of url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var hasher = SHA256()
        while let chunk = try handle.read(upToCount: 4 << 20), !chunk.isEmpty { hasher.update(data: chunk) }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }

    static func isReady(_ repo: String) -> Bool {
        let dir = AppPaths.modelDirRaw(repo)
        let fm = FileManager.default
        if fm.fileExists(atPath: dir.appendingPathComponent(".ready").path) { return true }
        // A folder linked in from another tool's cache.
        return (try? fm.destinationOfSymbolicLink(atPath: dir.path)) != nil && fm.fileExists(atPath: dir.appendingPathComponent("model.safetensors").path)
    }

    static func partialBytes(_ repo: String) -> Int64 {
        let dir = AppPaths.modelDirRaw(repo)
        let files = (try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: [.fileSizeKey])) ?? []
        return files.reduce(0) { $0 + Int64((try? $1.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0) }
    }

    static func download(repo: String, endpoint: String, progress: @escaping @Sendable (Int64, Int64) -> Void) async throws {
        let plan = try await plan(repo: repo, endpoint: endpoint)
        let items = plan.items
        let total = items.reduce(0) { $0 + $1.size }
        let dir = AppPaths.modelDirRaw(repo)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        var done: Int64 = 0
        progress(0, total)
        for item in items {
            try Task.checkCancellation()
            let final = dir.appendingPathComponent(item.name).standardizedFileURL
            guard final.path.hasPrefix(dir.standardizedFileURL.path + "/") else { throw TFailure(message: "下载清单里有不安全的文件名：\(item.name)") }
            if let size = (try? FileManager.default.attributesOfItem(atPath: final.path)[.size]) as? Int64, size == item.size, item.size > 0 {
                done += item.size; progress(done, total); continue
            }
            let part = final.appendingPathExtension("part")
            try FileManager.default.createDirectory(at: final.deletingLastPathComponent(), withIntermediateDirectories: true)
            let base = done
            try await Fetcher().fetch(URL(string: "\(endpoint)/\(repo)/resolve/\(plan.revision)/\(item.name)")!, to: part) { got in progress(base + got, total) }
            let got = (try? FileManager.default.attributesOfItem(atPath: part.path)[.size]) as? Int64 ?? 0
            if item.size > 0, got != item.size { try? FileManager.default.removeItem(at: part); throw TFailure(message: "network: \(item.name) 大小不对，已丢弃，重试即可") }
            if let expected = item.sha256, try sha256(of: part) != expected {
                try? FileManager.default.removeItem(at: part)
                throw TFailure(message: "network: \(item.name) 校验没通过，已丢弃，重试即可（换个下载源也行）")
            }
            try? FileManager.default.removeItem(at: final)
            try FileManager.default.moveItem(at: part, to: final)
            done += item.size
            progress(done, total)
        }
        FileManager.default.createFile(atPath: dir.appendingPathComponent(".ready").path, contents: Data())
    }

    /// Bytes per second for a short ranged read of a real weight file; nil when the host does not answer in time.
    static func probe(endpoint: String) async -> Double? {
        var request = URLRequest(url: URL(string: "\(endpoint)/\(LocalModel.asr)/resolve/main/model.safetensors")!, timeoutInterval: 12)
        request.setValue("bytes=0-1999999", forHTTPHeaderField: "Range")
        let start = Date()
        guard let (data, _) = try? await session().data(for: request), data.count > 500_000 else { return nil }
        return Double(data.count) / max(Date().timeIntervalSince(start), 0.05)
    }
}

private final class Fetcher: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    private var handle: FileHandle?
    private var written: Int64 = 0
    private var onBytes: ((Int64) -> Void)?
    private var continuation: CheckedContinuation<Void, Error>?
    private var session: URLSession?

    func fetch(_ url: URL, to part: URL, onBytes: @escaping (Int64) -> Void) async throws {
        if !FileManager.default.fileExists(atPath: part.path) { FileManager.default.createFile(atPath: part.path, contents: nil) }
        handle = try FileHandle(forWritingTo: part)
        let existing = Int64(try handle!.seekToEnd())
        written = existing
        self.onBytes = onBytes
        var request = URLRequest(url: url)
        request.setValue("语音转写", forHTTPHeaderField: "User-Agent")
        if existing > 0 { request.setValue("bytes=\(existing)-", forHTTPHeaderField: "Range") }
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 40
        session = URLSession(configuration: config, delegate: self, delegateQueue: nil)
        let task = session!.dataTask(with: request)
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { (c: CheckedContinuation<Void, Error>) in continuation = c; task.resume() }
        } onCancel: { task.cancel() }
        try? handle?.close()
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse, completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
        if let http = response as? HTTPURLResponse {
            if http.statusCode == 200, written > 0 { try? handle?.truncate(atOffset: 0); written = 0 }   // host ignored the range: start over
            else if http.statusCode >= 400 { continuation?.resume(throwing: TFailure(message: "network: HTTP \(http.statusCode)")); continuation = nil; completionHandler(.cancel); return }
        }
        completionHandler(.allow)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        try? handle?.write(contentsOf: data)
        written += Int64(data.count)
        onBytes?(written)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        session.finishTasksAndInvalidate()
        guard let c = continuation else { return }
        continuation = nil
        if let error { c.resume(throwing: (error as? URLError)?.code == .cancelled ? CancellationError() : error) } else { c.resume() }
    }
}
