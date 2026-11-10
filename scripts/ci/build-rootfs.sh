#!/bin/bash
# Runs as root only in an ephemeral native ARM64 builder. No modem access.
set -euo pipefail
[[ $EUID == 0 && $(uname -m) == aarch64 ]] || { echo 'Requires a native ARM64 root builder' >&2; exit 1; }
cd "$(dirname "$0")/../.."
project_dir=$PWD
rootfs=$project_dir/build/ci/debian-rootfs
[[ ! -e $rootfs ]] || { echo 'Refusing an existing rootfs' >&2; exit 1; }
: "${QMODEM_ADMIN_USER:?}" "${QMODEM_AUTHORIZED_KEYS:?}" "${SOURCE_DATE_EPOCH:?}"
ssh-keygen -lf "$QMODEM_AUTHORIZED_KEYS" >/dev/null
root_partuuid=$(python3 -c 'import json; print(json.load(open("deployment/layout.json"))["partitions"]["userdata"]["partuuid"])')
export DEBIAN_FRONTEND=noninteractive
# --foreign separates extraction from package scripts so policy-rc.d is in place.
# The second stage runs natively: no QEMU or binfmt registration.
debootstrap --arch=arm64 --foreign --variant=minbase --components=main \
    --force-check-gpg --keyring=/usr/share/keyrings/debian-archive-keyring.gpg \
    --include=systemd-sysv,udev,openssh-server,sudo,iproute2,iputils-ping,ca-certificates,systemd-timesyncd,e2fsprogs,procps,dbus,libpam-systemd \
    trixie "$rootfs" https://deb.debian.org/debian
printf '#!/bin/sh\nexit 101\n' > "$rootfs/usr/sbin/policy-rc.d"
chmod 755 "$rootfs/usr/sbin/policy-rc.d"
runner=(systemd-nspawn --settings=no --register=no --resolv-conf=copy-host \
    --directory="$rootfs" --setenv=DEBIAN_FRONTEND=noninteractive)
"${runner[@]}" /debootstrap/debootstrap --second-stage
"${runner[@]}" \
    --bind-ro="$project_dir/deployment/debian-configure.sh:/qmodem-configure.sh" \
    --bind-ro="$project_dir/deployment/debian-server-configure.sh:/qmodem-server-configure.sh" \
    --bind-ro="$QMODEM_AUTHORIZED_KEYS:/run/qmodem-authorized_keys" \
    --setenv="QMODEM_ADMIN_USER=$QMODEM_ADMIN_USER" \
    --setenv="QMODEM_ROOT_PARTUUID=$root_partuuid" \
    /bin/sh -ec '/bin/sh /qmodem-configure.sh; /bin/sh /qmodem-server-configure.sh'
# Never export build-machine identities or generated server private keys.
rm -f "$rootfs"/etc/ssh/ssh_host_* "$rootfs/var/lib/systemd/random-seed"
rm -f "$rootfs/etc/machine-id" "$rootfs/etc/resolv.conf" \
    "$rootfs/qmodem-configure.sh" "$rootfs/qmodem-server-configure.sh"
truncate -s 0 "$rootfs/etc/machine-id"
install -d "$rootfs/var/lib/dbus"
ln -sfn /etc/machine-id "$rootfs/var/lib/dbus/machine-id"
printf '# Configure DNS with the eventual uplink; USB alone supplies none.\n' > "$rootfs/etc/resolv.conf"
cp "$rootfs/var/lib/qmodem/build-packages.tsv" build/ci/debian-package-list.tsv
find "$rootfs/var/lib/apt/lists" -maxdepth 1 -type f -name '*InRelease' -exec sha256sum {} \; \
    | sed "s|$rootfs||g" > build/ci/debian-inrelease.sha256
# nspawn has left and cleaned its temporary mounts before this archive is made.
tar --sort=name --numeric-owner --acls --xattrs --one-file-system \
    --mtime="@$SOURCE_DATE_EPOCH" --clamp-mtime \
    -C "$rootfs" -I 'zstd -T0 -10' -cpf build/ci/rootfs.tar.zst .
chmod 644 build/ci/rootfs.tar.zst build/ci/debian-package-list.tsv build/ci/debian-inrelease.sha256
