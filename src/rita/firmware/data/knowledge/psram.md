# PSRAM over MSPI

Sources: https://docs.zephyrproject.org/latest/hardware/peripherals/mspi.html,
https://docs.zephyrproject.org/latest/build/dts/api/bindings/mspi/ambiq,mspi-device.html,
in-tree `drivers/memc/` (researched 2026-07-28)

External PSRAM attaches as an **MSPI device driven by a `memc` (memory
controller) driver**. In-tree example: `drivers/memc/memc_mspi_aps6404l.c`
— the APS6404L quad-SDR PSRAM (up to ~100 MHz, 8 MB) usable for XIP on
SoCs that support it. Higher-width parts (octal/**hex-mode** PSRAM, e.g.
APS-family x16 devices on Ambiq Apollo5) follow the same shape: a memc
driver configuring the device over the MSPI bus, then memory-mapped use.

Recipe for a PSRAM app on an MSPI controller (e.g. MSPI0):

1. Devicetree overlay: enable the controller node (`&mspi0`), add the
   PSRAM child with the right binding (`ambiq,mspi-device` on Ambiq),
   `mspi-io-mode` set to the wide mode (quad/octal/hex), `mspi-max-frequency`,
   dummy cycles and instruction settings from the datasheet.
2. `prj.conf`: `CONFIG_MSPI=y`, the memc driver's Kconfig
   (`CONFIG_MEMC=y` + device-specific symbol), `CONFIG_MSPI_MEMMAP=y` for
   XIP/memory-mapped access.
3. Code: either the memc-mapped region directly, or raw
   `mspi_transceive()` for explicit reads/writes; async via
   `CONFIG_MSPI_ASYNC` and `mspi_register_callback()`.
4. Verify with a ztest that writes/reads back patterns across the mapped
   region (twister-gated; `platform_allow` the target board).

Timing is per-board — `samples/drivers/mspi/mspi_timing_scan` finds
working timing values for a device/board pair.
