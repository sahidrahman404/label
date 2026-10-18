"""All geometry uses millimetres from the top-left of the backing sheet."""
from io import BytesIO
from pathlib import Path
from dataclasses import dataclass
import math

from pydantic import BaseModel, ConfigDict, Field, model_validator
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

STATIC = Path(__file__).parent / "static"
for name, filename in [("Label", "DejaVuSans.ttf"), ("Garamond", "EBGaramond-Regular.ttf"), ("Arial", "Arial.ttf")]:
    pdfmetrics.registerFont(TTFont(name, str(STATIC / filename)))


class Settings(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    names: str = Field(default="", max_length=100000)
    footer: str = Field(default="DI TEMPAT", max_length=150)
    # These are illustrative values only, until measurements are confirmed.
    width: float = Field(default=200, ge=100, le=216)
    height: float = Field(default=140, ge=100, le=356)
    left: float = Field(default=3, ge=0, le=50)
    top: float = Field(default=3, ge=0, le=50)
    gap_x: float = Field(default=1, ge=0, le=20)
    gap_y: float = Field(default=1, ge=0, le=20)
    offset_x: float = Field(default=0, ge=-20, le=20)
    offset_y: float = Field(default=0, ge=-20, le=20)
    start: int = Field(default=1, ge=1, le=12)
    measured: bool = False

    @model_validator(mode="before")
    @classmethod
    def remove_legacy_greeting(cls, value):
        if isinstance(value, dict):
            value = {key: item for key, item in value.items() if key != "greeting"}
        return value

    @model_validator(mode="after")
    def geometry(self):
        self.footer = " ".join(self.footer.split()).upper()
        if self.left + 3 * 64 + 2 * self.gap_x > self.width + 0.001:
            raise ValueError("The three columns extend beyond the sheet width.")
        if self.top + 4 * 32 + 3 * self.gap_y > self.height + 0.001:
            raise ValueError("The four rows extend beyond the sheet height.")
        if self.left + self.offset_x < 0 or self.top + self.offset_y < 0:
            raise ValueError("The print offset moves labels outside the sheet.")
        if self.left + 192 + 2*self.gap_x + self.offset_x > self.width + 0.001 or self.top + 128 + 3*self.gap_y + self.offset_y > self.height + 0.001:
            raise ValueError("The print offset moves labels outside the sheet.")
        return self

    def guests(self):
        return [line.strip() for line in self.names.splitlines() if line.strip()]

    def position(self, slot):
        return (self.left + (slot % 3) * (64 + self.gap_x) + self.offset_x,
                self.top + (slot // 3) * (32 + self.gap_y) + self.offset_y)


@dataclass
class TextLine:
    text: str
    font: str
    size: float
    x: float
    baseline: float


def wrap(text, font, size, width):
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if pdfmetrics.stringWidth(candidate, font, size) <= width:
            current = candidate
        elif current:
            lines.append(current)
            current = word
        else:
            current = word
    if current:
        lines.append(current)
    return lines


def typeset(name, s, x, y):
    """Shared font metrics and positions for SVG and PDF; never truncate names."""
    for text, font in [(name, "Garamond"), (s.footer, "Arial")]:
        unsupported = sorted({ch for ch in text if not ch.isspace() and ord(ch) not in pdfmetrics.getFont(font).face.charWidths})
        if unsupported:
            raise ValueError("Font does not support these characters: " + " ".join(unsupported))
    width = 58 * mm
    chosen = None
    for size in range(14, 7, -1):
        lines = wrap(name, "Garamond", size, width)
        shared_height = bool(s.footer.strip()) * 9 * 1.35
        total_height = shared_height + len(lines) * size * 1.35
        if len(lines) <= 3 and total_height <= 26 * mm and all(pdfmetrics.stringWidth(t, "Garamond", size) <= width for t in lines):
            chosen = (size, lines)
            break
    if chosen is None:
        raise ValueError(f"Name cannot fit at 8 pt: {name[:80]}")
    size, names = chosen
    blocks = []
    blocks.extend((t, "Garamond", size) for t in names)
    if s.footer.strip():
        blocks.append((s.footer.strip(), "Arial", 9))
    total = sum(pt * 1.35 for _, _, pt in blocks)
    if total > 26 * mm:
        raise ValueError(f"Text is too tall for label: {name[:80]}")
    cursor = y + (32 - total/mm) / 2
    result = []
    for text, font, pt in blocks:
        if pdfmetrics.stringWidth(text, font, pt) > width:
            raise ValueError("Location is too wide; shorten it.")
        cursor += pt / mm
        result.append(TextLine(text, font, pt, x + 32, cursor))
        cursor += pt * .35 / mm
    return result


def layout(s):
    guests = s.guests()
    pages = [[] for _ in range(max(1, math.ceil((len(guests) + s.start - 1)/12)))]
    for index, name in enumerate(guests, s.start - 1):
        page, slot = divmod(index, 12)
        x, y = s.position(slot)
        pages[page].append({"name": name, "slot": slot, "x": x, "y": y,
                            "lines": typeset(name, s, x, y)})
    return pages


def warnings(s, pages):
    result = []
    if not s.measured:
        result.append("Example measurements: measure your backing sheet, margins and gaps, then confirm below before exporting guest labels.")
    for page in pages:
        for label in page:
            for line in label["lines"]:
                half = pdfmetrics.stringWidth(line.text, line.font, line.size)/mm/2
                if line.x-half < 3 or line.x+half > s.width-3 or line.baseline-line.size/mm < 3 or line.baseline+1 > s.height-3:
                    result.append("Some text enters the printer’s 3 mm edge margin. Adjust the layout before printing.")
                    return result
    return result


def pdf(s, calibration=False):
    pages = layout(s) if not calibration else [[]]
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=(s.width*mm, s.height*mm))
    c.setTitle("TJ 103 calibration" if calibration else "Wedding guest labels")
    for page in pages:
        if calibration:
            for slot in range(12):
                x, y = s.position(slot)
                c.setStrokeColorRGB(.5, .5, .5)
                c.rect(x*mm, (s.height-y-32)*mm, 64*mm, 32*mm)
                c.setFont("Label", 10)
                c.drawCentredString((x+32)*mm, (s.height-y-12)*mm, f"Position {slot+1}")
                c.setFont("Label", 7)
                c.drawCentredString((x+32)*mm, (s.height-y-17)*mm, "64 × 32 mm")
                if slot == 0:
                    yy = (s.height-y-23)*mm
                    c.line((x+7)*mm, yy, (x+57)*mm, yy)
                    for xx in (x+7, x+57):
                        c.line(xx*mm, yy-2, xx*mm, yy+2)
                    c.drawCentredString((x+32)*mm, yy-9, "This line must measure 50 mm")
        else:
            for label in page:
                for line in label["lines"]:
                    c.setFont(line.font, line.size)
                    c.drawCentredString(line.x*mm, (s.height-line.baseline)*mm, line.text)
        c.showPage()
    c.save()
    return output.getvalue()
