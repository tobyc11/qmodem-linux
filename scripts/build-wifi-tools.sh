#!/bin/bash
# Build pinned ARM64 iw/libnl in this workspace. No root or device access.
set -euo pipefail
cd "$(dirname "$0")/.."
project=$PWD
python3 - <<'PY'
import json,subprocess
from pathlib import Path
sources=json.load(open('configs/wifi-sources.json'))
for name,directory in [('libnl','libnl-wifi'),('iw','iw-wifi'),('regdb','wireless-regdb-wifi')]:
    source=sources[name]; path=Path('src')/directory
    if not path.exists():
        subprocess.run(['git','clone','--no-checkout',source['url'],str(path)],check=True)
        subprocess.run(['git','-C',str(path),'checkout','--detach',source['commit']],check=True)
    actual=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
    if actual!=source['commit']:raise SystemExit('Unexpected source revision: '+name)
PY
if git -C src/libnl-wifi apply --reverse --check "$project/configs/libnl-time-header.patch" 2>/dev/null; then
    : # The required explicit time.h include is already applied.
else
    git -C src/libnl-wifi apply --check "$project/configs/libnl-time-header.patch"
    git -C src/libnl-wifi apply "$project/configs/libnl-time-header.patch"
fi
(cd src/libnl-wifi; autoreconf -fi)
mkdir -p build/wifi/libnl build/wifi/tools/bin
(cd build/wifi/libnl
    "$project/src/libnl-wifi/configure" --host=aarch64-linux-gnu \
        --prefix="$project/build/wifi/tools" --disable-shared --enable-static \
        --disable-cli --disable-pthreads --disable-debug
    make -j"${JOBS:-8}"
    make install)
PKG_CONFIG_LIBDIR="$project/build/wifi/tools/lib/pkgconfig" \
    make -C src/iw-wifi -j"${JOBS:-8}" CC=aarch64-linux-gnu-gcc LDFLAGS=-static
cp src/iw-wifi/iw build/wifi/tools/bin/iw
aarch64-linux-gnu-strip build/wifi/tools/bin/iw
sha256sum build/wifi/tools/bin/iw
