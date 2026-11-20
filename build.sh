#!/bin/bash
# Builds build/语音转写.app (native, no Python) and, with --dmg, dist/语音转写.dmg.
#   bash build.sh              app only
#   bash build.sh --install    also copy to ~/Applications
#   bash build.sh --dmg        also build the disk image
# Needs Vendor/ (bash Scripts/fetch-deps.sh) and the Metal toolchain (xcodebuild -downloadComponent MetalToolchain).
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$PROJECT_DIR/build"
APP="$BUILD_DIR/语音转写.app"
[ -d "$PROJECT_DIR/Vendor/mlx-swift" ] || { echo "缺少 Vendor：先运行 bash Scripts/fetch-deps.sh"; exit 1; }

echo "==> Swift (release)"
cd "$PROJECT_DIR"
mkdir -p "$BUILD_DIR"
set +e
swift build -c release -j 1 2>&1 | tee "$BUILD_DIR/swift-build.log"
BUILD_STATUS="${PIPESTATUS[0]}"
set -e
[ "$BUILD_STATUS" -eq 0 ] || { echo "编译失败"; exit "$BUILD_STATUS"; }
PRODUCTS="$PROJECT_DIR/.build/out/Products/Release"
[ -x "$PRODUCTS/Transcription" ] || { echo "编译失败"; exit 1; }

mkdir -p "$BUILD_DIR/AppIcon.iconset"
xcrun swift "$PROJECT_DIR/Scripts/Icon.swift" "$BUILD_DIR/icon.png"
for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$BUILD_DIR/icon.png" --out "$BUILD_DIR/AppIcon.iconset/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    sips -z "$double" "$double" "$BUILD_DIR/icon.png" --out "$BUILD_DIR/AppIcon.iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$BUILD_DIR/AppIcon.iconset" -o "$BUILD_DIR/AppIcon.icns"

echo "==> Bundle"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
# Restamp with the SDK we actually built against; the minimum system stays 14.0.
SDK_VERSION="$(xcrun --sdk macosx --show-sdk-version)"
vtool -set-build-version macos 14.0 "$SDK_VERSION" -replace -output "$APP/Contents/MacOS/Transcription" "$PRODUCTS/Transcription" 2>/dev/null
chmod 755 "$APP/Contents/MacOS/Transcription"
cp "$PROJECT_DIR/Info.plist" "$APP/Contents/Info.plist"
cp "$BUILD_DIR/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
for bundle in "$PRODUCTS"/*.bundle; do ditto "$bundle" "$APP/Contents/Resources/$(basename "$bundle")"; done
plutil -lint "$APP/Contents/Info.plist" >/dev/null

echo "==> Sign (ad-hoc)"
codesign --force --deep --sign - --timestamp=none "$APP"
codesign --verify --strict "$APP" && echo "signature ok"
echo "app: $(du -sh "$APP" | cut -f1)"

if [[ " $* " == *" --install "* ]]; then
    rm -rf "$HOME/Applications/语音转写.app"; mkdir -p "$HOME/Applications"
    ditto "$APP" "$HOME/Applications/语音转写.app"
    echo "已安装：$HOME/Applications/语音转写.app"
fi

if [[ " $* " == *" --dmg "* ]]; then
    echo "==> DMG"
    mkdir -p "$PROJECT_DIR/dist"
    STAGE="$BUILD_DIR/dmg-stage"; rm -rf "$STAGE"; mkdir -p "$STAGE"
    ditto "$APP" "$STAGE/语音转写.app"
    ln -s /Applications "$STAGE/Applications"
    cp "$PROJECT_DIR/Runtime/安装说明.txt" "$STAGE/安装说明.txt"
    rm -f "$PROJECT_DIR/dist/语音转写.dmg"
    hdiutil create -volname "语音转写" -srcfolder "$STAGE" -ov -format ULMO "$PROJECT_DIR/dist/语音转写.dmg" >/dev/null
    echo "dmg: $(du -sh "$PROJECT_DIR/dist/语音转写.dmg" | cut -f1)  → dist/语音转写.dmg"
fi
