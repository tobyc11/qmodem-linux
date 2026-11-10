# Debian root initramfs and deployment review

LK remains unchanged and forced-fastboot. A host uses the existing `fastboot
continue` command after installation; no boot delay, A/B, misc changes or new
bootloader command is introduced.

`scripts/pack-persistent.py --artifacts PATH` derives two boot images from the
verified cloud rescue artifacts. It preserves that kernel, DTB, static tools and
public SSH key, replacing PID 1 with the reviewed initramfs scripts:

- `ufi103s-debian.img`: find userdata by PARTUUID from sysfs, require ext4,
  mount `ro,noload` to check the Debian profile marker and executable init,
  then remount normally read-only for the real boot. An invalid/missing root
  enters RAM rescue without formatting, fsck repairs or journal replay.
- `ufi103s-debian-ram-test.img`: explicit `qmodem.test=1` skips the eMMC-root
  probe and exposes rescue. An operator can prepare a RAM-backed root and signal
  its PID-1 handoff with `/run/qmodem-test-ready`. The production command line
  does not enable this trigger.

The successful path creates USB ECM without starting initramfs DHCP or SSH,
moves proc/sys/dev/run into the new root, and `exec switch_root`s to Debian
systemd. Debian networkd owns the existing gadget and address. A RAM-test handoff
stops rescue DHCP/Dropbear first. No rescue process should own either service
after handoff. SSH host keys are generated on the writable Debian root once.

The probe never sources configuration from userdata. The expected PARTUUID is
embedded from `deployment/layout.json`. Provisioned root journal replay can
occur during the subsequent normal ext4 mount; regular ext4 boot/remount and
filesystem checking remain Debian's responsibility. An unmountable root falls
back to rescue; a failure after executing systemd requires reset to LK/rescue.
There is no automatic rollback or guaranteed recovery from a hung OS.

## Actual hardware tests

Cloud run 42772519702 supplied Linux 6.18.62, Debian 13 ARM64 and the public key.
The production-root probe rejected existing Android userdata and entered rescue;
the eMMC block-write counters remained zero. A separately prepared gzip SquashFS
RAM root with writable tmpfs /etc, /var and /tmp then booted the same handoff into
real systemd PID 1. `systemctl is-system-running` reported `running`, with zero
failed units; SSH, networkd and per-device host-key initialization were active.
Public-key `dave` login and passwordless sudo worked. Restarting SSH preserved
its host key. All four CPUs were online and LEDs remained off.

This RAM test deliberately substitutes an empty fstab to avoid any eMMC mount.
It does not prove installed ext4 remount, persistent data, fsck, fastboot continue
selection, or host keys across power cycles. Those are post-approval tests.
Existing platform SCM/SMSM/USB/regulator warnings remain. The run-4 Debian image
also logs a nonfatal missing `/etc/default/locale` PAM warning. Clock/NTP and
Internet access need a future uplink; the board has no verified persistent RTC.

Local evidence is in `build/persistent-root/`: `systemd-test.log`,
`systemd-load-test.log`, the image manifests and `deployment-review.json`.
Generated images/logs/private keys are excluded from the source repository.

## Offline ext4 image

```sh
python3 scripts/pack-persistent.py --artifacts build/ci-hardware-test/artifacts
python3 scripts/build-debian-ext4.py --artifacts build/ci-hardware-test/artifacts --public-key build/rescue_ed25519.pub
python3 scripts/prepare-deployment-review.py
```

The ext4 builder needs a recent mke2fs with libarchive tarball support (tested on
1.47.4). It imports numeric ownership directly from the verified tar archive,
requires no host root, creates only a new regular file, checks it with read-only
e2fsck and zero-pads the unused partial-block partition tail. It refuses an
existing output. Never substitute a device path.

The boot packer also pads a full-partition `boot-partition.bin` with zeroes.
The review preparer records both full-partition image hashes in
`build/persistent-root/deployment-review.json`. The review records exact sizes,
paths and verified backup manifest. The installer does not build/change images.

## Separate destructive approval

Writing userdata replaces all existing Android userdata. Writing boot replaces
its existing Android boot image. Only these two partitions are permitted.
Review exact images/hashes and backups before approval. `scripts/install-debian.py`
defaults to read-only verification: image/backup rereads, device geometry,
PARTUUIDs, GPT, no mounted eMMC, RAM-rescue PID 1 and unchanged current device
hashes relative to the backup. It refuses to run from Debian systemd.

After explicit approval, `--apply` additionally requires
`--approve-boot-sha256 HASH --approve-userdata-sha256 HASH`. It writes userdata
first via the RAM-rescue SSH stream, fsyncs and hashes the entire partition before
writing boot. It then fsyncs/readbacks boot, verifies protected partition hashes
and GPT unchanged, and records `installation.json`. It does not reboot or alter
LK. Interrupted writes require operator rescue; it is not an atomic update.

After verified writes, reboot into LK and use `fastboot continue`. Prove its
existing filesystem/extlinux scan actually selects this boot image. Check
systemd health, ext4 root PARTUUID/read-write mount, host-key/config/data
persistence across resets, rescue reachability and sustained workload. Preserve
all off-device backups and the known-good RAM rescue image.
