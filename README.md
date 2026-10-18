# Wedding guest labels · TJ 103

Local guest-label printing with a **Datastar 1.0.4** UI, Python/FastAPI, SQLite, and ReportLab PDFs. Guest names and calibration stay on the computer running the app. No account, cloud service, frontend build, or runtime CDN connection is required.

## Start

Install [mise](https://mise.jdx.dev/getting-started.html), open a terminal in this directory, then:

```sh
mise trust
mise install
mise run setup
mise run dev
```

Open **http://127.0.0.1:8000**. Keep the terminal running; Ctrl+C stops the app.

On Windows use PowerShell and the Windows mise installation instructions. If using an activated Python environment instead of mise, `uv sync --frozen` and `uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000` are equivalent. Development on Linux is also supported; transfer the PDF to the Windows print computer if needed.

## Prepare the sheet

TJ 103 is configured as **3 columns × 4 rows**, each label **64 mm wide × 32 mm tall**. The backing sheet is **not assumed to be A4**. The initial 200 × 140 mm sheet, 3 mm margins and 1 mm gaps are **examples, not verified TJ sheet specifications**.

Measure with a ruler:

- Full backing sheet width and height, including unused edges.
- Left edge to the first label, and top edge to the first label.
- Gap between adjacent labels horizontally and vertically (not the distance between their left/top edges).

Enter these values, check the measurement confirmation, and click **Save & update preview**. If measuring pitch is easier, horizontal gap = left-edge-to-left-edge distance − 64 mm; vertical gap = top-edge-to-top-edge distance − 32 mm.

## Print reliably on Windows / Epson L300

1. Paste one guest or household per line. Blank lines are ignored; duplicates and order are preserved. Guest names use EB Garamond and the location uses Arial. The location is automatically uppercased; clear it to omit it. Labels have no greeting. Long names wrap and shrink down to 8 pt; text that still cannot fit is rejected for correction.
2. Save, then download the alignment test. In the Epson driver’s Printing Preferences, create a **User-Defined** paper size matching your measured backing sheet. Match orientation to the PDF; the app uses the 64 mm side of each label horizontally.
3. Use plain paper cut to the same size for the first test. Open the PDF in a viewer such as Adobe Acrobat Reader. Select the matching paper size, **Actual size / 100%**, one PDF page per sheet, single-sided. Disable Fit, Shrink, scaling, and borderless expansion. The app cannot set Windows printer-driver options for you.
4. Measure the test’s reference line: it must be **50 mm**. Hold the print against the label sheet under light to compare outlines. Positive offsets move the output right/down; negative values move it left/up. If drift increases across the sheet, correct gap measurements or scaling rather than applying a uniform offset.
5. Save corrected settings and repeat. Text should remain at least 3 mm inside the sheet edges; the app flags text near the printer margin. Calibration outlines close to an edge may be clipped by the printer.
6. Download guest labels. Load one complete label sheet at a time into the L300 rear feeder, printable side up, and position its edge guide gently. Check feeding, smearing, and ink drying on one sheet before printing the batch. Use label stock suitable for inkjet printing; custom-size support alone does not guarantee a particular adhesive stock will feed well.

PDFs have the exact saved sheet dimensions and embedded fonts. Production PDFs contain text only. Screen outlines and position numbers are calibration aids. Downloads always use the **last saved settings**; the Save button also validates every name.

First label position 1–12 skips preceding positions on the first page; later pages start at position 1. Only reuse partially used sheets if your label manufacturer permits refeeding and the sheet is intact and flat.

## Storage and development

`data/labels.sqlite3` stores one local workspace, including guest names and calibration. It is excluded from Git. Back up this file with the app stopped; delete it to reset the workspace. Override its location with `LABEL_DB`. The app binds to loopback by default and is designed for one operator. Initial dependency installation needs internet access; subsequent operation uses bundled assets.

```sh
mise run test
```

Tests cover PDF dimensions and pagination, coordinates and offsets, long/Unicode names, invalid geometry, escaped HTML, save/reload behavior, local request guards, and PDF endpoints. Physical feeding and alignment require the printing test above.

Local interfaces:

- `GET /` — server-rendered workspace.
- `POST /settings` — JSON settings; validates and saves, then returns a Datastar SSE patch for `#preview`. Validation errors return an error patch without changing saved state.
- `GET /labels.pdf` — production PDF; requires confirmed measurements and at least one saved name.
- `GET /calibration.pdf` — alignment PDF using saved geometry; available before measurement confirmation.

All geometry is in millimetres from the backing sheet’s top-left; shared layout/font metrics drive both SVG preview and PDF. Unsupported font characters must be replaced with supported spelling; the app checks each label against its bundled font and flags unsupported characters.

Third-party assets: Datastar 1.0.4 (MIT; see `app/static/DATASTAR-LICENSE.txt`), DejaVu Sans for the interface/calibration (see `app/static/FONT-LICENSE.txt`), EB Garamond (see `app/static/EBGaramond-OFL.txt`), and Microsoft Arial (see `app/static/ARIAL-LICENSE.txt`; complete original distribution retained in `vendor/arial32.exe`).

References: [Datastar](https://data-star.dev/), [Epson L300 manual](https://files.support.epson.com/docid/cpd4/cpd40789.pdf).
# label
