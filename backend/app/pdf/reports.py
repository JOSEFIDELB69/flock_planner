"""Generación de informes PDF en el backend (ReportLab).

Tres informes: completo, ejecutivo y de optimización. Todo el contenido sale de la versión de plan
seleccionada (snapshot inmutable) y de los escenarios persistidos; no hay valores codificados.
"""

from __future__ import annotations

import io
import os
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from app.planning.compare import recommendation_key
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Paleta del sistema de diseño Flock IT
NIGHT = colors.HexColor("#1c002c")
PURPLE = colors.HexColor("#7f07c5")
ORANGE = colors.HexColor("#ff5102")
LILAC = colors.HexColor("#e9deff")
SUBTLE = colors.HexColor("#f1ecf7")
BORDER = colors.HexColor("#e3daec")
MUTED = colors.HexColor("#5e4e6b")
CHART = [colors.HexColor(c) for c in ("#7f07c5", "#ff5102", "#4f3ae2", "#fb116f")]
CHART_OTHER = colors.HexColor("#a698b3")
# Isologo blanco de Flock (flockit.com.ar, 222×57 px)
LOGO_PATH = Path(__file__).resolve().parent / "assets" / "flock-logo.png"
LOGO_RATIO = 222 / 57

REPORT_TITLES = {
    "full": "Informe completo del plan",
    "executive": "Informe ejecutivo",
    "optimization": "Informe de optimización",
}
REPORT_FILE_LABEL = {"full": "Plan", "executive": "Ejecutivo", "optimization": "Optimizacion"}
PRIORITY = {"low": "Baja", "medium": "Media", "high": "Alta", "critical": "Crítica"}
CONFIDENCE = {"low": "Baja", "medium": "Media", "high": "Alta"}
SEVERITY = {"low": "Baja", "medium": "Media", "high": "Alta"}
REQ_TYPE = {"functional": "Funcional", "non_functional": "No funcional", "technical": "Técnico",
            "security": "Seguridad", "integration": "Integración", "performance": "Rendimiento",
            "operational": "Operativo"}

_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_UNICODE_FONT = False


def _register_fonts() -> None:
    """Usa una fuente TrueType con soporte Unicode si está disponible (DejaVu en Linux, Arial en Windows)."""
    global _FONT, _FONT_BOLD, _UNICODE_FONT
    if _UNICODE_FONT:
        return
    candidates = [
        (os.environ.get("PDF_FONT_PATH"), os.environ.get("PDF_FONT_BOLD_PATH")),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ]
    for regular, bold in candidates:
        if regular and bold and os.path.exists(regular) and os.path.exists(bold):
            try:
                pdfmetrics.registerFont(TTFont("PMSans", regular))
                pdfmetrics.registerFont(TTFont("PMSans-Bold", bold))
                pdfmetrics.registerFontFamily("PMSans", normal="PMSans", bold="PMSans-Bold",
                                              italic="PMSans", boldItalic="PMSans-Bold")
                _FONT, _FONT_BOLD, _UNICODE_FONT = "PMSans", "PMSans-Bold", True
                return
            except Exception:  # noqa: BLE001 - se usa Helvetica como respaldo
                continue


def _t(text: Any) -> str:
    """Texto seguro para Paragraph: escapa XML y, sin fuente Unicode, reduce a cp1252."""
    s = "" if text is None else str(text)
    if not _UNICODE_FONT:
        s = s.replace("→", "->").replace("≥", ">=").replace("≤", "<=")
        s = s.encode("cp1252", errors="replace").decode("cp1252")
    return escape(s).replace("\n", "<br/>")


def fmt_num(value: Any, decimals: int = 1) -> str:
    if value is None:
        return "—"
    s = f"{float(value):,.{decimals}f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    if decimals and s.endswith("," + "0" * decimals):
        s = s[: -(decimals + 1)]
    return s


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def fmt_date(value: Any) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    return value.strftime("%d/%m/%Y")


def safe_filename(project_name: str, report_type: str, version_number: int) -> str:
    ascii_name = unicodedata.normalize("NFKD", project_name).encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^A-Za-z0-9]+", "_", ascii_name).strip("_")[:60] or "Proyecto"
    return f"Flock_Planner_{ascii_name}_{REPORT_FILE_LABEL[report_type]}_v{version_number}.pdf"


# --------------------------------------------------------------------------- estilos


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName=_FONT, fontSize=9.5, leading=13, textColor=NIGHT, alignment=TA_LEFT)
    return {
        "body": base,
        "small": ParagraphStyle("small", parent=base, fontSize=8, leading=10.5, textColor=MUTED),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8, leading=10),
        "cellb": ParagraphStyle("cellb", parent=base, fontSize=8, leading=10, fontName=_FONT_BOLD),
        "h1": ParagraphStyle("h1", parent=base, fontName=_FONT, fontSize=18, leading=22, spaceBefore=4,
                             spaceAfter=8, textColor=NIGHT),
        "h2": ParagraphStyle("h2", parent=base, fontName=_FONT_BOLD, fontSize=12, leading=15, spaceBefore=10,
                             spaceAfter=5, textColor=PURPLE, keepWithNext=1),
        "h3": ParagraphStyle("h3", parent=base, fontName=_FONT_BOLD, fontSize=10, leading=13, spaceBefore=6,
                             spaceAfter=3, keepWithNext=1),
        "kpi_label": ParagraphStyle("kl", parent=base, fontSize=7.5, leading=9, textColor=MUTED),
        "kpi_value": ParagraphStyle("kv", parent=base, fontSize=14, leading=17, fontName=_FONT_BOLD),
    }


def _table(rows: list[list[Any]], widths: list[float], header: bool = True, zebra: bool = True) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    style = [
        ("FONTNAME", (0, 0), (-1, -1), _FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), SUBTLE), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                  ("FONTNAME", (0, 0), (-1, 0), _FONT_BOLD)]
    if zebra:
        for i in range(2 if header else 1, len(rows), 2):
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#faf8fc")))
    t.setStyle(TableStyle(style))
    return t


class _Ctx:
    def __init__(self, project, version, report_type: str, scenarios: list | None = None,
                 baseline=None, version_numbers: dict[int, int] | None = None):
        self.version_numbers = version_numbers or {}
        self.project = project
        self.version = version
        self.report_type = report_type
        self.scenarios = scenarios or []
        self.baseline = baseline
        self.metrics = version.metrics or {}
        self.snapshot = version.backlog_snapshot or {}
        self.profile_names = {p["profile_key"]: p.get("profile_name", p["profile_key"])
                              for p in version.team_configuration}
        self.generated_at = datetime.now()
        self.s = _styles()

    def pname(self, key: str) -> str:
        return self.profile_names.get(key, key)


# --------------------------------------------------------------------------- lienzo con numeración


def _make_canvas(ctx: _Ctx):
    class NumberedCanvas(rl_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved: list[dict] = []

        def showPage(self):  # noqa: N802 - API de ReportLab
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved)
            for state in self._saved:
                self.__dict__.update(state)
                self._decorate(total)
                super().showPage()
            super().save()

        def _decorate(self, total: int) -> None:
            w, h = A4
            if self._pageNumber == 1:
                return
            # banda de marca: el isologo blanco de Flock solo se usa sobre violeta noche (no se recolorea)
            band = 12 * mm
            self.setFillColor(NIGHT)
            self.rect(0, h - band, w, band, stroke=0, fill=1)
            x = 18 * mm
            if LOGO_PATH.exists():
                logo_h = 5 * mm
                logo_w = logo_h * LOGO_RATIO
                self.drawImage(str(LOGO_PATH), x, h - band / 2 - logo_h / 2, logo_w, logo_h, mask="auto")
                x += logo_w + 3 * mm
            self.setFont(_FONT_BOLD, 7.5)
            self.setFillColor(colors.white)
            self.drawString(x, h - band / 2 - 2.5, "Planner")
            self.setFont(_FONT, 7.5)
            self.setFillColor(LILAC)
            head = f"{ctx.project.name} · {REPORT_TITLES[ctx.report_type]} · v{ctx.version.version_number}"
            self.drawRightString(w - 18 * mm, h - band / 2 - 2.5, _plain(head)[:100])
            self.setStrokeColor(BORDER)
            self.setLineWidth(0.5)
            self.line(18 * mm, 13 * mm, w - 18 * mm, 13 * mm)
            self.setFillColor(MUTED)
            self.drawString(18 * mm, 9 * mm, _plain(f"Generado el {ctx.generated_at.strftime('%d/%m/%Y %H:%M')}"
                                                    " · Las estimaciones no son garantías."))
            self.drawRightString(w - 18 * mm, 9 * mm, f"Página {self._pageNumber} de {total}")

    return NumberedCanvas


def _plain(s: str) -> str:
    if _UNICODE_FONT:
        return s
    return s.encode("cp1252", errors="replace").decode("cp1252")


def _cover(c: rl_canvas.Canvas, ctx: _Ctx) -> None:
    w, h = A4
    c.saveState()
    c.setFillColor(NIGHT)
    c.rect(0, h * 0.42, w, h * 0.58, stroke=0, fill=1)
    c.setFillColor(ORANGE)
    c.rect(0, h * 0.42, w, 3, stroke=0, fill=1)
    # marca: isologo "flock" + "Planner" en la misma línea (igual que el encabezado de la app)
    top = h - 22 * mm
    logo_h = 11 * mm
    x = 22 * mm
    if LOGO_PATH.exists():
        c.drawImage(str(LOGO_PATH), x, top - logo_h, logo_h * LOGO_RATIO, logo_h, mask="auto")
        x += logo_h * LOGO_RATIO + 4 * mm
        c.setStrokeColor(colors.Color(1, 1, 1, alpha=0.35))
        c.setLineWidth(0.8)
        c.line(x - 2 * mm, top - logo_h + 1 * mm, x - 2 * mm, top - 1 * mm)
    c.setFillColor(colors.white)
    c.setFont(_FONT, 26)
    c.drawString(x + 1 * mm, top - logo_h + 2.2 * mm, "Planner" if LOGO_PATH.exists() else "Flock Planner")
    c.setFont(_FONT, 9)
    c.setFillColor(LILAC)
    c.drawString(22 * mm, top - logo_h - 7 * mm, _plain("Planificación inteligente de proyectos"))
    c.setFillColor(colors.white)
    c.setFont(_FONT, 28)
    title = ctx.project.name
    lines = _wrap(title, 32)
    y = h * 0.62
    for line in lines[:3]:
        c.drawString(22 * mm, y, _plain(line))
        y -= 34
    c.setFont(_FONT, 14)
    c.setFillColor(LILAC)
    c.drawString(22 * mm, h * 0.62 + 40, _plain(REPORT_TITLES[ctx.report_type]))
    # bloque de datos
    c.setFillColor(NIGHT)
    c.setFont(_FONT, 10)
    v = ctx.version
    rows = [
        ("Versión", f"v{v.version_number} — {v.label}" + (" (línea base)" if v.is_baseline else "")),
        ("Fecha de generación", ctx.generated_at.strftime("%d/%m/%Y %H:%M")),
        ("Responsable", ctx.project.owner or "—"),
        ("Inicio planificado", fmt_date(v.start_date)),
        ("Fin estimado", fmt_date(v.estimated_completion_date)),
        ("Duración estimada", f"{v.estimated_duration} días laborables"),
        ("Esfuerzo planificado", f"{fmt_num(v.estimated_effort)} h"),
    ]
    y = h * 0.42 - 22 * mm
    for label, value in rows:
        c.setFillColor(MUTED)
        c.setFont(_FONT, 9)
        c.drawString(22 * mm, y, _plain(label))
        c.setFillColor(NIGHT)
        c.setFont(_FONT_BOLD, 10)
        c.drawString(70 * mm, y, _plain(str(value))[:80])
        y -= 8 * mm
    c.setFillColor(MUTED)
    c.setFont(_FONT, 7.5)
    c.drawString(22 * mm, 16 * mm, _plain("Documento generado por Flock Planner con datos persistidos de la versión "
                                          "indicada. Las estimaciones no constituyen garantías."))
    c.restoreState()


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for wd in words:
        if len(cur) + len(wd) + 1 > width and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = f"{cur} {wd}".strip()
    if cur:
        lines.append(cur)
    return lines or [""]


# --------------------------------------------------------------------------- bloques


def _kpis(ctx: _Ctx) -> Table:
    m, v = ctx.metrics, ctx.version
    items = [
        ("Duración estimada", f"{v.estimated_duration} días"),
        ("Fin estimado", fmt_date(v.estimated_completion_date)),
        ("Esfuerzo planificado", f"{fmt_num(v.estimated_effort)} h"),
        ("Esfuerzo base", f"{fmt_num(m.get('base_effort_hours'))} h"),
    ]
    if m.get("total_cost") is not None:
        items.append(("Coste (horas asignadas)", f"{ctx.project.currency} {fmt_num(m['total_cost'], 0)}"))
    if m.get("total_staffing_cost") is not None:
        items.append(("Coste de equipo", f"{ctx.project.currency} {fmt_num(m['total_staffing_cost'], 0)}"))
    value_style = ctx.s["kpi_value"]
    if len(items) > 4:  # con 5-6 indicadores, cifra más chica para que fechas y montos no se corten
        value_style = ParagraphStyle("kv_sm", parent=value_style, fontSize=10.5, leading=13)
    cells = [[Paragraph(_t(l), ctx.s["kpi_label"]), Paragraph(_t(val), value_style)] for l, val in items]
    row = [Table([[c[0]], [c[1]]], colWidths=[(174 * mm) / len(items) - 4]) for c in cells]
    t = Table([row], colWidths=[(174 * mm) / len(items)] * len(items), hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SUBTLE), ("LINEABOVE", (0, 0), (-1, 0), 2, PURPLE),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 6),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def _profile_chart(ctx: _Ctx) -> Drawing:
    data = [p for p in ctx.metrics.get("by_profile", []) if p.get("planned_hours", 0) > 0]
    width, bar_h, gap = 174 * mm, 12, 6
    height = max(40, len(data) * (bar_h + gap) + 20)
    d = Drawing(width, height)
    if not data:
        return d
    max_h = max(p["planned_hours"] for p in data) or 1
    label_w, avail = 52 * mm, width - 52 * mm - 30 * mm
    y = height - bar_h - 6
    for i, p in enumerate(data):
        color = CHART[i] if i < len(CHART) else CHART_OTHER
        d.add(String(0, y + 3, _plain(p["profile_name"])[:34], fontName=_FONT, fontSize=8, fillColor=NIGHT))
        bw = max(1, avail * p["planned_hours"] / max_h)
        d.add(Rect(label_w, y, bw, bar_h, fillColor=color, strokeColor=None))
        util = round(p.get("utilization", 0) * 100)
        d.add(String(label_w + bw + 4, y + 3, _plain(f"{fmt_num(p['planned_hours'])} h · {util} %"),
                     fontName=_FONT, fontSize=7.5, fillColor=MUTED))
        y -= bar_h + gap
    return d


def _gantt(ctx: _Ctx) -> Drawing | None:
    schedule = ctx.version.schedule or []
    if not schedule:
        return None
    groups: dict[str, dict[str, Any]] = {}
    use_epics = len({s["story_id"] for s in schedule}) > 40
    for s in schedule:
        key = s["epic_id"] if use_epics else s["story_id"]
        title = s["epic_title"] if use_epics else s["story_title"]
        g = groups.setdefault(key, {"title": title, "start": s["start"], "finish": s["finish"]})
        g["start"] = min(g["start"], s["start"])
        g["finish"] = max(g["finish"], s["finish"])
    rows = sorted(groups.values(), key=lambda g: (g["start"], g["title"]))
    end = max(g["finish"] for g in rows) or 1
    width, row_h = 174 * mm, 11
    label_w = 62 * mm
    height = len(rows) * row_h + 28
    d = Drawing(width, height)
    span = width - label_w - 4
    # escala de semanas
    weeks = max(1, int(end // 7) + 1)
    step = max(1, weeks // 10)
    for wk in range(0, weeks + 1, step):
        x = label_w + span * min(1.0, (wk * 7) / end)
        d.add(Line(x, 10, x, height - 4, strokeColor=BORDER, strokeWidth=0.4))
        d.add(String(x + 1, 2, f"S{wk + 1}" if wk < weeks else "", fontName=_FONT, fontSize=6.5, fillColor=MUTED))
    y = height - row_h - 4
    for i, g in enumerate(rows):
        d.add(String(0, y + 2, _plain(g["title"])[:44], fontName=_FONT, fontSize=7, fillColor=NIGHT))
        x0 = label_w + span * g["start"] / end
        x1 = label_w + span * g["finish"] / end
        d.add(Rect(x0, y, max(1.5, x1 - x0), row_h - 3, fillColor=CHART[i % 2], strokeColor=None))
        y -= row_h
    return d


def _bullets(items: list[str], style) -> list:
    return [Paragraph("• " + _t(i), style) for i in items if i]


def _section_summary(ctx: _Ctx, story: list) -> None:
    s = ctx.s
    story.append(Paragraph(_t("Resumen ejecutivo"), s["h2"]))
    story.append(_kpis(ctx))
    story.append(Spacer(1, 6))
    summary = ctx.version.executive_summary
    if summary:
        label = " (texto simulado, modo demostración)" if ctx.version.executive_summary_simulated else \
            " (redactado con IA a partir de las métricas del motor)"
        story.append(Paragraph(_t(summary), s["body"]))
        story.append(Paragraph(_t("Origen del texto:" + label), s["small"]))
    else:
        m = ctx.metrics
        mb = m.get("main_bottleneck")
        txt = (f"El plan requiere {fmt_num(ctx.version.estimated_effort)} h planificadas "
               f"({fmt_num(m.get('base_effort_hours'))} h de esfuerzo base más revisión y retrabajo). "
               f"Con el equipo configurado, el motor estima {ctx.version.estimated_duration} días laborables, "
               f"desde el {fmt_date(ctx.version.start_date)} hasta el {fmt_date(ctx.version.estimated_completion_date)}.")
        if m.get("contingency_days"):
            txt += (f" La duración incluye una reserva por imprevistos del {fmt_num(m.get('contingency_pct'), 0)} % "
                    f"({m['contingency_days']} días laborables); el trabajo planificado termina el "
                    f"{fmt_date(m.get('work_completion_date'))}.")
        if mb:
            txt += f" El perfil con mayor incidencia en el plazo es {ctx.pname(mb)}."
        if m.get("target_date"):
            txt += (" La fecha objetivo " + ("se cumple." if m.get("meets_target") else
                                            f"({fmt_date(m['target_date'])}) no se cumple con esta configuración."))
        story.append(Paragraph(_t(txt), s["body"]))
    _forecast_block(ctx, story)


def _forecast_block(ctx: _Ctx, story: list) -> None:
    """Probabilidad de cumplimiento (simulación Monte Carlo del motor)."""
    f = ctx.metrics.get("forecast")
    if not f:
        return
    s = ctx.s
    story.append(Paragraph(_t("Probabilidad de cumplimiento"), s["h3"]))
    rows = [["Confianza", "El trabajo termina a más tardar el", "Días laborables"]]
    for key, label in (("p50", "50 % (P50)"), ("p80", "80 % (P80)"), ("p90", "90 % (P90)")):
        rows.append([label, fmt_date(f[key]["date"]), str(f[key]["working_days"])])
    story.append(_table(rows, [40 * mm, 90 * mm, 44 * mm]))
    txt = (f"La fecha del plan ({fmt_date(ctx.version.estimated_completion_date)}) se cumple en el "
           f"{round(f['probability_plan'] * 100)} % de los {f['runs']} escenarios simulados")
    if f.get("probability_target") is not None and ctx.metrics.get("target_date"):
        txt += f"; la fecha objetivo ({fmt_date(ctx.metrics['target_date'])}), en el {round(f['probability_target'] * 100)} %"
    txt += (f". Para tener 80 % de confianza hace falta una reserva por imprevistos de al menos "
            f"{f['contingency_for_p80_pct']} % sobre la duración del trabajo. Método: simulación Monte Carlo sobre el "
            "mismo motor, con el rango optimista–pesimista de cada tarea (o el de la confianza de su historia).")
    story.append(Paragraph(_t(txt), s["small"]))


def _section_scope(ctx: _Ctx, story: list) -> None:
    s, p = ctx.s, ctx.project
    story.append(Paragraph(_t("Objetivos y alcance"), s["h2"]))
    if p.business_objective:
        story.append(Paragraph(_t("Objetivo de negocio: ") + _t(p.business_objective), s["body"]))
    if p.description:
        story.append(Paragraph(_t(p.description), s["body"]))
    epics = ctx.snapshot.get("epics", [])
    n_st = sum(len(e["stories"]) for e in epics)
    n_tk = sum(len(st["tasks"]) for e in epics for st in e["stories"])
    story.append(Paragraph(_t(f"Alcance planificado: {_plural(len(epics), 'épica', 'épicas')}, "
                              f"{_plural(n_st, 'historia de usuario', 'historias de usuario')} y "
                              f"{_plural(n_tk, 'subtarea', 'subtareas')}."), s["body"]))


def _section_requirements(ctx: _Ctx, story: list) -> None:
    reqs = ctx.snapshot.get("requirements", [])
    s = ctx.s
    story.append(Paragraph(_t("Requisitos principales"), s["h2"]))
    if not reqs:
        story.append(Paragraph(_t("No hay requisitos registrados en esta versión."), s["body"]))
        return
    rows = [["Código", "Requisito", "Tipo", "Prioridad"]]
    for r in reqs:
        rows.append([Paragraph(_t(r["code"]), s["cell"]), Paragraph(_t(r["title"]), s["cell"]),
                     Paragraph(_t(REQ_TYPE.get(r["type"], r["type"])), s["cell"]),
                     Paragraph(_t(PRIORITY.get(r["priority"], r["priority"])), s["cell"])])
    story.append(_table(rows, [20 * mm, 108 * mm, 26 * mm, 20 * mm]))


def _section_backlog(ctx: _Ctx, story: list, with_tasks: bool = True) -> None:
    s = ctx.s
    story.append(Paragraph(_t("Épicas, historias de usuario y criterios de aceptación"), s["h2"]))
    for e in ctx.snapshot.get("epics", []):
        hours = sum(t["estimated_hours"] for st in e["stories"] for t in st["tasks"])
        story.append(Paragraph(_t(f"{e['code']} · {e['title']}  ({fmt_num(hours)} h base)"), s["h3"]))
        if e.get("description"):
            story.append(Paragraph(_t(e["description"]), s["small"]))
        for st in e["stories"]:
            block = [Paragraph(_t(f"{st['code']} · {st['title']}"), s["cellb"])]
            meta = (f"Prioridad {PRIORITY.get(st['priority'], st['priority'])} · Valor {st.get('business_value', '—')}"
                    f" · Confianza {CONFIDENCE.get(st['estimate_confidence'], st['estimate_confidence'])} · "
                    f"Estimación {'revisada' if st.get('estimate_status') == 'revised' else 'inicial'}")
            block.append(Paragraph(_t(meta), s["small"]))
            if st.get("description"):
                block.append(Paragraph(_t(st["description"]), s["cell"]))
            for ac in st.get("acceptance_criteria", []) or []:
                block.append(Paragraph(_t(f"Dado {ac.get('given', '')}, cuando {ac.get('when', '')}, "
                                          f"entonces {ac.get('then', '')}."), s["cell"]))
            if st.get("assumptions"):
                block.append(Paragraph(_t("Supuestos: " + st["assumptions"]), s["small"]))
            if st.get("risks"):
                block.append(Paragraph(_t("Riesgos: " + st["risks"]), s["small"]))
            story.append(KeepTogether(block))
            if with_tasks and st["tasks"]:
                rows = [["Subtarea", "Perfil", "Horas", "Criterio de finalización"]]
                for t in st["tasks"]:
                    rows.append([Paragraph(_t(f"{t['code']} {t['title']}"), s["cell"]),
                                 Paragraph(_t(ctx.pname(t["profile_key"])), s["cell"]),
                                 Paragraph(_t(fmt_num(t["estimated_hours"])), s["cell"]),
                                 Paragraph(_t(t.get("done_criteria") or "—"), s["cell"])])
                story.append(_table(rows, [64 * mm, 32 * mm, 14 * mm, 64 * mm]))
            story.append(Spacer(1, 5))


def _section_estimates(ctx: _Ctx, story: list) -> None:
    s, m = ctx.s, ctx.metrics
    story.append(Paragraph(_t("Estimaciones por perfil"), s["h2"]))
    story.append(_profile_chart(ctx))
    rows = [["Perfil", "Horas base", "Horas planificadas", "Disponibles", "Utilización", "Coste"]]
    for p in m.get("by_profile", []):
        rows.append([p["profile_name"], fmt_num(p["base_hours"]), fmt_num(p["planned_hours"]),
                     fmt_num(p["available_hours"]), f"{round(p['utilization'] * 100)} %",
                     fmt_num(p["cost"], 0) if p.get("cost") is not None else "—"])
    rows.append(["Total", fmt_num(m.get("base_effort_hours")), fmt_num(m.get("planned_effort_hours")), "", "",
                 fmt_num(m.get("total_cost"), 0) if m.get("total_cost") is not None else "—"])
    story.append(_table([[Paragraph(_t(c), s["cell"]) for c in r] for r in rows],
                        [50 * mm, 22 * mm, 30 * mm, 24 * mm, 22 * mm, 26 * mm]))


def _section_team(ctx: _Ctx, story: list) -> None:
    s = ctx.s
    story.append(Paragraph(_t("Composición del equipo"), s["h2"]))
    rows = [["Perfil", "Cantidad", "Horas productivas/día", "Dedicación", "Tarifa/hora", "QA"]]
    for p in ctx.version.team_configuration:
        rows.append([p.get("profile_name"), str(p.get("quantity")), fmt_num(p.get("available_hours_per_day")),
                     f"{fmt_num(p.get('dedication_percentage'), 0)} %",
                     fmt_num(p["hourly_rate"]) if p.get("hourly_rate") is not None else "—",
                     "Sí" if p.get("is_qa") else "No"])
    story.append(_table([[Paragraph(_t(c), s["cell"]) for c in r] for r in rows],
                        [52 * mm, 18 * mm, 34 * mm, 22 * mm, 24 * mm, 24 * mm]))


def _section_assumptions(ctx: _Ctx, story: list) -> None:
    s = ctx.s
    story.append(Paragraph(_t("Supuestos de planificación"), s["h2"]))
    story.extend(_bullets(ctx.version.assumptions or [], s["body"]))


def _section_dependencies(ctx: _Ctx, story: list) -> None:
    s = ctx.s
    story.append(Paragraph(_t("Dependencias y camino crítico"), s["h2"]))
    titles = {}
    for e in ctx.snapshot.get("epics", []):
        for st in e["stories"]:
            titles[st["id"]] = f"{st['code']} {st['title']}"
    rows = [["Historia", "Depende de"]]
    for e in ctx.snapshot.get("epics", []):
        for st in e["stories"]:
            if st.get("depends_on"):
                rows.append([Paragraph(_t(titles[st["id"]]), s["cell"]),
                             Paragraph(_t(", ".join(titles.get(d, str(d)) for d in st["depends_on"])), s["cell"])])
    if len(rows) > 1:
        story.append(_table(rows, [87 * mm, 87 * mm]))
    else:
        story.append(Paragraph(_t("No hay dependencias explícitas entre historias. El motor aplica además la "
                                  "secuencia desarrollo → QA dentro de cada historia."), s["body"]))
    crit = ctx.metrics.get("critical_path", [])
    if crit:
        story.append(Paragraph(_t("Camino crítico (aproximación con restricciones de recursos)"), s["h3"]))
        kind = {"dependency": "dependencia", "resource": "recurso ocupado", "start": "inicio"}
        rows = [["Tarea", "Perfil / persona", "Inicio", "Fin", "Restricción"]]
        for c in crit:
            rows.append([Paragraph(_t(c["title"]), s["cell"]),
                         Paragraph(_t(f"{ctx.pname(c['profile_key'])} / {c['member_name']}"), s["cell"]),
                         fmt_date(c["start_date"]), fmt_date(c["end_date"]), kind.get(c["constraint"], "")])
        story.append(_table(rows, [70 * mm, 44 * mm, 18 * mm, 18 * mm, 24 * mm]))


def _section_schedule(ctx: _Ctx, story: list) -> None:
    s = ctx.s
    story.append(Paragraph(_t("Cronograma"), s["h2"]))
    g = _gantt(ctx)
    if g is not None:
        story.append(g)
        story.append(Paragraph(_t("Barras por historia (o por épica si hay muchas). Escala en semanas desde el "
                                  "inicio."), s["small"]))
    story.append(Paragraph(_t("Hitos"), s["h3"]))
    rows = [["Hito", "Fecha"]] + [[Paragraph(_t(m["name"]), s["cell"]), fmt_date(m["date"])]
                                   for m in ctx.metrics.get("milestones", [])]
    story.append(_table(rows, [140 * mm, 34 * mm]))
    story.append(Paragraph(_t(f"Fecha de finalización estimada: {fmt_date(ctx.version.estimated_completion_date)}"
                              f" ({ctx.version.estimated_duration} días laborables)."), s["h3"]))


def _section_risks(ctx: _Ctx, story: list) -> None:
    s = ctx.s
    story.append(Paragraph(_t("Riesgos"), s["h2"]))
    risks = list(ctx.version.risks or [])
    for e in ctx.snapshot.get("epics", []):
        for st in e["stories"]:
            if st.get("risks"):
                risks.append({"title": f"{st['code']} {st['title']}", "severity": "medium", "detail": st["risks"]})
    if not risks:
        story.append(Paragraph(_t("No se identificaron riesgos."), s["body"]))
        return
    rows = [["Riesgo", "Severidad", "Detalle"]]
    for r in risks[:60]:
        rows.append([Paragraph(_t(r["title"]), s["cell"]), SEVERITY.get(r.get("severity"), r.get("severity", "")),
                     Paragraph(_t(r.get("detail", "")), s["cell"])])
    story.append(_table(rows, [58 * mm, 20 * mm, 96 * mm]))


def _section_selected_scenario(ctx: _Ctx, story: list) -> None:
    s = ctx.s
    story.append(Paragraph(_t("Escenario seleccionado y versión"), s["h2"]))
    v = ctx.version
    txt = f"Versión v{v.version_number} ({v.label}), creada el {fmt_date(v.created_at.date())} por {v.created_by or '—'}."
    if v.is_baseline:
        txt += " Es la línea base del proyecto."
    if v.source_scenario_id:
        sc = next((x for x in ctx.scenarios if x.id == v.source_scenario_id), None)
        txt += f" Proviene del escenario '{sc.name if sc else v.source_scenario_id}'."
    if v.change_reason:
        txt += f" Motivo: {v.change_reason}"
    story.append(Paragraph(_t(txt), s["body"]))


def _section_optimization(ctx: _Ctx, story: list) -> None:
    s = ctx.s
    base = ctx.baseline or ctx.version
    story.append(Paragraph(_t("Línea base"), s["h2"]))
    story.append(Paragraph(_t(f"v{base.version_number}: {base.estimated_duration} días laborables, fin "
                              f"{fmt_date(base.estimated_completion_date)}, {fmt_num(base.estimated_effort)} h "
                              "planificadas."), s["body"]))
    sims = [x for x in ctx.scenarios if x.comparison_metrics]
    story.append(Paragraph(_t("Escenarios comparados"), s["h2"]))
    if not sims:
        story.append(Paragraph(_t("Todavía no hay escenarios simulados para este proyecto."), s["body"]))
        return
    rows = [["Escenario", "Estado", "Días", "Ahorro", "Variación", "Fin", "Coste horas", "Coste equipo",
             "Cuello de botella"]]
    status = {"simulated": "Simulado", "applied": "Aplicado", "draft": "Borrador", "error": "Error", "stale": "Desact."}
    for x in sims:
        c = x.comparison_metrics
        cost = fmt_num(c["scenario_cost"], 0) if c.get("scenario_cost") is not None else "—"
        staff = fmt_num(c["scenario_staffing_cost"], 0) if c.get("scenario_staffing_cost") is not None else "—"
        rows.append([Paragraph(_t(x.name), s["cell"]), status.get(x.status, x.status), str(c["scenario_duration"]),
                     f"{c['time_savings_days']:+d}", f"{c['variation_pct']:+.1f} %".replace(".", ","),
                     fmt_date(c["scenario_completion_date"]), cost, staff,
                     Paragraph(_t(ctx.pname(c.get("scenario_main_bottleneck") or "") or "—"), s["cell"])])
    story.append(_table(rows, [38 * mm, 16 * mm, 10 * mm, 13 * mm, 17 * mm, 19 * mm, 18 * mm, 18 * mm, 25 * mm]))
    story.append(Paragraph(_t(
        f"Variación = (duración del escenario − duración de la línea base v{base.version_number}) / duración de la "
        "línea base × 100. Ahorro = línea base − escenario (días laborables). Coste horas = horas asignadas × "
        "tarifa. Coste equipo = horas pagadas del equipo durante el plan × tarifa (incluye esperas y "
        "coordinación)."), s["small"]))
    story.append(Paragraph(_t("Cambios de capacidad"), s["h2"]))
    for x in sims:
        cm = x.comparison_metrics
        changes = [ch for ch in cm.get("capacity_changes", []) if ch["quantity_delta"] or ch["daily_capacity_delta"]]
        parts = [f"{ch['profile_name']}: {ch['baseline_quantity']} → {ch['scenario_quantity']} personas "
                 f"({fmt_num(ch['baseline_daily_capacity'])} → {fmt_num(ch['scenario_daily_capacity'])} h/día)"
                 for ch in changes]
        if cm.get("scenario_contingency_pct") or cm.get("baseline_contingency_pct"):
            parts.append(f"Reserva por imprevistos {fmt_num(cm.get('baseline_contingency_pct') or 0, 0)} % → "
                         f"{fmt_num(cm.get('scenario_contingency_pct') or 0, 0)} % "
                         f"(+{cm.get('scenario_contingency_days') or 0} días de reserva)")
        if not parts:
            continue
        desc = "; ".join(parts)
        story.append(Paragraph(_t(f"{x.name}: {desc}"), s["cell"]))
    no_gain = set()
    for x in sims:
        no_gain.update(x.comparison_metrics.get("profiles_without_gain", []))
    story.append(Paragraph(_t("Cuellos de botella"), s["h2"]))
    for b in (base.metrics or {}).get("bottlenecks", [])[:5]:
        story.append(Paragraph(_t(f"{b['profile_name']}: " + ("; ".join(b["reasons"]) or
                                                              f"utilización {round(b['utilization'] * 100)} %")),
                               s["body"]))
    if no_gain:
        story.append(Paragraph(_t("Perfiles que no mejoran el plazo al sumar una persona: "
                                  + ", ".join(ctx.pname(k) for k in sorted(no_gain)) + "."), s["body"]))
    story.append(Paragraph(_t("Recomendación"), s["h2"]))
    best = min(sims, key=lambda x: recommendation_key(x.name, x.comparison_metrics))
    c = best.comparison_metrics
    gain = c["time_savings_days"]
    text = (f"Según los cálculos del motor, el escenario recomendado es '{best.name}': {c['scenario_duration']} días "
            f"laborables, " + (f"{gain} días menos que la línea base" if gain > 0 else "sin ahorro de plazo frente a "
                                                                                       "la línea base") + ".")
    if c.get("staffing_cost_delta") is not None:
        text += f" Diferencia de coste de equipo: {ctx.project.currency} {fmt_num(c['staffing_cost_delta'], 0)}."
    text += (" Entre escenarios con igual duración se prioriza el menor coste de equipo y la menor cantidad de "
             "personas agregadas. Antes de decidir, considerá los riesgos y la disponibilidad real de las personas.")
    story.append(Paragraph(_t(text), s["body"]))
    applied = [x for x in ctx.scenarios if x.status == "applied"]
    if applied:
        story.append(Paragraph(_t("Escenario aplicado: " + ", ".join(
            f"{x.name} (versión v{ctx.version_numbers.get(x.applied_version_id, '?')})" for x in applied)),
            s["body"]))


# --------------------------------------------------------------------------- ensamblado


def build_pdf(project, version, report_type: str, scenarios: list | None = None, baseline=None,
              version_numbers: dict[int, int] | None = None) -> bytes:
    _register_fonts()
    ctx = _Ctx(project, version, report_type, scenarios, baseline, version_numbers)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
        title=f"{project.name} — {REPORT_TITLES[report_type]} v{version.version_number}",
        author=project.owner or "Flock Planner", subject=REPORT_TITLES[report_type], creator="Flock Planner",
        keywords="Flock Planner, Flock IT, planificación, proyecto",
    )
    s = ctx.s
    story: list = [PageBreak()]  # la portada se dibuja en la primera página
    story.append(Paragraph(_t(REPORT_TITLES[report_type]), s["h1"]))
    if report_type == "full":
        _section_summary(ctx, story)
        _section_scope(ctx, story)
        _section_requirements(ctx, story)
        _section_backlog(ctx, story)
        _section_estimates(ctx, story)
        _section_team(ctx, story)
        _section_assumptions(ctx, story)
        _section_dependencies(ctx, story)
        _section_schedule(ctx, story)
        _section_risks(ctx, story)
        _section_selected_scenario(ctx, story)
    elif report_type == "executive":
        _section_summary(ctx, story)
        _section_scope(ctx, story)
        _section_team(ctx, story)
        _section_estimates(ctx, story)
        _section_schedule(ctx, story)
        _section_risks(ctx, story)
        _section_assumptions(ctx, story)
    else:
        _section_optimization(ctx, story)
        _section_selected_scenario(ctx, story)
    doc.build(story, onFirstPage=lambda c, d: _cover(c, ctx), canvasmaker=_make_canvas(ctx))
    data = buf.getvalue()
    if not data.startswith(b"%PDF") or len(data) < 1500:
        raise RuntimeError("El PDF generado está vacío o es inválido.")
    return data
