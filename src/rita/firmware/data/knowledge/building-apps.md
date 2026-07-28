# Building Zephyr applications

Source: https://docs.zephyrproject.org/latest/develop/application/index.html
(researched 2026-07-28, Zephyr "latest" docs)

Three application types, by location:
- **Workspace application** (recommended): lives inside the west workspace
  but outside `zephyr/` — e.g. `zephyrproject/applications/my-app/`.
- **Freestanding application**: outside any west workspace; needs
  `ZEPHYR_BASE` or a CMake package lookup to find Zephyr.
- **Repository application**: inside the `zephyr/` tree itself (samples
  live this way; user apps should not).

A minimal application:

```
my-app/
├── CMakeLists.txt      # build entry point
├── prj.conf            # Kconfig fragment
├── src/main.c
└── app.overlay         # optional devicetree overlay (picked up by name)
```

CMakeLists.txt must call `find_package(Zephyr)` BEFORE `project()`; Zephyr's
build system creates the `app` CMake target that sources attach to:

```cmake
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(my_app)
target_sources(app PRIVATE src/main.c)
```

Build with `west build -b <board>` from the app directory (or pass the app
path: `west build -b <board> path/to/my-app`). `prj.conf` and `app.overlay`
are found by convention; extra Kconfig via `-DEXTRA_CONF_FILE=`, extra
overlays via `-DEXTRA_DTC_OVERLAY_FILE=`.
