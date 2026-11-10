#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
project_dir=$PWD
if [ -f build/linux/.qmodem-checkpoint ]; then
    echo 'The kernel output contains a diagnostic checkpoint. Rebuild with scripts/build-kernel.sh before packing the rescue image.' >&2
    exit 1
fi
root=$project_dir/build/rootfs
mkdir -p "$root"/{bin,sbin,usr/bin,usr/sbin,proc,sys,dev,etc,root/.ssh,tmp,run}
make -C src/busybox-1.37.0 O="$project_dir/build/busybox" CROSS_COMPILE=aarch64-linux-gnu- CONFIG_PREFIX="$root" install
cp build/dropbear/dropbear "$root/sbin/"
cp scripts/rescue-init "$root/init"
chmod 755 "$root/init"
echo 'root:x:0:0:root:/root:/bin/sh' > "$root/etc/passwd"
echo 'root:*:19000:0:99999:7:::' > "$root/etc/shadow"
echo 'root:x:0:' > "$root/etc/group"
echo /bin/sh > "$root/etc/shells"
if [ -n "${QMODEM_AUTHORIZED_KEYS:-}" ]; then
    ssh-keygen -lf "$QMODEM_AUTHORIZED_KEYS" >/dev/null
    cp "$QMODEM_AUTHORIZED_KEYS" "$root/root/.ssh/authorized_keys"
else
    if [ ! -f build/rescue_ed25519 ]; then
        ssh-keygen -q -t ed25519 -N '' -f build/rescue_ed25519 -C qmodem-rescue
    fi
    cp build/rescue_ed25519.pub "$root/root/.ssh/authorized_keys"
fi
chmod 700 "$root/root" "$root/root/.ssh"
chmod 600 "$root/root/.ssh/authorized_keys" "$root/etc/shadow"
(cd "$root"; find . -print0 | cpio --null -o --format=newc --owner=0:0 2>/dev/null | gzip -9) > images/initramfs.cpio.gz
python3 scripts/mkbootimg.py --kernel build/linux/arch/arm64/boot/Image.gz --dtb build/linux/arch/arm64/boot/dts/qcom/msm8916-qmodem-rescue.dtb --ramdisk images/initramfs.cpio.gz --output images/ufi103s-rescue.img
sha256sum images/ufi103s-rescue.img > images/SHA256SUMS
