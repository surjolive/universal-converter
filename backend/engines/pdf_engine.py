from pathlib import Path
from html import escape
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Preformatted
import shutil
import fitz


def text_to_pdf(input_path: Path, output_path: Path, settings: dict):
    text = input_path.read_text(encoding="utf-8", errors="replace")
    page = A4 if settings.get("page_size", "A4").upper() == "A4" else letter
    margin = float(settings.get("margin_mm", 15)) * mm
    orientation = settings.get("orientation", "portrait")
    if orientation == "landscape":
        page = tuple(reversed(page))
    doc = SimpleDocTemplate(str(output_path), pagesize=page, rightMargin=margin, leftMargin=margin,
                            topMargin=margin, bottomMargin=margin)
    styles = getSampleStyleSheet()
    story = [Preformatted(text, styles["Code"])]
    doc.build(story)
    return {"text_characters": len(text), "page_size": settings.get("page_size", "A4")}


def pdf_to_html(input_path: Path, output_path: Path, settings: dict):
    document = fitz.open(input_path)
    sections = []
    for page_number, page in enumerate(document, start=1):
        text = page.get_text("text").strip()
        escaped = escape(text)
        sections.append(f'<section><h2>Page {page_number}</h2><pre>{escaped}</pre></section>')
    document.close()
    output_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>PDF Text Preview</title><style>body{margin:0;font:15px/1.65 system-ui;color:#1f2937;background:#f4f5f2}main{max-width:900px;margin:32px auto;padding:24px}section{background:#fff;border:1px solid #dfe3da;margin:12px 0;padding:18px;border-radius:8px}h2{font-size:16px;margin:0 0 10px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.7 ui-monospace,monospace}</style></head><body><main>"
        + "".join(sections)
        + "</main></body></html>", encoding="utf-8"
    )
    return {"pages": len(sections), "mode": "text extraction"}


def pdf_passthrough(input_path: Path, output_path: Path, settings: dict):
    shutil.copyfile(input_path, output_path)
    with fitz.open(output_path) as document:
        page_count = document.page_count
    return {"pages": page_count, "mode": "preserved PDF"}


def txt_to_html(input_path: Path, output_path: Path, settings: dict):
    text = input_path.read_text(encoding="utf-8", errors="replace")
    escaped = escape(text)
    output_path.write_text(f"<!doctype html><html><head><meta charset='utf-8'></head><body><pre>{escaped}</pre></body></html>", encoding="utf-8")
    return {"characters": len(text)}
