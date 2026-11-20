import Foundation

/// Every run owns a fresh directory, including retries of the same task.
/// Exclusive writes also protect files if a path is unexpectedly already occupied.
enum TranscriptionOutput {
    static func write(source: URL, taskID: Int, root: URL, text: String, subtitles: String,
                      checkCancellation: () throws -> Void) throws -> (txt: URL, srt: URL) {
        try checkCancellation()
        let directory = root.appendingPathComponent(String(taskID), isDirectory: true)
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        let stem = source.deletingPathExtension().lastPathComponent
        let txt = directory.appendingPathComponent(stem + ".txt")
        let srt = directory.appendingPathComponent(stem + ".srt")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var written: [URL] = []
        do {
            try checkCancellation()
            try Data(text.utf8).write(to: txt, options: .withoutOverwriting)
            written.append(txt)
            try checkCancellation()
            try Data(subtitles.utf8).write(to: srt, options: .withoutOverwriting)
            written.append(srt)
            try checkCancellation()
            return (txt, srt)
        } catch {
            for file in written { try? FileManager.default.removeItem(at: file) }
            // Remove only an empty run directory; preserve any unexpected existing files.
            if (try? FileManager.default.contentsOfDirectory(atPath: directory.path).isEmpty) == true {
                try? FileManager.default.removeItem(at: directory)
            }
            throw error
        }
    }
}
