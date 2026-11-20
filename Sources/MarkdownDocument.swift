import Foundation

/// Foundation parses CommonMark structure; the view supplies the reading styles.
/// Keeping block structure separate makes all heading and list levels testable.
struct MarkdownDocument {
    enum Kind: Equatable { case heading(Int), paragraph, code, rule, table }
    enum Marker: Equatable { case bullet, number(Int), task(Bool), continuation }
    struct ListItem: Equatable { var depth: Int; var marker: Marker }
    struct TableRow { var header: Bool; var cells: [AttributedString] }
    struct Block: Identifiable {
        let id: Int
        var kind: Kind
        var text: AttributedString
        var list: ListItem?
        var quoteDepth = 0
        var rows: [TableRow] = []
        var columns: [PresentationIntent.TableColumn] = []

        var isLabel: Bool {
            let meaningful = text.runs.filter { !String(text[$0.range].characters).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            return !meaningful.isEmpty && meaningful.allSatisfy { $0.inlinePresentationIntent?.contains(.stronglyEmphasized) == true }
        }
    }
    let blocks: [Block]

    init(_ source: String) {
        guard let parsed = try? AttributedString(markdown: source) else {
            blocks = [Block(id: 0, kind: .paragraph, text: AttributedString(source))]
            return
        }
        struct Leaf { let intent: PresentationIntent; var text: AttributedString }
        var leaves: [Leaf] = []
        for run in parsed.runs {
            guard let intent = run.presentationIntent else { continue }
            var text = AttributedString(parsed[run.range])
            if run.inlinePresentationIntent?.contains(.softBreak) == true { text = AttributedString("\n") }
            if leaves.last?.intent == intent { leaves[leaves.count - 1].text.append(text) }
            else { leaves.append(Leaf(intent: intent, text: text)) }
        }
        var result: [Block] = [], seenItems = Set<Int>()
        var lastTableRow: Int?
        for leaf in leaves {
            let components = leaf.intent.components
            guard let first = components.first else { continue }
            var block = Block(id: first.identity, kind: .paragraph, text: leaf.text)
            var ordinal: Int?, itemID: Int?, ordered: Bool?, listDepth = 0
            var tableID: Int?, rowID: Int?, cellColumn: Int?, header = false
            for component in components {
                switch component.kind {
                case .header(let level): block.kind = .heading(level)
                case .codeBlock: block.kind = .code
                case .thematicBreak: block.kind = .rule
                case .blockQuote: block.quoteDepth += 1
                case .listItem(let value):
                    if itemID == nil { itemID = component.identity; ordinal = value }
                case .orderedList:
                    listDepth += 1
                    if ordered == nil { ordered = true }
                case .unorderedList:
                    listDepth += 1
                    if ordered == nil { ordered = false }
                case .table(let columns): tableID = component.identity; block.columns = columns
                case .tableHeaderRow: rowID = component.identity; header = true
                case .tableRow: rowID = component.identity
                case .tableCell(let column): cellColumn = column
                default: break
                }
            }
            if let tableID, let rowID {
                if result.last?.id != tableID {
                    result.append(Block(id: tableID, kind: .table, text: AttributedString(), columns: block.columns))
                }
                let tableIndex = result.count - 1
                // Row identities stay stable throughout a single parse.
                if lastTableRow != rowID || result[tableIndex].rows.isEmpty {
                    result[tableIndex].rows.append(TableRow(header: header, cells: []))
                }
                let rowIndex = result[tableIndex].rows.count - 1
                let column = cellColumn ?? result[tableIndex].rows[rowIndex].cells.count
                while result[tableIndex].rows[rowIndex].cells.count <= column {
                    result[tableIndex].rows[rowIndex].cells.append(AttributedString())
                }
                result[tableIndex].rows[rowIndex].cells[column] = block.text
                lastTableRow = rowID
                continue
            }
            if let itemID {
                var marker: Marker = ordered == true ? .number(ordinal ?? 1) : .bullet
                if !seenItems.insert(itemID).inserted { marker = .continuation }
                else {
                    let plain = String(block.text.characters)
                    if plain.hasPrefix("[ ] ") || plain.lowercased().hasPrefix("[x] ") {
                        marker = .task(plain.lowercased().hasPrefix("[x] "))
                        let end = block.text.characters.index(block.text.startIndex, offsetBy: 4)
                        block.text = AttributedString(block.text[end...])
                    }
                }
                block.list = ListItem(depth: max(0, listDepth - 1), marker: marker)
            }
            result.append(block)
        }
        blocks = result
    }
}
