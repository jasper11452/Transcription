import Foundation

/// Keys and options live in one small config file (permissions 600), the same one the earlier Transcript install used.
enum ConfigEnv {
    private static var path: URL { AppPaths.layout.config }

    static func read(_ name: String) -> String? {
        guard let text = try? String(contentsOf: path, encoding: .utf8) else { return nil }
        for line in text.split(separator: "\n") where line.trimmingCharacters(in: .whitespaces).hasPrefix("\(name)=") {
            let value = line.split(separator: "=", maxSplits: 1).last.map(String.init) ?? ""
            let trimmed = value.trimmingCharacters(in: CharacterSet(charactersIn: " \"'"))
            return trimmed.isEmpty ? nil : trimmed
        }
        return nil
    }

    static func save(_ name: String, _ raw: String) {
        let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        var lines = ((try? String(contentsOf: path, encoding: .utf8)) ?? "").split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
        if let index = lines.firstIndex(where: { $0.trimmingCharacters(in: .whitespaces).hasPrefix("\(name)=") }) { lines[index] = "\(name)=\(value)" }
        else { lines.append("\(name)=\(value)") }
        while lines.last == "" { lines.removeLast() }
        let tmp = path.appendingPathExtension("tmp")
        try? FileManager.default.createDirectory(at: path.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? (lines.joined(separator: "\n") + "\n").write(to: tmp, atomically: false, encoding: .utf8)
        try? FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: tmp.path)
        _ = try? FileManager.default.replaceItemAt(path, withItemAt: tmp)
    }
}
