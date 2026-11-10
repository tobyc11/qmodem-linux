#!/usr/bin/env python3
"""Build an offline, unmounted userdata ext4 image without root or device access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--artifacts',type=Path,required=True)
p.add_argument('--public-key',type=Path,required=True)
p.add_argument('--output',type=Path,default=root/'build/persistent-root/userdata.ext4')
a=p.parse_args()
layout=json.loads((root/'deployment/layout.json').read_text())
manifest=json.loads((a.artifacts/'build-manifest.json').read_text())
archive=a.artifacts/'rootfs.tar.zst'
with archive.open('rb') as f:
    digest=hashlib.file_digest(f,'sha256').hexdigest()
if digest!=manifest['files']['rootfs.tar.zst']['sha256']:p.error('root archive hash mismatch')
a.output.parent.mkdir(parents=True,exist_ok=True)
# Exclusive creation and regular-file checks forbid overwriting any path/device.
fd=os.open(a.output,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
size=layout['partitions']['userdata']['bytes']
# ext4 uses complete blocks; pad its unused partition tail with zeroes.
blocks=size//4096
os.ftruncate(fd,blocks*4096)
os.close(fd)
fsuuid=str(uuid.uuid4())
try:
    # libarchive reads the numeric uid/gid/modes directly; no privileged extraction.
    subprocess.run(['mke2fs','-q','-t','ext4','-b','4096','-I','256','-m','1',
        '-L','qmodem-root','-U',fsuuid,'-E','lazy_itable_init=0,lazy_journal_init=0',
        '-d',str(archive),str(a.output),str(blocks)],check=True)
    subprocess.run(['e2fsck','-fn',str(a.output)],check=True)
    subprocess.run(['python3',str(root/'scripts/verify-debian-ext4.py'),str(a.output),
        '--public-key',str(a.public_key),'--admin-user',manifest['ssh_admin_user']],check=True)
    admin=manifest['ssh_admin_user']
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}',admin):p.error('invalid admin username')
    for path in ['/sbin/init','/etc/qmodem-release',f'/home/{admin}/.ssh/authorized_keys']:
        # Logged for review; all source archive ownership was retained by libarchive.
        subprocess.run(['debugfs','-R','stat '+path,str(a.output)],check=True)
except BaseException:
    print('Incomplete image retained for diagnosis:',a.output)
    raise
# Include all partition bytes so deployment readback hashes are unambiguous.
os.truncate(a.output,size)
with a.output.open('rb') as f: image_hash=hashlib.file_digest(f,'sha256').hexdigest()
review={'status':'OFFLINE IMAGE ONLY; not flashed','source_rootfs_sha256':digest,
        'source_revision':manifest['source_revision'],'filesystem_uuid':fsuuid,
        'root_partuuid':layout['root']['partuuid'],'target_partition':'userdata',
        'target_partition_number':27,'target_partition_bytes':size,
        'image_bytes':a.output.stat().st_size,'zero_padded_tail_bytes':size-blocks*4096,
        'sha256':image_hash,'e2fsck_read_only':'passed'}
a.output.with_suffix('.json').write_text(json.dumps(review,indent=2)+'\n')
print(json.dumps(review,indent=2))
