#!/usr/bin/env python3
"""Read-only validation of critical Debian files and permissions in an offline ext4 image."""
import argparse
import json
from pathlib import Path
import re
import subprocess

root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('image',type=Path)
p.add_argument('--public-key',type=Path,required=True)
p.add_argument('--admin-user',default='dave')
a=p.parse_args()
if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}',a.admin_user):p.error('invalid username')
def debug(command):
    r=subprocess.run(['debugfs','-R',command,str(a.image)],text=True,capture_output=True,check=True)
    if 'File not found' in r.stderr:raise SystemExit('Missing required path')
    return r.stdout
def metadata(path,mode,uid,gid):
    s=debug('stat '+path)
    if not re.search(r'Mode:\s+0*'+mode+r'\b',s):raise SystemExit('Wrong mode: '+path)
    if not re.search(r'User:\s+'+str(uid)+r'\s+Group:\s+'+str(gid)+r'\b',s):
        raise SystemExit('Wrong owner: '+path)
    return s
metadata('/usr/bin/sudo','4755',0,0)
metadata('/etc/shadow','640',0,42)
metadata('/etc/sudoers.d/90-qmodem-admin','440',0,0)
passwd=debug('cat /etc/passwd')
account=[x.split(':') for x in passwd.splitlines() if x.startswith(a.admin_user+':')]
if len(account)!=1:raise SystemExit('Missing/duplicate admin')
uid,gid=map(int,account[0][2:4])
metadata(f'/home/{a.admin_user}/.ssh','700',uid,gid)
metadata(f'/home/{a.admin_user}/.ssh/authorized_keys','600',uid,gid)
if debug(f'cat /home/{a.admin_user}/.ssh/authorized_keys')!=a.public_key.read_text():
    raise SystemExit('Public key mismatch')
for record in debug('cat /etc/shadow').splitlines():
    if not record.split(':')[1].startswith(('!','*')):raise SystemExit('Enabled account password')
metadata('/etc/machine-id','644',0,0)
if debug('cat /etc/machine-id'):raise SystemExit('Machine identity leaked')
if 'ssh_host_' in debug('ls -p /etc/ssh'):raise SystemExit('SSH host identity leaked')
uuid=json.loads((root/'deployment/layout.json').read_text())['root']['partuuid']
if debug('cat /etc/qmodem-release')!=f'profile=ufi103s-v03\nsuite=trixie\nroot_partuuid={uuid}\n':
    raise SystemExit('Root profile mismatch')
if debug('cat /etc/fstab')!=f'PARTUUID={uuid} / ext4 defaults,noatime 0 1\n':
    raise SystemExit('Root fstab mismatch')
if 'Fast link dest: "../lib/systemd/systemd"' not in debug('stat /usr/sbin/init'):
    raise SystemExit('Unexpected init link')
metadata('/usr/lib/systemd/systemd','755',0,0)
print('Offline ext4: numeric ownership, sudo setuid, key-only account, empty identities, PARTUUID and systemd init verified')
