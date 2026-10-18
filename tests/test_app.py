from io import BytesIO
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pypdf import PdfReader
from reportlab.lib.units import mm

from app import main
from app.layout import Settings, layout, pdf, typeset, warnings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB", tmp_path / "labels.sqlite3")
    return TestClient(main.app)


def configured(**kwargs):
    return Settings(measured=True, **kwargs)


@pytest.mark.parametrize("count,pages", [(1,1),(12,1),(13,2)])
def test_pdf_pagination_and_embedded_font(count, pages):
    s = configured(names="\n".join(f"Guest {i}" for i in range(count)))
    doc = PdfReader(BytesIO(pdf(s)))
    assert len(doc.pages) == pages
    assert float(doc.pages[0].mediabox.width) == pytest.approx(s.width*mm, abs=.001)
    assert float(doc.pages[0].mediabox.height) == pytest.approx(s.height*mm, abs=.001)
    assert "Guest 0" in doc.pages[0].extract_text()
    fonts = doc.pages[0]["/Resources"]["/Font"]
    assert any("/FontDescriptor" in f.get_object() for f in fonts.values())


def test_order_blanks_duplicates_and_start():
    s = configured(names="  André  \n\nSiti\nAndré\n", start=12)
    pages = layout(s)
    assert pages[0][0]["slot"] == 11
    assert [x["name"] for p in pages for x in p] == ["André", "Siti", "André"]
    assert pages[1][0]["slot"] == 0
    assert s.position(11) == (133, 102)


def test_offsets_and_consistent_rendering():
    s = configured(names="Siti Rahma", offset_x=1, offset_y=2)
    item = layout(s)[0][0]
    assert (item["x"],item["y"]) == (4,5)
    assert item["lines"] == typeset("Siti Rahma", s, 4, 5)
    assert all(line.x == 36 for line in item["lines"])


def test_long_names_wrap_or_fail():
    s = configured(names="Bapak Muhammad Abdul Rahman dan Keluarga Besar")
    assert len([x for x in layout(s)[0][0]["lines"] if x.font == "Garamond"]) >= 2
    with pytest.raises(ValueError, match="cannot fit"):
        layout(configured(names="X"*300))
    with pytest.raises(ValueError, match="too wide"):
        layout(configured(names="Siti", footer="Long location "*10))


@pytest.mark.parametrize("kwargs", [dict(width=190),dict(height=125),dict(offset_x=-10),dict(offset_y=20),dict(width=float('nan')),dict(start=13)])
def test_invalid_geometry(kwargs):
    with pytest.raises(ValidationError):
        configured(**kwargs)


def test_calibration_and_production():
    s = configured(names="José & Siti")
    calibration = PdfReader(BytesIO(pdf(s, True)))
    text = calibration.pages[0].extract_text()
    assert "Position 12" in text and "50 mm" in text
    production = PdfReader(BytesIO(pdf(s)))
    assert "José & Siti" in production.pages[0].extract_text()
    assert "Position" not in production.pages[0].extract_text()
    assert warnings(Settings(), layout(Settings()))


def test_endpoints_and_persistence(client):
    home = client.get("/")
    assert home.status_code == 200
    assert 'data-bind="names"' in home.text
    assert client.get("/static/datastar.js").text.startswith("// Datastar v1.0.4")
    assert client.get("/labels.pdf").status_code == 422
    body = configured(names="André\nSiti").model_dump()
    response = client.post("/settings", json=body)
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: datastar-patch-elements" in response.text
    assert "2 guests" in response.text
    assert "André" in client.get("/").text
    assert main.load().names == body["names"]
    with sqlite3.connect(main.DB) as db:
        assert json.loads(db.execute("SELECT value FROM workspace").fetchone()[0])["names"] == body["names"]
    assert client.get("/labels.pdf").content.startswith(b"%PDF")
    assert client.get("/calibration.pdf").content.startswith(b"%PDF")


def test_invalid_update_does_not_overwrite_saved_state(client):
    client.get("/")
    good = configured(names="Siti").model_dump()
    client.post("/settings", json=good)
    bad = {**good, "names":"New name", "width":180}
    response = client.post("/settings", json=bad)
    assert "Update needs attention" in response.text
    assert "href=\"/labels.pdf\"" not in response.text
    assert main.load().names == "Siti"


def test_escape_text_and_request_guards(client):
    client.get("/")
    body = configured(names="<script>alert(1)</script>").model_dump()
    response = client.post("/settings", json=body)
    assert "&lt;script&gt;" in response.text
    assert "<script>alert" not in response.text
    assert client.post("/settings", json=body, headers={"Origin":"https://example.com"}).status_code == 403
    assert client.get("/", headers={"Host":"evil.example"}).status_code == 403


def test_first_request_can_save_and_unsupported_glyphs_fail(client):
    body = configured(names="Rahman").model_dump()
    response = client.post("/settings", json=body)
    assert "1 guest" in response.text
    assert main.load().names == "Rahman"
    body["names"] = "Guest \U0001f9d1"
    response = client.post("/settings", json=body)
    assert "does not support" in response.text
    assert main.load().names == "Rahman"


def test_label_typography_and_legacy_settings(client):
    body = configured(names="André & Siti", footer="  di tempat  ").model_dump()
    body["greeting"] = "Kepada Yth."
    response = client.post("/settings", json=body)
    assert 'font-family="Garamond"' in response.text
    assert 'font-family="Arial"' in response.text
    assert "Kepada Yth." not in response.text
    assert "DI TEMPAT" in response.text
    saved = main.load()
    assert saved.footer == "DI TEMPAT"
    assert "greeting" not in saved.model_dump()
    lines = layout(saved)[0][0]["lines"]
    assert [(line.text, line.font) for line in lines] == [("André & Siti", "Garamond"), ("DI TEMPAT", "Arial")]
    doc = PdfReader(BytesIO(pdf(saved)))
    assert "Kepada Yth." not in doc.pages[0].extract_text()
    assert "DI TEMPAT" in doc.pages[0].extract_text()
    fonts = [f.get_object() for f in doc.pages[0]["/Resources"]["/Font"].values()]
    assert any("Garamond" in f["/BaseFont"] for f in fonts)
    assert any("Arial" in f["/BaseFont"] for f in fonts)
    assert 'id="greeting"' not in client.get("/").text
