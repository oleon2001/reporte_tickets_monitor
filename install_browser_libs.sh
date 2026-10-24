#!/bin/bash
LIBS=/home/aplicaciones/reporte_tickets_monitor/libs
LIBDIR=$LIBS/usr/lib/x86_64-linux-gnu
cd /tmp/deblibs || exit 1

# Faltantes por índice desactualizado: tomarlos del pool
NSS=$(curl -s http://deb.debian.org/debian/pool/main/n/nss/ | grep -oE 'libnss3_[0-9][^"]+_amd64.deb' | sort -V | tail -1)
[ -n "$NSS" ] && curl -sS -O "http://deb.debian.org/debian/pool/main/n/nss/$NSS" && echo "OK $NSS"
GBM=$(curl -s http://deb.debian.org/debian/pool/main/m/mesa/ | grep -oE 'libgbm1_[0-9][^"]+_amd64.deb' | sort -V | tail -1)
[ -n "$GBM" ] && curl -sS -O "http://deb.debian.org/debian/pool/main/m/mesa/$GBM" && echo "OK $GBM"
XR=$(curl -s http://deb.debian.org/debian/pool/main/libx/libxrender/ | grep -oE 'libxrender1_[0-9][^"]+_amd64.deb' | sort -V | tail -1)
[ -n "$XR" ] && curl -sS -O "http://deb.debian.org/debian/pool/main/libx/libxrender/$XR" && echo "OK $XR"
XI=$(curl -s http://deb.debian.org/debian/pool/main/libx/libxi/ | grep -oE 'libxi6_[0-9][^"]+_amd64.deb' | sort -V | tail -1)
[ -n "$XI" ] && curl -sS -O "http://deb.debian.org/debian/pool/main/libx/libxi/$XI" && echo "OK $XI"

# Extraer todo (sin root)
rm -rf "$LIBS"
mkdir -p "$LIBS"
for f in *.deb; do dpkg-deb -x "$f" "$LIBS"; done
echo "--- extraidas: $(ls -1 *.deb | wc -l) ---"

BIN=$(find /home/aplicaciones/.cache/ms-playwright -name chrome-headless-shell | head -1)
echo "BIN=$BIN"
echo "--- ldd faltantes con LD_LIBRARY_PATH ---"
LD_LIBRARY_PATH="$LIBDIR" ldd "$BIN" | grep "not found" || echo NONE_MISSING
