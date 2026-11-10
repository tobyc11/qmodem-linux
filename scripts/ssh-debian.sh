#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec ssh -i build/rescue_ed25519 -o IdentitiesOnly=yes -o ConnectTimeout=15 \
    -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=build/debian_known_hosts \
    -b 192.168.77.2 "${QMODEM_ADMIN_USER:-dave}@192.168.77.1" "$@"
