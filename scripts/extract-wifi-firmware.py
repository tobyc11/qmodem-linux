#!/usr/bin/env python3
"""Extract only this device's WCNSS firmware/calibration from preserved backups.

No downloads, filesystem mounts or device access. Output is private/local only.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
root=Path(__file__).resolve().parents[1]
os.umask(0o077)
out=root/'build/wifi/firmware'
out.mkdir(parents=True,exist_ok=True)
modem=root/'backups/modem.bin'
data=modem.read_bytes()
bps=struct.unpack_from('<H',data,11)[0]; spc=data[13]
reserved=struct.unpack_from('<H',data,14)[0]; nfats=data[16]
root_entries=struct.unpack_from('<H',data,17)[0]; fatsz=struct.unpack_from('<H',data,22)[0]
if bps!=512 or not spc or not fatsz:raise SystemExit('Expected known FAT16 firmware volume')
fat=data[reserved*bps:(reserved+fatsz)*bps]
root_start=(reserved+nfats*fatsz)*bps
root_size=root_entries*32
data_start=root_start+((root_size+bps-1)//bps)*bps
cluster_bytes=bps*spc
def chain(cluster):
    content=bytearray(); seen=set()
    while 2<=cluster<0xfff8:
        if cluster in seen:raise SystemExit('FAT cycle')
        seen.add(cluster)
        start=data_start+(cluster-2)*cluster_bytes
        if start+cluster_bytes>len(data):raise SystemExit('FAT cluster out of bounds')
        content+=data[start:start+cluster_bytes]
        cluster=struct.unpack_from('<H',fat,cluster*2)[0]
    return bytes(content)
files={}
def walk(directory,prefix=''):
    for pos in range(0,len(directory),32):
        e=directory[pos:pos+32]
        if not e or e[0]==0:break
        if e[0]==0xe5 or e[11]==0x0f or e[11]&8:continue
        name=e[:8].decode('ascii').strip(); ext=e[8:11].decode('ascii').strip()
        if name in ('.','..'):continue
        name=(name+('.'+ext if ext else '')).lower()
        cluster=struct.unpack_from('<H',e,26)[0]; size=struct.unpack_from('<I',e,28)[0]
        path=prefix+name
        if e[11]&16:walk(chain(cluster),path+'/')
        elif name.startswith('wcnss.'):
            payload=chain(cluster)[:size]
            if len(payload)!=size:raise SystemExit('Truncated file')
            (out/name).write_bytes(payload)
            files[name]={'source':'backups/modem.bin:'+path,'bytes':size,'sha256':hashlib.sha256(payload).hexdigest()}
walk(data[root_start:root_start+root_size])
if 'wcnss.mdt' not in files:raise SystemExit('WCNSS metadata missing')
nv=out/'wlan/prima/WCNSS_qcom_wlan_nv.bin'; nv.parent.mkdir(parents=True,exist_ok=True)
subprocess.run(['debugfs','-R',f'dump /WCNSS_qcom_wlan_nv.bin {nv}',str(root/'backups/persist.bin')],check=True)
if nv.stat().st_size!=29816:raise SystemExit('Unexpected board NV size')
files['wlan/prima/WCNSS_qcom_wlan_nv.bin']={'source':'backups/persist.bin:/WCNSS_qcom_wlan_nv.bin','bytes':nv.stat().st_size,'sha256':hashlib.sha256(nv.read_bytes()).hexdigest()}
manifest={'origin':'Original backups from this UFI103S V03; no third-party firmware download',
          'redistribution':'not assessed; keep firmware and device-specific calibration private',
          'sources':{},'files':files}
for name in ('modem','persist'):
    with (root/f'backups/{name}.bin').open('rb') as f:manifest['sources'][name]=hashlib.file_digest(f,'sha256').hexdigest()
(root/'build/wifi/firmware-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Extracted',len(files),'WCNSS firmware/calibration files to',out)
