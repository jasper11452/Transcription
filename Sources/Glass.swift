import SwiftUI

/// Liquid Glass on macOS 26 and later; a quiet translucent fill before that.
/// Glass belongs to the control layer (buttons, the player, the composer bar), never to text the person reads.
extension View {
    @ViewBuilder func glassCapsule(tint: Color? = nil) -> some View {
        if #available(macOS 26.0, *) {
            if let tint { self.glassEffect(.regular.tint(tint).interactive(), in: .capsule) }
            else { self.glassEffect(.regular.interactive(), in: .capsule) }
        } else {
            self.background(Capsule().fill(tint ?? Color.primary.opacity(0.07)))
        }
    }

    @ViewBuilder func glassPanel(radius: CGFloat = 22) -> some View {
        if #available(macOS 26.0, *) {
            self.glassEffect(.regular, in: .rect(cornerRadius: radius))
        } else {
            self.background(.regularMaterial, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
        }
    }

    /// The system glass button: `.glass` for secondary actions, `.glassProminent` (accent) for the one primary action.
    @ViewBuilder func glassButton(prominent: Bool = false) -> some View {
        if #available(macOS 26.0, *) {
            if prominent { self.buttonStyle(.glassProminent).tint(Brand.accent) } else { self.buttonStyle(.glass) }
        } else {
            if prominent { self.buttonStyle(.borderedProminent).tint(Brand.accent) } else { self.buttonStyle(.bordered) }
        }
    }

    /// Groups neighbouring glass shapes so they sample the backdrop once and morph into each other.
    @ViewBuilder func glassGroup(spacing: CGFloat = 12) -> some View {
        if #available(macOS 26.0, *) { GlassEffectContainer(spacing: spacing) { self } } else { self }
    }
}
