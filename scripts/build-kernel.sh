#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
project_dir=$PWD
kernel_dir=$project_dir/src/linux-git
output_dir=$project_dir/build/linux
mkdir -p "$output_dir"
make -C "$kernel_dir" O="$output_dir" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- defconfig
config="$kernel_dir/scripts/config --file $output_dir/.config"
# Discard generic loadable drivers before disabling modules (otherwise m becomes y).
sed -i 's/^CONFIG_\([A-Z0-9_]*\)=m$/# CONFIG_\1 is not set/' "$output_dir/.config"
# Keep a small built-in-only Qualcomm kernel, with all USB access dependencies.
while read -r symbol; do
    [ "$symbol" = ARCH_QCOM ] || $config --disable "$symbol"
done < <(sed -n 's/^CONFIG_\(ARCH_[A-Z0-9_]*\)=y$/\1/p' "$output_dir/.config")
for symbol in MODULES DRM SOUND SND MEDIA_SUPPORT BT NFC PCI PCIEPORTBUS KVM VIRTUALIZATION DEBUG_INFO BPF_SYSCALL USB_DWC3 USB_DWC2 USB_MUSB_HDRC USB_XHCI_HCD USB_EHCI_HCD USB_OHCI_HCD QCOM_Q6V5_MSS QCOM_VENUS SCSI ATA NETDEVICES INPUT ACPI XEN EFI RANDOMIZE_BASE LOCALVERSION_AUTO; do
    $config --disable "$symbol"
done
for symbol in BLK_DEV_INITRD RD_GZIP DEVTMPFS DEVTMPFS_MOUNT TMPFS PROC_FS SYSFS NET INET UNIX PACKET TTY UNIX98_PTYS SERIAL_MSM SERIAL_MSM_CONSOLE USB USB_GADGET USB_CHIPIDEA USB_CHIPIDEA_UDC USB_CHIPIDEA_MSM PHY_QCOM_USB_HS EXTCON EXTCON_QCOM_SPMI_MISC CONFIGFS_FS USB_CONFIGFS USB_CONFIGFS_ECM MMC MMC_BLOCK MMC_SDHCI MMC_SDHCI_PLTFM MMC_SDHCI_MSM QCOM_SMEM QCOM_SMD_RPM QCOM_SPMI_PMIC QCOM_SPMI_TEMP_ALARM SPMI_MSM_PMIC_ARB REGULATOR_QCOM_SMD_RPM REGULATOR_QCOM_SPMI REGULATOR_FIXED_VOLTAGE PINCTRL_MSM8916 PINCTRL_QCOM_SPMI_PMIC MSM_GCC_8916 QCOM_CLK_RPM INTERCONNECT_QCOM_MSM8916; do
    $config --enable "$symbol"
done
# WCN3620 Wi-Fi; non-secure WCNSS loader supports the installed minimal TF-A.
for symbol in WIRELESS WLAN WLAN_VENDOR_ATH CFG80211 MAC80211 WCN36XX WCN36XX_DEBUGFS REMOTEPROC QCOM_WCNSS_PIL QCOM_WCNSS_CTRL QCOM_SMP2P QCOM_SMSM RFKILL FW_LOADER CRYPTO_AES CRYPTO_CCM CRYPTO_GCM; do
    $config --enable "$symbol"
done
$config --set-str LOCALVERSION '-qmodem-rescue'
$config --set-val NR_CPUS 4
$config --enable IPV6
$config --enable PSTORE_RAM --enable PSTORE_CONSOLE --enable PSTORE_PMSG
$config --enable POWER_RESET_QCOM_PON --enable INPUT --enable INPUT_MISC --enable INPUT_PM8941_PWRKEY
$config --enable NULL_TTY --enable NETDEVICES
$config --enable CPU_FREQ --enable CPUFREQ_DT --enable CPU_FREQ_STAT
$config --enable CPU_FREQ_GOV_SCHEDUTIL --enable CPU_FREQ_DEFAULT_GOV_SCHEDUTIL
$config --enable CPU_FREQ_GOV_USERSPACE --enable CPU_FREQ_GOV_ONDEMAND
$config --enable CPU_IDLE --enable CPU_IDLE_GOV_MENU
# The installed MSM8916 TF-A implements CPU_ON, but not CPU_OFF/CPU_SUSPEND.
# Use architectural WFI and do not expose unsupported power-down interfaces.
$config --disable ARM_PSCI_CPUIDLE --disable HOTPLUG_CPU
$config --disable SUSPEND --disable HIBERNATION
$config --enable QCOM_SPM --enable QCOM_SPMI_VADC
$config --enable THERMAL --enable CPU_THERMAL --enable QCOM_TSENS
$config --disable THERMAL_EMULATION
$config --enable HW_RANDOM --enable CRYPTO_DEV_QCOM_RNG
make -C "$kernel_dir" O="$output_dir" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
cp "$output_dir/.config" configs/kernel.config
make -C "$kernel_dir" O="$output_dir" ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j"${JOBS:-12}" Image.gz qcom/msm8916-qmodem-rescue.dtb
rm -f "$output_dir/.qmodem-checkpoint"
