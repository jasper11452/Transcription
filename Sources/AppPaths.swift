import Darwin
import Foundation

/// Where things live: user data, the model cache and keys.
enum AppPaths {
    static let fm = FileManager.default
    static let home = fm.homeDirectoryForCurrentUser

    struct Layout {
        let dataDir: URL
        let config: URL
        let glossary: URL
        let modelCache: URL
        /// History kept by the earlier Transcript install, imported read-only on first run.
        let legacyDB: URL
        /// Models another tool already downloaded are linked in instead of fetched again.
        let reuseSystemModels: Bool
    }

    /// `-DataRoot <dir>` points everything at an empty directory, to see a true first run without touching real data.
    private static let override: URL? = {
        let args = CommandLine.arguments
        guard let i = args.firstIndex(of: "-DataRoot"), i + 1 < args.count else { return nil }
        return URL(fileURLWithPath: args[i + 1])
    }()

    static var isTestRoot: Bool { override != nil }
    /// The port other tools expect; a sandboxed test run picks its own.
    static let serverPort: Int = isTestRoot ? freePort() : 18475

    static let layout: Layout = {
        if let root = override {
            return Layout(dataDir: root.appendingPathComponent("data"), config: root.appendingPathComponent("data/config.env"),
                          glossary: root.appendingPathComponent("data/glossary.txt"), modelCache: root.appendingPathComponent("models"),
                          legacyDB: root.appendingPathComponent("none.db"), reuseSystemModels: false)
        }
        let support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("语音转写")
        let legacyDB = home.appendingPathComponent("Documents/Transcript/state.db")
        if fm.fileExists(atPath: legacyDB.path) {
            return Layout(dataDir: support.appendingPathComponent("data"), config: home.appendingPathComponent(".config/transcript/config.env"),
                          glossary: home.appendingPathComponent(".config/transcript/glossary.txt"), modelCache: support.appendingPathComponent("models"),
                          legacyDB: legacyDB, reuseSystemModels: true)
        }
        return Layout(dataDir: support.appendingPathComponent("data"), config: support.appendingPathComponent("data/config.env"),
                      glossary: support.appendingPathComponent("data/glossary.txt"), modelCache: support.appendingPathComponent("models"),
                      legacyDB: support.appendingPathComponent("none.db"), reuseSystemModels: true)
    }()

    static var systemModelCache: URL { home.appendingPathComponent(".cache/huggingface/hub") }

    static func prepareDataDirectory() {
        for dir in [layout.dataDir, layout.modelCache, layout.config.deletingLastPathComponent()] {
            try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
        }
        // The model loader finds its files through this variable.
        setenv("HF_HUB_CACHE", layout.modelCache.path, 1)
        setenv("HF_HOME", layout.modelCache.deletingLastPathComponent().path, 1)
    }

    /// Folder of one model inside the cache, in the layout the loader expects.
    static func modelDirRaw(_ repo: String) -> URL {
        layout.modelCache.appendingPathComponent("mlx-audio/" + repo.replacingOccurrences(of: "/", with: "_"), isDirectory: true)
    }

    /// Same folder with any link followed, for code that lists its files.
    static func modelDir(_ repo: String) -> URL {
        modelDirRaw(repo).resolvingSymlinksInPath()
    }

    static func isPortFree(_ port: Int) -> Bool {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return false }
        defer { close(fd) }
        var addr = sockaddr_in(sin_len: UInt8(MemoryLayout<sockaddr_in>.size), sin_family: sa_family_t(AF_INET), sin_port: in_port_t(port).bigEndian,
                               sin_addr: in_addr(s_addr: inet_addr("127.0.0.1")), sin_zero: (0, 0, 0, 0, 0, 0, 0, 0))
        return withUnsafePointer(to: &addr) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0 } }
    }

    static func freePort() -> Int {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        defer { close(fd) }
        var addr = sockaddr_in(sin_len: UInt8(MemoryLayout<sockaddr_in>.size), sin_family: sa_family_t(AF_INET), sin_port: 0,
                               sin_addr: in_addr(s_addr: inet_addr("127.0.0.1")), sin_zero: (0, 0, 0, 0, 0, 0, 0, 0))
        _ = withUnsafeMutablePointer(to: &addr) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) } }
        var length = socklen_t(MemoryLayout<sockaddr_in>.size)
        _ = withUnsafeMutablePointer(to: &addr) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(fd, $0, &length) } }
        return Int(UInt16(bigEndian: addr.sin_port))
    }
}
