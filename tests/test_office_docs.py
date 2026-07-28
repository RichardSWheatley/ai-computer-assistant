"""Word + Excel builders produce real, openable files."""

import importlib.util
from pathlib import Path

import pytest

_PLUGINS = Path(__file__).resolve().parents[1] / "plugins"


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, str(file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_docx_report(tmp_path):
    docx = pytest.importorskip("docx")
    from rita.business.docx_builder import build_report
    spec = {
        "title": "Q3 Report", "subtitle": "Board",
        "sections": [
            {"heading": "Summary", "paragraphs": ["Revenue up."],
             "bullets": ["Point A", "Point B"]},
            {"heading": "Numbers",
             "table": {"headers": ["Metric", "Q2", "Q3"],
                       "rows": [["Revenue", "14", "19"]]}},
        ],
    }
    out = tmp_path / "r.docx"
    build_report(spec, str(out))
    assert out.exists() and out.stat().st_size > 0
    doc = docx.Document(str(out))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Q3 Report" in text and "Point A" in text
    assert len(doc.tables) == 1


def test_build_xlsx_workbook(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from rita.business.xlsx_builder import build_workbook
    spec = {"sheets": [{
        "name": "Revenue", "headers": ["Quarter", "Revenue"],
        "rows": [["Q1", 10], ["Q2", 14], ["Q3", 19]],
        "chart": {"kind": "bar", "title": "Revenue",
                  "categories_col": 1, "values_col": 2}}]}
    out = tmp_path / "w.xlsx"
    build_workbook(spec, str(out))
    assert out.exists()
    wb = openpyxl.load_workbook(str(out))
    ws = wb["Revenue"]
    assert ws["A1"].value == "Quarter" and ws["B4"].value == 19


def test_documents_plugin_dispatch(tmp_path):
    pytest.importorskip("docx")
    pytest.importorskip("openpyxl")
    mod = _load("documents_plugin", _PLUGINS / "documents" / "plugin.py")
    plugin = mod.create()
    d = plugin.invoke("create_document",
                      {"spec": {"title": "Hi", "sections": []},
                       "out": str(tmp_path / "d.docx")})
    assert d.ok and (tmp_path / "d.docx").exists()
    x = plugin.invoke("create_spreadsheet",
                      {"spec": {"sheets": [{"name": "S", "headers": ["a"],
                                            "rows": [[1]]}]},
                       "out": str(tmp_path / "x.xlsx")})
    assert x.ok and (tmp_path / "x.xlsx").exists()
    # missing required fields -> graceful error
    assert not plugin.invoke("create_document", {"spec": {}}).ok
