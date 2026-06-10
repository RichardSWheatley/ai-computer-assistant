"""Local control tests — perception fusion, a11y find, and the action tools.

All run headless: input/desktop are in dry-run (simulated), and perception uses
injected fake backends. The OS-specific a11y/capture walks need on-device
tuning, but the pure logic and tool wiring are covered here.
"""

from aica.action.desktop import DesktopController
from aica.action.input import InputController
from aica.core.interfaces import Element
from aica.perception.a11y import A11yBackend, NullA11y, get_a11y_backend
from aica.perception.desktop import DesktopPerception, fuse
from aica.plugins.computer_use import ComputerUsePlugin


class FakeA11y(A11yBackend):
    def __init__(self, els):
        self._els = els

    def elements(self):
        return self._els


def _els():
    return [
        Element("Save", "button", 100, 200, "a11y"),
        Element("Cancel", "button", 300, 200, "a11y"),
        Element("File name", "edit", 150, 50, "a11y"),
    ]


# --- perception ------------------------------------------------------------

def test_fuse_dedupes_by_label_and_position():
    a = [Element("OK", "button", 10, 10), Element("OK", "button", 11, 11)]
    merged = fuse(a, None)
    assert len(merged) == 1  # same label, same ~position bucket


def test_a11y_find_exact_then_substring():
    b = FakeA11y(_els())
    assert b.find("Save").x == 100
    assert b.find("file").label == "File name"   # case-insensitive substring
    assert b.find("nope") is None


def test_desktop_perception_observe_with_fake_backend():
    p = DesktopPerception(a11y=FakeA11y(_els()), capture=lambda: None)
    state = p.observe()
    assert len(state.elements) == 3
    assert "3 elements" in state.summary


def test_locate_returns_coordinates():
    p = DesktopPerception(a11y=FakeA11y(_els()), capture=lambda: None)
    assert p.locate("Cancel") == (300, 200)
    assert p.locate("missing") is None


def test_null_backend_when_unsupported(monkeypatch):
    import aica.perception.a11y as mod
    monkeypatch.setattr(mod.platform_support, "current_os", lambda: "Linux")
    assert isinstance(get_a11y_backend(), NullA11y)


# --- input (dry-run / simulated) ------------------------------------------

def test_input_simulates_when_dry_run():
    ic = InputController(dry_run=True)
    assert ic.click(5, 9).ok and "(5,9)" in ic.click(5, 9).output
    assert "ctrl+s" in ic.hotkey("ctrl", "s").output
    assert ic.double_click(1, 2).ok and ic.scroll(-3).ok and ic.press("enter").ok


def test_desktop_ops_simulated_when_dry_run():
    dc = DesktopController(dry_run=True)
    assert "Notepad" in dc.open_app("Notepad").output
    assert dc.focus_window("Editor").ok
    assert dc.clipboard_set("hi").ok and dc.clipboard_get().ok


# --- plugin dispatch -------------------------------------------------------

def test_plugin_exposes_rich_toolset():
    names = {s.name for s in ComputerUsePlugin().describe()}
    assert {"click", "click_label", "open_app", "scroll", "clipboard_get",
            "focus_window", "press", "double_click"} <= names


def test_click_label_resolves_via_locator():
    found = {"Save": (100, 200)}
    plugin = ComputerUsePlugin(
        InputController(dry_run=True),
        DesktopController(dry_run=True),
        locator=lambda label: found.get(label),
    )
    ok = plugin.invoke("click_label", {"label": "Save"})
    assert ok.ok and "(100,200)" in ok.output
    miss = plugin.invoke("click_label", {"label": "Nope"})
    assert not miss.ok and "not found" in miss.error


def test_click_label_without_locator_errors():
    plugin = ComputerUsePlugin(InputController(dry_run=True))
    res = plugin.invoke("click_label", {"label": "x"})
    assert not res.ok and "headless" in res.error


def test_open_app_tool_dispatch():
    plugin = ComputerUsePlugin(InputController(dry_run=True),
                               DesktopController(dry_run=True))
    res = plugin.invoke("open_app", {"name": "Notepad"})
    assert res.ok and "Notepad" in res.output
