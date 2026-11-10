#!/usr/bin/env python3
"""Fetch pinned public build sources into a fresh checkout, never device backups."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

root = Path(__file__).resolve().parents[2]
lock = json.loads((root / 'configs/ci-sources.json').read_text())
src, downloads = root / 'src', root / 'downloads'
src.mkdir(exist_ok=True); downloads.mkdir(exist_ok=True)
kernel = src / 'linux-git'
if kernel.exists():
    raise SystemExit('Use a fresh checkout: refusing to replace an existing kernel working tree')
k = lock['kernel']
subprocess.run(['git', 'clone', '--depth=1', '--branch', k['tag'], k['url'], str(kernel)], check=True)
commit = subprocess.check_output(['git', '-C', str(kernel), 'rev-parse', 'HEAD'], text=True).strip()
if commit != k['commit']:
    raise SystemExit('Kernel tag does not match pinned commit')
subprocess.run(['git', '-C', str(kernel), 'apply', '--check', str(root / 'configs/kernel.patch')], check=True)
subprocess.run(['git', '-C', str(kernel), 'apply', str(root / 'configs/kernel.patch')], check=True)
for archive in lock['archives']:
    path = downloads / archive['filename']
    if not path.exists():
        temp = path.with_suffix(path.suffix + '.partial')
        subprocess.run(['curl', '--fail', '--location', '--retry', '3', archive['url'], '-o', str(temp)], check=True)
        temp.replace(path)
    with path.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    if digest != archive['sha256']:
        raise SystemExit('Archive hash mismatch: ' + path.name)
    target = src / archive['directory']
    if target.exists():
        raise SystemExit('Refusing existing archive source directory: ' + str(target))
    with tarfile.open(path) as tar:
        for member in tar.getmembers():
            if Path(member.name).parts[0] != archive['directory']:
                raise SystemExit('Unexpected archive root')
        tar.extractall(src, filter='data')
print('Pinned kernel, board patch, BusyBox and Dropbear sources prepared')
