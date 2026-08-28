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


def _gcc_version(cc: str | Path) -> tuple[int, int] | None:
    """major.minor from `<cc> --version`; None when it can't run/parse."""
    try:
        proc = subprocess.run([str(cc), "--version"], capture_output=True,
                              text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = _VERSION_RE.search(proc.stdout or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def _sdk_arm_gcc() -> Path | None:
    from .workspace import read_sdk_info

    sdk = read_sdk_info()
    if not sdk:
        return None
    for name in ("arm-zephyr-eabi-gcc", "arm-zephyr-eabi-gcc.exe"):
        cand = Path(sdk["path"]) / "arm-zephyr-eabi" / "bin" / name
        if cand.is_file():
            return cand
    return None


def zephyr_gcc_version() -> tuple[int, int] | None:
    """The gcc version Zephyr builds with on THIS machine (its SDK)."""
    cand = _sdk_arm_gcc()
    return _gcc_version(cand) if cand else None


def _candidates() -> list[tuple[str, Path]]:
    """(source, gcc path) in preference order; existence already checked."""
    out: list[tuple[str, Path]] = []
    exe = "arm-none-eabi-gcc.exe" if os.name == "nt" else "arm-none-eabi-gcc"
    own = _rita_toolchain_dir() / "bin" / exe
    if not own.is_file():
        own = _rita_toolchain_dir() / "bin" / "arm-none-eabi-gcc"
    if own.is_file():
        out.append(("rita", own))
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
    sdk = _sdk_arm_gcc()
    if sdk:
        out.append(("sdk", sdk))
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
        for cand in Path(sdk["path"]).glob("sysroots/*/usr/bin/qemu-system-arm*"):
            if cand.is_file() and cand.suffix in ("", ".exe"):
                return str(cand)
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


def install_arm_gcc(release: str | None = None,
                    archive_suffix: str | None = None) -> InstallResult:
    """Download + extract the Arm GNU toolchain matching Zephyr's gcc.

    The release is chosen from the Zephyr SDK's gcc version when known
    (the owner's rule: versions must match); explicit `release` overrides.
    """
    import tarfile
    import tempfile
    import zipfile

    dest = _rita_toolchain_dir()
    want = zephyr_gcc_version()
    if release is None:
        if want is None:
            return InstallResult(
                ok=False, path=str(dest),
                detail="I can't read your Zephyr SDK's gcc version, so I "
                       "won't guess a toolchain — the versions must match. "
                       "Check that your SDK has arm-zephyr-eabi/bin, or "
                       "install a specific release with "
                       "`rita toolchain install --release 14.3.rel1` "
                       "(use your SDK's gcc major.minor).")
        release = release_for(want)
    host, ext = _host_tag()
    if archive_suffix:
        ext = archive_suffix
    url = _BASE_URL.format(rel=release, host=host, ext=ext)
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
            if dest.exists():
                shutil.rmtree(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(root), str(dest))
    except Exception as exc:
        return InstallResult(ok=False, path=str(dest),
                             detail=f"download/extract of {url} failed: {exc}")
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
    matched = (f", matching your Zephyr SDK's gcc {want[0]}.{want[1]}"
               if want is not None else "")
    return InstallResult(ok=True, path=str(dest),
                         detail=f"Arm GNU toolchain {release} installed at "
                                f"{dest} (gcc {ver or 'unverified'}"
                                f"){matched}")
