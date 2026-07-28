# MSPI — the multi-bit SPI bus

Sources: https://docs.zephyrproject.org/latest/hardware/peripherals/mspi.html
and https://docs.zephyrproject.org/latest/samples/drivers/mspi/index.html
(researched 2026-07-28)

MSPI is Zephyr's generic API for advanced multi-line SPI controllers with
command/address/data phases — **single, dual, quad, octal, and hex IO, SDR
and DDR data rates**, XIP (memory-mapped execution), and scrambling. Ambiq
MSPI is one of the in-tree controller families (also QSPI/OSPI/FlexSPI).

Key API: `mspi_config()` (controller), `mspi_dev_config()` (per-device
config from the datasheet: io mode, data rate, instruction/address
lengths, dummy cycles), `mspi_transceive()` with `mspi_xfer` /
`mspi_xfer_packet`, `mspi_register_callback()` (async,
`CONFIG_MSPI_ASYNC`), `mspi_xip_config()` / memory-map via
`CONFIG_MSPI_MEMMAP`, `mspi_timing_config()`.

Devicetree: controllers bind `mspi-controller.yaml`; devices sit on the
bus with `mspi-device.yaml` properties — `mspi-max-frequency`,
`mspi-io-mode` (e.g. `MSPI_IO_MODE_HEX_8_8_16`-class modes),
`mspi-data-rate`, `read-instruction`, `write-instruction`, `rx-dummy`,
`tx-dummy`, `ce-gpios`. Ambiq devices use the `ambiq,mspi-device` binding.

In-tree samples (all under `zephyr/samples/drivers/mspi/`):
- `mspi_async` — async MSPI transfers to a memory device
- `mspi_flash` — flash API over an MSPI NOR flash
- `mspi_timing_scan` — find timing for a device/board pair
- `mspi_throughput` — throughput measurement

Kconfig: `CONFIG_MSPI=y`, plus `CONFIG_MSPI_ASYNC`, `CONFIG_MSPI_MEMMAP`,
`CONFIG_MSPI_DMA` as needed.
