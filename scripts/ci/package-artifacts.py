#!/usr/bin/env python3
"""Export an explicit allowlist. Never archive the checkout, build dir or backups."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[2]
out = root / 'artifacts'
if out.exists():
    raise SystemExit('Refusing existing artifacts directory')
out.mkdir()
files = {
    'rootfs.tar.zst': 'build/ci/rootfs.tar.zst',
    'ufi103s-rescue.img': 'images/ufi103s-rescue.img',
    'Image.gz': 'build/linux/arch/arm64/boot/Image.gz',
    'msm8916-qmodem-rescue.dtb': 'build/linux/arch/arm64/boot/dts/qcom/msm8916-qmodem-rescue.dtb',
    'kernel.config': 'configs/kernel.config',
    'kernel.patch': 'configs/kernel.patch',
    'sources.json': 'configs/ci-sources.json',
    'debian-package-list.tsv': 'build/ci/debian-package-list.tsv',
    'debian-inrelease.sha256': 'build/ci/debian-inrelease.sha256',
}
for name, source in files.items():
    shutil.copyfile(root / source, out / name)

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

manifest = {
    'status': 'cloud build; hardware boot testing required',
    'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'target': 'UFI103S V03 / MSM8916 Cortex-A53 / arm64',
    'suite': 'Debian 13 trixie + updates/security at build time',
    'runner_architecture': os.uname().machine,
    'source_revision': os.environ.get('GITHUB_SHA', 'local'),
    'source_date_epoch': os.environ.get('SOURCE_DATE_EPOCH'),
    'kernel': json.loads((root / 'configs/ci-sources.json').read_text())['kernel'],
    'kernel_release': (root / 'build/linux/include/config/kernel.release').read_text().strip(),
    'ssh_admin_user': os.environ.get('QMODEM_ADMIN_USER', 'dave'),
    'ssh_public_key_fingerprint': (root / 'build/ci/ssh-fingerprint.txt').read_text().strip(),
    'boot_image_role': 'RAM rescue; does not mount or install the Debian root. Persistent root initramfs is deployment step 3.',
    'deployment': 'local review only; no flash/GPT/LK changes; current LK remains forced-fastboot',
    'reproducibility': 'upstream source pins and final package versions recorded; live Debian mirrors are not a frozen snapshot',
    'files': {p.name: {'bytes': p.stat().st_size, 'sha256': digest(p)} for p in sorted(out.iterdir())},
}
(out / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
(out / 'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in sorted(out.iterdir()) if p.name != 'SHA256SUMS'))
print('Allowlisted rootfs, rescue boot image, kernel/DTB and provenance assembled')
