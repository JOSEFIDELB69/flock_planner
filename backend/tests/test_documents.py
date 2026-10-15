"""Importación de requisitos desde Word (.docx) y PDF: documentos reales construidos en memoria."""

import io
import zipfile

import pytest

from app.errors import AppError
from app.services.documents import extract_text

API = "/api/v1"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def make_docx(body_xml: str, macros: bool = False) -> bytes:
    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           f'<w:document xmlns:w="{W_NS}"><w:body>{body_xml}</w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", doc)
        if macros:
            z.writestr("word/vbaProject.bin", b"\x00macro")
    return buf.getvalue()


def p(text: str, bullet: bool = False) -> str:
    num = '<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>' if bullet else ""
    return f"<w:p>{num}<w:r><w:t xml:space=\"preserve\">{text}</w:t></w:r></w:p>"


SAMPLE_DOCX = make_docx(
    p("Requisitos del portal de turnos")
    + p("El paciente reserva turnos desde la web.", bullet=True)
    + p("El administrador gestiona agendas y feriados.", bullet=True)
    + p("El sistema envía recordatorios por email y SMS.", bullet=True)
    + "<w:tbl><w:tr><w:tc>" + p("RNF-01") + "</w:tc><w:tc>" + p("Disponibilidad 99,5 %") + "</w:tc></w:tr></w:tbl>"
)


def make_pdf(lines: list[str], encrypt: bool = False) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in lines:
        c.drawString(60, y, line)
        y -= 20
    c.showPage()
    c.save()
    data = buf.getvalue()
    if encrypt:
        from pypdf import PdfReader, PdfWriter

        w = PdfWriter()
        for page in PdfReader(io.BytesIO(data)).pages:
            w.add_page(page)
        w.encrypt("clave")
        out = io.BytesIO()
        w.write(out)
        data = out.getvalue()
    return data


def test_docx_keeps_bullets_and_tables():
    r = extract_text("requisitos.docx", SAMPLE_DOCX)
    assert r.kind == "Word (.docx)"
    assert "- El paciente reserva turnos desde la web." in r.text
    assert "- El administrador gestiona agendas y feriados." in r.text
    assert "- RNF-01 | Disponibilidad 99,5 %" in r.text


def test_docx_with_macros_is_rejected():
    with pytest.raises(AppError) as exc:
        extract_text("x.docx", make_docx(p("hola"), macros=True))
    assert exc.value.status_code == 415


def test_old_doc_and_docm_are_rejected():
    for name in ("viejo.doc", "macro.docm"):
        with pytest.raises(AppError) as exc:
            extract_text(name, b"cualquier cosa")
        assert exc.value.status_code == 415


def test_plain_text_with_any_extension():
    for name in ("notas.text", "datos.tsv", "export.log", "README", "requisitos.cfg"):
        r = extract_text(name, "- Requisito uno con ñ.\n- Requisito dos.".encode("utf-8"))
        assert "Requisito uno con ñ." in r.text
    latin = extract_text("viejo.txt", "- Configuración\n- Reserva de turnos".encode("latin-1"))
    assert "Configuración" in latin.text


def test_binary_with_unknown_extension_is_rejected():
    for blob in (b"MZ\x90\x00\x03\x00\x00\x00", bytes(range(1, 32)) * 50):
        with pytest.raises(AppError) as exc:
            extract_text("programa.bin", blob)
        assert exc.value.status_code == 415


def test_fake_docx_is_rejected():
    with pytest.raises(AppError) as exc:
        extract_text("falso.docx", b"esto no es un zip")
    assert exc.value.status_code == 422


def test_pdf_text_is_extracted():
    r = extract_text("req.pdf", make_pdf(["- El paciente reserva turnos.", "- El sistema envía recordatorios."]))
    assert r.kind == "PDF" and r.pages == 1
    assert "El paciente reserva turnos." in r.text


def test_scanned_pdf_without_text_is_reported():
    with pytest.raises(AppError) as exc:
        extract_text("escaneado.pdf", make_pdf([]))
    assert exc.value.status_code == 422 and "escaneado" in exc.value.message


def test_encrypted_pdf_is_reported():
    with pytest.raises(AppError) as exc:
        extract_text("protegido.pdf", make_pdf(["secreto"], encrypt=True))
    assert "contraseña" in exc.value.message


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _upload(client, pid, name, data, mime):
    return client.post(f"{API}/projects/{pid}/documents", files={"file": (name, io.BytesIO(data), mime)})


def test_validate_document_does_not_transform_and_accepts_scanned_pdf():
    from app.services.documents import validate_document

    assert validate_document("req.docx", SAMPLE_DOCX) == "docx"
    assert validate_document("req.pdf", make_pdf(["- Uno."])) == "pdf"
    assert validate_document("escaneado.pdf", make_pdf([])) == "pdf"  # el agente lo lee de forma visual
    assert validate_document("notas.log", b"- Uno\n- Dos") == "text"
    for name, data in (("viejo.doc", b"x"), ("m.docm", b"x"), ("x.docx", make_docx(p("a"), macros=True)),
                       ("p.pdf", make_pdf(["s"], encrypt=True)), ("x.bin", b"MZ\x90\x00\x03")):
        with pytest.raises(AppError):
            validate_document(name, data)


def test_document_is_attached_as_is_and_downloadable(client, project):
    pid = project["id"]
    r = _upload(client, pid, "Especificación funcional.docx", SAMPLE_DOCX, DOCX_MIME)
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["kind"] == "docx" and doc["status"] == "pending" and doc["size_bytes"] == len(SAMPLE_DOCX)
    dl = client.get(f"{API}/documents/{doc['id']}/download")
    assert dl.status_code == 200 and dl.content == SAMPLE_DOCX  # el original, byte por byte
    assert "attachment" in dl.headers["content-disposition"]
    assert [d["filename"] for d in client.get(f"{API}/projects/{pid}/documents").json()] == ["Especificación funcional.docx"]


def test_agent_extracts_suggested_requirements_linked_to_document(client, project, fake_ai):
    pid = project["id"]
    pdf = make_pdf(["- El paciente reserva turnos."])
    doc = _upload(client, pid, "req.pdf", pdf, "application/pdf").json()
    r = client.post(f"{API}/documents/{doc['id']}/extract")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "processed" and out["requirements_created"] == 2
    assert "Falta definir horarios" in out["summary"]
    assert fake_ai.last_document == ("req.pdf", "pdf", pdf)  # el agente recibe el archivo original
    reqs = client.get(f"{API}/projects/{pid}/requirements").json()
    assert {r["status"] for r in reqs} == {"suggested"}
    assert all(r["source_document_id"] == doc["id"] and r["source"].startswith("documento req.pdf") for r in reqs)
    # confirmar una sugerencia y reprocesar: solo se reemplazan las que siguen sin revisar
    client.post(f"{API}/projects/{pid}/requirements/status", json={"ids": [reqs[0]["id"]], "status": "confirmed"})
    client.post(f"{API}/documents/{doc['id']}/extract")
    after = client.get(f"{API}/projects/{pid}/requirements").json()
    assert sum(1 for r in after if r["status"] == "confirmed") == 1
    assert sum(1 for r in after if r["status"] == "suggested") == 2
    # quitar el adjunto conserva los requisitos (sin vínculo)
    assert client.delete(f"{API}/documents/{doc['id']}").status_code == 204
    kept = client.get(f"{API}/projects/{pid}/requirements").json()
    assert len(kept) == 3 and all(r["source_document_id"] is None for r in kept)


def test_ai_failure_marks_document_error_and_keeps_attachment(client, project, failing_ai):
    pid = project["id"]
    doc = _upload(client, pid, "req.txt", b"- Uno\n- Dos", "text/plain").json()
    r = client.post(f"{API}/documents/{doc['id']}/extract")
    assert r.status_code == 503
    docs = client.get(f"{API}/projects/{pid}/documents").json()
    assert docs[0]["status"] == "error" and docs[0]["error"]
    assert client.get(f"{API}/projects/{pid}/requirements").json() == []


def test_bulk_status_confirms_suggestions(client, project, fake_ai):
    pid = project["id"]
    doc = _upload(client, pid, "req.txt", b"- Uno\n- Dos", "text/plain").json()
    ids = client.post(f"{API}/documents/{doc['id']}/extract").json()["requirement_ids"]
    r = client.post(f"{API}/projects/{pid}/requirements/status", json={"ids": ids, "status": "confirmed"})
    assert r.json() == {"updated": 2, "status": "confirmed"}
    assert {x["status"] for x in client.get(f"{API}/projects/{pid}/requirements").json()} == {"confirmed"}


def test_claude_code_receives_file_with_read_tool_only():
    import json as _json
    import subprocess
    import sys as _sys
    from pathlib import Path

    from app.ai.claude_code import ClaudeCodeProvider
    from app.config import Settings

    seen = {}

    def runner(args, **kw):
        cwd = Path(kw["cwd"])
        seen["tools"] = args[args.index("--tools") + 1]
        seen["files"] = {f.name: f.read_bytes() for f in cwd.iterdir()}
        seen["short_path"] = "~" in str(cwd)
        body = {"summary": "ok", "requirements": [{"title": "Uno"}], "observations": []}
        return subprocess.CompletedProcess(args, 0, stdout=_json.dumps(
            {"type": "result", "is_error": False, "result": _json.dumps(body)}), stderr="")

    prov = ClaudeCodeProvider(Settings(claude_code_path=_sys.executable), runner=runner)
    pdf = make_pdf(["- Uno."])
    out = prov.extract_requirements_from_document({"name": "X"}, "req.pdf", "pdf", pdf)
    assert out.requirements[0].title == "Uno"
    assert seen["tools"] == "Read" and seen["files"] == {"documento.pdf": pdf} and not seen["short_path"]
    prov.extract_requirements_from_document({"name": "X"}, "req.docx", "docx", SAMPLE_DOCX)
    assert list(seen["files"]) == ["documento.txt"]  # .docx: el agente recibe su texto (no puede abrir binarios)
    assert "El paciente reserva turnos" in seen["files"]["documento.txt"].decode("utf-8")


def test_document_size_limit(client, project, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_document_bytes", 1000)
    r = _upload(client, project["id"], "grande.pdf", b"%PDF" + b"0" * 2000, "application/pdf")
    assert r.status_code == 413
