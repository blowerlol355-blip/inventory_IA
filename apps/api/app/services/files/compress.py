"""Compresión: empaquetar varios archivos en un ZIP o reducir el peso de un PDF o imagen.

Síncrono y de CPU: llamarlo con asyncio.to_thread.
"""

import io

import pymupdf
from PIL import Image

from app.services.files.convert import ConversionError, OutputFile, stem, zip_bytes
from app.services.ingestion.filetypes import EXTENSIONS, IMAGE_TYPES, JPEG, PDF, PNG, ZIP

# Imágenes dentro de un PDF por encima de este DPI se reducen a PDF_TARGET_DPI.
PDF_DPI_THRESHOLD = 150
PDF_TARGET_DPI = 110
JPEG_QUALITY = 70
MAX_IMAGE_SIDE = 1600


def make_zip(files: list[tuple[str, bytes]], name: str) -> OutputFile:
    if not files:
        raise ConversionError("No hay archivos para comprimir.")
    archive_name = name if name.lower().endswith(".zip") else f"{name}.zip"
    return OutputFile(archive_name, zip_bytes(files), ZIP)


def _reduce_pdf(data: bytes) -> bytes:
    pdf = pymupdf.open(stream=data, filetype="pdf")
    with pdf:
        pdf.rewrite_images(
            dpi_threshold=PDF_DPI_THRESHOLD, dpi_target=PDF_TARGET_DPI, quality=JPEG_QUALITY
        )
        buffer = io.BytesIO()
        pdf.save(buffer, garbage=4, deflate=True, clean=True)
    return buffer.getvalue()


def _reduce_image(data: bytes) -> tuple[bytes, str]:
    image = Image.open(io.BytesIO(data))
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    buffer = io.BytesIO()
    has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
    if has_alpha:
        # Con transparencia se mantiene PNG, con paleta de 256 colores.
        image.quantize(256).save(buffer, format="PNG", optimize=True)
        return buffer.getvalue(), PNG
    image.convert("RGB").save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buffer.getvalue(), JPEG


def reduce_size(data: bytes, content_type: str, filename: str) -> tuple[OutputFile, bool]:
    """Devuelve (archivo, se_redujo). Si la versión nueva no pesa menos, se devuelve el original."""
    if content_type == PDF:
        reduced, new_type = _reduce_pdf(data), PDF
    elif content_type in IMAGE_TYPES:
        reduced, new_type = _reduce_image(data)
    else:
        raise ConversionError(
            f"{filename}: solo se puede reducir el peso de PDFs e imágenes. "
            "Los archivos de Office ya vienen comprimidos; para agruparlos usa un ZIP."
        )
    if len(reduced) >= len(data):
        return OutputFile(filename, data, content_type), False
    name = f"{stem(filename)}_comprimido.{EXTENSIONS[new_type]}"
    return OutputFile(name, reduced, new_type), True
