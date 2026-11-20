import Foundation

/// Reasoning settings are keyed by endpoint and model so changing a model never
/// silently reuses a budget selected for another model.
enum LLMReasoning {
    struct Option: Identifiable, Hashable {
        let id: String
        let title: String
        var isDefault: Bool { id.isEmpty }
    }

    static let all: [Option] = [
        Option(id: "", title: "服务默认"),
        Option(id: "minimal", title: "极少"),
        Option(id: "low", title: "低"),
        Option(id: "medium", title: "中"),
        Option(id: "high", title: "高"),
        Option(id: "xhigh", title: "极高")
    ]

    static func options(model: String, supportsReasoning: Bool = true) -> [Option] {
        guard supportsReasoning else { return [all[0]] }
        if model.lowercased().contains("glm-5.3") {
            return [all[0], all[2], all[4], Option(id: "max", title: "最大")]
        }
        return all
    }

    private static func key(base: String, model: String) -> String {
        "llmReasoning:" + base.trimmingCharacters(in: CharacterSet(charactersIn: "/ ")) + ":" + model
    }

    static func read(base: String, model: String) -> String {
        guard let values = UserDefaults.standard.dictionary(forKey: "llmReasoningByModel") as? [String: String] else { return "" }
        return values[key(base: base, model: model)] ?? ""
    }

    static func save(_ effort: String, base: String, model: String) {
        var values = UserDefaults.standard.dictionary(forKey: "llmReasoningByModel") as? [String: String] ?? [:]
        let key = key(base: base, model: model)
        if effort.isEmpty { values.removeValue(forKey: key) } else { values[key] = effort }
        UserDefaults.standard.set(values, forKey: "llmReasoningByModel")
    }

    static func requestValue(base: String, model: String) -> String? {
        let value = read(base: base, model: model)
        return value.isEmpty ? nil : value
    }
}
