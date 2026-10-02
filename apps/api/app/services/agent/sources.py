"""Fuentes numeradas y citas.

Los fragmentos recuperados se numeran [1..n] (la numeración continúa entre búsquedas de un
mismo turno); el modelo cita con esos números y el backend los traduce a {documento, página}.
Así la cita es verificable y no depende de que el modelo copie bien nombres de archivo.
"""

import re
import uuid
from dataclasses import dataclass
from html import escape
from typing import Any

from app.services.retrieval.search import RetrievedChunk

CITATION_RE = re.compile(r"\[(\d+(?:\s*[,\]\[]\s*\d+)*)\]")
SNIPPET_CHARS = 280


@dataclass
class Source:
    n: int
    document_id: uuid.UUID
    filename: str
    page: int
    snippet: str
    content: str
    content_type: str = ""

    def public(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "document_id": str(self.document_id),
            "filename": self.filename,
            "page": self.page,
            "snippet": self.snippet,
            "content_type": self.content_type,
        }


def build_sources(chunks: list[RetrievedChunk], start: int = 1) -> list[Source]:
    return [
        Source(
            n=i,
            document_id=c.document_id,
            filename=c.filename,
            page=c.page,
            snippet=" ".join(c.content.split())[:SNIPPET_CHARS],
            content=c.content,
            content_type=c.content_type,
        )
        for i, c in enumerate(chunks, start=start)
    ]


def format_sources(sources: list[Source]) -> str:
    parts = [
        f'<fuente id="{s.n}" documento="{escape(s.filename)}" pagina="{s.page}">\n'
        f"{s.content}\n</fuente>"
        for s in sources
    ]
    return "<fuentes>\n" + "\n".join(parts) + "\n</fuentes>"


def extract_citations(text: str, sources: list[Source]) -> list[dict[str, Any]]:
    """Fuentes efectivamente citadas en la respuesta, en orden de aparición."""
    by_n = {s.n: s for s in sources}
    cited: list[dict[str, Any]] = []
    seen: set[int] = set()
    for match in CITATION_RE.finditer(text):
        for number in re.findall(r"\d+", match.group(1)):
            n = int(number)
            if n in by_n and n not in seen:
                seen.add(n)
                cited.append(by_n[n].public())
    return cited
