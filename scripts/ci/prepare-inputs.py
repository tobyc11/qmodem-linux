#!/usr/bin/env python3
"""Validate workflow input through environment variables, never shell interpolation."""
import os
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[2]
key = os.environ.get('QMODEM_SSH_PUBLIC_KEY', '').strip()
admin = os.environ.get('QMODEM_ADMIN_USER', 'dave')
if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', admin) or admin in {'root', 'daemon', 'bin', 'nobody', 'sshd'}:
    raise SystemExit('Invalid administrative username')
if '\n' in key or '\r' in key or len(key) > 4096 or not key.startswith('ssh-ed25519 '):
    raise SystemExit('Provide one Ed25519 PUBLIC key, without authorized_keys options')
out = root / 'build/ci'
out.mkdir(parents=True, exist_ok=True)
path = out / 'authorized_keys'
path.write_text(key + '\n')
result = subprocess.run(['ssh-keygen', '-lf', str(path)], text=True, capture_output=True)
if result.returncode:
    path.unlink()
    raise SystemExit('Invalid SSH public key')
(out / 'ssh-fingerprint.txt').write_text(result.stdout.split()[1] + '\n')
print('Validated public key and administrative username; no private key created')
