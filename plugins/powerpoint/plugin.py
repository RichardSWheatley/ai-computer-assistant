"""PowerPoint plugin — generate richly-designed .pptx decks.

Accepts a deck spec (see aica.business.pptx_builder) and writes a real, editable
PowerPoint file. Opt-in (enabled=false) because it needs python-pptx.
"""

from aica.business.pptx_builder import build_deck
from aica.core.interfaces import Plugin, ToolResult, ToolSchema


class PowerPointPlugin(Plugin):
    name = "powerpoint"

    def describe(self) -> list[ToolSchema]:
        return [ToolSchema(
            name="create_deck",
            description=(
                "Build a polished, editable PowerPoint (.pptx). Pass a 'spec' "
                "object with title/subtitle/theme and a 'slides' list (bullets, "
                "charts, section dividers, big-number slides) and an output path."
            ),
            parameters={"spec": "str", "out": "str=deck.pptx"},
            permission_tier="local_write",
        )]

    def invoke(self, tool: str, args: dict) -> ToolResult:
        if tool != "create_deck":
            return ToolResult(ok=False, error=f"unknown tool {tool}")
        spec = args.get("spec")
        if not isinstance(spec, dict):
            # allow the spec fields to be passed at the top level too
            spec = {k: v for k, v in args.items() if k != "out"}
        if not spec.get("title"):
            return ToolResult(ok=False, error="create_deck needs a deck spec with a 'title'")
        out = str(args.get("out", "deck.pptx"))
        try:
            path = build_deck(spec, out)
        except Exception as exc:
            return ToolResult(ok=False, error=f"deck build failed: {exc}")
        return ToolResult(ok=True, output=f"wrote deck: {path}")


def create() -> Plugin:
    return PowerPointPlugin()
