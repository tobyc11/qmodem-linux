#!/usr/bin/env python3
"""Read-only Wi-Fi boot-update preflight; exact hash approval required for writes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--review',type=Path,default=root/'build/wifi/boot-review.json')
p.add_argument('--apply',action='store_true')
p.add_argument('--approve-sha256')
a=p.parse_args()
m=json.loads(a.review.read_text())
image=root/m['image']['path']
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
if not image.is_file() or image.is_symlink() or image.stat().st_size!=16777216:
    p.error('not an exact-size regular boot image')
if digest(image)!=m['image']['sha256']:p.error('image hash changed')
backup=root/m['backup']['path']
if not backup.is_file() or backup.is_symlink() or backup.stat().st_size!=16777216:
    p.error('not an exact-size regular backup')
if digest(backup)!=m['backup']['sha256']:p.error('backup hash mismatch')
if a.apply and a.approve_sha256!=m['image']['sha256']:p.error('exact proposed-image SHA256 approval required')
def ssh(command,timeout=120):
    return subprocess.check_output(['bash',str(root/'scripts/ssh-debian.sh'),command],text=True,timeout=timeout)
check=('test "$(cat /sys/block/mmcblk0/size)" = 7634944 && '
       'test "$(cat /sys/class/block/mmcblk0p22/start)" = 396384 && '
       'test "$(cat /sys/class/block/mmcblk0p22/size)" = 32768 && '
       'grep -qx "PARTUUID=ee8de777-10d5-9d19-572a-18e0f3c3de69" /sys/class/block/mmcblk0p22/uevent && '
       '! awk \'$3 == "179:22" { found=1 } END { exit !found }\' /proc/self/mountinfo')
ssh(check)
layout=json.loads((root/'deployment/layout.json').read_text())
gpt_command='sudo -n dd if=/dev/mmcblk0 bs=512 count=34 status=none | sha256sum'
if ssh(gpt_command).split()[0]!=layout['gpt_sha256']:p.error('GPT mismatch')
if ssh('sudo -n sha256sum /dev/mmcblk0p22').split()[0]!=m['backup']['sha256']:p.error('current boot differs from backup')
if not a.apply:
    print('READ-ONLY PASS: exact boot image, verified current boot backup, GPT, geometry, identity and unmounted boot')
    raise SystemExit(0)
expected=m['protected_before']
paths=[]
for line in expected.splitlines():
    sha,path=line.split()
    if not re.fullmatch(r'[0-9a-f]{64}',sha) or not re.fullmatch(r'/dev/mmcblk0p[0-9]+',path):p.error('invalid protected hash entry')
    paths.append(path)
if len(paths)!=25 or len(set(paths))!=25 or '/dev/mmcblk0p22' in paths or '/dev/mmcblk0p27' in paths:
    p.error('wrong protected partition inventory')
protected_command='sudo -n sha256sum '+' '.join(paths)
if ssh(protected_command,600)!=expected:p.error('protected partition differs from baseline')
ssh(check)
with image.open('rb') as stream:
    subprocess.run(['bash',str(root/'scripts/ssh-debian.sh'),
        'sudo -n dd of=/dev/mmcblk0p22 bs=1048576 conv=fsync status=none'],stdin=stream,check=True,timeout=120)
actual=ssh('sudo -n sha256sum /dev/mmcblk0p22').split()[0]
if actual!=m['image']['sha256']:raise RuntimeError('boot readback mismatch')
if ssh(protected_command,600)!=expected:raise RuntimeError('protected partition changed')
if ssh(gpt_command).split()[0]!=layout['gpt_sha256']:raise RuntimeError('GPT changed')
result={'status':'boot written/readback verified; GPT/protected partitions unchanged; installed boot test pending',
        'review':m,'boot_readback_sha256':actual}
(a.review.parent/'boot-installation.json').write_text(json.dumps(result,indent=2)+'\n')
print(result['status'])
