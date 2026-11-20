import AppKit
import SwiftUI

/// Semantic Markdown, with explicit heading and list hierarchy in both appearances.
struct MarkdownView: View {
    let source: String
    var onSeek: ((Double) -> Void)? = nil
    @StateObject private var cache = MarkdownCache()
    private typealias Block = MarkdownDocument.Block

    private enum Ink {
        static let teal = Color(nsColor: NSColor(name: nil) { appearance in
            appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
                ? NSColor(red: 0.42, green: 0.79, blue: 0.76, alpha: 1)
                : NSColor(red: 0.10, green: 0.42, blue: 0.40, alpha: 1)
        })
        static let completed = Color(nsColor: NSColor(name: nil) { appearance in
            appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
                ? NSColor(red: 0.48, green: 0.80, blue: 0.58, alpha: 1)
                : NSColor(red: 0.15, green: 0.45, blue: 0.25, alpha: 1)
        })
    }

    private func inline(_ source: AttributedString, size: CGFloat = 16) -> Text {
        var text = source
        for run in source.runs where run.inlinePresentationIntent?.contains(.code) == true {
            text[run.range].font = .system(size: size * 0.9, design: .monospaced)
            text[run.range].foregroundColor = Ink.teal
            text[run.range].backgroundColor = Color.primary.opacity(0.06)
        }
        return Text(text)
    }

    private func stamped(_ text: AttributedString) -> (Double, AttributedString)? {
        let plain = String(text.characters)
        guard let range = plain.range(of: #"^\[(\d{1,2}:)?\d{1,2}:\d{2}\]\s*"#, options: .regularExpression) else { return nil }
        let parts = plain[range].trimmingCharacters(in: CharacterSet(charactersIn: "[] \n")).split(separator: ":").compactMap { Double($0) }
        let end = text.characters.index(text.startIndex, offsetBy: plain.distance(from: plain.startIndex, to: range.upperBound))
        return (parts.reduce(0) { $0 * 60 + $1 }, AttributedString(text[end...]))
    }

    @ViewBuilder private func paragraph(_ text: AttributedString) -> some View {
        if let (time, rest) = stamped(text) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                if let onSeek {
                    Button { onSeek(time) } label: { Text(clock(time)).monospacedDigit() }
                        .buttonStyle(.plain).font(.system(size: 13, weight: .medium)).foregroundStyle(Brand.accent)
                        .accessibilityLabel("跳到 \(clock(time))")
                } else {
                    Text(clock(time)).font(.system(size: 13, weight: .medium)).monospacedDigit().foregroundStyle(.secondary)
                }
                inline(rest)
            }
        } else { inline(text) }
    }

    private func headingSize(_ level: Int) -> CGFloat {
        switch level { case 1: return 28; case 2: return 23; case 3: return 20; case 4: return 18; case 5: return 16; default: return 15 }
    }

    private func headingColor(_ level: Int) -> Color {
        switch level { case 2: return Brand.accent; case 3: return Ink.teal; case 6: return .primary.opacity(0.7); default: return .primary }
    }

    private func heading(_ block: Block, level: Int) -> some View {
        inline(block.text, size: headingSize(level))
            .font(.system(size: headingSize(level), weight: level == 1 ? .bold : .semibold))
            .foregroundStyle(headingColor(level))
            .lineSpacing(level < 3 ? 3 : 4)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.bottom, level == 1 ? 10 : 0)
            .overlay(alignment: .bottomLeading) {
                if level == 1 { RoundedRectangle(cornerRadius: 1).fill(Brand.accent.opacity(0.65)).frame(width: 28, height: 3) }
            }
            .accessibilityAddTraits(.isHeader)
    }

    @ViewBuilder private func marker(_ item: MarkdownDocument.ListItem) -> some View {
        switch item.marker {
        case .task(let done):
            Image(systemName: done ? "checkmark.square.fill" : "square")
                .font(.system(size: 14)).foregroundStyle(done ? Ink.completed : Brand.accent)
                .accessibilityLabel(done ? "已完成" : "未完成")
        case .number(let number):
            Text("\(number).")
                .font(.system(size: 14, weight: .medium)).monospacedDigit()
                .foregroundStyle(item.depth == 0 ? Brand.accent : Ink.teal)
        case .bullet:
            if item.depth == 0 {
                Circle().fill(Brand.accent).frame(width: 6, height: 6)
            } else if item.depth == 1 {
                Circle().strokeBorder(Ink.teal, lineWidth: 1.3).frame(width: 6, height: 6)
            } else {
                RoundedRectangle(cornerRadius: 1).fill(Color.secondary).frame(width: 4, height: 4)
            }
        case .continuation: Color.clear.frame(width: 6, height: 6)
        }
    }

    @ViewBuilder private func content(_ block: Block) -> some View {
        switch block.kind {
        case .heading(let level): heading(block, level: level)
        case .code:
            ScrollView(.horizontal) {
                Text(String(block.text.characters).replacingOccurrences(of: #"\n$"#, with: "", options: .regularExpression))
                    .font(.system(size: 13, design: .monospaced)).lineSpacing(5)
                    .padding(14).frame(maxWidth: .infinity, alignment: .leading)
            }
            .background(RoundedRectangle(cornerRadius: 8).fill(Color.primary.opacity(0.045)))
            .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Color.primary.opacity(0.07)))
        case .rule: Divider().padding(.vertical, 4)
        case .table: table(block)
        case .paragraph:
            paragraph(block.text)
                .font(.system(size: block.list?.depth == 0 && block.isLabel ? 17 : 16))
                .foregroundStyle(block.isLabel && block.list != nil ? (block.list?.depth == 0 ? Brand.accent : Ink.teal) : Color.primary)
                .lineSpacing(6)
        }
    }

    private func row(_ block: Block) -> some View {
        HStack(alignment: .top, spacing: 0) {
            ForEach(0..<block.quoteDepth, id: \.self) { _ in
                RoundedRectangle(cornerRadius: 1).fill(Ink.teal.opacity(0.45)).frame(width: 2)
                    .padding(.trailing, 14)
            }
            if let item = block.list {
                ForEach(0..<item.depth, id: \.self) { _ in
                    Rectangle().fill(Brand.accent.opacity(0.14)).frame(width: 1).frame(width: 22)
                }
                marker(item)
                    .frame(width: 22, height: 25, alignment: .center)
                    .padding(.trailing, 5)
            }
            content(block).frame(maxWidth: .infinity, alignment: .leading)
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    private func table(_ block: Block) -> some View {
        ScrollView(.horizontal) {
            Grid(alignment: .leading, horizontalSpacing: 0, verticalSpacing: 0) {
                ForEach(block.rows.indices, id: \.self) { row in
                    GridRow(alignment: .top) {
                        ForEach(block.columns.indices, id: \.self) { column in
                            let cells = block.rows[row].cells
                            inline(column < cells.count ? cells[column] : AttributedString(), size: 15)
                                .font(.system(size: 15, weight: block.rows[row].header ? .semibold : .regular))
                                .foregroundStyle(block.rows[row].header ? Brand.accent : Color.primary)
                                .lineSpacing(5)
                                .frame(minWidth: 120, maxWidth: 240, alignment: tableAlignment(block, column: column))
                                .padding(.horizontal, 14).padding(.vertical, 10)
                                .background(block.rows[row].header ? Brand.accent.opacity(0.07) : Color.primary.opacity(row.isMultiple(of: 2) ? 0.025 : 0))
                                .overlay(alignment: .bottom) { Color.primary.opacity(0.07).frame(height: 1) }
                        }
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Color.primary.opacity(0.09)))
        }
    }

    private func tableAlignment(_ block: Block, column: Int) -> Alignment {
        switch block.columns[column].alignment { case .center: return .center; case .right: return .trailing; default: return .leading }
    }

    private func spacing(before block: Block, previous: Block?) -> CGFloat {
        guard let previous else { return 0 }
        if case .heading(let level) = block.kind { return level == 1 ? 34 : level == 2 ? 26 : 20 }
        if case .heading = previous.kind { return 12 }
        if let item = block.list, let last = previous.list {
            if item.depth < last.depth { return item.depth == 0 ? 16 : 10 }
            return 7
        }
        return 16
    }

    var body: some View {
        let blocks = cache.blocks(for: source)
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(blocks.enumerated()), id: \.element.id) { index, block in
                row(block).padding(.top, spacing(before: block, previous: index > 0 ? blocks[index - 1] : nil))
            }
        }
        .font(.system(size: 16)).tint(Brand.accent)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// Player updates should not parse an unchanged summary again.
private final class MarkdownCache: ObservableObject {
    private var source: String?
    private var parsed: [MarkdownDocument.Block] = []
    func blocks(for source: String) -> [MarkdownDocument.Block] {
        if self.source != source { self.source = source; parsed = MarkdownDocument(source).blocks }
        return parsed
    }
}

/// Each received snapshot is visible immediately; no task captures an older snapshot.
struct StreamingMarkdown: View {
    let source: String
    let live: Bool
    var onSeek: ((Double) -> Void)? = nil

    var body: some View {
        MarkdownView(source: source, onSeek: onSeek)
    }
}
