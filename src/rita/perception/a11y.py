"""Accessibility-tree backends — the cheap, reliable way to 'see' the screen.

Reading the OS accessibility tree gives structured, labeled, addressable
elements with coordinates — far more robust than pixels. We prefer it and fall
back to vision/OCR only when it's empty (see docs/PERFORMANCE.md).

Backends (first pass: Windows + macOS):
  WindowsA11y — UI Automation via the `uiautomation` package.
  MacA11y     — AXUIElement via pyobjc (ApplicationServices).
  NullA11y    — headless / unsupported; returns no elements.

The OS traversals are lazily imported and fully guarded, so this module loads on
any platform. `find()` (label -> element) is pure and unit-tested; the OS walks
need on-device tuning.
"""

from __future__ import annotations

from .. import platform_support
from ..core.interfaces import Element

# Bound traversal so a deep UI tree can't stall perception.
_MAX_NODES = 400
_MAX_DEPTH = 8


class A11yBackend:
    """Base: subclasses implement `elements()`. `find()` is shared."""

    def elements(self) -> list[Element]:
        return []

    def find(self, label: str) -> Element | None:
        """Resolve a human label to an element (exact match, then substring)."""
        want = label.strip().lower()
        els = self.elements()
        for e in els:
            if e.label.strip().lower() == want:
                return e
        for e in els:
            if want and want in e.label.lower():
                return e
        return None


class NullA11y(A11yBackend):
    pass


class WindowsA11y(A11yBackend):
    """UI Automation traversal of the foreground window."""

    def elements(self) -> list[Element]:  # pragma: no cover - needs Windows
        try:
            import uiautomation as auto  # type: ignore
        except Exception:
            return []
        from collections import deque

        out: list[Element] = []
        try:
            root = auto.GetForegroundControl()
        except Exception:
            return out
        if root is None:
            return out

        queue = deque([(root, 0)])
        seen = 0
        while queue and seen < _MAX_NODES:
            ctrl, depth = queue.popleft()
            seen += 1
            try:
                rect = ctrl.BoundingRectangle
                name = (ctrl.Name or "").strip()
                role = ctrl.ControlTypeName or ""
                if name and rect and rect.width() > 0 and rect.height() > 0:
                    cx = (rect.left + rect.right) // 2
                    cy = (rect.top + rect.bottom) // 2
                    out.append(Element(label=name, role=role, x=cx, y=cy, source="a11y"))
            except Exception:
                pass
            if depth < _MAX_DEPTH:
                try:
                    for child in ctrl.GetChildren():
                        queue.append((child, depth + 1))
                except Exception:
                    pass
        return out


class MacA11y(A11yBackend):
    """AXUIElement traversal of the focused application (best-effort).

    Requires Accessibility permission (System Settings > Privacy). First-pass
    implementation — refine attribute extraction on-device.
    """

    def elements(self) -> list[Element]:  # pragma: no cover - needs macOS
        try:
            from ApplicationServices import (  # type: ignore
                AXUIElementCreateSystemWide,
                AXUIElementCopyAttributeValue,
                AXValueGetValue,
                kAXFocusedApplicationAttribute,
                kAXChildrenAttribute,
                kAXRoleAttribute,
                kAXTitleAttribute,
                kAXPositionAttribute,
                kAXSizeAttribute,
                kAXValueTypeCGPoint,
                kAXValueTypeCGSize,
            )
            import Quartz  # type: ignore  # noqa: F401
        except Exception:
            return []

        def attr(el, name):
            try:
                err, val = AXUIElementCopyAttributeValue(el, name, None)
                return val if err == 0 else None
            except Exception:
                return None

        out: list[Element] = []
        try:
            system = AXUIElementCreateSystemWide()
            app = attr(system, kAXFocusedApplicationAttribute)
            if app is None:
                return out
        except Exception:
            return out

        from collections import deque
        queue = deque([(app, 0)])
        seen = 0
        while queue and seen < _MAX_NODES:
            el, depth = queue.popleft()
            seen += 1
            try:
                title = attr(el, kAXTitleAttribute) or ""
                role = attr(el, kAXRoleAttribute) or ""
                pos = attr(el, kAXPositionAttribute)
                size = attr(el, kAXSizeAttribute)
                if title and pos is not None and size is not None:
                    okp, p = AXValueGetValue(pos, kAXValueTypeCGPoint, None)
                    oks, s = AXValueGetValue(size, kAXValueTypeCGSize, None)
                    if okp and oks:
                        cx = int(p.x + s.width / 2)
                        cy = int(p.y + s.height / 2)
                        out.append(Element(label=str(title), role=str(role),
                                           x=cx, y=cy, source="a11y"))
            except Exception:
                pass
            if depth < _MAX_DEPTH:
                children = attr(el, kAXChildrenAttribute) or []
                for child in children:
                    queue.append((child, depth + 1))
        return out


def get_a11y_backend() -> A11yBackend:
    os_name = platform_support.current_os()
    if os_name == platform_support.WINDOWS:
        return WindowsA11y()
    if os_name == platform_support.MACOS:
        return MacA11y()
    return NullA11y()
