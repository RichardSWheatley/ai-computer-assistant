# Flashing and debugging

Source: https://docs.zephyrproject.org/latest/develop/west/build-flash-debug.html
(researched 2026-07-28)

- `west flash` deploys the current build (rebuilds first by default).
  Pick the tool with `--runner jlink|nrfjprog|pyocd|openocd`; list what a
  board supports with `west flash -H` from the build dir.
- `west debug` opens GDB against the board; `west debugserver` exposes a
  port for IDEs.
- Batch/device testing goes through twister's hardware map instead:
  `west twister --generate-hardware-map map.yaml` detects connected
  boards, ports, and runners; `--device-testing --hardware-map map.yaml`
  runs suites on them. Serial ports and probe ids always come from the
  generated map, never hardcoded.
- RTT and stateful serial interaction in tests belong to the pytest
  harness (pytest-twister-harness), keeping twister the single gate.
