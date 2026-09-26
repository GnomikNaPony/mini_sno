#!/bin/zsh
set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
PYTHON="$PROJECT_DIR/.venv/bin/python"
NGROK="$(command -v ngrok || true)"
NGROK_CONFIG="$HOME/Library/Application Support/ngrok/ngrok.yml"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/Orbita"
USER_ID="$(id -u)"

[[ "$(uname -s)" == "Darwin" ]] || { echo 'Этот скрипт предназначен для macOS.' >&2; exit 1; }
[[ -x "$PYTHON" ]] || { echo 'Сначала создайте .venv и установите requirements.txt.' >&2; exit 1; }
[[ -n "$NGROK" ]] || { echo 'Установите ngrok: brew install ngrok/ngrok/ngrok' >&2; exit 1; }
[[ -f "$NGROK_CONFIG" ]] || { echo 'Настройте ngrok: ngrok config add-authtoken ВАШ_ТОКЕН' >&2; exit 1; }

mkdir -p "$AGENTS_DIR" "$LOG_DIR"

cat > "$AGENTS_DIR/com.orbita.science-newsroom.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.orbita.science-newsroom</string>
  <key>ProgramArguments</key><array>
    <string>$PYTHON</string><string>-m</string><string>uvicorn</string><string>app:app</string>
    <string>--host</string><string>127.0.0.1</string><string>--port</string><string>8000</string>
    <string>--workers</string><string>1</string><string>--no-proxy-headers</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJECT_DIR</string>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$LOG_DIR/server.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/server-error.log</string>
</dict></plist>
PLIST

cat > "$AGENTS_DIR/com.orbita.ngrok.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.orbita.ngrok</string>
  <key>ProgramArguments</key><array>
    <string>$NGROK</string><string>http</string><string>8000</string>
    <string>--config</string><string>$NGROK_CONFIG</string>
    <string>--log</string><string>$LOG_DIR/ngrok-agent.log</string>
    <string>--log-format</string><string>json</string>
  </array>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$LOG_DIR/ngrok.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/ngrok-error.log</string>
</dict></plist>
PLIST

for label in com.orbita.science-newsroom com.orbita.ngrok; do
  plist="$AGENTS_DIR/$label.plist"
  plutil -lint "$plist" >/dev/null
  if launchctl print "gui/$USER_ID/$label" >/dev/null 2>&1; then
    launchctl bootout "gui/$USER_ID/$label"
    for _ in {1..25}; do
      launchctl print "gui/$USER_ID/$label" >/dev/null 2>&1 || break
      sleep .2
    done
  fi
  launchctl bootstrap "gui/$USER_ID" "$plist"
  launchctl kickstart -k "gui/$USER_ID/$label"
done

echo 'Орбита запущена: http://127.0.0.1:8000'
for _ in {1..30}; do
  if curl -fsS --max-time 2 http://127.0.0.1:4040/api/tunnels > /tmp/orbita-tunnels.json 2>/dev/null; then
    url="$($PYTHON - <<'PY'
import json
try:
    with open('/tmp/orbita-tunnels.json') as source:
        urls = [item['public_url'] for item in json.load(source).get('tunnels', []) if item.get('proto') == 'https']
    print(urls[0] if urls else '')
except (OSError, ValueError, KeyError):
    print('')
PY
)"
    if [[ -n "$url" ]]; then
      echo "Ссылка для телефона: $url"
      exit 0
    fi
  fi
  sleep .5
done

echo "ngrok ещё запускается. Проверьте ссылку командой: curl http://127.0.0.1:4040/api/tunnels" >&2
exit 1
