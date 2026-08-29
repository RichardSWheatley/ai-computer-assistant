"""The ARM toolchain: Zephyr's compiler family, acquired by RITA.

The owner's rule: whatever compiler Zephyr uses, RITA uses — and the
VERSION must match Zephyr's gcc. The unit tier compiles with
arm-none-eabi-gcc; when it's missing, RITA downloads the Arm GNU
toolchain release matching the Zephyr SDK's gcc version into
~/.rita/toolchains, exactly as she acquires CERBERUS and Unity. No LLVM,
no MinGW, nothing foreign — and never a silent skip.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import urllib.request as urllib_request
from dataclasses import dataclass
from pathlib import Path

from .cerberus_setup import InstallResult
from .install_guard import single_flight

def release_for(version: tuple[int, int]) -> str:
    """Arm GNU release name for a gcc (major, minor) — the naming is
    uniform (`{maj}.{min}.rel1`, verified against Arm's server), so it
    is DERIVED, never table-limited: a hardcoded table rots (it once
    topped out at 14.2 while the owner's SDK was on gcc 14.3, silently
    downloading a mismatched default — the opposite of the rule that
    RITA uses exactly Zephyr's compiler version)."""
    return f"{version[0]}.{version[1]}.rel1"

_BASE_URL = ("https://developer.arm.com/-/media/Files/downloads/gnu/"
             "{rel}/binrel/arm-gnu-toolchain-{rel}-{host}-arm-none-eabi{ext}")

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.\d+")


@dataclass(frozen=True)
class ToolchainInfo:
    cc: str                 # full path to arm-none-eabi-gcc (or -zephyr-)
    source: str             # "rita" | "path" | "gnuarmemb" | "sdk"
    root: str
    version: tuple[int, int] | None = None
    mismatch: bool = False  # True when Zephyr's gcc version is known and differs


def _rita_toolchain_dir() -> Path:
    from ..home import toolchains_dir

    return toolchains_dir() / "arm-none-eabi"


def _rita_roots() -> list[Path]:
    """Every RITA-installed toolchain root, newest first: the legacy
    `arm-none-eabi` dir plus versioned `arm-none-eabi-<release>` dirs —
    the fallback landing spots when an old dir can't be replaced."""
    from ..home import toolchains_dir

    roots = []
    base = toolchains_dir()
    for cand in [base / "arm-none-eabi"] + sorted(base.glob("arm-none-eabi-*")):
        if cand.is_dir() and any(
                (cand / "bin" / n).is_file()
                for n in ("arm-none-eabi-gcc", "arm-none-eabi-gcc.exe")):
            roots.append(cand)
    roots.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return roots


def _root_gcc(root: Path) -> Path:
    exe = root / "bin" / "arm-none-eabi-gcc.exe"
    return exe if exe.is_file() else root / "bin" / "arm-none-eabi-gcc"


def _run_cc(cc: str | Path, flag: str):
    """One version query. stdin is pinned to DEVNULL: windowed frozen
    apps on Windows can hand children an invalid stdin handle."""
    try:
        proc = subprocess.run([str(cc), flag], capture_output=True,
                              text=True, timeout=30,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return None, f"running `{cc} {flag}` failed: {exc}"
    return proc, (proc.stdout or "").strip()


def _gcc_version_raw(cc: str | Path) -> tuple[tuple[int, int] | None, str]:
    """(major.minor, raw evidence of the attempt).

    -dumpfullversion first — it prints the bare version (e.g. 14.3.0),
    immune to vendor text. The --version fallback strips parentheticals
    before parsing: SDK 1.0's line `arm-zephyr-eabi-gcc (Zephyr SDK
    1.0.1) 14.3.0` would otherwise match the SDK version 1.0 first."""
    last = ""
    for flag in ("-dumpfullversion", "-dumpversion"):
        proc, out = _run_cc(cc, flag)
        if proc is None:
            return None, out
        if proc.returncode == 0:
            m = re.match(r"(\d+)\.(\d+)", out)
            if m:
                return (int(m.group(1)), int(m.group(2))), out
        last = out or last
    proc, out = _run_cc(cc, "--version")
    if proc is None:
        return None, out
    line = (out.splitlines() or [""])[0]
    m = _VERSION_RE.search(re.sub(r"\([^)]*\)", "", line))
    if m:
        return (int(m.group(1)), int(m.group(2))), line
    return None, f"unparseable version output: {line or last!r}"


def _gcc_version(cc: str | Path) -> tuple[int, int] | None:
    """major.minor of a gcc; None when it can't run/parse."""
    return _gcc_version_raw(cc)[0]


_SDK_GCC_NAMES = ("arm-zephyr-eabi-gcc", "arm-zephyr-eabi-gcc.exe")


def _sdk_arm_gcc() -> Path | None:
    """The SDK's arm gcc, found by SEARCHING the SDK — never one
    assumed path. Layouts rot: 0.x kept toolchains at the SDK root,
    1.0 moved them under gnu/; a bounded glob catches whatever comes
    next without walking a multi-GB tree."""
    from .workspace import read_sdk_info

    sdk = read_sdk_info()
    if not sdk:
        return None
    root = Path(sdk["path"])
    for rel in ("arm-zephyr-eabi/bin", "gnu/arm-zephyr-eabi/bin"):
        for name in _SDK_GCC_NAMES:
            cand = root / rel / name
            if cand.is_file():
                return cand
    for pattern in ("*/arm-zephyr-eabi/bin", "*/*/arm-zephyr-eabi/bin"):
        for bindir in sorted(root.glob(pattern)):
            for name in _SDK_GCC_NAMES:
                cand = bindir / name
                if cand.is_file():
                    return cand
    # A layout even the search missed: the LEARNED machine fact (agent-
    # investigated, RITA-validated at discovery time, path re-checked).
    from ..learning import facts

    learned = facts.fact("sdk-arm-gcc")
    if learned and learned.get("path"):
        cand = Path(learned["path"])
        if cand.is_file():
            return cand
    return None


def zephyr_gcc_probe() -> tuple[tuple[int, int] | None, str]:
    """(the gcc version Zephyr builds with, evidence). The evidence is
    the trail — which SDK was searched, what was found, why reading it
    failed — so failure messages never make the owner guess."""
    from .workspace import read_sdk_info

    sdk = read_sdk_info()
    if not sdk:
        return None, ("no Zephyr SDK found (ZEPHYR_SDK_INSTALL_DIR is "
                      "unset and no zephyr-sdk-* directory is in the "
                      "standard locations)")
    cand = _sdk_arm_gcc()
    if cand is None:
        return None, (f"the Zephyr SDK at {sdk['path']} has no "
                      f"arm-zephyr-eabi gcc anywhere under it (searched "
                      f"arm-zephyr-eabi/bin, gnu/arm-zephyr-eabi/bin, "
                      f"and up to two directory levels deep) — a "
                      f"minimal or LLVM-only SDK bundle has no ARM GNU "
                      f"toolchain")
    ver, raw = _gcc_version_raw(cand)
    if ver is None:
        return None, f"found {cand} but could not read its version: {raw}"
    return ver, f"{cand} reports gcc {ver[0]}.{ver[1]}"


def zephyr_gcc_version() -> tuple[int, int] | None:
    """The gcc version Zephyr builds with on THIS machine (its SDK)."""
    cand = _sdk_arm_gcc()
    return _gcc_version(cand) if cand else None


def _candidates() -> list[tuple[str, Path]]:
    """(source, gcc path) in preference order; existence already checked."""
    out: list[tuple[str, Path]] = []
    for root in _rita_roots():
        out.append(("rita", _root_gcc(root)))
    found = shutil.which("arm-none-eabi-gcc")
    if found:
        out.append(("path", Path(found)))
    gnu = os.environ.get("GNUARMEMB_TOOLCHAIN_PATH")
    if gnu:
        for name in ("arm-none-eabi-gcc", "arm-none-eabi-gcc.exe"):
            cand = Path(gnu) / "bin" / name
            if cand.is_file():
                out.append(("gnuarmemb", cand))
                break
    # The SDK's arm-zephyr-eabi-gcc is deliberately NOT a candidate: it is
    # built FOR Zephyr, not a standalone compiler (the owner's rule). It
    # only sets the WANTED version via zephyr_gcc_version().
    return out


def detect_arm_gcc() -> ToolchainInfo | None:
    """First candidate whose gcc VERSION matches Zephyr's; if none match
    (or Zephyr's is unknown), the first candidate — with the mismatch
    recorded so reports can say so. Never an unrelated native compiler."""
    cands = _candidates()
    if not cands:
        return None
    want = zephyr_gcc_version()
    # A Zephyr SDK gcc that exists but can't report a version still means
    # there IS a version to match — an unverifiable match is surfaced.
    must_match = want is not None or _sdk_arm_gcc() is not None

    def info(source: str, cc: Path, matched: bool) -> ToolchainInfo:
        return ToolchainInfo(cc=str(cc), source=source,
                             root=str(cc.parent.parent),
                             version=_gcc_version(cc),
                             mismatch=not matched and must_match)

    if want is not None:
        for source, cc in cands:
            if _gcc_version(cc) == want:
                return info(source, cc, matched=True)
    source, cc = cands[0]
    return info(source, cc, matched=not must_match)


def detect_qemu() -> str | None:
    """qemu-system-arm: PATH first, then the Zephyr SDK's host tools."""
    found = shutil.which("qemu-system-arm")
    if found:
        return found
    from .workspace import read_sdk_info

    sdk = read_sdk_info()
    if sdk:
        # 0.x: sysroots/ at the SDK root. 1.0: hosttools/ — per-tool
        # dirs on Windows, a poky sysroot on Linux, opt/ on macOS.
        patterns = ("sysroots/*/usr/bin/qemu-system-arm*",
                    "hosttools/qemu*/qemu-system-arm*",
                    "hosttools/qemu*/bin/qemu-system-arm*",
                    "hosttools/sysroots/*/usr/bin/qemu-system-arm*",
                    "hosttools/opt/qemu/bin/qemu-system-arm*")
        for pattern in patterns:
            for cand in sorted(Path(sdk["path"]).glob(pattern)):
                if cand.is_file() and cand.suffix in ("", ".exe"):
                    return str(cand)
    from ..learning import facts

    learned = facts.fact("qemu-system-arm")
    if learned and learned.get("path") and Path(learned["path"]).is_file():
        return str(learned["path"])
    return None


def _host_tag() -> tuple[str, str]:
    """(host string, archive extension) for the Arm GNU release naming."""
    if os.name == "nt":
        return "mingw-w64-i686", ".zip"
    if sys.platform == "darwin":
        arch = os.uname().machine
        return ("darwin-arm64" if arch == "arm64" else "darwin-x86_64"), ".tar.xz"
    arch = os.uname().machine
    return ("aarch64" if arch in ("aarch64", "arm64") else "x86_64"), ".tar.xz"


def _ssl_contexts():
    """(name, ssl context) attempts, in order: system trust first — it
    honors the OS store and SSL_CERT_FILE, so corporate/proxy CAs keep
    working — then RITA's bundled Mozilla CA set (certifi), the rescue
    for frozen apps whose embedded OpenSSL can't see the OS store.
    Verification is NEVER disabled."""
    out = [("system", None)]
    try:
        import ssl

        import certifi

        out.append(("bundled CAs",
                    ssl.create_default_context(cafile=certifi.where())))
    except Exception:
        pass
    return out


def _open(url: str, *, byte_range: str | None = None):
    """Open a URL through the two-stage TLS chain (system trust, then
    RITA's bundled CAs). Shared by downloads and existence probes."""
    import ssl  # noqa: F401  (imported for the error types via helpers)

    headers = {"User-Agent": "rita-installer"}
    if byte_range:
        headers["Range"] = byte_range
    req = urllib_request.Request(url, headers=headers)
    last = None
    for _name, ctx in _ssl_contexts():
        try:
            return urllib_request.urlopen(req, timeout=120, context=ctx)
        except Exception as exc:
            if not _is_cert_error(exc):
                raise
            last = exc
    raise OSError(
        f"TLS certificate verification failed with the system "
        f"certificates AND RITA's bundled CA set ({last}). A security "
        f"product or proxy may be intercepting HTTPS — its certificate "
        f"must be installed in Windows' certificate store. Verification "
        f"is never disabled.")


def _exists(url: str) -> bool:
    """Does Arm actually publish this file? A one-byte ranged GET."""
    import urllib.error

    try:
        with _open(url, byte_range="bytes=0-0") as r:
            return getattr(r, "status", 200) in (200, 206)
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 403, 410):
            return False
        raise


def _url_for(release: str, archive_suffix: str | None = None) -> str:
    host, ext = _host_tag()
    if archive_suffix:
        ext = archive_suffix
    return _BASE_URL.format(rel=release, host=host, ext=ext)


def resolve_release_online(want: tuple[int, int]) -> tuple[str, bool]:
    """The release for the SDK's GCC branch, VERIFIED against Arm's
    server — probe the branch's revs and pick the newest that is
    actually published. Returns (release, verified). A probe that can't
    reach the network at all falls back to the derived rel1 unverified —
    the download itself will report any real problem."""
    found = None
    for rev in (1, 2, 3):
        rel = f"{want[0]}.{want[1]}.rel{rev}"
        if _exists(_url_for(rel)):
            found = rel                       # keep going: newest rev wins
    return found, True


def _is_cert_error(exc) -> bool:
    import ssl
    import urllib.error

    if isinstance(exc, ssl.SSLCertVerificationError):
        return True
    if isinstance(exc, urllib.error.URLError):
        return isinstance(getattr(exc, "reason", None),
                          ssl.SSLCertVerificationError)
    return False


def _download(url: str, dest: Path) -> None:
    req = urllib_request.Request(url, headers={"User-Agent": "rita-installer"})
    contexts = _ssl_contexts()
    last = None
    for _name, ctx in contexts:
        try:
            with urllib_request.urlopen(req, timeout=600, context=ctx) as r,                     dest.open("wb") as f:
                shutil.copyfileobj(r, f)
            return
        except Exception as exc:
            if not _is_cert_error(exc):
                raise
            last = exc
    raise OSError(
        f"TLS certificate verification failed with the system "
        f"certificates AND RITA's bundled CA set ({last}). A security "
        f"product or proxy may be intercepting HTTPS — its certificate "
        f"must be installed in Windows' certificate store. Verification "
        f"is never disabled.")


def _nap(seconds: float) -> None:  # injectable for tests
    import time

    time.sleep(seconds)


def _force_rmtree(path: Path) -> None:
    """rmtree that survives Windows weather: clears read-only on the
    blocked entry and retries the whole tree with backoff — antivirus
    scanners hold freshly written executables briefly, and read-only
    leftovers make bare rmtree fail with WinError 5."""
    def _unblock(func, p, _exc):
        os.chmod(p, 0o700)
        func(p)

    kwargs = ({"onexc": _unblock} if sys.version_info >= (3, 12)
              else {"onerror": _unblock})
    for attempt in range(3):
        try:
            shutil.rmtree(path, **kwargs)
            return
        except OSError:
            if attempt == 2:
                raise
            _nap(0.5 * (2 ** attempt))


def _replace_dir(src: Path, dst: Path) -> None:
    """One swap attempt: drop the old dst, rename src into place.
    Retried with backoff by the caller."""
    if dst.exists():
        _force_rmtree(dst)
    os.rename(str(src), str(dst))


def install_arm_gcc(release: str | None = None,
                    archive_suffix: str | None = None) -> InstallResult:
    """Download + extract the Arm GNU toolchain matching Zephyr's gcc.

    The release is chosen from the Zephyr SDK's gcc version when known
    (the owner's rule: versions must match); explicit `release` overrides.
    Single-flight: launch auto-setup, the Modules button, and the CLI
    can all fire this — only one may touch the disk at a time."""
    from .install_guard import already_running_detail

    with single_flight("the ARM toolchain") as mine:
        if not mine:
            return InstallResult(
                ok=False, path=str(_rita_toolchain_dir()),
                detail=already_running_detail("the ARM toolchain"))
        try:
            return _install_arm_gcc_locked(release, archive_suffix)
        except Exception as exc:
            # An installer must NEVER raise: an escaped exception loses
            # its traceback in the GUI and strands the user with one
            # bare line. Return it as evidence instead.
            import traceback

            tb = "".join(traceback.format_exception(exc)).strip()
            return InstallResult(
                ok=False, path=str(_rita_toolchain_dir()),
                detail=f"unexpected failure: {type(exc).__name__}: "
                       f"{exc}\n--- where ---\n{tb[-900:]}")


def _install_arm_gcc_locked(release: str | None,
                            archive_suffix: str | None) -> InstallResult:
    import tarfile
    import tempfile
    import zipfile

    dest = _rita_toolchain_dir()
    want = zephyr_gcc_version()
    if release is None:
        if want is None:
            _, evidence = zephyr_gcc_probe()
            return InstallResult(
                ok=False, path=str(dest),
                detail=f"I can't read your Zephyr SDK's gcc version, so "
                       f"I won't guess a toolchain — the versions must "
                       f"match. What I found: {evidence}. You can "
                       f"install a specific release with "
                       f"`rita toolchain install --release 14.3.rel1` "
                       f"(use your SDK's gcc major.minor).")
        try:
            release, verified = resolve_release_online(want)
        except OSError:
            # Probe unreachable (offline?): fall back to the derived name
            # unverified — the download itself will report any problem.
            release, verified = release_for(want), False
        if release is None:
            # The probe WORKED and Arm publishes nothing on this branch.
            return InstallResult(
                ok=False, path=str(dest),
                detail=f"developer.arm.com publishes no arm-none-eabi "
                       f"release for GCC {want[0]}.{want[1]} (probed "
                       f"rel1-rel3) — your SDK's branch has no matching "
                       f"standalone download. Install one manually or "
                       f"pass --release explicitly.")
    # Check BEFORE downloading: a RITA install already matching the
    # wanted GCC branch means there is nothing to do — the Install
    # button is idempotent, never a blind 1.5 GB re-download.
    branch = want
    if branch is None:
        m = re.match(r"^(\d+)\.(\d+)\.", release)
        branch = (int(m.group(1)), int(m.group(2))) if m else None
    if branch is not None:
        for root in _rita_roots():
            cc = _root_gcc(root)
            if _gcc_version(cc) == branch:
                return InstallResult(
                    ok=True, path=str(root),
                    detail=f"already installed: {cc} is gcc "
                           f"{branch[0]}.{branch[1]}, matching what's "
                           f"wanted — nothing to download.")
    _host, ext = _host_tag()
    if archive_suffix:
        ext = archive_suffix
    url = _url_for(release, archive_suffix)
    toolroot = dest.parent
    toolroot.mkdir(parents=True, exist_ok=True)
    for stale in toolroot.glob(".staging-*"):
        try:
            _force_rmtree(stale)
        except OSError:
            pass
    # Stage NEXT TO dest (same volume: the final step is one rename),
    # and verify the staged tree BEFORE the old install is touched — a
    # failure anywhere up to the swap leaves the existing toolchain
    # working.
    staging = toolroot / f".staging-arm-none-eabi-{os.getpid()}"
    try:
        with tempfile.TemporaryDirectory(prefix="rita-toolchain-") as tmp:
            archive = Path(tmp) / f"toolchain{ext}"
            _download(url, archive)
            extract = Path(tmp) / "x"
            if ext == ".zip":
                with zipfile.ZipFile(archive) as z:
                    z.extractall(extract)
            else:
                with tarfile.open(archive) as t:
                    t.extractall(extract, filter="tar")
            # The archive wraps everything in one release-named directory.
            roots = [p for p in extract.iterdir() if p.is_dir()]
            root = roots[0] if len(roots) == 1 else extract
            if not any((root / "bin" / n).is_file() for n in
                       ("arm-none-eabi-gcc", "arm-none-eabi-gcc.exe")):
                return InstallResult(
                    ok=False, path=str(dest),
                    detail="extracted, but bin/arm-none-eabi-gcc is "
                           "missing — wrong archive layout?")
            if staging.exists():
                _force_rmtree(staging)
            shutil.move(str(root), str(staging))
    except Exception as exc:
        return InstallResult(ok=False, path=str(dest),
                             detail=f"download/extract of {url} failed: {exc}")
    # The swap. Retried with backoff: antivirus scanners hold freshly
    # written executables briefly — that's weather, not an error.
    last: Exception | None = None
    for attempt in range(3):
        try:
            _replace_dir(staging, dest)
            last = None
            break
        except OSError as exc:
            last = exc
            _nap(0.5 * (2 ** attempt))
    if last is not None:
        # The old dir won't let go (AV hold, stuck partial install,
        # foreign ACLs). The verified download is NOT thrown away:
        # it lands under a fresh versioned name and detection flips to
        # it — deleting the blocked dir becomes best-effort cleanup.
        fallback = toolroot / f"arm-none-eabi-{release}"
        try:
            if fallback.exists():
                _force_rmtree(fallback)
            os.rename(str(staging), str(fallback))
            dest = fallback
        except OSError as exc:
            try:
                _force_rmtree(staging)
            except OSError:
                pass
            return InstallResult(
                ok=False, path=str(dest),
                detail=f"the new toolchain downloaded and verified, but "
                       f"I couldn't replace {dest} ({last}) or place it "
                       f"beside the old one ({exc}). A security scanner "
                       f"may be holding the folder — wait a minute and "
                       f"press Install again, or delete {dest} manually.")
    else:
        # Successful swap: sweep superseded roots, best-effort — the
        # just-installed dest is now the one and only. (In the fallback
        # path the old dir is KNOWN to be held; it is left for the next
        # successful run to sweep.)
        for old_root in _rita_roots():
            if old_root != dest and old_root.exists():
                try:
                    _force_rmtree(old_root)
                except OSError:
                    pass
    info = detect_arm_gcc()
    if info is None or info.source != "rita":
        return InstallResult(ok=False, path=str(dest),
                             detail="extracted, but bin/arm-none-eabi-gcc "
                                    "is missing — wrong archive layout?")
    ver = _gcc_version(info.cc)
    if want is not None and ver is not None and ver != want:
        return InstallResult(
            ok=False, path=str(dest),
            detail=f"downloaded gcc {ver[0]}.{ver[1]} but your Zephyr SDK "
                   f"is on {want[0]}.{want[1]} — refusing the mismatch")
    matched = (f", matching your Zephyr SDK's gcc {want[0]}.{want[1]} "
               f"(Arm's standalone builds report {want[0]}.{want[1]}.1 — "
               f"same GCC {want[0]}.{want[1]} branch as the SDK's "
               f"{want[0]}.{want[1]}.0)" if want is not None else "")
    return InstallResult(ok=True, path=str(dest),
                         detail=f"Arm GNU toolchain {release} installed at "
                                f"{dest} (gcc {ver or 'unverified'}"
                                f"){matched}")
