import AppKit

// App icon: sound becomes text. Waveform bars on the left flow into text lines on the right.
// Usage: swift Icon.swift <output.png>   (1024x1024 px)
let output = CommandLine.arguments[1]
let size = 1024
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size, bitsPerSample: 8,
                           samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
                           bytesPerRow: 0, bitsPerPixel: 0)!
let ctx = NSGraphicsContext(bitmapImageRep: rep)!
NSGraphicsContext.current = ctx
let cg = ctx.cgContext
let space = CGColorSpaceCreateDeviceRGB()

// Brand indigo (light value of Brand.accent): 0.33, 0.39, 0.82
func indigo(_ k: CGFloat, _ a: CGFloat = 1) -> CGColor {
    CGColor(colorSpace: space, components: [0.33 * k, 0.39 * k, 0.82 * k, a])!
}

// Superellipse body, 824 x 824 at (100, 100)
func squircle(_ r: CGRect, n: CGFloat = 4.2) -> CGPath {
    let p = CGMutablePath()
    let steps = 360
    for i in 0...steps {
        let t = CGFloat(i) / CGFloat(steps) * 2 * .pi
        let c = cos(t), s = sin(t)
        let x = r.midX + r.width / 2 * (c < 0 ? -1 : 1) * pow(abs(c), 2 / n)
        let y = r.midY + r.height / 2 * (s < 0 ? -1 : 1) * pow(abs(s), 2 / n)
        i == 0 ? p.move(to: CGPoint(x: x, y: y)) : p.addLine(to: CGPoint(x: x, y: y))
    }
    p.closeSubpath()
    return p
}
let body = CGRect(x: 100, y: 100, width: 824, height: 824)
let shape = squircle(body)

// Soft drop shadow
cg.saveGState()
cg.setShadow(offset: CGSize(width: 0, height: -14), blur: 28, color: CGColor(gray: 0, alpha: 0.28))
cg.setFillColor(indigo(0.8))
cg.addPath(shape); cg.fillPath()
cg.restoreGState()

// Body gradient + top highlight, clipped to the shape
cg.saveGState()
cg.addPath(shape); cg.clip()
let grad = CGGradient(colorsSpace: space, colors: [indigo(1.30), indigo(0.80)] as CFArray, locations: [0, 1])!
cg.drawLinearGradient(grad, start: CGPoint(x: 512, y: 924), end: CGPoint(x: 512, y: 100), options: [])
let glow = CGGradient(colorsSpace: space,
                      colors: [CGColor(gray: 1, alpha: 0.22), CGColor(gray: 1, alpha: 0)] as CFArray, locations: [0, 1])!
cg.drawRadialGradient(glow, startCenter: CGPoint(x: 512, y: 960), startRadius: 0,
                      endCenter: CGPoint(x: 512, y: 960), endRadius: 520, options: [])
cg.restoreGState()
// Inner top rim light
cg.saveGState()
cg.addPath(shape); cg.clip()
cg.setStrokeColor(CGColor(gray: 1, alpha: 0.28))
cg.setLineWidth(3)
cg.addPath(squircle(body.insetBy(dx: 1.5, dy: 1.5))); cg.strokePath()
cg.restoreGState()

// Foreground: three waveform bars -> three text lines
func capsule(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat, alpha: CGFloat) {
    let r = CGRect(x: x, y: y, width: w, height: h)
    cg.saveGState()
    cg.setShadow(offset: CGSize(width: 0, height: -6), blur: 12, color: CGColor(gray: 0, alpha: 0.18))
    cg.setFillColor(CGColor(gray: 1, alpha: alpha))
    cg.addPath(CGPath(roundedRect: r, cornerWidth: min(w, h) / 2, cornerHeight: min(w, h) / 2, transform: nil))
    cg.fillPath()
    cg.restoreGState()
}
let t: CGFloat = 60  // stroke thickness
let dx: CGFloat = 13  // optical centering of the whole group
for (x, h) in [(CGFloat(262), CGFloat(170)), (344, 330), (426, 230)] {
    capsule(x + dx, 512 - h / 2, t, h, alpha: 0.97)
}
for (y, w, a) in [(CGFloat(594), CGFloat(210), CGFloat(0.97)), (482, 210, 0.72), (370, 130, 0.46)] {
    capsule(526 + dx, y, w, t, alpha: a)
}
NSGraphicsContext.current = nil
try rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: output))
