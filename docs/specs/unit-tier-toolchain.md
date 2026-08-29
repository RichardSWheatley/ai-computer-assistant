# Unit tier on Zephyr's own ARM GCC — RITA installs it herself

The owner's rule: whatever compiler Zephyr uses, RITA uses. The unit tier
therefore compiles its per-function Unity tests with **arm-none-eabi-gcc**
(the same ARM GCC family Zephyr's toolchains are built from) — never a
foreign host compiler, and RITA never asks the user to install LLVM or
MinGW. If the toolchain is missing, RITA downloads and installs it
herself, exactly as she acquires CERBERUS and Unity.

**The unit tier does not touch Zephyr or west.** No CMake, no app
wrapper. `arm-none-eabi-gcc` is invoked directly on unity.c + the test
file + the sources under test; the binary runs directly under
`qemu-system-arm` (an ARM binary cannot execute on a PC), with Unity's
output arriving over semihosting and parsed exactly as before. Zephyr and
west remain the FINAL_TEST stage's business, unchanged.

## Behavior

- `firmware/toolchain.py`:
  - `detect_arm_gcc()` -> `ToolchainInfo(cc, source, root)`; order:
    RITA's own install (`~/.rita/toolchains/arm-none-eabi/bin`), PATH
    (`arm-none-eabi-gcc`), `GNUARMEMB_TOOLCHAIN_PATH`, then the Zephyr
    SDK's `arm-zephyr-eabi-gcc` (same family, already on the machine).
  - `detect_qemu()` -> qemu-system-arm from PATH or the Zephyr SDK's
    bundled host tools; None reported honestly.
  - `install_arm_gcc()` downloads the Arm GNU toolchain for this OS/arch
    into `~/.rita/toolchains/arm-none-eabi/`, extracts, and verifies
    `arm-none-eabi-gcc --version` runs. Honest `InstallResult` always.
  - Reachable as `rita toolchain install`, a Modules-page button, and an
    installer step guarded by a presence Check (updates never re-fetch).
- `unity.py`: `find_compiler(None)` resolves via `detect_arm_gcc()`;
  compile `-mcpu=arm926ej-s --specs=rdimon.specs`; run
  `qemu-system-arm -M versatilepb -cpu arm926 -nographic -audio none
  -semihosting -kernel <elf>`; parse with the existing regexes. The
  proven recipe (this container): 3 Tests 1 Failures detected, exit 1.
  `host_cc` stays as an explicit NATIVE override (binary runs directly)
  for development and CI speed.
- Diagnostics: an **ARM toolchain** check reporting the resolved gcc, its
  source, and the QEMU used; Unity's check reports the same toolchain.
- Missing toolchain/QEMU => the stage and checks report exactly what to
  press/run; never silently green, never "install LLVM".

## Acceptance criteria

- Detection honors the documented order and ignores unrelated native
  compilers present on the machine (CI runners ship clang).
- `install_arm_gcc()` produces a runnable gcc under ~/.rita/toolchains
  (verified by --version) or an honest failure naming the step.
- With ARM gcc + QEMU present (this container): the mini_unity fixture
  suite runs under QEMU with correct pass/fail counts, failures detected.
- Without them: `UnitResult.unavailable` with a reason naming
  `rita toolchain install` / the Modules button.
- The four CI failures are gone: unit-tier tests monkeypatch their
  toolchain surface instead of assuming the machine's contents.

## Acquisition addendum (v0.22.1)

The release is DERIVED from the Zephyr SDK's gcc (`{maj}.{min}.rel1` —
Arm's uniform naming, verified live); an unreadable SDK version is a
refusal, never a default. Downloads verify TLS via system trust first,
then RITA's bundled certifi CAs; verification is never disabled.

## Discovery addendum (v0.23.1)

SDK layouts rot like release tables: SDK 1.0 moved GNU toolchains to
`<sdk>/gnu/` and host tools to `<sdk>/hosttools/`. The SDK's gcc and
qemu are therefore FOUND by search (known layouts probed first, then a
bounded two-level glob — never a full tree walk), and the version is
read with `-dumpfullversion` (prose `--version` parsing regex-trapped
on SDK 1.0's `(Zephyr SDK 1.0.1)` parenthetical). Every failure carries
the probe's evidence: the SDK path searched, the gcc found, the raw
output that failed to parse.
