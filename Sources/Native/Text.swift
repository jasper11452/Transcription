import Foundation

// MARK: - Chunk planning (ported from the Python pipeline: cut at silence, never longer than maxS)

struct Chunk: Codable, Equatable { let start: Double; let end: Double }

func mergeGaps(_ spans: [(Double, Double)], maxGap: Double) -> [(Double, Double)] {
    var merged: [(Double, Double)] = []
    for span in spans.sorted(by: { $0.0 < $1.0 }) {
        if let last = merged.last, span.0 - last.1 <= maxGap { merged[merged.count - 1] = (last.0, max(last.1, span.1)) }
        else { merged.append(span) }
    }
    return merged
}

func planChunks(_ spansIn: [(Double, Double)], duration: Double, minS: Double = 20, maxS: Double = 40) -> [Chunk] {
    guard duration > 0 else { return [] }
    if duration <= minS { return [Chunk(start: 0, end: duration)] }
    let spans = spansIn.map { (max(0, $0.0), min(duration, $0.1)) }.filter { $0.1 > $0.0 }.sorted { $0.0 < $1.0 }
    var cuts: [Double] = []
    var cursor = 0.0, i = 0
    while duration - cursor > maxS {
        var acc = 0.0, j = i
        var best: Double?
        while j < spans.count, spans[j].1 > cursor {
            acc += spans[j].1 - spans[j].0
            if j + 1 < spans.count, spans[j + 1].0 - spans[j].1 >= 0.15 {
                let candidate = (spans[j].1 + spans[j + 1].0) / 2
                if candidate - cursor > maxS { break }
                best = candidate
                if acc >= minS { break }
            }
            if acc >= maxS { break }
            j += 1
        }
        let cut = max(cursor + 1, min(duration, best ?? cursor + maxS))
        cuts.append(cut)
        cursor = cut
        while i < spans.count, spans[i].1 <= cursor { i += 1 }
    }
    let bounds = [0.0] + cuts + [duration]
    return (0..<bounds.count - 1).compactMap { bounds[$0 + 1] - bounds[$0] > 0.01 ? Chunk(start: bounds[$0], end: bounds[$0 + 1]) : nil }
}

// MARK: - Sentences and subtitles (ported from the Python pipeline's align.py)
//
// The recogniser's text is the truth; the aligner (or the cloud's word times) only lends it a clock.
// Every character keeps a time, times never go backwards, and no sentence is ever dropped:
// a mismatch may blur a boundary, never lose words.

private let hardBreak: Set<Character> = ["。", "！", "？", "!", "?", "…", "\n"]
private let softBreak: Set<Character> = ["，", ",", "；", ";", "、", "：", ":"]
private let maxCueSeconds = 15.0, softMinChars = 12, softMinSeconds = 5.0, minTailChars = 4, minCueSeconds = 0.35
/// A cue never outgrows two 42-column lines (a CJK character is two columns wide).
private let maxCueColumns = 84, orphanColumns = 24

func isSpoken(_ c: Character) -> Bool { c.isLetter || c.isNumber }

struct TimedChar { let char: Character; let start: Double; let end: Double }

/// Spreads each aligned item's time over its spoken characters.
func timedChars(_ items: [(text: String, start: Double, end: Double)]) -> [TimedChar] {
    var out: [TimedChar] = []
    for item in items {
        let chars = item.text.filter(isSpoken)
        let span = (item.end - item.start) / Double(max(chars.count, 1))
        for (k, c) in chars.enumerated() {
            out.append(TimedChar(char: c, start: item.start + span * Double(k), end: item.start + span * Double(k + 1)))
        }
    }
    return out
}

/// Gives each character of `text` a time: matching characters take the aligner's time, the rest are interpolated
/// between their known neighbours. Punctuation gets nil.
func mapTimes(_ text: [Character], _ aligned: [TimedChar]) -> [(Double, Double)?] {
    let content = text.filter(isSpoken)
    guard !aligned.isEmpty, !content.isEmpty else { return Array(repeating: nil, count: text.count) }
    let skeleton = aligned.map { Character($0.char.lowercased()) }
    let target = content.map { Character($0.lowercased()) }
    // Characters the diff leaves untouched are the matches, in order on both sides.
    let diff = target.difference(from: skeleton)
    var removed = Set<Int>(), inserted = Set<Int>()
    for change in diff {
        switch change {
        case .remove(let o, _, _): removed.insert(o)
        case .insert(let o, _, _): inserted.insert(o)
        }
    }
    let kept = skeleton.indices.filter { !removed.contains($0) }
    var times = [(Double, Double)?](repeating: nil, count: content.count)
    var k = 0
    for j in content.indices where !inserted.contains(j) {
        guard k < kept.count else { break }
        times[j] = (aligned[kept[k]].start, aligned[kept[k]].end); k += 1
    }
    // Fill the gaps: ends take the nearest known time, the middle is spread evenly between neighbours.
    let known = times.indices.filter { times[$0] != nil }
    if let first = known.first, let last = known.last {
        for i in 0..<first { times[i] = times[first] }
        for i in (last + 1)..<times.count { times[i] = times[last] }
        for (l, r) in zip(known, known.dropFirst()) where r - l > 1 {
            let a = times[l]!, b = times[r]!
            for step in 1..<(r - l) {
                let f = Double(step) / Double(r - l)
                times[l + step] = (a.0 + (b.0 - a.0) * f, a.1 + (b.1 - a.1) * f)
            }
        }
    }
    var out: [(Double, Double)?] = [], cursor = 0
    for c in text {
        if isSpoken(c) { out.append(times[cursor]); cursor += 1 } else { out.append(nil) }
    }
    return out
}

/// Splits into readable cues, as `[start, end)` character ranges:
/// 1. a sentence end always breaks;
/// 2. a comma breaks once the line is long enough (12 characters or 5 seconds)…
/// 3. …but never right after a dangling lead-in such as "第二，", which would leave the viewer hanging;
/// 4. 15 seconds without punctuation breaks anyway.
func sentenceRanges(_ text: [Character], times: [(Double, Double)?]) -> [Range<Int>] {
    func span(_ a: Int, _ b: Int) -> Double? {
        let known = times[a..<b].compactMap { $0 }
        guard let f = known.first, let l = known.last else { return nil }
        return l.1 - f.0
    }
    func tail(_ a: Int, _ end: Int) -> Int {
        var i = end - 2
        while i > a, !(isBreak(i, hardBreak) || isBreak(i, softBreak)) { i -= 1 }
        let from = i > a ? i + 1 : a
        return from < end - 1 ? text[from..<(end - 1)].filter(isSpoken).count : 0
    }
    func columns(_ a: Int, _ b: Int) -> Int { text[a..<b].reduce(0) { $0 + ($1.isASCII ? 1 : 2) } }
    func isBreak(_ i: Int, _ set: Set<Character>) -> Bool {
        let c = text[i], next = i + 1 < text.count ? text[i + 1] : " "
        // "2,500" and "3.14" are numbers, not pauses.
        if c.isASCII, i > 0, text[i - 1].isNumber, next.isNumber { return false }
        if set.contains(c) { return true }
        // A Latin full stop ends a sentence only before a space.
        return set == hardBreak && (c == "." || c == ";") && (next.isWhitespace) && i > 0 && text[i - 1].isLetter
    }
    /// A punctuation mark just ahead is a better place to cut than here; it saves an orphan like "four months."
    func nearBreak(_ from: Int) -> Bool {
        var i = from
        while i < text.count, columns(from, i) < orphanColumns {
            if isBreak(i, hardBreak) || isBreak(i, softBreak) { return true }
            i += 1
        }
        return i >= text.count
    }
    var ranges: [Range<Int>] = [], start = 0
    for (i, c) in text.enumerated() {
        let end = i + 1
        var cut = isBreak(i, hardBreak)
        if !cut, isBreak(i, softBreak) {
            let s = span(start, end)
            cut = (end - start >= softMinChars || (s ?? 0) >= softMinSeconds) && tail(start, end) >= minTailChars
        }
        // Hard limits never split a Latin word in half.
        let midWord = c.isASCII && c.isLetter && i + 1 < text.count && text[i + 1].isASCII && text[i + 1].isLetter
        if !cut, !midWord {
            let next = i + 1 < text.count ? text[i + 1] : " "
            let wordEnd = !c.isASCII || next.isWhitespace || !next.isASCII
            cut = (span(start, end) ?? 0) >= maxCueSeconds || (wordEnd && columns(start, end) >= maxCueColumns && !nearBreak(end))
        }
        if cut { ranges.append(start..<end); start = end }
    }
    if start < text.count { ranges.append(start..<text.count) }
    return ranges.filter { text[$0].contains(where: isSpoken) }
}

/// Plain sentences without times, for places that only need the words.
func sentences(_ text: String) -> [String] {
    let chars = Array(text)
    return sentenceRanges(chars, times: Array(repeating: nil, count: chars.count)).map { String(chars[$0]).trimmingCharacters(in: .whitespacesAndNewlines) }
}

struct TCue { var start: Double; var end: Double; var text: String }

/// One cue per readable sentence. Times come from the aligner wherever it matches the text;
/// with no clock at all they are spread over [from, to] by length, so nothing is lost.
func cues(for text: String, aligned: [TimedChar], from: Double, to: Double) -> [TCue] {
    let chars = Array(text)
    var times = mapTimes(chars, aligned)
    let timed = times.contains { $0 != nil }
    if !timed {
        let spoken = chars.filter(isSpoken).count
        guard spoken > 0 else { return [] }
        var n = 0
        times = chars.map { c in
            guard isSpoken(c) else { return nil }
            defer { n += 1 }
            let step = (to - from) / Double(spoken)
            return (from + step * Double(n), from + step * Double(n + 1))
        }
    }
    var out: [TCue] = [], previousEnd = from
    for range in sentenceRanges(chars, times: timed ? times : Array(repeating: nil, count: chars.count)) {
        let known = times[range].compactMap { $0 }
        guard let first = known.first, let last = known.last else { continue }
        let line = String(chars[range]).trimmingCharacters(in: .whitespacesAndNewlines)
        let start = max(previousEnd, first.0)
        let end = max(start + minCueSeconds, last.1)
        out.append(TCue(start: start, end: end, text: line))
        previousEnd = start + 0.05
    }
    // Times never go backwards: overlapping or reversed cues make players and editors drop subtitles.
    var last = 0.0
    for i in out.indices {
        out[i].start = max(out[i].start, last)
        out[i].end = max(out[i].end, out[i].start + 0.05)
        last = out[i].end
    }
    return out
}

func timestamp(_ seconds: Double) -> String {
    let ms = Int((max(0, seconds) * 1000).rounded())
    return String(format: "%02d:%02d:%02d,%03d", ms / 3_600_000, ms / 60_000 % 60, ms / 1000 % 60, ms % 1000)
}

func renderSRT(_ cues: [TCue]) -> String {
    var last = 0.0
    return cues.enumerated().map { index, cue in
        let start = max(cue.start, last)
        last = max(cue.end, start)
        return "\(index + 1)\n\(timestamp(start)) --> \(timestamp(max(cue.end, start)))\n\(wrapped(cue.text))\n"
    }.joined(separator: "\n")
}

private func wrapped(_ text: String, limit: Int = 42) -> String {
    guard text.count > limit else { return text }
    let chars = Array(text), mid = chars.count / 2
    // Break at punctuation or a space near the middle; only when there is neither, in the middle of a word.
    for distance in 0..<min(14, mid) {
        for i in [mid + distance, mid - distance] where i > 0 && i < chars.count - 1 {
            if "，,。；;、：:！？!?".contains(chars[i]) { return String(chars[...i]).trimmingCharacters(in: .whitespaces) + "\n" + String(chars[(i + 1)...]).trimmingCharacters(in: .whitespaces) }
            if chars[i] == " " { return String(chars[..<i]) + "\n" + String(chars[(i + 1)...]) }
        }
    }
    return String(chars[..<mid]) + "\n" + String(chars[mid...])
}

// MARK: - Hot words and replacements
//
// One plain file, shared with the earlier Transcript install:
//   小新                  a hot word: passed to the recogniser and the summary, never replaced
//   ## 产品               a group heading for the hot words below it (display only)
//   乐谱 -> 悦普          a correction, applied after recognition
// `#` starts a comment, also after a space at the end of a line.

private let separators = ["->", "=>", "→", "=", "\t", "|"]

private func stripComment(_ line: String) -> String {
    let chars = Array(line)
    for i in chars.indices where chars[i] == "#" && (i == 0 || chars[i - 1].isWhitespace) { return String(chars[..<i]) }
    return line
}

struct HotWordGroup: Identifiable, Equatable { var id = UUID(); var name: String; var words: [String] }
struct Correction: Identifiable, Equatable { var id = UUID(); var wrong: String; var right: String }

struct Glossary: Equatable {
    var groups: [HotWordGroup] = []
    var corrections: [Correction] = []
    /// Plain `#` comment lines, kept so a save from Settings does not throw away someone's notes.
    var notes: [String] = []

    init() {}
    init(file: URL) { self.init(text: (try? String(contentsOf: file, encoding: .utf8)) ?? "") }

    init(text: String) {
        var current: Int?
        for raw in text.components(separatedBy: .newlines) {
            let trimmed = raw.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("## ") || trimmed.hasPrefix("##\t") {
                let name = stripComment(String(trimmed.dropFirst(3))).trimmingCharacters(in: .whitespaces)
                guard !name.isEmpty else { continue }
                if let i = groups.firstIndex(where: { $0.name == name }) { current = i } else { groups.append(.init(name: name, words: [])); current = groups.count - 1 }
                continue
            }
            if trimmed.hasPrefix("#") { notes.append(trimmed); continue }
            let line = stripComment(raw).trimmingCharacters(in: .whitespaces)
            guard !line.isEmpty else { continue }
            if let sep = separators.first(where: { line.contains($0) }) {
                let parts = line.components(separatedBy: sep)
                let wrong = parts[0].trimmingCharacters(in: .whitespaces), right = parts.dropFirst().joined(separator: sep).trimmingCharacters(in: .whitespaces)
                if !wrong.isEmpty, !right.isEmpty, wrong != right, !corrections.contains(where: { $0.wrong == wrong }) { corrections.append(.init(wrong: wrong, right: right)) }
            } else {
                if current == nil {
                    if let i = groups.firstIndex(where: { $0.name.isEmpty }) { current = i } else { groups.insert(.init(name: "", words: []), at: 0); current = 0 }
                }
                if !groups[current!].words.contains(line) { groups[current!].words.append(line) }
            }
        }
    }

    /// Every correct spelling the recogniser and the summary should know: hot words plus the right side of corrections.
    var hotwords: [String] {
        hotwords(in: Set(groups.map(\.name)))
    }

    /// Returns only the selected groups, while keeping correction targets global.
    /// Group names are used as stable identifiers because the glossary is a text file.
    func hotwords(in selectedGroups: Set<String>) -> [String] {
        var out: [String] = []
        let selected = groups.filter { selectedGroups.contains($0.name) }
        for w in selected.flatMap(\.words) + corrections.map(\.right) where !w.isEmpty && !out.contains(w) {
            out.append(w)
        }
        return Array(out.prefix(80))
    }

    var text: String {
        var lines = notes
        for group in groups {
            let words = group.words.map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
            if !lines.isEmpty { lines.append("") }
            if !group.name.isEmpty { lines.append("## " + group.name) }
            lines += words
        }
        let rules = corrections.filter { !$0.wrong.isEmpty && !$0.right.isEmpty }
        if !rules.isEmpty { if !lines.isEmpty { lines.append("") }; lines += rules.map { "\($0.wrong) -> \($0.right)" } }
        return lines.joined(separator: "\n") + "\n"
    }

    /// Longest wrong spelling first, so "O I D C" is not half-replaced by a shorter rule.
    func apply(_ text: String) -> String {
        corrections.sorted { $0.wrong.count > $1.wrong.count }.reduce(text) { $0.replacingOccurrences(of: $1.wrong, with: $1.right) }
    }

    static func == (a: Glossary, b: Glossary) -> Bool { a.text == b.text }
}
