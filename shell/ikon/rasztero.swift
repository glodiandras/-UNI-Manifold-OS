// SVG → átlátszó hátterű PNG (AppKit/CoreSVG; hálózat és külső eszköz nélkül). Használat: rasztero <be.svg> <ki.png> <px>
// A qlmanage nem jó: az SVG-t fehér, nem átlátszó háttérre rendereli, így a macOS-rács lekerekített sarkai fehérek lennének.
import AppKit

let arg = CommandLine.arguments
guard arg.count == 4, let px = Int(arg[3]), px > 0 else {
    FileHandle.standardError.write(Data("használat: rasztero <be.svg> <ki.png> <px>\n".utf8))
    exit(2)
}
guard let kep = NSImage(contentsOfFile: arg[1]) else {
    FileHandle.standardError.write(Data("nem olvasható SVG: \(arg[1])\n".utf8))
    exit(1)
}
guard let rep = NSBitmapImageRep(
    bitmapDataPlanes: nil, pixelsWide: px, pixelsHigh: px, bitsPerSample: 8, samplesPerPixel: 4,
    hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 32
) else { exit(1) }
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
NSGraphicsContext.current?.imageInterpolation = .high
NSColor.clear.set()
NSRect(x: 0, y: 0, width: px, height: px).fill(using: .copy)
kep.draw(in: NSRect(x: 0, y: 0, width: px, height: px), from: .zero, operation: .sourceOver, fraction: 1)
NSGraphicsContext.restoreGraphicsState()
guard let png = rep.representation(using: .png, properties: [:]) else { exit(1) }
try png.write(to: URL(fileURLWithPath: arg[2]))
