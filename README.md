# Native ARM64 GitHub Actions build

Workflow: `.github/workflows/debian-arm64.yml`, manually started with
workflow_dispatch on `ubuntu-24.04-arm`. It uses the runner's sudo inside an
Ephemeral cloud VM. No laptop root, QEMU, binfmt setup, OBS or modem connection
is required. No LK modification, flashing, partitioning or deployment job exists.

## Build outputs

- `rootfs.tar.zst`: Debian 13 trixie arm64, updated from main/updates/security,
  normal writable-root profile for the existing userdata PARTUUID.
- `ufi103s-rescue.img`: the existing Android-v0 RAM rescue image format, rebuilt
  from our source-pinned kernel/DTB, BusyBox and Dropbear. **It does not mount or
  install the Debian root.** Persistent-root initramfs work remains deployment
  step 3; do not flash this expecting an installed Debian boot yet.
- `Image.gz`, DTB, effective kernel config and board patch.
- SHA256SUMS, source pins, final Debian package list, signed APT metadata hashes
  and build-manifest.json. Hardware validation remains local and separate.

Kernel/source pins are in configs/ci-sources.json. Source fetching uses a real
Git clone of upstream stable v6.18.62, verifies its commit, then applies the tracked
board patch. BusyBox/Dropbear release archives have pinned SHA256s. These are the
known-working versions, not an automatic latest-version upgrade. The build does
not use `-march=native`; BusyBox's SHA instruction auto-detection remains disabled
for our Cortex-A53 baseline. Debian base packages are official authenticated
binary packages, not rebuilt from source. Live Debian repositories and rolling
runner images mean separate build dates are not bit-for-bit reproducible; final
versions and hashes are recorded.

## Inputs and access

Supply one Ed25519 **public** key and an admin username (default dave). Input is
passed as environment data and validated, never interpolated into shell code.
No private key, access token or additional GitHub secret is required for the
build. The rescue image permits that key as root, as our current local image does.
The Debian root uses the supplied normal admin account with key-only SSH and
passwordless sudo; root SSH/password/keyboard-interactive login are disabled.

The image contains no generated SSH host private keys or build-machine ID.
An SSH dependency unit creates host keys once on the actual device and preserves
them on its persistent root. Only public authorized_keys are embedded. Keep your
private client key on your own machine.

The Debian root includes systemd-networkd configuration for usb0 at
192.168.77.1/24, serving host .2 without advertising a gateway/DNS. Future persistent
initramfs must create the USB gadget and coordinate network handoff. This workflow
does not implement that pending boot step. Journals are volatile and capped at
16MiB. fstab uses the existing device-specific userdata PARTUUID; no filesystem is
formatted or mounted on the modem by CI.

## Put the source in a repository

Only the files listed by scripts/ci/export-workflow.py are needed. Do not upload
backups, calibration, EDL programmers, prebuilt firmware, build directories,
client private keys or the whole workspace. A clean source bundle can be made
without including any of those:

```sh
python3 scripts/ci/export-workflow.py
```

Extract `build/github-actions-source.tar.gz` into a fresh checkout of your chosen
GitHub repository, review and commit it, then push the workflow to its default
branch. GitHub requires a workflow_dispatch workflow to exist on the default
branch to start it in the Actions UI. The bundle is source code/configuration
only; there are no device backups or generated keys in it.

Choose **Actions -> Debian ARM64 image -> Run workflow**, paste your public key
and choose your username. Or from this local workspace, after authenticating gh:

```sh
gh workflow run debian-arm64.yml --repo OWNER/REPO \
  -f admin_user=dave \
  -f ssh_public_key="$(cat build/rescue_ed25519.pub)"
```

Download `qmodem-debian13-arm64-<run number>` after success. Artifacts are retained
for 14 days and are not automatically published as releases. Public/private
repository visibility determines who can access builds/artifacts. Verify the
included SHA256SUMS locally and review before any future installation.

## Checks

The job runs local regression tests for key validation and artifact rejection,
builds real sources, then validates the Android image header/digest, ARM64 Image
magic, appended DTB, approved rescue public key, archive paths, complete checksums,
root footprint and absence of generated SSH/TLS private identities, enabled
passwords, machine IDs and build-only policy files. Upload is an explicit artifact
allowlist, never build/ or the workspace.

Local checks:

```sh
python3 scripts/ci/test_ci.py
python3 -m py_compile scripts/ci/*.py
bash -n scripts/ci/build-rootfs.sh scripts/pack-rescue.sh
sh -n deployment/debian-server-configure.sh
# If installed locally:
actionlint .github/workflows/debian-arm64.yml
```

Native debootstrap/root service configuration must still pass on an actual hosted
runner; local syntax/parser tests are not a successful cloud build or a modem
boot test. A repository target and valid GitHub authentication are needed to
publish/run it. The workflow does not need access to the local host or USB device.

The persistent-root initramfs, RAM systemd test and offline installation review are
documented in [PERSISTENT_ROOT.md](PERSISTENT_ROOT.md). Deployment is a separate,
explicitly approved operation; the Actions workflow does not flash a device.

Board Wi-Fi source support and private firmware import are documented in
[WIFI.md](WIFI.md). Default CI artifacts contain no OEM radio firmware or
board calibration.
