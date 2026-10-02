"""Conversión de formatos en Python puro (sin LibreOffice ni binarios del sistema).

Las conversiones entre imágenes, PDF, CSV y Excel conservan el contenido completo. Las de
Office → PDF reconstruyen texto y tablas, no el diseño original (fuentes, colores, posiciones).

Todo es síncrono y de CPU: llamarlo con asyncio.to_thread.
"""

import csv
import io
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from pathlib import PurePath
from typing import Literal

import docx
import openpyxl
import pymupdf
from docx.table import Table
from PIL import Image

from app.services.ingestion.filetypes import (
    CSV,
    DOCX,
    EXTENSIONS,
    IMAGE_TYPES,
    JPEG,
    PDF,
    PNG,
    PPTX,
    TXT,
    WEBP,
    XLSX,
    ZIP,
)
from app.services.ingestion.parsing import ParsingError, parse_document, read_csv_rows

TargetFormat = Literal["pdf", "docx", "txt", "csv", "xlsx", "png", "jpg", "webp"]
TARGET_TYPES: dict[str, str] = {
    "pdf": PDF,
    "docx": DOCX,
    "txt": TXT,
    "csv": CSV,
    "xlsx": XLSX,
    "png": PNG,
    "jpg": JPEG,
    "webp": WEBP,
}
IMAGE_TARGETS = {"png": "PNG", "jpg": "JPEG", "webp": "WEBP"}
RENDER_DPI = 150
MAX_TABLE_ROWS = 2000

PDF_CSS = """
* { font-family: sans-serif; }
body { font-size: 10pt; color: #222; }
h1 { font-size: 16pt; } h2 { font-size: 13pt; } h3 { font-size: 11pt; }
table { border-collapse: collapse; width: 100%; margin: 6px 0; }
th, td { border: 1px solid #999; padding: 3px; font-size: 9pt; }
th { background-color: #eee; }
pre { font-family: monospace; font-size: 9pt; white-space: pre-wrap; }
"""


class ConversionError(Exception):
    pass


@dataclass
class OutputFile:
    filename: str
    data: bytes
    content_type: str


# --------------------------------------------------------------------------- utilidades


def stem(filename: str) -> str:
    return PurePath(filename).stem or "archivo"


def html_to_pdf(sections: list[str]) -> bytes:
    """Renderiza HTML a PDF A4. Cada sección empieza en una página nueva."""
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (40, 40, -40, -40)
    for html in sections or [""]:
        story = pymupdf.Story(html=html, user_css=PDF_CSS)
        more = True
        while more:
            device = writer.begin_page(mediabox)
            more, _ = story.place(where)
            story.draw(device)
            writer.end_page()
    writer.close()
    return buffer.getvalue()


def table_html(rows: list[list[str]], header: bool = True) -> str:
    if not rows:
        return "<p><i>(sin datos)</i></p>"
    shown = rows[:MAX_TABLE_ROWS]
    head = ""
    if header:
        head = "<tr>" + "".join(f"<th>{escape(c)}</th>" for c in shown[0]) + "</tr>"
        shown = shown[1:]
    body = "".join("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in r) + "</tr>" for r in shown)
    note = (
        f"<p><i>Se muestran {MAX_TABLE_ROWS} de {len(rows)} filas.</i></p>"
        if len(rows) > MAX_TABLE_ROWS
        else ""
    )
    return f"<table>{head}{body}</table>{note}"


def text_html(text: str) -> str:
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    return "".join(f"<p>{escape(p).replace(chr(10), '<br/>')}</p>" for p in paragraphs)


def zip_bytes(files: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in files:
            unique, n = name, 1
            while unique in used:
                path = PurePath(name)
                unique = f"{path.stem} ({n}){path.suffix}"
                n += 1
            used.add(unique)
            archive.writestr(unique, data)
    return buffer.getvalue()


def _text_of(data: bytes, content_type: str) -> str:
    try:
        parsed = parse_document(data, content_type)
    except ParsingError as exc:
        raise ConversionError(str(exc)) from exc
    if parsed.ocr_pages:
        raise ConversionError(
            "El documento es una imagen o un escaneo: conviértelo a PDF o a otra imagen; "
            "para extraer su texto, súbelo y pregunta por su contenido."
        )
    return parsed.full_text


def _docx_from_text(blocks: list[tuple[str | None, str]]) -> bytes:
    """blocks: (título opcional, texto). Cada bloque con título empieza en página nueva."""
    document = docx.Document()
    for index, (heading, text) in enumerate(blocks):
        if heading:
            if index:
                document.add_page_break()
            document.add_heading(heading, level=2)
        for paragraph in text.split("\n\n"):
            if paragraph.strip():
                document.add_paragraph(paragraph.strip())
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _sheets(data: bytes) -> list[tuple[str, list[list[str]]]]:
    workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheets = []
    for sheet in workbook.worksheets:
        rows = [
            ["" if v is None else str(v) for v in row]
            for row in sheet.iter_rows(values_only=True)
            if any(v is not None and str(v).strip() for v in row)
        ]
        sheets.append((sheet.title, rows))
    workbook.close()
    return sheets


def _csv_bytes(rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    # BOM para que Excel reconozca UTF-8 al abrir el CSV.
    return buffer.getvalue().encode("utf-8-sig")


def _xlsx_bytes(rows: list[list[str]], title: str) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = title[:31] or "Datos"
    for row in rows:
        sheet.append([_number_or_text(c) for c in row])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _number_or_text(value: str) -> float | int | str:
    cleaned = value.strip()
    try:
        return int(cleaned) if cleaned.lstrip("-").isdigit() else float(cleaned)
    except ValueError:
        return value


def _image_bytes(image: Image.Image, target: str) -> bytes:
    fmt = IMAGE_TARGETS[target]
    if fmt == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, quality=90)
    return buffer.getvalue()


# ----------------------------------------------------------------- conversiones por origen


def _from_pdf(data: bytes, name: str, target: str) -> OutputFile:
    pdf = pymupdf.open(stream=data, filetype="pdf")
    with pdf:
        if target in IMAGE_TARGETS:
            images = []
            for index in range(1, pdf.page_count + 1):
                pix = pdf[index - 1].get_pixmap(dpi=RENDER_DPI)
                image = Image.open(io.BytesIO(pix.tobytes("png")))
                images.append((f"{name}_p{index}.{target}", _image_bytes(image, target)))
            if len(images) == 1:
                return OutputFile(f"{name}.{target}", images[0][1], TARGET_TYPES[target])
            return OutputFile(f"{name}_{target}.zip", zip_bytes(images), ZIP)
        pages = [pdf[i].get_text("text", sort=True).strip() for i in range(pdf.page_count)]
    if not any(pages):
        raise ConversionError(
            "El PDF no tiene texto extraíble (es un escaneo). Súbelo como documento para que "
            "se lea con OCR, o conviértelo a imagen."
        )
    if target == "txt":
        text = "\n\n".join(f"--- Página {i} ---\n{t}" for i, t in enumerate(pages, start=1))
        return OutputFile(f"{name}.txt", text.encode("utf-8"), TXT)
    data_docx = _docx_from_text([(f"Página {i}", t) for i, t in enumerate(pages, start=1)])
    return OutputFile(f"{name}.docx", data_docx, DOCX)


def _from_docx(data: bytes, name: str, target: str) -> OutputFile:
    document = docx.Document(io.BytesIO(data))
    if target == "txt":
        return OutputFile(f"{name}.txt", _text_of(data, DOCX).encode("utf-8"), TXT)
    parts: list[str] = []
    # Párrafos y tablas en el orden real del documento.
    for item in document.iter_inner_content():
        if isinstance(item, Table):
            parts.append(
                table_html([[cell.text.strip() for cell in row.cells] for row in item.rows])
            )
            continue
        if not item.text.strip():
            continue
        style = (item.style.name if item.style is not None else "").lower()
        level = next((n for n in "123" if style in (f"heading {n}", f"título {n}")), None)
        if style == "title":
            level = "1"
        tag = f"h{level}" if level else "p"
        parts.append(f"<{tag}>{escape(item.text)}</{tag}>")
    return OutputFile(f"{name}.pdf", html_to_pdf(["".join(parts)]), PDF)


def _from_xlsx(data: bytes, name: str, target: str) -> OutputFile:
    sheets = [(title, rows) for title, rows in _sheets(data) if rows]
    if not sheets:
        raise ConversionError("La planilla está vacía.")
    if target == "csv":
        if len(sheets) == 1:
            return OutputFile(f"{name}.csv", _csv_bytes(sheets[0][1]), CSV)
        files = [(f"{name}_{title}.csv", _csv_bytes(rows)) for title, rows in sheets]
        return OutputFile(f"{name}_csv.zip", zip_bytes(files), ZIP)
    if target == "txt":
        return OutputFile(f"{name}.txt", _text_of(data, XLSX).encode("utf-8"), TXT)
    sections = [f"<h2>Hoja: {escape(title)}</h2>{table_html(rows)}" for title, rows in sheets]
    return OutputFile(f"{name}.pdf", html_to_pdf(sections), PDF)


def _from_csv(data: bytes, name: str, target: str) -> OutputFile:
    rows = read_csv_rows(_text_of(data, TXT))
    if not rows:
        raise ConversionError("El CSV está vacío.")
    if target == "xlsx":
        return OutputFile(f"{name}.xlsx", _xlsx_bytes(rows, name), XLSX)
    if target == "txt":
        return OutputFile(f"{name}.txt", _text_of(data, CSV).encode("utf-8"), TXT)
    return OutputFile(
        f"{name}.pdf", html_to_pdf([f"<h2>{escape(name)}</h2>{table_html(rows)}"]), PDF
    )


def _from_pptx(data: bytes, name: str, target: str) -> OutputFile:
    try:
        parsed = parse_document(data, PPTX)
    except ParsingError as exc:
        raise ConversionError(str(exc)) from exc
    if not parsed.full_text:
        raise ConversionError("La presentación no tiene contenido.")
    if target == "txt":
        return OutputFile(f"{name}.txt", parsed.full_text.encode("utf-8"), TXT)
    sections = []
    for page in parsed.pages:
        title, _, body = page.text.partition("\n")
        sections.append(f"<h1>{escape(title)}</h1>{text_html(body)}")
    return OutputFile(f"{name}.pdf", html_to_pdf(sections), PDF)


def _from_image(data: bytes, name: str, target: str) -> OutputFile:
    image = Image.open(io.BytesIO(data))
    if target == "pdf":
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PDF", resolution=RENDER_DPI)
        return OutputFile(f"{name}.pdf", buffer.getvalue(), PDF)
    return OutputFile(f"{name}.{target}", _image_bytes(image, target), TARGET_TYPES[target])


def _from_txt(data: bytes, name: str, target: str) -> OutputFile:
    text = _text_of(data, TXT)
    if not text:
        raise ConversionError("El archivo de texto está vacío.")
    if target == "docx":
        return OutputFile(f"{name}.docx", _docx_from_text([(None, text)]), DOCX)
    return OutputFile(f"{name}.pdf", html_to_pdf([f"<pre>{escape(text)}</pre>"]), PDF)


Converter = Callable[[bytes, str, str], OutputFile]

CONVERSIONS: dict[str, tuple[set[str], Converter]] = {
    PDF: ({"docx", "txt", "png", "jpg", "webp"}, _from_pdf),
    DOCX: ({"pdf", "txt"}, _from_docx),
    XLSX: ({"csv", "pdf", "txt"}, _from_xlsx),
    CSV: ({"xlsx", "pdf", "txt"}, _from_csv),
    PPTX: ({"pdf", "txt"}, _from_pptx),
    TXT: ({"pdf", "docx"}, _from_txt),
    **{t: ({"png", "jpg", "webp", "pdf"} - {EXTENSIONS[t]}, _from_image) for t in IMAGE_TYPES},
}


def supported_targets(content_type: str) -> list[str]:
    return sorted(CONVERSIONS.get(content_type, (set(), _from_txt))[0])


def convert(data: bytes, content_type: str, filename: str, target: str) -> OutputFile:
    if content_type not in CONVERSIONS:
        raise ConversionError(f"No sé convertir archivos de tipo {content_type}.")
    targets, converter = CONVERSIONS[content_type]
    if target not in targets:
        options = ", ".join(sorted(targets)) or "ninguno"
        raise ConversionError(
            f"{filename} no se puede convertir a {target}. Formatos posibles: {options}."
        )
    try:
        return converter(data, stem(filename), target)
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(
            f"No se pudo convertir {filename}: archivo dañado o ilegible"
        ) from exc
