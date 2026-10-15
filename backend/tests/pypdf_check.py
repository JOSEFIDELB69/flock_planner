"""Utilidades para validar PDFs generados (lectura con pypdf)."""

import io

from pypdf import PdfReader


def pdf_page_count(data: bytes) -> int:
    return len(PdfReader(io.BytesIO(data)).pages)


def pdf_text_sample(data: bytes, pages: int = 3) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages[:pages])


def pdf_metadata(data: bytes) -> dict:
    meta = PdfReader(io.BytesIO(data)).metadata or {}
    return {k: str(v) for k, v in meta.items()}
