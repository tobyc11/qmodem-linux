#!/usr/bin/env python3
"""Check image format, key-only rescue and archive hygiene before publishing."""
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import struct
import subprocess
import tarfile

root = Path(__file__).resolve().parents[2]
out = root / 'artifacts'
expected = {'rootfs.tar.zst', 'ufi103s-rescue.img', 'Image.gz',
            'msm8916-qmodem-rescue.dtb', 'kernel.config', 'kernel.patch',
            'sources.json', 'debian-package-list.tsv', 'debian-inrelease.sha256',
            'build-manifest.json', 'SHA256SUMS'}
if {p.name for p in out.iterdir()} != expected:
    raise SystemExit('Unexpected or missing publishable artifact')
checked = set()
for line in (out / 'SHA256SUMS').read_text().splitlines():
    digest, name = line.split('  ', 1)
    if name not in expected or name == 'SHA256SUMS':
        raise SystemExit('Invalid checksum path')
    if name in checked: raise SystemExit('Duplicate checksum entry')
    checked.add(name)
    with (out / name).open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != digest:
            raise SystemExit('Artifact checksum mismatch: ' + name)
if checked != expected - {'SHA256SUMS'}:
    raise SystemExit('Incomplete checksum list')
image = (out / 'ufi103s-rescue.img').read_bytes()
if image[:8] != b'ANDROID!' or len(image) > 15 * 1024**2:
    raise SystemExit('Invalid/oversized boot image')
klen, _, rlen, _, slen, _, _, page, _, _ = struct.unpack_from('<10I', image, 8)
if page != 2048 or slen or not klen or not rlen:
    raise SystemExit('Unexpected boot image header')
align = lambda n: (n + page - 1) // page * page
if len(image) != page + align(klen) + align(rlen):
    raise SystemExit('Boot image length mismatch')
kernel = image[page:page+klen]
ramdisk = image[page+align(klen):page+align(klen)+rlen]
dtb = (out / 'msm8916-qmodem-rescue.dtb').read_bytes()
if dtb[:4] != b'\xd0\x0d\xfe\xed' or kernel != (out / 'Image.gz').read_bytes() + dtb:
    raise SystemExit('Boot image kernel/DTB mismatch')
if gzip.decompress((out / 'Image.gz').read_bytes())[56:60] != b'ARM\x64':
    raise SystemExit('Kernel is not an ARM64 Image')
digest = hashlib.sha1()
for data in (kernel, ramdisk, b''):
    digest.update(data); digest.update(struct.pack('<I', len(data)))
if image[576:596] != digest.digest():
    raise SystemExit('Boot image digest mismatch')
# Decode newc without extraction, to check no client private key was packed.
cpio = gzip.decompress(ramdisk); offset = 0; authorized = None; trailer = False
while offset + 110 <= len(cpio):
    header = cpio[offset:offset+110]
    if header[:6] != b'070701': raise SystemExit('Invalid initramfs cpio')
    size = int(header[54:62], 16); namesize = int(header[94:102], 16)
    if namesize < 1 or offset + 110 + namesize > len(cpio):
        raise SystemExit('Invalid cpio name length')
    name = cpio[offset+110:offset+110+namesize-1].decode()
    offset = (offset + 110 + namesize + 3) & ~3
    content = cpio[offset:offset+size]
    if len(content) != size: raise SystemExit('Truncated cpio content')
    offset = (offset + size + 3) & ~3
    if name == 'TRAILER!!!': trailer = True; break
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts: raise SystemExit('Unsafe cpio path')
    if '.ssh' in p.parts and p.name != 'authorized_keys' and size:
        raise SystemExit('Unexpected SSH material in rescue image')
    if str(p) == 'root/.ssh/authorized_keys': authorized = content
if not trailer or authorized != (root / 'build/ci/authorized_keys').read_bytes():
    raise SystemExit('Rescue image does not contain the approved public key')
# Stream the compressed rootfs; do not extract device nodes or trust archive paths.
proc = subprocess.Popen(['zstd', '-dc', str(out / 'rootfs.tar.zst')], stdout=subprocess.PIPE)
found = set()
manifest = json.loads((out / 'build-manifest.json').read_text())
admin = manifest['ssh_admin_user']
root_authorized = None
root_bytes = 0
try:
    with tarfile.open(fileobj=proc.stdout, mode='r|') as tar:
        for member in tar:
            p = PurePosixPath(member.name)
            if p.is_absolute() or '..' in p.parts: raise SystemExit('Unsafe rootfs path')
            name = str(p); found.add(name)
            if member.isfile(): root_bytes += member.size
            if name == f'home/{admin}/.ssh/authorized_keys':
                root_authorized = tar.extractfile(member).read()
            if name.startswith('etc/ssh/ssh_host_') or ('.ssh' in p.parts and p.name.startswith('id_')):
                raise SystemExit('Private SSH identity in rootfs')
            if name.startswith('etc/ssl/private/') and member.isfile() and member.size:
                raise SystemExit('Private TLS identity in rootfs')
            if name in {'usr/sbin/policy-rc.d', 'var/lib/systemd/random-seed'}:
                raise SystemExit('Build-only identity/policy in rootfs')
            if name == 'etc/machine-id' and (not member.isfile() or member.size):
                raise SystemExit('Build machine identity was not cleared')
            if name == 'etc/shadow':
                for record in tar.extractfile(member).read().decode().splitlines():
                    if not record.split(':')[1].startswith(('!', '*')):
                        raise SystemExit('An enabled password was found in rootfs')
    if proc.wait() != 0: raise SystemExit('Rootfs decompression failed')
finally:
    if proc.poll() is None: proc.kill(); proc.wait()
if root_authorized != (root / 'build/ci/authorized_keys').read_bytes():
    raise SystemExit('Debian administrator public key mismatch')
if root_bytes > 2 * 1024**3:
    raise SystemExit('Root filesystem exceeds its 2GiB initial-install budget')
for name in ('etc/qmodem-release', 'etc/fstab', 'etc/machine-id',
             f'home/{admin}/.ssh/authorized_keys', 'etc/systemd/system/qmodem-hostkeys.service'):
    if name not in found: raise SystemExit('Missing server file: ' + name)
print('Boot format, rescue key, file allowlist, checksums and rootfs identity hygiene verified')
