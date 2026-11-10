#!/usr/bin/env python3
"""Prepare exact-image review metadata; no device access or approval implied."""
import hashlib
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
base=root/'build/persistent-root'
layout=json.loads((root/'deployment/layout.json').read_text())
backup=json.loads((root/'deployment/backup-status.json').read_text())
images={}
for name,file in [('boot','boot-partition.bin'),('userdata','userdata.ext4')]:
    path=base/file
    if not path.is_file() or path.is_symlink():raise SystemExit('Not a regular image')
    if path.stat().st_size!=layout['partitions'][name]['bytes']:raise SystemExit('Wrong partition size')
    with path.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    images[name]={'path':str(path.relative_to(root)),'bytes':path.stat().st_size,
                  'sha256':sha,'device':'/dev/mmcblk0p'+str(layout['partitions'][name]['partition_number'])}
review={'status':'REVIEW ONLY: NOT APPROVED OR FLASHED',
        'effect':'Replace all boot and userdata contents. userdata loses all Android files. LK/GPT/misc/firmware untouched.',
        'backup_directory':backup['backup_directory'],'backup_manifest':backup['manifest'],'images':images}
path=base/'deployment-review.json'
path.write_text(json.dumps(review,indent=2)+'\n')
print(path)
