#!/usr/bin/env python3
"""Local tests for public-key input and artifact rejection; no root/network/device."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]

class CITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'scripts/ci').mkdir(parents=True)
        for name in ('prepare-inputs.py', 'verify-artifacts.py'):
            shutil.copyfile(REPO / 'scripts/ci' / name, self.root / 'scripts/ci' / name)
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(self.root / 'test-key')], check=True)
        self.key = (self.root / 'test-key.pub').read_text()

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, key=None, user='dave'):
        return subprocess.run([sys.executable, str(self.root / 'scripts/ci/prepare-inputs.py')],
            env={**os.environ, 'QMODEM_SSH_PUBLIC_KEY': self.key if key is None else key,
                 'QMODEM_ADMIN_USER': user}, capture_output=True, text=True)

    def test_accepts_only_public_key(self):
        self.assertEqual(self.prepare().returncode, 0)
        self.assertEqual((self.root / 'build/ci/authorized_keys').read_text(), self.key)
        for key in (self.key.strip() + '\n' + self.key, (self.root / 'test-key').read_text(), 'command="id" '+self.key):
            self.assertNotEqual(self.prepare(key).returncode, 0)
        for user in ('root', 'dave;id', '../root', 'a\nb'):
            self.assertNotEqual(self.prepare(user=user).returncode, 0)

    @staticmethod
    def cpio(files):
        out = bytearray()
        for name, data in [*files.items(), ('TRAILER!!!', b'')]:
            fields = [1, 0o100600, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(name)+1, 0]
            out += b'070701' + ''.join(f'{v:08x}' for v in fields).encode()
            out += name.encode() + b'\0'
            out += bytes((-len(out)) % 4)
            out += data
            out += bytes((-len(out)) % 4)
        return bytes(out)

    def fixture(self, leak=False):
        self.assertEqual(self.prepare().returncode, 0)
        out = self.root / 'artifacts'; out.mkdir(exist_ok=True)
        raw = bytearray(64); raw[56:60] = b'ARM\x64'
        kernel = out / 'Image.gz'; kernel.write_bytes(gzip.compress(raw))
        dtb = out / 'msm8916-qmodem-rescue.dtb'; dtb.write_bytes(b'\xd0\x0d\xfe\xed'+bytes(36))
        initrd = self.root / 'initramfs.gz'
        initrd.write_bytes(gzip.compress(self.cpio({'root/.ssh/authorized_keys': self.key.encode()})))
        subprocess.run([sys.executable, str(REPO/'scripts/mkbootimg.py'), '--kernel', str(kernel),
            '--dtb', str(dtb), '--ramdisk', str(initrd), '--output', str(out/'ufi103s-rescue.img')], check=True, capture_output=True)
        rootfiles = {'etc/qmodem-release': b'profile=ufi103s-v03\n', 'etc/fstab': b'root\n',
            'etc/machine-id': b'', 'etc/shadow': b'root:!:0:0:99999:7:::\n',
            'home/dave/.ssh/authorized_keys': self.key.encode(),
            'etc/systemd/system/qmodem-hostkeys.service': b'[Service]\nType=oneshot\n'}
        if leak: rootfiles['etc/ssh/ssh_host_ed25519_key'] = b'private-key-test'
        tarpath = self.root/'root.tar'
        with tarfile.open(tarpath, 'w') as tar:
            for name,data in rootfiles.items():
                entry=tarfile.TarInfo(name); entry.size=len(data); tar.addfile(entry,io.BytesIO(data))
        subprocess.run(['zstd','-q','-f',str(tarpath),'-o',str(out/'rootfs.tar.zst')],check=True)
        for name in ('kernel.config','kernel.patch','sources.json','debian-package-list.tsv','debian-inrelease.sha256'):
            (out/name).write_text('fixture\n')
        (out/'build-manifest.json').write_text(json.dumps({'ssh_admin_user':'dave'}))
        self.checksums()
        return out

    def checksums(self):
        out=self.root/'artifacts'
        (out/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n'
            for p in sorted(out.iterdir()) if p.name!='SHA256SUMS'))

    def verify(self):
        return subprocess.run([sys.executable,str(self.root/'scripts/ci/verify-artifacts.py')],capture_output=True,text=True)

    def test_image_and_archive_pass(self):
        self.fixture(); result=self.verify(); self.assertEqual(result.returncode,0,result.stderr)

    def test_private_host_key_is_rejected(self):
        self.fixture(leak=True); result=self.verify()
        self.assertNotEqual(result.returncode,0); self.assertIn('Private SSH',result.stderr)

    @unittest.skipUnless((REPO/'images/ufi103s-rescue.img').exists(), 'No local hardware-tested image')
    def test_existing_hardware_image_format(self):
        self.key=(REPO/'build/rescue_ed25519.pub').read_text()
        out=self.fixture()
        shutil.copyfile(REPO/'images/ufi103s-rescue.img',out/'ufi103s-rescue.img')
        shutil.copyfile(REPO/'build/linux/arch/arm64/boot/Image.gz',out/'Image.gz')
        shutil.copyfile(REPO/'build/linux/arch/arm64/boot/dts/qcom/msm8916-qmodem-rescue.dtb',out/'msm8916-qmodem-rescue.dtb')
        self.checksums(); result=self.verify()
        self.assertEqual(result.returncode,0,result.stderr)

    def test_corruption_and_extra_files_rejected(self):
        out=self.fixture(); (out/'Image.gz').write_bytes(b'corrupt')
        self.assertNotEqual(self.verify().returncode,0)
        (out/'unexpected.bin').write_bytes(b'extra'); self.checksums()
        self.assertIn('Unexpected or missing',self.verify().stderr)

if __name__ == '__main__': unittest.main()
