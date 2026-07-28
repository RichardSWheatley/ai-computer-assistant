# west build / flash conventions

Source: https://docs.zephyrproject.org/latest/develop/west/build-flash-debug.html
(researched 2026-07-28)

- `west build -b <board> [-d <builddir>] [app_path]` — board resolution
  order: `-b` flag, `BOARD` env var, `build.board` config.
- Board qualifiers: `name/soc/variant` (e.g. `apollo510_evb/apollo510`,
  `nrf52840dk/nrf52840`). `west boards` lists them.
- `-p` / `--pristine=always` wipes the build dir first; `--pristine=auto`
  detects when a wipe is needed (use when the board may change).
- `-t <target>`: `run` (emulators), `clean`, `menuconfig`.
- `--sysbuild` for multi-image builds; `--domain <name>` selects one.
- CMake args after `--`: `west build -b b -- -DEXTRA_CONF_FILE=extra.conf`.
- `west flash [--runner jlink|nrfjprog|pyocd|openocd]` — rebuilds by
  default (`flash.rebuild` config). `west flash -H` lists runners for the
  built board.
- Useful config for automation: `west config build.dir-fmt
  "build/{board}/{app}"` keeps build dirs distinct per board.
