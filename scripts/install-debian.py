#!/usr/bin/env python3
"""Review or apply the two approved Debian partition images over RAM rescue SSH.

Default is read-only preflight. --apply additionally requires both exact SHA256
approval arguments. Never formats on-device or changes LK, GPT, misc or firmware.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

root=Path(__file__).resolve().parents[1]
os.chdir(root)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--review',type=Path,default=root/'build/persistent-root/deployment-review.json')
p.add_argument('--apply',action='store_true')
p.add_argument('--approve-boot-sha256')
p.add_argument('--approve-userdata-sha256')
a=p.parse_args()
review=json.loads(a.review.read_text())
layout=json.loads((root/'deployment/layout.json').read_text())
backup=json.loads((root/review['backup_manifest']).read_text())
if not backup['status'].startswith('complete;'):p.error('backup not complete')

def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def ssh(command,timeout=120):
    return subprocess.run(['bash','scripts/ssh-rescue.sh',command],text=True,
        stdout=subprocess.PIPE,check=True,timeout=timeout).stdout

for name in ('userdata','boot'):
    entry=review['images'][name]
    path=root/entry['path']
    if not path.is_file() or path.is_symlink():p.error('expected regular image: '+name)
    if entry['bytes']!=layout['partitions'][name]['bytes'] or path.stat().st_size!=entry['bytes']:
        p.error('wrong partition image size: '+name)
    if digest(path)!=entry['sha256']:p.error('image hash mismatch: '+name)
    original=backup['partitions'][name]
    if original['status']!='verified' or digest(root/review['backup_directory']/(name+'.bin'))!=original['sha256']:
        p.error('backup hash mismatch: '+name)
if a.apply:
    if a.approve_boot_sha256!=review['images']['boot']['sha256'] or a.approve_userdata_sha256!=review['images']['userdata']['sha256']:
        p.error('--apply requires exact approval hashes for both reviewed images')

check=('test "$(readlink /proc/1/exe)" = /bin/busybox && '
       'grep -q "rdinit=/init" /proc/cmdline && '
       'test "$(cat /sys/block/mmcblk0/size)" = 7634944 && '
       '! grep -q " 179:" /proc/self/mountinfo')
for name,part in layout['partitions'].items():
    number=part['partition_number']
    check+=f' && test "$(cat /sys/class/block/mmcblk0p{number}/start)" = {part["start_lba"]}'
    check+=f' && test "$(cat /sys/class/block/mmcblk0p{number}/size)" = {part["bytes"]//512}'
    check+=f' && grep -qx "PARTUUID={part["partuuid"]}" /sys/class/block/mmcblk0p{number}/uevent'
ssh(check)
if ssh('dd if=/dev/mmcblk0 bs=512 count=34 2>/dev/null | sha256sum').split()[0]!=layout['gpt_sha256']:
    p.error('GPT mismatch')
# Refuse replacing data that has changed since the fresh reviewed backup.
for name in ('boot','userdata'):
    number=layout['partitions'][name]['partition_number']
    actual=ssh(f'sha256sum /dev/mmcblk0p{number}',timeout=600).split()[0]
    if actual!=backup['partitions'][name]['sha256']:p.error('device differs from backup: '+name)
print('Verified images, backups, GPT, partition identity, unmounted rescue and current device hashes.',flush=True)
if not a.apply:
    print('READ-ONLY REVIEW: no writes. userdata will be erased only after explicit approval.')
    print(json.dumps(review['images'],indent=2))
    raise SystemExit(0)
# Record hashes of every protected partition before and after installation.
protected=[f'/dev/{line.split("=",1)[1]}' for line in ssh(
    'for d in /sys/class/block/mmcblk0p*/uevent; do cat "$d"; echo; done').splitlines()
    if line.startswith('DEVNAME=') and line not in ('DEVNAME=mmcblk0p22','DEVNAME=mmcblk0p27')]
if len(protected)!=len(layout['protected_partitions']):p.error('unexpected protected partition inventory')
protected_command='sha256sum '+' '.join(protected)
before=ssh(protected_command,timeout=600)
state={'status':'writing userdata','review':review,'protected_before':before}
state_path=a.review.parent/'installation.json'
def save():state_path.write_text(json.dumps(state,indent=2)+'\n')
save()
for name in ('userdata','boot'):
    ssh(check)
    entry=review['images'][name]
    number=layout['partitions'][name]['partition_number']
    print('WRITING '+name,flush=True)
    with (root/entry['path']).open('rb') as source:
        subprocess.run(['bash','scripts/ssh-rescue.sh',f'dd of=/dev/mmcblk0p{number} bs=1048576 conv=fsync'],
            stdin=source,check=True,timeout=1200)
    actual=ssh(f'sha256sum /dev/mmcblk0p{number}',timeout=600).split()[0]
    if actual!=entry['sha256']:raise RuntimeError('readback mismatch: '+name)
    state[name]={'status':'readback verified','sha256':actual}; save()
after=ssh(protected_command,timeout=600)
if after!=before:raise RuntimeError('protected partition hash changed')
if ssh('dd if=/dev/mmcblk0 bs=512 count=34 2>/dev/null | sha256sum').split()[0]!=layout['gpt_sha256']:
    raise RuntimeError('GPT changed')
state['status']='both partition writes and readbacks verified; protected partitions/GPT unchanged; boot test pending'
save()
print(state['status'])
