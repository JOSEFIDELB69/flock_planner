"""Extracción de texto de documentos de requisitos (.txt, .md, .csv, .docx, .pdf).

El contenido se trata siempre como datos: no se ejecutan macros, scripts ni enlaces. Protecciones:
* .docx se lee como XML dentro del ZIP (sin macros; .docm/.doc se rechazan) con límite de tamaño descomprimido;
* .pdf se lee con pypdf (no ejecuta JavaScript); se rechazan PDF cifrados y se limita la cantidad de páginas;
* el texto extraído se recorta a MAX_TEXT_CHARS.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from app.errors import AppError

MAX_TEXT_CHARS = 100_000
MAX_DOCX_XML_BYTES = 30_000_000
MAX_PDF_PAGES = 300
TEXT_EXT = {".txt", ".text", ".md", ".markdown", ".csv", ".tsv", ".log"}
DOC_EXT = {".docx", ".pdf"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass
class Extracted:
    text: str
    kind: str
    pages: int | None = None
    warnings: list[str] = field(default_factory=list)


def _unsupported(msg: str) -> AppError:
    return AppError(msg, code="unsupported_file", status_code=415)


def _unreadable(msg: str) -> AppError:
    return AppError(msg, code="unreadable_file", status_code=422)


def _text_file(data: bytes) -> str:
    if b"\x00" in data:
        raise _unsupported("El archivo no parece ser de texto.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _looks_like_text(data: bytes) -> bool:
    """Texto plano: sin bytes nulos, decodificable y con muy pocos caracteres de control."""
    if not data or b"\x00" in data[:65536]:
        return False
    sample = data[:65536]
    try:
        text = sample.decode("utf-8")
    except UnicodeDecodeError:
        text = sample.decode("latin-1")  # siempre decodifica; un binario se delata por sus caracteres de control
    control = sum(1 for ch in text if (ord(ch) < 32 and ch not in "\n\r\t\f") or 0x7F <= ord(ch) < 0xA0)
    return control <= max(1, len(text) // 200)


def _docx(data: bytes) -> Extracted:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise _unreadable("El archivo Word está dañado o no es un .docx válido.")
    with zf:
        names = set(zf.namelist())
        if "word/document.xml" not in names:
            raise _unreadable("El archivo no tiene el contenido de un documento Word (.docx).")
        if "word/vbaProject.bin" in names:
            raise _unsupported("El documento contiene macros. Guardalo como .docx sin macros y volvé a subirlo.")
        info = zf.getinfo("word/document.xml")
        if info.file_size > MAX_DOCX_XML_BYTES:
            raise _unreadable("El documento Word es demasiado grande para procesarlo.")
        xml = zf.read("word/document.xml")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise _unreadable("No pudimos leer el contenido del documento Word.")
    body = root.find(f"{W}body")
    if body is None:
        raise _unreadable("El documento Word está vacío.")
    lines: list[str] = []

    def para_text(p: ET.Element) -> str:
        parts: list[str] = []
        for node in p.iter():
            if node.tag == f"{W}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{W}tab":
                parts.append("\t")
            elif node.tag in (f"{W}br", f"{W}cr"):
                parts.append(" ")
        return "".join(parts).strip()

    def is_list(p: ET.Element) -> bool:
        ppr = p.find(f"{W}pPr")
        if ppr is None:
            return False
        if ppr.find(f"{W}numPr") is not None:
            return True
        style = ppr.find(f"{W}pStyle")
        val = (style.get(f"{W}val") or "").lower() if style is not None else ""
        return any(k in val for k in ("list", "vineta", "viñeta"))  # ListParagraph, Lista, Viñeta…

    for block in body:
        if block.tag == f"{W}p":
            text = para_text(block)
            if not text:
                lines.append("")
            elif is_list(block):
                lines.append(f"- {text}")
            else:
                lines.append(text)
        elif block.tag == f"{W}tbl":
            # cada fila de tabla se toma como una línea con sus celdas separadas por " | "
            for row in block.iter(f"{W}tr"):
                cells = [" ".join(para_text(p) for p in cell.iter(f"{W}p")).strip() for cell in row.iter(f"{W}tc")]
                cells = [c for c in cells if c]
                if cells:
                    lines.append("- " + " | ".join(cells))
            lines.append("")
    text = "\n".join(lines)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    if not text.strip():
        raise _unreadable("El documento Word no tiene texto.")
    return Extracted(text=text.strip(), kind="Word (.docx)")


def _pdf(data: bytes) -> Extracted:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
    except (PdfReadError, ValueError, OSError):
        raise _unreadable("El PDF está dañado o no se puede leer.")
    if reader.is_encrypted:
        raise _unreadable("El PDF está protegido con contraseña. Quitá la protección y volvé a subirlo.")
    warnings: list[str] = []
    total = len(reader.pages)
    pages = reader.pages[:MAX_PDF_PAGES]
    if total > MAX_PDF_PAGES:
        warnings.append(f"Se leyeron las primeras {MAX_PDF_PAGES} de {total} páginas.")
    chunks: list[str] = []
    for page in pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - una página ilegible no invalida el resto
            warnings.append("Algunas páginas no se pudieron leer.")
    text = "\n\n".join(c.strip() for c in chunks if c and c.strip())
    if not text.strip():
        raise _unreadable("El PDF no tiene texto seleccionable (parece escaneado o es una imagen). "
                          "Exportalo con texto o pegá el contenido en el cuadro de texto.")
    return Extracted(text=text, kind="PDF", pages=total, warnings=warnings)


def extract_text(filename: str, data: bytes) -> Extracted:
    name = (filename or "").lower()
    ext = name[name.rfind("."):] if "." in name else ""
    if ext == ".doc":
        raise _unsupported("El formato .doc (Word 97-2003) no está soportado. Guardalo como .docx y volvé a subirlo.")
    if ext == ".docm":
        raise _unsupported("Los documentos con macros (.docm) no están permitidos. Guardalo como .docx.")
    if ext in TEXT_EXT:
        result = Extracted(text=_text_file(data), kind=ext[1:].upper())
    elif ext == ".docx":
        if not data.startswith(b"PK"):
            raise _unreadable("El archivo no es un .docx válido.")
        result = _docx(data)
    elif ext == ".pdf":
        if not data.lstrip()[:5].startswith(b"%PDF"):
            raise _unreadable("El archivo no es un PDF válido.")
        result = _pdf(data)
    elif _looks_like_text(data):
        # texto plano con cualquier extensión (o sin extensión): .text, .tsv, .log, .markdown…
        result = Extracted(text=_text_file(data), kind="texto plano")
    else:
        raise _unsupported("Formato no admitido. Usá Word (.docx), PDF o un archivo de texto plano.")
    if len(result.text) > MAX_TEXT_CHARS:
        result.text = result.text[:MAX_TEXT_CHARS]
        result.warnings.append(f"El texto se recortó a los primeros {MAX_TEXT_CHARS:,} caracteres.".replace(",", "."))
    return result


def split_free_text(text: str) -> list[str]:
    """Divide texto libre en requisitos: viñetas/numeración o párrafos separados por línea en blanco."""
    lines = [l.rstrip() for l in text.replace("\r\n", "\n").split("\n")]
    bullet = re.compile(r"^\s*(?:[-*•]|\d+[.)]|[a-zA-Z][.)])\s+")
    if sum(1 for l in lines if bullet.match(l)) >= 2:
        # el texto previo a la primera viñeta (título o introducción) no se toma como requisito
        items, cur, started = [], "", False
        for l in lines:
            if bullet.match(l):
                if cur:
                    items.append(cur.strip())
                cur = bullet.sub("", l)
                started = True
            elif l.strip() and started:
                cur += " " + l.strip()
        if cur:
            items.append(cur.strip())
        return items
    return [p.strip().replace("\n", " ") for p in re.split(r"\n\s*\n", text) if p.strip()]

CONTENT_TYPES = {"pdf": "application/pdf",
                 "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                 "text": "text/plain; charset=utf-8"}


def validate_document(filename: str, data: bytes) -> str:
    """Valida un adjunto SIN transformarlo y devuelve su tipo: pdf | docx | text.

    Rechaza .doc, .docm, documentos con macros, PDF cifrados, archivos dañados y binarios. Un PDF escaneado
    (sin texto) se acepta: el agente lo lee de forma visual."""
    name = (filename or "").lower()
    ext = name[name.rfind("."):] if "." in name else ""
    if ext == ".doc":
        raise _unsupported("El formato .doc (Word 97-2003) no está soportado. Guardalo como .docx y volvé a subirlo.")
    if ext == ".docm":
        raise _unsupported("Los documentos con macros (.docm) no están permitidos. Guardalo como .docx.")
    if ext == ".docx":
        if not data.startswith(b"PK"):
            raise _unreadable("El archivo no es un .docx válido.")
        _docx(data)  # valida estructura, macros y tamaño; el texto se descarta
        return "docx"
    if ext == ".pdf":
        if not data.lstrip()[:5].startswith(b"%PDF"):
            raise _unreadable("El archivo no es un PDF válido.")
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(io.BytesIO(data))
        except (PdfReadError, ValueError, OSError):
            raise _unreadable("El PDF está dañado o no se puede leer.")
        if reader.is_encrypted:
            raise _unreadable("El PDF está protegido con contraseña. Quitá la protección y volvé a subirlo.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise _unreadable(f"El PDF tiene más de {MAX_PDF_PAGES} páginas. Dividilo en partes más chicas.")
        return "pdf"
    if ext in TEXT_EXT or _looks_like_text(data):
        if not _looks_like_text(data):
            raise _unsupported("El archivo no parece ser de texto plano.")
        return "text"
    raise _unsupported("Formato no admitido. Adjuntá un Word (.docx), un PDF o un archivo de texto plano.")
