#!/bin/sh
# Native/chroot-only image provisioning; receives an authorized PUBLIC key.
set -eu
test "$(dpkg --print-architecture)" = arm64
: "${QMODEM_ADMIN_USER:?}" "${QMODEM_ROOT_PARTUUID:?}"
case "$QMODEM_ADMIN_USER" in ''|*[!a-z0-9_-]*|root) exit 1;; esac
if getent passwd "$QMODEM_ADMIN_USER" >/dev/null; then echo 'Account already exists' >&2; exit 1; fi
ssh-keygen -lf /run/qmodem-authorized_keys >/dev/null
useradd --create-home --shell /bin/bash --groups sudo "$QMODEM_ADMIN_USER"
install -d -m 700 -o "$QMODEM_ADMIN_USER" -g "$QMODEM_ADMIN_USER" "/home/$QMODEM_ADMIN_USER/.ssh"
install -m 600 -o "$QMODEM_ADMIN_USER" -g "$QMODEM_ADMIN_USER" \
    /run/qmodem-authorized_keys "/home/$QMODEM_ADMIN_USER/.ssh/authorized_keys"
printf '%s ALL=(ALL:ALL) NOPASSWD: ALL\n' "$QMODEM_ADMIN_USER" > /etc/sudoers.d/90-qmodem-admin
chmod 440 /etc/sudoers.d/90-qmodem-admin
visudo -cf /etc/sudoers.d/90-qmodem-admin
mkdir -p /etc/ssh/sshd_config.d /etc/systemd/system/ssh.service.d
cat > /etc/ssh/sshd_config.d/20-qmodem.conf <<'SSH'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
UsePAM yes
SSH
cat > /etc/systemd/system/qmodem-hostkeys.service <<'UNIT'
[Unit]
Description=Create per-device SSH host keys
Before=ssh.service
[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A
RemainAfterExit=yes
UNIT
cat > /etc/systemd/system/ssh.service.d/20-hostkeys.conf <<'UNIT'
[Unit]
Requires=qmodem-hostkeys.service
After=qmodem-hostkeys.service
UNIT
mkdir -p /etc/systemd/network /etc/systemd/journald.conf.d
cat > /etc/systemd/network/20-usb.network <<'NETWORK'
[Match]
Name=usb0
[Link]
RequiredForOnline=no
[Network]
Address=192.168.77.1/24
LinkLocalAddressing=ipv6
IPv6AcceptRA=no
DHCPServer=yes
[DHCPServer]
PoolOffset=2
PoolSize=9
EmitRouter=no
EmitDNS=no
EmitNTP=no
[DHCPServerStaticLease]
MACAddress=02:00:00:10:03:02
Address=192.168.77.2
NETWORK
cat > /etc/systemd/journald.conf.d/20-qmodem.conf <<'JOURNAL'
[Journal]
Storage=volatile
RuntimeMaxUse=16M
JOURNAL
printf 'qmodem\n' > /etc/hostname
printf '127.0.0.1 localhost\n127.0.1.1 qmodem\n::1 localhost ip6-localhost\n' > /etc/hosts
printf 'PARTUUID=%s / ext4 defaults,noatime 0 1\n' "$QMODEM_ROOT_PARTUUID" > /etc/fstab
printf 'profile=ufi103s-v03\nsuite=trixie\nroot_partuuid=%s\n' "$QMODEM_ROOT_PARTUUID" > /etc/qmodem-release
systemctl enable ssh.service systemd-networkd.service systemd-timesyncd.service
systemctl set-default multi-user.target
mkdir -p /run/sshd
sshd -t
sshd -T | grep -qx 'passwordauthentication no'
sshd -T | grep -qx 'permitrootlogin no'
test -z "$(dpkg --audit)"
