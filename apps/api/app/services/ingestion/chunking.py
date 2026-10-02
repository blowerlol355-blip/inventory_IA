"""Troceado de páginas en fragmentos de ~N tokens con solapamiento.

Reglas:
- Un fragmento nunca cruza de una página a otra (la cita debe apuntar a una sola página).
- Se corta preferentemente entre bloques (párrafos, tablas); un bloque demasiado grande
  se parte por líneas y, en último caso, por palabras.
- Un título no queda suelto al final de un fragmento: pasa al siguiente.
- Cada fragmento nuevo empieza con la cola del anterior (solapamiento).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.services.ingestion.parsing import PageText

TokenCounter = Callable[[str], int]


def approx_tokens(text: str) -> int:
    """Estimación barata (~4 caracteres por token) para cuando no hay tokenizer."""
    return max(1, len(text) // 4)


@dataclass
class TextChunk:
    page: int
    index: int
    content: str


def _is_heading(text: str) -> bool:
    line = text.strip()
    return "\n" not in line and len(line) <= 80 and not line.endswith((".", ":", ";", ","))


def _split_to_fit(text: str, budget: int, count: TokenCounter) -> list[str]:
    """Parte un bloque en piezas de como máximo `budget` tokens."""
    if count(text) <= budget:
        return [text]
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if len(lines) > 1:
        return [piece for ln in lines for piece in _split_to_fit(ln, budget, count)]
    pieces: list[str] = []
    current: list[str] = []
    for word in text.split():
        if current and count(" ".join([*current, word])) > budget:
            pieces.append(" ".join(current))
            current = []
        current.append(word)
    if current:
        pieces.append(" ".join(current))
    return pieces


def _tail(units: list[str], overlap: int, count: TokenCounter) -> list[str]:
    """Últimas unidades del fragmento anterior que caben en `overlap` tokens."""
    tail: list[str] = []
    total = 0
    for unit in reversed(units):
        n = count(unit)
        if total + n > overlap:
            if not tail:  # unidad grande: tomar sus últimas palabras
                words = unit.split()
                kept: list[str] = []
                while words and count(" ".join([words[-1], *kept])) <= overlap:
                    kept.insert(0, words.pop())
                if kept:
                    tail.append(" ".join(kept))
            break
        tail.insert(0, unit)
        total += n
    return tail


def chunk_pages(
    pages: list[PageText],
    max_tokens: int = 500,
    overlap_tokens: int = 50,
    count: TokenCounter = approx_tokens,
) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for page in pages:
        for content in _chunk_text(page.text, max_tokens, overlap_tokens, count):
            chunks.append(TextChunk(page.page, len(chunks), content))
    return chunks


def _chunk_text(text: str, max_tokens: int, overlap_tokens: int, count: TokenCounter) -> list[str]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    units = [piece for b in blocks for piece in _split_to_fit(b, max_tokens, count)]

    out: list[str] = []
    current: list[str] = []
    current_tokens = 0
    fresh = 0  # unidades nuevas (no de solapamiento) en el fragmento actual
    for unit in units:
        n = count(unit)
        if fresh and current_tokens + n > max_tokens:
            carry: list[str] = []
            if fresh > 1 and _is_heading(current[-1]):
                carry = [current.pop()]
            out.append("\n\n".join(current))
            current = _tail(current, overlap_tokens, count) + carry
            current_tokens = sum(count(u) for u in current)
            fresh = len(carry)
        while current and current_tokens + n > max_tokens:
            # El solapamiento no puede impedir que la unidad quepa.
            current_tokens -= count(current.pop(0))
            fresh = min(fresh, len(current))
        current.append(unit)
        current_tokens += n
        fresh += 1
    if fresh:
        out.append("\n\n".join(current))
    return out
