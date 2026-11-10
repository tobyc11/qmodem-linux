#!/bin/sh
# Runs inside the ARM64 rootfs container, not directly on the host.
set -eu
test "$(dpkg --print-architecture)" = arm64
cat > /etc/apt/sources.list <<'SOURCES'
deb https://deb.debian.org/debian trixie main
deb https://deb.debian.org/debian trixie-updates main
deb https://security.debian.org/debian-security trixie-security main
SOURCES
apt-get update
apt-get -y --no-install-recommends full-upgrade
apt-get clean
dpkg --audit
mkdir -p /var/lib/qmodem
dpkg-query -W > /var/lib/qmodem/build-packages.tsv
rm -f /usr/sbin/policy-rc.d
