# The Zephyr SDK

Source: https://docs.zephyrproject.org/latest/develop/toolchains/zephyr_sdk.html
(researched 2026-07-28)

The SDK provides the cross toolchains (GNU or LLVM bundles; `minimal` has
host tools only) for ARM, RISC-V, x86, Xtensa, and more.

Install locations by convention — a directory named `zephyr-sdk-<version>`
under: Linux/macOS `$HOME`, `$HOME/.local`, `$HOME/.local/opt`, `/opt`,
`/usr/local`; Windows `%HOMEPATH%`, `%PROGRAMFILES%`.

Discovery order tools should follow:
1. `ZEPHYR_SDK_INSTALL_DIR` env var (may point at a parent holding several
   `zephyr-sdk-*` versions);
2. the CMake package registry (populated by the SDK's setup script);
3. scanning the standard locations above.

The SDK root carries an `sdk_version` file naming its exact version;
otherwise the directory name is the version. A missing SDK means builds
for real boards cannot run — report it, don't guess.
