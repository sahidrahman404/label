from pathlib import Path
import json
import os
import sqlite3
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import ValidationError

from app.layout import Settings, layout, warnings, pdf

BASE = Path(__file__).parent
DB = Path(os.environ.get("LABEL_DB", str(BASE.parent / "data" / "labels.sqlite3")))
lock = Lock()
templates = Environment(loader=FileSystemLoader(BASE / "templates"), autoescape=select_autoescape())
app = FastAPI(title="TJ 103 Guest Labels", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


def load():
    with lock:
        DB.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB) as db:
            db.execute("CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            row = db.execute("SELECT value FROM workspace WHERE id=1").fetchone()
    return Settings.model_validate_json(row[0]) if row else Settings()


def save(s):
    DB.parent.mkdir(parents=True, exist_ok=True)
    with lock, sqlite3.connect(DB) as db:
        db.execute("CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO workspace (id,value) VALUES (1,?)", (s.model_dump_json(),))


def render(name, **kwargs):
    return templates.get_template(name).render(**kwargs)


def preview(s, error=None):
    try:
        pages = layout(s)
        notices = warnings(s, pages)
    except ValueError as exc:
        pages, notices = [], []
        error = str(exc)
    return render("preview.html", s=s, pages=pages, notices=notices, error=error,
                  count=len(s.guests()), ready=s.measured and bool(s.guests()) and not error)


def patch(html):
    # Each data line is repeated to preserve multiline HTML in the SSE event.
    event = "event: datastar-patch-elements\ndata: selector #preview\ndata: mode outer\n"
    event += "".join(f"data: elements {line}\n" for line in html.splitlines()) + "\n"
    return StreamingResponse(iter([event]), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


def error_text(exc):
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str,e['loc'])) or 'Layout'}: {e['msg']}" for e in exc.errors())
    return str(exc)


@app.middleware("http")
async def local_only(request: Request, call_next):
    # Bind to loopback, and reject cross-origin writes and DNS rebinding hosts.
    if request.url.hostname not in {"localhost", "127.0.0.1", "testserver"}:
        return Response("Use localhost or 127.0.0.1", status_code=403)
    origin = request.headers.get("origin")
    if request.method == "POST" and origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
        return Response("Cross-origin write rejected", status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", response_class=HTMLResponse)
def index():
    s = load()
    return render("index.html", s=s, signals=json.dumps(s.model_dump()), preview=preview(s))


@app.post("/settings")
async def settings(request: Request):
    try:
        s = Settings.model_validate(await request.json())
        layout(s)  # Validate all names before saving or enabling PDF export.
        save(s)
        return patch(preview(s))
    except (ValidationError, ValueError) as exc:
        return patch(preview(load(), error_text(exc)))


@app.get("/labels.pdf")
def labels_pdf():
    s = load()
    if not s.measured or not s.guests():
        return Response("Confirm sheet measurements and save at least one guest first.", status_code=422)
    try:
        result = pdf(s)
    except ValueError as exc:
        return Response(str(exc), status_code=422)
    return Response(result, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="guest-labels.pdf"'})


@app.get("/calibration.pdf")
def calibration_pdf():
    return Response(pdf(load(), calibration=True), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="tj103-calibration.pdf"'})
