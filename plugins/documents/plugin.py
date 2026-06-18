"""Documents plugin — generate Word (.docx) and Excel (.xlsx) files.

Opt-in (enabled=false); needs python-docx + openpyxl. Both write real, editable
files. See aica.business.docx_builder / xlsx_builder for the spec shapes.
"""

from aica.business.docx_builder import build_report
from aica.business.xlsx_builder import build_workbook
from aica.core.interfaces import Plugin, ToolResult, ToolSchema


class DocumentsPlugin(Plugin):
    name = "documents"

    def describe(self) -> list[ToolSchema]:
        return [
            ToolSchema("create_document",
                       "Build a Word .docx report. Pass a 'spec' (title, "
                       "sections with paragraphs/bullets/tables) and 'out' path.",
                       {"spec": "str", "out": "str=report.docx"}, "local_write"),
            ToolSchema("create_spreadsheet",
                       "Build an Excel .xlsx workbook. Pass a 'spec' (sheets with "
                       "headers/rows/optional chart) and 'out' path.",
                       {"spec": "str", "out": "str=workbook.xlsx"}, "local_write"),
        ]

    def invoke(self, tool: str, args: dict) -> ToolResult:
        spec = args.get("spec")
        if not isinstance(spec, dict):
            spec = {k: v for k, v in args.items() if k != "out"}
        try:
            if tool == "create_document":
                if not spec.get("title"):
                    return ToolResult(ok=False, error="create_document needs a 'title'")
                path = build_report(spec, str(args.get("out", "report.docx")))
                return ToolResult(ok=True, output=f"wrote document: {path}")
            if tool == "create_spreadsheet":
                if not spec.get("sheets"):
                    return ToolResult(ok=False, error="create_spreadsheet needs 'sheets'")
                path = build_workbook(spec, str(args.get("out", "workbook.xlsx")))
                return ToolResult(ok=True, output=f"wrote workbook: {path}")
            return ToolResult(ok=False, error=f"unknown tool {tool}")
        except Exception as exc:
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")


def create() -> Plugin:
    return DocumentsPlugin()
