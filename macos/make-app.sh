#!/bin/bash
# 生成可双击的「Speak Drill.app」：没在跑就后台起服务，然后打开网页。
# 用法：macos/make-app.sh [安装目录，默认 ~/Applications]
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$HOME/Applications}"
APP="$DEST/Speak Drill.app"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
PORT=8765

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Speak Drill</string>
  <key>CFBundleIdentifier</key><string>local.speak-drill</string>
  <key>CFBundleExecutable</key><string>launcher</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSUIElement</key><true/>
</dict></plist>
PLIST

# Finder 启动的进程 PATH 很短，ffmpeg（homebrew）和 uv 都要显式给
cat > "$APP/Contents/MacOS/launcher" <<LAUNCHER
#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:\$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export no_proxy="localhost,127.0.0.1,::1" NO_PROXY="localhost,127.0.0.1,::1"
URL="http://127.0.0.1:$PORT/"
LOG="\$HOME/Library/Logs/speak-drill.log"

if ! curl -s --noproxy '*' -m 1 -o /dev/null "\${URL}api/drills"; then
  nohup "$UV" run --project "$PROJECT" speak-drill gui --no-browser --port $PORT >>"\$LOG" 2>&1 &
  for _ in \$(seq 1 60); do
    curl -s --noproxy '*' -m 1 -o /dev/null "\${URL}api/drills" && break
    sleep 0.5
  done
fi
open "\$URL"
LAUNCHER
chmod +x "$APP/Contents/MacOS/launcher"

# 图标：macos/icon.png 转成 icns（没有就用系统默认图标）
ICON_SRC="$PROJECT/macos/icon.png"
if [ -f "$ICON_SRC" ]; then
  ICONSET="$(mktemp -d)/icon.iconset"; mkdir -p "$ICONSET"
  for s in 16 32 128 256 512; do
    sips -z $s $s "$ICON_SRC" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
    sips -z $((s*2)) $((s*2)) "$ICON_SRC" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/icon.icns" || true
fi

touch "$APP"
echo "已生成：$APP"
