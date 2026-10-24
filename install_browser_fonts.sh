#!/bin/bash
P=/home/aplicaciones/reporte_tickets_monitor
mkdir -p "$P/fontconfig" "$P/fonts" "$P/fontcache"
cat > "$P/fontconfig/fonts.conf" <<'EOF'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <dir>/home/aplicaciones/reporte_tickets_monitor/fonts</dir>
  <cachedir>/home/aplicaciones/reporte_tickets_monitor/fontcache</cachedir>
</fontconfig>
EOF
cp "$P"/venv/lib/python3.11/site-packages/matplotlib/mpl-data/fonts/ttf/*.ttf "$P/fonts/" 2>/dev/null
echo "fuentes: $(ls -1 "$P/fonts" | wc -l)"

BIN=$(find /home/aplicaciones/.cache/ms-playwright -name chrome-headless-shell | head -1)
L="$P/libs/usr/lib/x86_64-linux-gnu"
echo "--- chrome con FONTCONFIG_FILE ---"
FONTCONFIG_FILE="$P/fontconfig/fonts.conf" LD_LIBRARY_PATH="$L" "$BIN" \
  --no-sandbox --headless --disable-gpu --virtual-time-budget=8000 \
  --dump-dom http://10.48.12.77:3500/sv 2>&1 | tail -6
