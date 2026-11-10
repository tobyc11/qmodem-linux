#!/usr/bin/env python3
"""Derive persistent-root and RAM-test boot images from verified CI rescue artifacts."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess

root = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--artifacts', type=Path, required=True)
p.add_argument('--output', type=Path, default=root/'build/persistent-root')
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=True)
expected = {}
for line in (a.artifacts/'SHA256SUMS').read_text().splitlines():
    digest, name = line.split('  ', 1)
    if PurePosixPath(name).name != name or name in expected:
        p.error('invalid checksum filename')
    expected[name] = digest
for name in ('ufi103s-rescue.img', 'Image.gz', 'msm8916-qmodem-rescue.dtb'):
    if hashlib.sha256((a.artifacts/name).read_bytes()).hexdigest() != expected.get(name):
        p.error('artifact checksum mismatch: '+name)
image = (a.artifacts/'ufi103s-rescue.img').read_bytes()
if image[:8] != b'ANDROID!': p.error('not an Android boot image')
klen, _, rlen, _, _, _, _, page = struct.unpack_from('<8I', image, 8)
if page != 2048: p.error('unexpected page size')
start = page + (klen+page-1)//page*page
blob = gzip.decompress(image[start:start+rlen])
entries = {}
offset = 0
while offset+110 <= len(blob):
    header = blob[offset:offset+110]
    if header[:6] != b'070701': p.error('unsupported cpio')
    values = [int(header[i:i+8],16) for i in range(6,110,8)]
    size, namesize = values[6], values[11]
    name = blob[offset+110:offset+110+namesize-1].decode()
    offset = (offset+110+namesize+3)&~3
    data = blob[offset:offset+size]
    offset = (offset+size+3)&~3
    if name == 'TRAILER!!!': break
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or len(data)!=size: p.error('unsafe cpio')
    entries[str(path)] = (values[1], data)
else: p.error('missing cpio trailer')
original_init = entries['init'][1]
for point, fs in [('proc','proc'),('sys','sysfs'),('dev','devtmpfs')]:
    line=f'mount -t {fs} {fs} /{point}'.encode()
    original_init=original_init.replace(line, f'mountpoint -q /{point} || '.encode()+line)
# Only the explicit test command line enables a manual PID-1 handoff from rescue.
old = b'while true; do setsid cttyhack /bin/sh; sleep 1; done'
new = b'''while true; do
    case " $(cat /proc/cmdline) " in
        *' qmodem.test=1 '*)
            if [ -e /run/qmodem-test-ready ] && /sbin/qmodem-check-root; then
                exec /sbin/qmodem-handoff
            fi;;
    esac
    sleep 1
done'''
if old not in original_init: p.error('unexpected rescue init layout')
entries['rescue-init'] = (0o100755, original_init.replace(old,new))
for source, target in [('init','init'),('check-root','sbin/qmodem-check-root'),
                       ('usb-gadget','sbin/qmodem-usb-gadget'),('handoff','sbin/qmodem-handoff')]:
    entries[target] = (0o100755,(root/'scripts/initramfs'/source).read_bytes())
uuid = json.loads((root/'deployment/layout.json').read_text())['root']['partuuid']
if not re.fullmatch(r'[0-9a-f-]{36}',uuid): p.error('invalid root PARTUUID')
entries['etc/qmodem-root.conf'] = (0o100644,f'QMODEM_ROOT_PARTUUID={uuid}\n'.encode())
entries['newroot'] = (0o40755,b'')
# Do not carry locally generated server or client identities into derived images.
for name in entries:
    if name.startswith('etc/dropbear/') or ('.ssh/' in name and not name.endswith('/authorized_keys')):
        p.error('unexpected identity in source initramfs')
output = bytearray()
for index,(name,(mode,data)) in enumerate([*sorted(entries.items()),('TRAILER!!!',(0,b''))],1):
    values = [index,mode,0,0,1,0,len(data),0,0,0,0,len(name.encode())+1,0]
    output += b'070701'+b''.join(f'{v:08x}'.encode() for v in values)+name.encode()+b'\0'
    output += bytes(-len(output)%4)
    output += data
    output += bytes(-len(output)%4)
ramdisk=a.output/'initramfs.cpio.gz'
ramdisk.write_bytes(gzip.compress(output,mtime=0))
manifest={'source_rescue_sha256':expected['ufi103s-rescue.img'],'root_partuuid':uuid,
          'storage_writes':'none; deployment requires separate exact-image approval','files':{}}
for name,test in [('ufi103s-debian.img',False),('ufi103s-debian-ram-test.img',True)]:
    target=a.output/name
    cmd='console=null rdinit=/init loglevel=4 panic=10 lk2nd.pass-ramoops reboot=warm'
    if test: cmd+=' qmodem.test=1'
    subprocess.run(['python3',str(root/'scripts/mkbootimg.py'),'--kernel',str(a.artifacts/'Image.gz'),
                    '--dtb',str(a.artifacts/'msm8916-qmodem-rescue.dtb'),'--ramdisk',str(ramdisk),
                    '--output',str(target),'--cmdline',cmd],check=True)
    if target.stat().st_size>15*1024**2:p.error('boot image exceeds deployment budget')
    manifest['files'][name]={'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
boot_partition=a.output/'boot-partition.bin'
boot_data=(a.output/'ufi103s-debian.img').read_bytes()
boot_size=json.loads((root/'deployment/layout.json').read_text())['partitions']['boot']['bytes']
boot_partition.write_bytes(boot_data+bytes(boot_size-len(boot_data)))
manifest['files']['boot-partition.bin']={'bytes':boot_size,'sha256':hashlib.sha256(boot_partition.read_bytes()).hexdigest()}
(a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(a.output/'manifest.json')
