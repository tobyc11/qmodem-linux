#!/usr/bin/env python3
"""Build legacy Android boot header v0 with an appended Qualcomm DTB."""
import argparse
import hashlib
import pathlib
import struct

p = argparse.ArgumentParser()
p.add_argument('--kernel', required=True)
p.add_argument('--dtb', required=True)
p.add_argument('--ramdisk', required=True)
p.add_argument('--output', required=True)
p.add_argument('--cmdline', help='Override the complete kernel command line for RAM boot experiments')
a = p.parse_args()
kernel = pathlib.Path(a.kernel).read_bytes() + pathlib.Path(a.dtb).read_bytes()
ramdisk = pathlib.Path(a.ramdisk).read_bytes()
cmdline = (b'console=null rdinit=/init loglevel=4 panic=10 '
           b'lk2nd.pass-ramoops reboot=warm')
if a.cmdline is not None:
    cmdline = a.cmdline.encode('ascii')
if len(cmdline) > 511:
    p.error('command line exceeds the supported 511-byte header field')
page = 2048
digest = hashlib.sha1()
for blob in (kernel, ramdisk, b''):
    digest.update(blob)
    digest.update(struct.pack('<I', len(blob)))
header = struct.pack('<8s10I16s512s32s1024s', b'ANDROID!',
                     len(kernel), 0x80080000, len(ramdisk), 0x84000000,
                     0, 0x80f00000, 0x81e00000, page, 0, 0,
                     b'qmodem-rescue', cmdline, digest.digest(), b'')
def padded(blob):
    return blob + bytes((-len(blob)) % page)
pathlib.Path(a.output).write_bytes(padded(header) + padded(kernel) + padded(ramdisk))
print(f'{a.output}: kernel+dtb={len(kernel)}, ramdisk={len(ramdisk)}')
