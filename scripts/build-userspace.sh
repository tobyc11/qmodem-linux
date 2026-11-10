#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
project_dir=$PWD
jobs=${JOBS:-12}
mkdir -p build/busybox
make -C src/busybox-1.37.0 O="$project_dir/build/busybox" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- defconfig
sed -i 's/# CONFIG_STATIC is not set/CONFIG_STATIC=y/' build/busybox/.config
sed -i 's/^CONFIG_TC=y/# CONFIG_TC is not set/' build/busybox/.config
sed -i 's/^CONFIG_SHA1_HWACCEL=y/# CONFIG_SHA1_HWACCEL is not set/; s/^CONFIG_SHA256_HWACCEL=y/# CONFIG_SHA256_HWACCEL is not set/' build/busybox/.config
make -C src/busybox-1.37.0 O="$project_dir/build/busybox" CROSS_COMPILE=aarch64-linux-gnu- -j"$jobs"
mkdir -p build/dropbear
cd build/dropbear
cp "$project_dir/configs/dropbear-localoptions.h" localoptions.h
"$project_dir/src/dropbear-2024.86/configure" --host=aarch64-linux-gnu --disable-zlib --enable-static --disable-lastlog --disable-utmp --disable-utmpx --disable-wtmp --disable-wtmpx
make -j"$jobs" PROGRAMS=dropbear STATIC=1
