#!/usr/bin/env python3
"""Create a source-only handoff bundle for a fresh GitHub repository."""
from pathlib import Path
import tarfile

root=Path(__file__).resolve().parents[2]
files=(
 '.github/workflows/debian-arm64.yml', '.gitignore',
 'configs/ci-sources.json', 'configs/kernel.patch', 'configs/dropbear-localoptions.h',
 'deployment/layout.json', 'deployment/debian-configure.sh',
 'deployment/debian-server-configure.sh', 'deployment/GITHUB_ACTIONS.md',
 'scripts/build-kernel.sh', 'scripts/build-userspace.sh', 'scripts/pack-rescue.sh',
 'scripts/rescue-init', 'scripts/mkbootimg.py',
 'scripts/verify-debian-ext4.py', 'scripts/prepare-deployment-review.py',
 'scripts/ssh-debian.sh',
 'scripts/pack-persistent.py', 'scripts/build-debian-ext4.py', 'scripts/install-debian.py',
 'scripts/initramfs/init', 'scripts/initramfs/check-root', 'scripts/initramfs/usb-gadget',
 'scripts/initramfs/handoff', 'scripts/initramfs/prepare-ram-test',
 'deployment/PERSISTENT_ROOT.md',
 'scripts/ci/fetch-sources.py', 'scripts/ci/prepare-inputs.py',
 'scripts/ci/build-rootfs.sh', 'scripts/ci/package-artifacts.py',
 'scripts/ci/verify-artifacts.py', 'scripts/ci/test_ci.py', 'scripts/ci/export-workflow.py',
)
out=root/'build/github-actions-source.tar.gz'
out.parent.mkdir(exist_ok=True)
with tarfile.open(out,'w:gz') as archive:
 for name in files:
  path=root/name
  if not path.is_file() or path.is_symlink():raise SystemExit('Unexpected source: '+name)
  archive.add(path,arcname=name,recursive=False)
 archive.add(root/'deployment/GITHUB_ACTIONS.md',arcname='README.md',recursive=False)
print(f'{out}: {len(files)+1} allowlisted source/configuration files')
