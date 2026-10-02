"""Detección del tipo real del archivo a partir de sus bytes (no de la extensión).

Los formatos binarios (PDF, Office, imágenes) se reconocen por su firma. CSV y TXT no
tienen firma: se aceptan solo si la extensión lo indica Y el contenido es texto válido.
"""

from pathlib import PurePath

import filetype

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
CSV = "text/csv"
TXT = "text/plain"
ZIP = "application/zip"
PNG = "image/png"
JPEG = "image/jpeg"
WEBP = "image/webp"
TIFF = "image/tiff"

IMAGE_TYPES = {PNG, JPEG, TIFF, WEBP}
TEXT_TYPES = {CSV, TXT}
BINARY_TYPES = {PDF, DOCX, XLSX, PPTX, *IMAGE_TYPES}
ALLOWED_TYPES = BINARY_TYPES | TEXT_TYPES

TEXT_EXTENSIONS = {".csv": CSV, ".txt": TXT, ".md": TXT}

EXTENSIONS = {
    PDF: "pdf",
    DOCX: "docx",
    XLSX: "xlsx",
    PPTX: "pptx",
    CSV: "csv",
    TXT: "txt",
    ZIP: "zip",
    PNG: "png",
    JPEG: "jpg",
    WEBP: "webp",
    TIFF: "tiff",
}


def decode_text(data: bytes) -> str | None:
    """Texto si los bytes son UTF-8 (o Latin-1 sin caracteres de control); si no, None."""
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
        controls = sum(1 for ch in text if ord(ch) < 32 and ch not in "\r\n\t")
        return text if controls == 0 else None


def detect_content_type(data: bytes, filename: str | None = None) -> str | None:
    """Devuelve el MIME real si está permitido; si no, None."""
    kind = filetype.guess(data)
    if kind is not None:
        mime: str = kind.mime
        return mime if mime in BINARY_TYPES else None
    extension = PurePath(filename or "").suffix.lower()
    if extension in TEXT_EXTENSIONS and decode_text(data) is not None:
        return TEXT_EXTENSIONS[extension]
    return None
