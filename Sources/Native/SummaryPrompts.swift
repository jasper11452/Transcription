import Foundation

/// Named summary prompts. The built-in "默认" profile can be edited and reset, but never deleted.
struct SummaryPrompts: Equatable {
    struct Profile: Codable, Equatable { var name: String; var prompt: String }
    static let defaultName = "默认"
    static let migratedName = "我的提示词"

    private(set) var selected = SummaryPrompts.defaultName
    private(set) var profiles: [Profile] = []
    private let defaultPrompt: String

    init(defaultPrompt: String) {
        self.defaultPrompt = defaultPrompt
        profiles = [Profile(name: Self.defaultName, prompt: defaultPrompt)]
    }

    var names: [String] { profiles.map(\.name) }
    var current: Profile { profiles.first { $0.name == selected } ?? profiles[0] }
    func prompt(named name: String) -> String? { profiles.first { $0.name == name }?.prompt }

    // MARK: Editing

    mutating func select(_ name: String) { if names.contains(name) { selected = name } }

    /// Stores `prompt` into the named profile; an empty prompt falls back to the built-in text.
    mutating func update(_ name: String, prompt: String) {
        guard let i = profiles.firstIndex(where: { $0.name == name }) else { return }
        let text = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        profiles[i].prompt = text.isEmpty ? defaultPrompt : prompt
    }

    /// Adds and selects a profile. Fails on an empty or duplicate name.
    @discardableResult mutating func add(_ name: String, prompt: String) -> Bool {
        let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty, !names.contains(name) else { return false }
        profiles.append(Profile(name: name, prompt: prompt)); selected = name
        return true
    }

    /// A free name like "方案 2".
    func freshName() -> String {
        var n = 2
        while names.contains("方案 \(n)") { n += 1 }
        return "方案 \(n)"
    }

    @discardableResult mutating func rename(_ old: String, to new: String) -> Bool {
        let new = new.trimmingCharacters(in: .whitespacesAndNewlines)
        guard old != Self.defaultName, !new.isEmpty, !names.contains(new),
              let i = profiles.firstIndex(where: { $0.name == old }) else { return false }
        profiles[i].name = new
        if selected == old { selected = new }
        return true
    }

    @discardableResult mutating func delete(_ name: String) -> Bool {
        guard name != Self.defaultName, let i = profiles.firstIndex(where: { $0.name == name }) else { return false }
        profiles.remove(at: i)
        if selected == name { selected = Self.defaultName }
        return true
    }

    mutating func resetDefault() { update(Self.defaultName, prompt: defaultPrompt) }

    // MARK: Persistence: `{ "selected": …, "profiles": [{ "name", "prompt" }] }`

    private struct Stored: Codable { var selected: String; var profiles: [Profile] }

    func save(to file: URL) {
        try? FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        if let data = try? encoder.encode(Stored(selected: selected, profiles: profiles)) { try? data.write(to: file, options: .atomic) }
    }

    /// Reads `file`. Without a usable file, imports a custom legacy `summary-prompt.txt` as "我的提示词" (the legacy file is left in place).
    static func load(file: URL, legacy: URL, defaultPrompt: String) -> SummaryPrompts {
        var result = SummaryPrompts(defaultPrompt: defaultPrompt)
        if let data = try? Data(contentsOf: file), let stored = try? JSONDecoder().decode(Stored.self, from: data) {
            for p in stored.profiles where !p.name.isEmpty {
                if let i = result.profiles.firstIndex(where: { $0.name == p.name }) { result.profiles[i].prompt = p.prompt }
                else { result.profiles.append(p) }
            }
            result.select(stored.selected)
            return result
        }
        let custom = ((try? String(contentsOf: legacy, encoding: .utf8)) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if !custom.isEmpty, custom != defaultPrompt.trimmingCharacters(in: .whitespacesAndNewlines) {
            result.add(migratedName, prompt: custom)
            result.save(to: file)
        }
        return result
    }
}
